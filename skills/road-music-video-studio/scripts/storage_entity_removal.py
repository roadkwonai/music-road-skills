"""Verified whole-project/group removal with durable intent and recoverable isolation."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import time

from management_db import ManagementDBError
from delivery_store import SNAPSHOT_FILES
from storage_manager import MAX_JSON, StorageError, _id, _json_read
from storage_packaging import TRUSTED_ROOT, is_workspace
from work_library import WorkLibrary, _sha256
from storage_scan import SOURCE_METADATA_MARKERS, _ownership_metadata
from storage_overview import _sources_from_metadata, _jizura_command_audio

PLAN_TTL = 15 * 60
ID = re.compile(r"[0-9a-f]{64}\Z")
PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
MODEL_EXTENSIONS = {".safetensors", ".gguf", ".ggml", ".ckpt", ".pth", ".pt", ".bin"}
TABLES = ("delivery_groups", "delivery_projects", "delivery_versions", "delivery_files", "delivery_file_tombstones")


def _fingerprint(value):
    return _id(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def _entries(group):
    return [group["source"], *group.get("files", []), *group.get("artifacts", [])]


class StorageEntityRemoval:
    def __init__(self, manager, root=None):
        self.manager = manager
        raw = Path(root) if root is not None else TRUSTED_ROOT
        if raw is None or not raw.is_absolute() or raw.is_symlink() or not is_workspace(raw):
            raise StorageError("현재 Road Music 작업 폴더에서만 전체 제거합니다.", "unsafe_root")
        self.root = raw.resolve(strict=True)
        self.library = WorkLibrary(manager.data_dir / "video-studio-library.json")
        self.database = self.root / ".roadmusic" / "history.sqlite3"
        self.db = manager.management_db

    @staticmethod
    def _request(params, key):
        if not isinstance(params, dict) or set(params) != {key} or not isinstance(params[key], str) or not ID.fullmatch(params[key]):
            raise StorageError(f"올바른 {key}가 필요합니다.", "invalid_request")
        return params[key]

    def _safe(self, path):
        if path == self.manager.data_dir or self.manager.data_dir.is_relative_to(path):
            raise StorageError("관리 DB·프로필은 전체 제거하지 않습니다.", "protected")
        if not path.is_absolute() or path.is_symlink() or path.resolve(strict=True) != path:
            raise StorageError("심볼릭 링크 또는 변경된 경로는 전체 제거하지 않습니다.", "unsafe_path")
        if any(part.casefold() in {"models", "model", "engines", "engine", "node_modules", ".git"} or part.casefold().endswith(".app") for part in path.relative_to(self.root).parts):
            raise StorageError("프로그램·모델 경로는 전체 제거하지 않습니다.", "protected")

    def _inventory(self, target):
        self._safe(target)
        files, directories = [], []
        paths = [target] if target.is_file() else []
        if target.is_dir():
            for base, dirs, names in os.walk(target, followlinks=False):
                for name in dirs:
                    path = Path(base) / name; self._safe(path)
                    directories.append(str(path.relative_to(target)))
                paths.extend(Path(base) / name for name in names)
        for path in paths:
            self._safe(path)
            if not path.is_file() or path.suffix.casefold() in MODEL_EXTENSIONS:
                raise StorageError("모델·특수 파일이 있어 전체 제거를 차단했습니다.", "protected")
            stat = path.stat(follow_symlinks=False)
            files.append({"relativePath": str(path.relative_to(target)) if path != target else "", "dev": stat.st_dev, "inode": stat.st_ino, "bytes": stat.st_size, "mtimeNs": stat.st_mtime_ns, "ctimeNs": stat.st_ctime_ns, "nlink": stat.st_nlink, "sha256": _sha256(path), "allocatedBytes": stat.st_blocks * 512 if stat.st_nlink == 1 else 0})
        return {"directories": sorted(directories), "files": sorted(files, key=lambda item: item["relativePath"])}

    def _verify_isolated(self, target, path, partial=False):
        actual, expected = self._inventory(path), deepcopy(target["inventory"])
        for inventory in (actual, expected):
            for item in inventory["files"]: item.pop("ctimeNs", None)
        if partial:
            expected_files = {item["relativePath"]: item for item in expected["files"]}
            valid = set(actual["directories"]).issubset(expected["directories"]) and all(expected_files.get(item["relativePath"]) == item for item in actual["files"])
        else:
            valid = actual == expected
        if not valid:
            raise StorageError("격리 자료가 변경되어 제거·복구를 차단했습니다.", "recovery_required")

    def _delivery(self):
        if not self.database.exists():
            return {table: [] for table in TABLES}
        self._safe(self.database)
        with closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            return {table: sorted([dict(row) for row in connection.execute("SELECT * FROM " + table)], key=lambda row: json.dumps(row, sort_keys=True)) if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() else [] for table in TABLES}

    @staticmethod
    def _trim_entry(item, selected_paths):
        result = deepcopy(item)
        origins = [origin for origin in result.get("origins", []) if origin.get("project") not in selected_paths]
        if not origins:
            return None
        result["origins"] = origins
        if result.get("project") in selected_paths:
            for key in ("project", "mode", "styleLabel", "styleId"):
                result[key] = origins[0][key]
        return result

    @staticmethod
    def _project_references(project):
        root = Path(project["path"])
        if not root.is_absolute() or root.is_symlink() or root.resolve(strict=True) != root or not root.is_dir():
            raise StorageError("남는 프로젝트의 경로를 안전하게 검증할 수 없습니다.", "unsafe_path")
        paths, found = set(), False
        markers = SOURCE_METADATA_MARKERS | set(SNAPSHOT_FILES) | {"plan.json", "production-plan.json", "manifest.json", "project.json", "production-state.json", "preset.json", "qa/delivery-check.json"}
        def add(raw):
            if not isinstance(raw, str) or not raw.strip(): return
            candidate = Path(raw)
            paths.add((candidate if candidate.is_absolute() else root / candidate).resolve(strict=False))
        def visit(value, key=""):
            if isinstance(value, dict):
                for name, child in value.items(): visit(child, name)
            elif isinstance(value, list):
                for child in value: visit(child, key)
            elif isinstance(value, str) and (key in {"path", "file", "src", "source", "source_audio", "sourceAudio", "userAudio"} or key.endswith("_path") or key.endswith("Path")):
                add(value)
        for name in sorted(markers):
            marker = root / name
            if not marker.exists() and not marker.is_symlink(): continue
            found = True
            if marker.is_symlink() or not marker.is_file() or marker.resolve(strict=True) != marker or marker.stat().st_size > MAX_JSON:
                raise StorageError("남는 프로젝트의 제작 메타데이터를 안전하게 검증할 수 없습니다.", "unsafe_path")
            value = _json_read(marker, None)
            if not isinstance(value, (dict, list)):
                raise StorageError("남는 프로젝트의 제작 메타데이터를 읽을 수 없습니다.", "corrupt_state")
            for source in _sources_from_metadata(_ownership_metadata(value)): add(source["sourcePath"])
            add(_jizura_command_audio(value))
            # Paths remain dependencies even when their source SHA is absent or the
            # producer stores a relative path; ordinary text is never a path guess.
            visit(value)
        if not found and project.get("origin") != "road-music-workspace":
            raise StorageError("남는 프로젝트의 알려진 제작 메타데이터가 없어 참조를 검증할 수 없습니다.", "missing_proof")
        return paths

    def _build(self, scope, entity_id):
        registry, library, delivery = self.manager._read(), self.library._read(), self._delivery()
        groups = library["groups"]
        if scope == "project":
            if entity_id not in registry["projects"]:
                raise StorageError("등록된 프로젝트가 아닙니다.", "not_found")
            project_ids = {entity_id}
            selected_paths = {registry["projects"][entity_id]["path"]}
            group_ids = {gid for gid, group in groups.items() if any(origin.get("project") in selected_paths for item in _entries(group) for origin in item.get("origins", []))}
        else:
            if entity_id not in groups:
                raise StorageError("등록된 음악 그룹이 아닙니다.", "not_found")
            group_ids = {entity_id}
            selected_paths = {origin["project"] for item in _entries(groups[entity_id]) for origin in item.get("origins", [])}
            project_ids = {pid for pid, project in registry["projects"].items() if project.get("path") in selected_paths}
        blocked, preserved, targets = [], [], []
        with self.db.transaction() as connection:
            plans = connection.execute("SELECT value_json FROM management_documents WHERE name LIKE 'entity-removal:%'").fetchall() if self.db._has_table(connection, "management_documents") else []
            if self.db._has_table(connection, "production_tasks"):
                project_marks = ",".join("?" for _ in project_ids)
                group_marks = ",".join("?" for _ in group_ids)
                predicates, task_values = [], []
                if project_ids:
                    predicates.append("project_id IN (" + project_marks + ")"); task_values.extend(sorted(project_ids))
                if group_ids:
                    predicates.append("group_id IN (" + group_marks + ")"); task_values.extend(sorted(group_ids))
                active = connection.execute("SELECT task_id,project_id FROM production_tasks WHERE status IN ('queued','running') AND (" + " OR ".join(predicates) + ") LIMIT 20", task_values).fetchall() if predicates else []
                for task_id, project_id in active:
                    blocked.append({"taskId": task_id, "projectId": project_id, "reason": "진행 중인 제작 작업의 종료 또는 명시 취소 기록이 필요합니다."})
        for row in plans:
            pending = json.loads(row[0])
            if pending.get("state") in {"applying", "committed"}:
                blocked.append({"planId": pending.get("planId"), "reason": "먼저 중단된 제거 계획의 복구 또는 격리 정리를 완료해야 합니다."})
        new_library = deepcopy(library)
        if scope == "group":
            new_library["groups"].pop(entity_id)
        else:
            for gid in group_ids:
                group = new_library["groups"][gid]
                source = self._trim_entry(group["source"], selected_paths)
                if source is None:
                    new_library["groups"].pop(gid); continue
                group["source"] = source
                for section in ("files", "artifacts"):
                    group[section] = [kept for item in group.get(section, []) if (kept := self._trim_entry(item, selected_paths)) is not None]
        removed_groups = set(groups) - set(new_library["groups"])
        remaining_origins = {origin["project"] for group in new_library["groups"].values() for item in _entries(group) for origin in item.get("origins", [])}
        remove_projects = {pid for pid in project_ids if registry["projects"][pid]["path"] not in remaining_origins}
        if scope == "project": remove_projects = project_ids
        work = self.root / ".roadmusic" / "work"
        for path in selected_paths:
            if scope == "group" and not any(project.get("path") == path for project in registry["projects"].values()):
                blocked.append({"path": path, "reason": "미등록 외부 프로젝트의 진행 상태를 확인할 수 없습니다."})
        for pid in sorted(project_ids):
            project = registry["projects"][pid]; path = Path(project["path"])
            if self.manager._busy(registry, pid): blocked.append({"projectId": pid, "reason": "진행 중인 제작 lease가 있습니다."})
            if any(entry.get("pinned") for entry in project.get("entries", {}).values()): blocked.append({"projectId": pid, "reason": "보존 핀 항목이 있습니다."})
            if pid not in remove_projects:
                preserved.append({"path": str(path), "reason": "다른 음악 그룹이 사용하는 프로젝트입니다."}); continue
            if path == work or not path.is_relative_to(work):
                preserved.append({"path": str(path), "reason": "표준 private work 밖의 외부 원본 프로젝트를 보존합니다."}); continue
            if path.exists() or path.is_symlink():
                try: targets.append({"path": str(path), "kind": "project", "inventory": self._inventory(path)})
                except (StorageError, OSError, ValueError) as error: blocked.append({"path": str(path), "reason": str(error)})
        selected_delivery_projects = {row["project_id"] for row in delivery["delivery_projects"] if (scope == "group" and row["group_id"] == entity_id) or (scope == "project" and row.get("logical_project_id") == entity_id)}
        versions = {row["id"] for row in delivery["delivery_versions"] if row["project_id"] in selected_delivery_projects}
        selected_files = [row for row in delivery["delivery_files"] if row["version_id"] in versions]
        shared_paths = {row["path"] for row in delivery["delivery_files"] if row["version_id"] not in versions}
        shared_paths.update(item["path"] for group in new_library["groups"].values() for item in _entries(group))
        for row in selected_files:
            path = Path(row["path"])
            if any(target["path"] == str(path) for target in targets): continue
            if str(path) in shared_paths:
                preserved.append({"path": str(path), "reason": "다른 등록 또는 음악 그룹이 사용하는 공유 파일입니다."}); continue
            if not path.is_relative_to(self.root / "Output"):
                preserved.append({"path": str(path), "reason": "Output 밖의 외부 원음·파일을 보존합니다."}); continue
            try:
                if not path.exists() and not path.is_symlink(): continue
                inventory = self._inventory(path)
                if len(inventory["files"]) != 1 or inventory["files"][0]["sha256"] != row["sha256"] or inventory["files"][0]["bytes"] != row["bytes"]:
                    raise StorageError("등록 뒤 완성 파일이 변경되었습니다.", "changed_file")
                targets.append({"path": str(path), "kind": "canonical", "inventory": inventory})
            except (StorageError, OSError, ValueError) as error: blocked.append({"path": str(path), "reason": str(error)})
        # Every surviving registered root is protected independently of its inputs.
        for pid, project in registry["projects"].items():
            if pid in remove_projects: continue
            raw_root = Path(project["path"])
            if any(raw_root == Path(target["path"]) or raw_root.is_relative_to(Path(target["path"])) for target in targets):
                blocked.append({"projectId": pid, "path": str(raw_root), "reason": "남는 등록 프로젝트가 제거 대상 폴더 안에 있습니다."})
            try:
                references = self._project_references(project)
            except (OSError, RuntimeError, ValueError, StorageError) as error:
                blocked.append({"projectId": pid, "path": str(raw_root), "reason": "남는 프로젝트의 참조를 안전하게 검증할 수 없습니다: " + str(error)})
                continue
            for path in sorted(references):
                if any(path == Path(target["path"]) or path.is_relative_to(Path(target["path"])) for target in targets):
                    blocked.append({"projectId": pid, "path": str(path), "reason": "남는 프로젝트에서 사용하는 입력·파일입니다."})
        for path in shared_paths:
            if any(Path(path) == Path(target["path"]) or Path(path).is_relative_to(Path(target["path"])) for target in targets):
                blocked.append({"path": path, "reason": "남는 음악 그룹에서 사용하는 프로젝트 내부 파일입니다."})
        # ProjectFinish receipts are entity-specific metadata, never the shared history DB.
        for pid in sorted(remove_projects):
            receipt = self.root / ".roadmusic" / "finished" / (pid + ".json")
            if receipt.exists() or receipt.is_symlink():
                try: targets.append({"path": str(receipt), "kind": "receipt", "inventory": self._inventory(receipt)})
                except (StorageError, OSError, ValueError) as error: blocked.append({"path": str(receipt), "reason": str(error)})
        # Never isolate overlapping roots, including a registered child project.
        for index, target in enumerate(targets):
            if any(Path(target["path"]).is_relative_to(Path(other["path"])) or Path(other["path"]).is_relative_to(Path(target["path"])) for other in targets[:index]):
                blocked.append({"path": target["path"], "reason": "제거 경로가 중첩되어 안전하게 격리할 수 없습니다."})
        retained_paths = {item["path"] for group in new_library["groups"].values() for item in _entries(group)}
        original_paths = {item["path"] for gid in group_ids for item in _entries(groups[gid])}
        original_paths.update(row["original_path"] for row in selected_files if row.get("original_path"))
        for raw in sorted(original_paths - retained_paths):
            path = Path(raw)
            if not any(path == Path(target["path"]) or path.is_relative_to(Path(target["path"])) for target in targets):
                preserved.append({"path": raw, "reason": "외부 원본 또는 선택한 SQLite 납품 소유권으로 검증되지 않은 파일을 보존합니다."})
        selected = {"delivery_groups": [row for row in delivery["delivery_groups"] if row["group_id"] in removed_groups or any(project["group_id"] == row["group_id"] and project["project_id"] in selected_delivery_projects for project in delivery["delivery_projects"])], "delivery_projects": [row for row in delivery["delivery_projects"] if row["project_id"] in selected_delivery_projects], "delivery_versions": [row for row in delivery["delivery_versions"] if row["id"] in versions], "delivery_files": selected_files, "delivery_file_tombstones": [row for row in delivery["delivery_file_tombstones"] if row["version_id"] in versions]}
        # Keep a delivery group while a surviving delivery project still references it.
        selected["delivery_groups"] = [row for row in selected["delivery_groups"] if not any(project["group_id"] == row["group_id"] and project["project_id"] not in selected_delivery_projects for project in delivery["delivery_projects"])]
        new_registry = deepcopy(registry)
        for pid in remove_projects:
            new_registry["projects"].pop(pid, None); new_registry["leases"].pop(pid, None)
        after_delivery = {table: [row for row in delivery[table] if row not in selected[table]] for table in TABLES}
        return {"deliveryAfterHash": _fingerprint(after_delivery), "backupRegistry": registry, "backupLibrary": library, "scope": scope, "entityId": entity_id, "projectIds": sorted(remove_projects), "groupIds": sorted(removed_groups), "registryHash": _fingerprint(registry), "libraryHash": _fingerprint(library), "deliveryHash": _fingerprint(delivery), "newRegistry": new_registry, "newLibrary": new_library, "delivery": selected, "targets": targets, "preserved": list({(item["path"], item["reason"]): item for item in preserved}.values()), "blocked": blocked}

    @staticmethod
    def _public(plan):
        targets = [{key: target[key] for key in ("path", "kind")} | {"fileCount": len(target["inventory"]["files"]), "bytes": sum(item["bytes"] for item in target["inventory"]["files"]), "allocatedBytes": sum(item["allocatedBytes"] for item in target["inventory"]["files"])} for target in plan["targets"]]
        return {"eligible": not plan["blocked"], "planId": plan.get("planId"), "expiresAt": plan.get("expiresAt"), "scope": plan["scope"], "projectIds": plan["projectIds"], "groupIds": plan["groupIds"], "targets": targets, "preserved": plan["preserved"], "blocked": plan["blocked"], "warnings": ["선택한 범위의 실제 작업 자료·등록 완성 파일·변경 이력과 경로 연결을 영구 제거합니다. 복구할 수 없습니다."], "summary": {"projectCount": len(plan["projectIds"]), "groupCount": len(plan["groupIds"]), "fileCount": sum(item["fileCount"] for item in targets), "bytes": sum(item["bytes"] for item in targets), "allocatedBytes": sum(item["allocatedBytes"] for item in targets), "versionCount": len(plan["delivery"]["delivery_versions"])}}

    def _preview(self, scope, entity_id):
        with self.manager._write_lock(), self.library._write_lock():
            plan = self._build(scope, entity_id)
            if not plan["blocked"]:
                plan.update({"planId": secrets.token_hex(24), "state": "ready", "expiresAt": time.time() + PLAN_TTL})
                self.db.write_document("entity-removal:" + plan["planId"], plan)
            return self._public(plan)

    def preview_project(self, params):
        return self._preview("project", self._request(params, "projectId"))

    def preview_group(self, params):
        return self._preview("group", self._request(params, "groupId"))

    def _delivery_delete(self, plan):
        if not self.database.exists(): return
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("PRAGMA foreign_keys=ON"); connection.execute("BEGIN IMMEDIATE")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, column in (("delivery_file_tombstones", "version_id"), ("delivery_files", "version_id"), ("delivery_versions", "id"), ("delivery_projects", "project_id"), ("delivery_groups", "group_id")):
                if table not in tables: continue
                keys = {row[column] for row in plan["delivery"][table]}
                connection.executemany("DELETE FROM " + table + " WHERE " + column + "=?", [(key,) for key in keys])
            connection.commit()

    def _delivery_restore(self, plan):
        if not self.database.exists(): return
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("PRAGMA foreign_keys=ON"); connection.execute("BEGIN IMMEDIATE")
            for table in TABLES:
                rows = plan["delivery"][table]
                if not rows: continue
                columns = list(rows[0]); query = "INSERT OR IGNORE INTO " + table + "(" + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in columns) + ")"
                connection.executemany(query, [[row[column] for column in columns] for row in rows])
            connection.commit()

    def _stage(self, plan):
        staging = self.root / ".roadmusic" / "cache" / "entity-removal" / plan["planId"]
        current = self.root
        for part in staging.relative_to(self.root).parts:
            current /= part
            if current.is_symlink() or (current.exists() and not current.is_dir()):
                raise StorageError("전체 제거 격리 경로가 안전하지 않습니다.", "unsafe_path")
            current.mkdir(exist_ok=True)
        return staging

    def _drop_profile(self, plan, connection):
        self.manager._save(plan["newRegistry"], connection=connection)
        self.library._save(plan["newLibrary"], connection=connection)
        # Every other ready preview is stale after these shared document changes.
        for name, raw in connection.execute("SELECT name,value_json FROM management_documents WHERE name LIKE 'entity-removal:%'").fetchall():
            if name != "entity-removal:" + plan["planId"] and json.loads(raw).get("state") in {"ready", "failed", "recovered"}:
                connection.execute("DELETE FROM management_documents WHERE name=?", (name,))
        for pid in plan["projectIds"]: self.db.drop_project(pid, connection=connection)
        for gid in plan["groupIds"]: self.db.drop_group(gid, connection=connection)
        for target in plan["targets"]:
            raw = target["path"]
            connection.execute("DELETE FROM management_paths WHERE path=? OR substr(path,1,?)=?", (raw, len(raw) + 1, raw + "/"))
            if self.db._has_table(connection, "storage_tracking_files"):
                relative = str(Path(raw).relative_to(self.root))
                connection.execute("DELETE FROM storage_tracking_files WHERE workspace=? AND (relative_path=? OR substr(relative_path,1,?)=?)", (str(self.root), relative, len(relative) + 1, relative + "/"))

    def _profile_backup(self, plan):
        result = {}
        with self.db.transaction() as connection:
            for table in ("management_events", "management_paths", "storage_tracking_files", "production_projects", "production_prompts", "production_tasks", "production_files", "work_favorites"):
                if not self.db._has_table(connection, table): continue
                queries = []
                if table not in {"storage_tracking_files", "work_favorites"}:
                    queries.extend(("project_id=?", (pid,)) for pid in plan["projectIds"])
                    queries.extend(("group_id=?", (gid,)) for gid in plan["groupIds"])
                elif table == "work_favorites":
                    queries.extend(("group_id=?", (gid,)) for gid in plan["groupIds"])
                if table in {"management_paths", "storage_tracking_files"}:
                    for target in plan["targets"]:
                        raw = target["path"] if table == "management_paths" else str(Path(target["path"]).relative_to(self.root))
                        column = "path" if table == "management_paths" else "relative_path"
                        where = f"({column}=? OR substr({column},1,?)=?)"
                        values = (raw, len(raw) + 1, raw + "/")
                        if table == "storage_tracking_files": where += " AND workspace=?"; values += (str(self.root),)
                        queries.append((where, values))
                rows = {}
                for where, values in queries:
                    cursor = connection.execute("SELECT * FROM " + table + " WHERE " + where, values)
                    columns = [item[0] for item in cursor.description]
                    for row in cursor.fetchall(): rows[tuple(row)] = dict(zip(columns, row))
                result[table] = sorted(rows.values(), key=lambda row: json.dumps(row, sort_keys=True))
        return result

    def cleanup(self, params):
        if not isinstance(params, dict) or set(params) != {"planId", "confirm"} or params.get("confirm") is not True:
            raise StorageError("같은 제거 계획과 명시 확인이 필요합니다.", "confirm_required")
        plan_id = params.get("planId")
        if not isinstance(plan_id, str) or not PLAN_ID.fullmatch(plan_id):
            raise StorageError("올바른 제거 계획이 필요합니다.", "invalid_plan")
        name = "entity-removal:" + plan_id
        with self.manager._write_lock(), self.library._write_lock():
            plan = self.db.read_document(name, fallback={})
            if plan.get("state") == "applying":
                raise StorageError("이전 실행이 중단되어 자료를 격리 보존했습니다. 자동 삭제 없이 복구 점검이 필요합니다.", "recovery_required")
            if plan.get("state") not in {"ready", "committed"} or (plan.get("state") == "ready" and plan.get("expiresAt", 0) < time.time()):
                raise StorageError("만료되었거나 사용한 제거 계획입니다.", "stale_plan")
            if plan["state"] == "ready":
                current = self._build(plan["scope"], plan["entityId"])
                if any(current[key] != plan[key] for key in current):
                    raise StorageError("계획 뒤 파일·등록·이력 또는 진행 상태가 변경되었습니다.", "stale_plan")
                staging = self._stage(plan)
                if any(staging.iterdir()): raise StorageError("격리 폴더가 이미 사용 중입니다.", "recovery_required")
                plan["moves"] = [{"source": target["path"], "staging": str(staging / str(index))} for index, target in enumerate(plan["targets"])]
                if any(Path(move["source"]).stat().st_dev != staging.stat().st_dev for move in plan["moves"]):
                    raise StorageError("다른 파일시스템의 자료는 안전하게 격리할 수 없습니다.", "unsafe_path")
                plan["backupProfileRows"] = self._profile_backup(plan)
                plan["beforeFree"] = shutil.disk_usage(self.root).free
                plan["state"] = "applying"; self.db.write_document(name, plan)
                try:
                    for move in plan["moves"]: os.replace(move["source"], move["staging"])
                    with self.db.transaction(write=True) as connection:
                        self._drop_profile(plan, connection)
                        self._delivery_delete(plan)
                        plan["state"] = "committed"; self.db.write_document(name, plan, connection=connection)
                except (OSError, sqlite3.Error, ValueError, StorageError) as error:
                    try:
                        self._delivery_restore(plan)
                        for target, move in reversed(list(zip(plan["targets"], plan["moves"]))):
                            source, isolated = Path(move["source"]), Path(move["staging"])
                            if isolated.exists() or isolated.is_symlink():
                                self._safe(source.parent); self._verify_isolated(target, isolated)
                                if source.exists() or source.is_symlink(): raise OSError("복구 원래 경로가 사용 중입니다")
                                os.replace(isolated, source)
                        plan["state"] = "failed"; self.db.write_document(name, plan)
                    except (OSError, sqlite3.Error, ValueError, StorageError) as recovery_error:
                        raise StorageError("실행이 중단되어 격리 자료와 복구 계획을 보존했습니다: " + str(recovery_error), "recovery_required") from error
                    raise StorageError("제거 반영에 실패하여 원래 파일과 SQL 상태를 복구했습니다: " + str(error), "cleanup_rolled_back") from error
            # Both metadata stores committed before any isolated file is unlinked.
            try:
                staging = self._stage(plan)
                expected_moves = [{"source": target["path"], "staging": str(staging / str(index))} for index, target in enumerate(plan["targets"])]
                if plan["moves"] != expected_moves: raise StorageError("격리 제거 경로가 변경되었습니다.", "recovery_required")
                for target, move in zip(plan["targets"], expected_moves):
                    path = Path(move["staging"])
                    if path.exists() or path.is_symlink(): self._verify_isolated(target, path, partial=True)
                    if path.is_dir(): shutil.rmtree(path)
                    else: path.unlink(missing_ok=True)
            except OSError as error:
                raise StorageError("SQL 제거는 완료했고 격리 자료를 보존했습니다. 같은 계획으로 정리를 다시 실행할 수 있습니다.", "cleanup_pending") from error
            for target in plan["targets"]:
                boundary = self.root / ("Output" if target["kind"] == "canonical" else ".roadmusic/work" if target["kind"] == "project" else ".roadmusic/finished")
                parent = Path(target["path"]).parent
                while parent != boundary and parent.is_relative_to(boundary):
                    try:
                        self._safe(parent); parent.rmdir()
                    except (OSError, StorageError): break
                    parent = parent.parent
            try: self._stage(plan).rmdir()
            except OSError: pass
            public = self._public(plan); summary = public["summary"]
            result = {"scope": plan["scope"], "removedProjects": len(plan["projectIds"]), "removedGroups": len(plan["groupIds"]), "removedFiles": summary["fileCount"], "freedBytes": summary["bytes"], "freedAllocatedBytes": summary["allocatedBytes"], "diskFreeDeltaBytes": shutil.disk_usage(self.root).free - plan["beforeFree"], "preserved": plan["preserved"], "remaining": self._remaining(plan)}
            # Compact receipt contains no removed paths or metadata snapshots.
            self.db.write_document(name, {"state": "used", "planId": plan_id, "completedAt": int(time.time()), "result": {key: value for key, value in result.items() if key != "preserved"}})
            return result

    def recover(self, params):
        if not isinstance(params, dict) or set(params) != {"planId", "confirm"} or params.get("confirm") is not True:
            raise StorageError("같은 복구 계획과 명시 확인이 필요합니다.", "confirm_required")
        plan_id = params.get("planId")
        if not isinstance(plan_id, str) or not PLAN_ID.fullmatch(plan_id):
            raise StorageError("올바른 복구 계획이 필요합니다.", "invalid_plan")
        name = "entity-removal:" + plan_id
        with self.manager._write_lock(), self.library._write_lock():
            plan = self.db.read_document(name, fallback={})
            if plan.get("state") != "applying":
                raise StorageError("중단되어 격리 보존된 계획만 복구할 수 있습니다.", "stale_plan")
            if _fingerprint(self.manager._read()) != plan.get("registryHash") or _fingerprint(self.library._read()) != plan.get("libraryHash"):
                raise StorageError("중단 뒤 등록 정보가 변경되어 격리 상태를 보존합니다.", "recovery_required")
            current_delivery = self._delivery()
            if _fingerprint(current_delivery) not in {plan.get("deliveryHash"), plan.get("deliveryAfterHash")}:
                raise StorageError("중단 뒤 납품 이력이 변경되어 격리 상태를 보존합니다.", "recovery_required")
            # A profile transaction either committed its new documents and state together,
            # or rolled back. Applying can therefore restore only the original profile.
            if self._profile_backup(plan) != plan.get("backupProfileRows"):
                raise StorageError("중단 뒤 소유권·이력이 변경되어 격리 상태를 보존합니다.", "recovery_required")
            staging = self._stage(plan)
            expected_moves = [{"source": target["path"], "staging": str(staging / str(index))} for index, target in enumerate(plan["targets"])]
            if plan.get("moves") != expected_moves:
                raise StorageError("복구 경로 계획이 변경되었습니다.", "recovery_required")
            restoring = []
            for target, move in zip(plan["targets"], expected_moves):
                source, isolated = Path(move["source"]), Path(move["staging"])
                if not source.is_relative_to(self.root) or not isolated.is_relative_to(staging):
                    raise StorageError("복구 경로가 안전하지 않습니다.", "recovery_required")
                self._safe(source.parent)
                source_exists, isolated_exists = source.exists() or source.is_symlink(), isolated.exists() or isolated.is_symlink()
                if source_exists == isolated_exists:
                    raise StorageError("원래 경로와 격리 경로 상태가 달라 복구를 차단했습니다.", "recovery_required")
                self._verify_isolated(target, source if source_exists else isolated)
                if isolated_exists: restoring.append(move)
            try:
                self._delivery_restore(plan)
                for move in reversed(restoring):
                    source, isolated = Path(move["source"]), Path(move["staging"])
                    self._safe(source.parent); self._safe(isolated)
                    if source.exists() or source.is_symlink(): raise OSError("원래 복구 경로가 사용 중입니다")
                    os.replace(isolated, source)
                if _fingerprint(self._delivery()) != plan["deliveryHash"]:
                    raise OSError("복구된 납품 이력이 원래 기록과 다릅니다")
                self.db.write_document(name, {"state": "recovered", "planId": plan_id, "completedAt": int(time.time()), "restoredTargets": len(expected_moves)})
            except (OSError, sqlite3.Error, ValueError, StorageError) as error:
                # Keep any already restored files; every target still has one copy.
                raise StorageError("복구가 중단되어 자료와 계획을 보존했습니다. 같은 계획으로 복구를 다시 실행할 수 있습니다: " + str(error), "recovery_required") from error
            try: staging.rmdir()
            except OSError: pass
            return {"planId": plan_id, "recovered": True, "restoredTargets": len(expected_moves), "removedFiles": 0}

    def _remaining(self, plan):
        registry, library, delivery = self.manager._read(), self.library._read(), self._delivery()
        pids, gids = set(plan["projectIds"]), set(plan["groupIds"])
        remaining = {"projects": len(pids & set(registry["projects"])), "groups": len(gids & set(library["groups"]))}
        with self.db.transaction() as connection:
            for table, key in (("management_events", "events"), ("management_paths", "paths"), ("production_projects", "productionProjects"), ("production_prompts", "productionPrompts"), ("production_tasks", "productionTasks"), ("production_files", "productionFiles"), ("work_favorites", "favorites")):
                if not self.db._has_table(connection, table):
                    remaining[key] = 0; continue
                predicates, values = [], []
                if pids and table != "work_favorites":
                    predicates.append("project_id IN (" + ",".join("?" for _ in pids) + ")"); values.extend(sorted(pids))
                if gids:
                    predicates.append("group_id IN (" + ",".join("?" for _ in gids) + ")"); values.extend(sorted(gids))
                remaining[key] = connection.execute("SELECT count(*) FROM " + table + " WHERE " + " OR ".join(predicates), values).fetchone()[0] if predicates else 0
        project_rows = {row["project_id"] for row in plan["delivery"]["delivery_projects"]}
        version_rows = {row["id"] for row in plan["delivery"]["delivery_versions"]}
        remaining.update({"deliveryProjects": sum(row["project_id"] in project_rows for row in delivery["delivery_projects"]), "deliveryGroups": sum(row["group_id"] in {item["group_id"] for item in plan["delivery"]["delivery_groups"]} for row in delivery["delivery_groups"]), "deliveryVersions": sum(row["id"] in version_rows for row in delivery["delivery_versions"]), "deliveryFiles": sum(row["version_id"] in version_rows for row in delivery["delivery_files"])})
        return remaining
