"""One-file final delivery removal, limited to registered canonical Output files."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time

from storage_manager import MAX_JSON, StorageError, _atomic_json, _id, _json_read, _snapshot
from storage_packaging import TRUSTED_ROOT, is_workspace
from work_library import WorkLibrary, _sha256


PLAN_TTL = 15 * 60
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class StorageFileRemoval:
    def __init__(self, manager, root=None):
        self.manager = manager
        self.root = Path(root) if root is not None else TRUSTED_ROOT
        if self.root is None or not is_workspace(self.root):
            raise StorageError("현재 Road Music 작업 폴더에서만 완성 파일을 정리합니다.", "unsafe_root")
        self.root = self.root.resolve()
        self.output = self.root / "Output"
        if self.output.is_symlink():
            raise StorageError("Output 심볼릭 링크는 완성 파일을 정리할 수 없습니다.", "unsafe_path")
        self.library = WorkLibrary(manager.data_dir / "video-studio-library.json")
        self.plans = manager.data_dir / "storage-file-remove-plans"
        self.database = self.root / ".roadmusic" / "history.sqlite3"

    def _plan_path(self, plan_id):
        if not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{48}", plan_id):
            raise StorageError("파일 제거 계획이 올바르지 않습니다.", "invalid_plan")
        if self.plans.exists() and self.plans.is_symlink():
            raise StorageError("파일 제거 계획 경로가 안전하지 않습니다.", "unsafe_path")
        self.plans.mkdir(parents=True, exist_ok=True)
        path = self.plans / f"{plan_id}.json"
        if path.exists() and path.is_symlink():
            raise StorageError("파일 제거 계획 경로가 안전하지 않습니다.", "unsafe_path")
        return path

    def _canonical(self, item):
        raw = Path(item.get("path", ""))
        if not raw.is_absolute() or raw.is_symlink():
            raise StorageError("심볼릭 링크가 아닌 canonical 완성 파일만 정리할 수 있습니다.", "unsafe_path")
        try:
            path = raw.resolve(strict=True)
        except OSError as error:
            raise StorageError("완성 파일을 찾을 수 없습니다.", "missing_file") from error
        if path != raw or not path.is_file() or path.is_symlink() or not path.is_relative_to(self.output):
            raise StorageError("Output 안의 canonical 완성 파일만 정리할 수 있습니다.", "protected")
        snapshot = _snapshot(path)
        if snapshot["bytes"] != item.get("size") or _sha256(path) != item.get("sha256"):
            raise StorageError("등록 뒤 완성 파일이 변경되었습니다.", "changed_file")
        return path, snapshot

    def _entry(self, group_id, file_id):
        if not isinstance(group_id, str) or not SHA256.fullmatch(group_id) or not isinstance(file_id, str) or not SHA256.fullmatch(file_id):
            raise StorageError("음악 그룹과 파일 ID가 올바르지 않습니다.", "invalid_request")
        group = self.library._group_data(group_id)
        if group["source"].get("id") == file_id:
            return group, group["source"], "현재 원음은 개별 제거할 수 없습니다."
        item = next((value for value in group.get("files", []) if isinstance(value, dict) and value.get("id") == file_id), None)
        if item is None:
            raise StorageError("등록된 완성 파일이 아닙니다.", "not_found")
        return group, item, None

    def _library_references(self, path, group_id, file_id):
        references = []
        for key, group in self.library._read()['groups'].items():
            for item in [group.get('source', {}), *group.get('files', []), *group.get('artifacts', [])]:
                if key == group_id and item.get('id') == file_id:
                    continue
                raw = Path(item.get('path', ''))
                if raw.is_absolute() and raw.resolve(strict=False) == path:
                    references.append({'type': 'library-reference', 'groupId': key, 'fileId': item.get('id'), 'path': str(path)})
        return references

    def _project_references(self, path):
        dependencies, metadata = [], []
        data = self.manager._read()
        for project_id, project in data["projects"].items():
            try:
                _, root = self.manager._project(data, project_id)
                marker = root / "studio-project.json"
                if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > MAX_JSON:
                    continue
                fingerprint = _sha256(marker)
                value = _json_read(marker, None)
                media = value.get("media") if isinstance(value, dict) else None
                if not isinstance(media, list):
                    continue
                matching = []
                for item in media:
                    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                        continue
                    candidate = Path(item["path"])
                    if not candidate.is_absolute() or candidate.is_symlink() or candidate.resolve(strict=True) != path:
                        continue
                    if item.get("id") == "music" and item.get("kind") == "music":
                        dependencies.append({"type": "project-input", "projectId": project_id, "path": str(root), "state": project.get("state", "editing"), "busy": self.manager._busy(data, project_id)})
                    else:
                        matching.append(item.get("id"))
                if matching:
                    if self.manager._busy(data, project_id):
                        dependencies.append({"type": "active-project-final", "projectId": project_id, "path": str(root), "state": project.get("state", "editing"), "busy": True})
                    else:
                        metadata.append({"projectId": project_id, "path": str(root), "fingerprint": fingerprint, "mediaIds": matching})
            except (OSError, StorageError):
                continue
        return dependencies, metadata

    def _update_project_metadata(self, refs, target):
        removed = 0
        for ref in refs:
            project = Path(ref["path"]); marker = project / "studio-project.json"
            if marker.is_symlink() or not marker.is_file() or _sha256(marker) != ref["fingerprint"]:
                raise StorageError("계획 뒤 프로젝트 완성본 목록이 변경되었습니다.", "stale_plan")
            value = _json_read(marker, None)
            media = value.get("media") if isinstance(value, dict) else None
            if not isinstance(media, list):
                raise StorageError("프로젝트 완성본 목록이 올바르지 않습니다.", "stale_plan")
            kept = []
            for item in media:
                if not isinstance(item, dict) or item.get("id") not in ref["mediaIds"]:
                    kept.append(item); continue
                candidate = Path(item.get("path", ""))
                if item.get("id") == "music" or not candidate.is_absolute() or candidate.is_symlink() or candidate != target:
                    raise StorageError("프로젝트 완성본 목록이 변경되었습니다.", "stale_plan")
                removed += 1
            if len(kept) == len(media):
                raise StorageError("프로젝트 완성본 목록이 변경되었습니다.", "stale_plan")
            value["media"] = kept; _atomic_json(marker, value)
        return removed

    def _db_refs(self, path):
        if not self.database.exists():
            return []
        if self.database.is_symlink() or not self.database.is_file():
            raise StorageError("버전 이력 DB가 안전하지 않습니다.", "unsafe_path")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute("SELECT version_id,kind,name,sha256,bytes,path FROM delivery_files WHERE path=?", (str(path),)).fetchall()
            except sqlite3.Error as error:
                raise StorageError("버전 이력 DB를 확인할 수 없습니다.", "corrupt_state") from error
        return [dict(row) for row in rows]

    @staticmethod
    def _db_fingerprint(rows):
        return _id(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    def _tombstone_table(self, connection):
        connection.execute("CREATE TABLE IF NOT EXISTS delivery_file_tombstones (version_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, deleted_at INTEGER NOT NULL, plan_id TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'applied')")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(delivery_file_tombstones)")}
        if "state" not in columns:
            connection.execute("ALTER TABLE delivery_file_tombstones ADD COLUMN state TEXT NOT NULL DEFAULT 'applied'")

    def _begin_tombstones(self, rows, plan):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("BEGIN IMMEDIATE"); self._tombstone_table(connection)
            connection.executemany("INSERT INTO delivery_file_tombstones(version_id,kind,name,path,sha256,bytes,deleted_at,plan_id,state) VALUES(?,?,?,?,?,?,?,?,?)", [(row["version_id"], row["kind"], row["name"], row["path"], row["sha256"], row["bytes"], int(time.time()), plan["planId"], "pending") for row in rows])
            connection.commit()

    def _finish_tombstones(self, plan):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("BEGIN IMMEDIATE"); self._tombstone_table(connection)
            connection.execute("UPDATE delivery_file_tombstones SET state='applied' WHERE plan_id=? AND state='pending'", (plan["planId"],))
            connection.commit()

    def _clear_pending_tombstones(self, plan):
        try:
            with closing(sqlite3.connect(self.database)) as connection:
                connection.execute("DELETE FROM delivery_file_tombstones WHERE plan_id=?", (plan["planId"],)); connection.commit()
        except sqlite3.Error:
            pass

    def _staging_path(self, plan, path):
        root = self.root / ".roadmusic" / "maintenance" / "file-remove-staging" / plan["planId"]
        current = self.root
        for part in root.relative_to(self.root).parts:
            current /= part
            if current.exists() and current.is_symlink():
                raise StorageError("파일 제거 격리 경로가 안전하지 않습니다.", "unsafe_path")
            current.mkdir(exist_ok=True)
        return root / path.name

    @staticmethod
    def _restore_json(path, raw):
        with tempfile.NamedTemporaryFile("wb", dir=Path(path).parent, prefix=f".{Path(path).name}.", delete=False) as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno()); temporary = Path(stream.name)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def preview(self, params):
        if not isinstance(params, dict) or set(params) != {"groupId", "fileId"}:
            raise StorageError("groupId와 fileId가 필요합니다.", "invalid_request")
        with self.manager._write_lock(), self.library._write_lock():
            group, item, protected = self._entry(params["groupId"], params["fileId"])
            public = self.library._public_file(item)
            if protected:
                return {"eligible": False, "file": {**public, "removeDisabled": True, "protectedReason": protected}, "dependencies": []}
            path, snapshot = self._canonical(item)
            dependencies, metadata_refs = self._project_references(path)
            dependencies.extend(self._library_references(path, params['groupId'], params['fileId']))
            if dependencies:
                return {"eligible": False, "file": {**public, "removeDisabled": True, "protectedReason": "다른 음악·제작 자료에서 참조 중입니다."}, "dependencies": dependencies}
            rows = self._db_refs(path)
            if not rows:
                return {"eligible": False, "file": {**public, "removeDisabled": True, "protectedReason": "버전 이력에 연결되지 않은 파일은 제거할 수 없습니다."}, "dependencies": []}
            plan_id = os.urandom(24).hex()
            warnings = ["이 음악 그룹의 마지막 완성 파일을 제거합니다. 버전 이력만 남고 재생·다운로드는 불가능해집니다."] if len(group.get("files", [])) == 1 else []
            plan = {"schemaVersion": 1, "planId": plan_id, "state": "ready", "expiresAt": time.time() + PLAN_TTL,
                    "groupId": params["groupId"], "fileId": params["fileId"], "file": {"path": str(path), "sha256": item["sha256"], "snapshot": snapshot},
                    "libraryHash": _id(json.dumps(self.library._read(), ensure_ascii=False, sort_keys=True)), "dbFingerprint": self._db_fingerprint(rows), "dbRefs": rows, "metadataRefs": metadata_refs}
            _atomic_json(self._plan_path(plan_id), plan)
            return {"eligible": True, "planId": plan_id, "expiresAt": plan["expiresAt"], "file": {**public, "removeDisabled": False}, "dependencies": [], "metadataReferences": metadata_refs, "versionReferences": len(rows), "warnings": warnings}

    def cleanup(self, params):
        if not isinstance(params, dict) or set(params) - {"planId", "confirm"} or params.get("confirm") is not True:
            raise StorageError("같은 파일 제거 계획과 명시 확인이 필요합니다.", "confirm_required")
        plan_path = self._plan_path(params.get("planId", ""))
        with self.manager._write_lock(), self.library._write_lock():
            plan = _json_read(plan_path, {})
            if not isinstance(plan, dict) or plan.get("state") != "ready" or plan.get("expiresAt", 0) < time.time():
                raise StorageError("만료되었거나 사용한 파일 제거 계획입니다.", "stale_plan")
            group, item, protected = self._entry(plan.get("groupId"), plan.get("fileId"))
            if protected:
                raise StorageError(protected, "protected")
            path, snapshot = self._canonical(item)
            expected = plan.get("file", {})
            if str(path) != expected.get("path") or item.get("sha256") != expected.get("sha256") or snapshot != expected.get("snapshot"):
                raise StorageError("계획 뒤 완성 파일이 변경되었습니다.", "stale_plan")
            dependencies, metadata_refs = self._project_references(path)
            dependencies.extend(self._library_references(path, plan['groupId'], plan['fileId']))
            if _id(json.dumps(self.library._read(), ensure_ascii=False, sort_keys=True)) != plan.get("libraryHash") or dependencies or metadata_refs != plan.get("metadataRefs"):
                raise StorageError("계획 뒤 등록 또는 입력 참조가 변경되었습니다.", "stale_plan")
            rows = self._db_refs(path)
            if not rows or self._db_fingerprint(rows) != plan.get("dbFingerprint"):
                raise StorageError("계획 뒤 버전 이력이 변경되었습니다.", "stale_plan")
            project_backups = []
            for ref in plan.get("metadataRefs", []):
                marker = Path(ref["path"]) / "studio-project.json"
                if marker.is_symlink() or not marker.is_file() or _sha256(marker) != ref["fingerprint"]:
                    raise StorageError("계획 뒤 프로젝트 완성본 목록이 변경되었습니다.", "stale_plan")
                project_backups.append((marker, marker.read_bytes()))
            library_backup = self.library._read()
            profile_saved = False
            ownership = []
            staging = self._staging_path(plan, path)
            if staging.exists() or staging.is_symlink():
                raise StorageError("파일 제거 격리 경로가 이미 사용 중입니다.", "stale_plan")
            before_free = shutil.disk_usage(self.root).free
            allocated = path.stat(follow_symlinks=False).st_blocks * 512
            try:
                self._begin_tombstones(rows, plan)
                os.replace(path, staging)
                metadata_removed = self._update_project_metadata(plan.get("metadataRefs", []), path)
                group["files"] = [value for value in group["files"] if value.get("id") != item["id"]]
                value = self.library._read(); value["groups"][group["groupId"]] = group
                with self.manager.management_db.transaction(write=True) as connection:
                    ownership = connection.execute("SELECT path,role,project_id,group_id,workspace,kind,updated_at FROM management_paths WHERE path=?", (str(path),)).fetchall()
                    self.library._save(value, connection=connection)
                    connection.execute("DELETE FROM management_paths WHERE path=?", (str(path),))
                    event_id = self.manager.management_db.record_event("file_removed", group_id=group["groupId"], before=item, path=str(path), connection=connection)["id"]
                    self._finish_tombstones(plan)
                profile_saved = True
                staging.unlink()
            except (OSError, sqlite3.Error, ValueError) as error:
                if staging.exists() and not path.exists():
                    os.replace(staging, path)
                for marker, raw in project_backups:
                    self._restore_json(marker, raw)
                if profile_saved:
                    with self.manager.management_db.transaction(write=True) as connection:
                        self.library._save(library_backup, connection=connection)
                        connection.execute("DELETE FROM management_events WHERE id=?", (event_id,))
                        connection.executemany("INSERT OR REPLACE INTO management_paths(path,role,project_id,group_id,workspace,kind,updated_at) VALUES(?,?,?,?,?,?,?)", ownership)
                self._clear_pending_tombstones(plan)
                raise StorageError("완성 파일 제거를 반영하지 못해 원래 상태로 복구했습니다: " + str(error), "cleanup_rolled_back") from error
            plan["state"] = "used"; _atomic_json(plan_path, plan)
            return {"removedFiles": 1, "freedBytes": snapshot["bytes"], "freedAllocatedBytes": allocated, "diskFreeDeltaBytes": shutil.disk_usage(self.root).free - before_free, "file": {"id": item["id"], "path": str(path), "name": item["name"]}, "metadataRemoved": metadata_removed, "tombstonedVersions": len(rows)}
