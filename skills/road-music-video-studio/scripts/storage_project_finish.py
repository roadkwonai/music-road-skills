"""Finish one published private work project, retaining only canonical delivery history."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from storage_manager import PLAN_TTL, StorageError, _atomic_json, _id, _json_read
from storage_packaging import is_workspace
from work_library import WorkLibrary


FINAL_KINDS = frozenset({"music", "video", "lyrics", "captions", "storyboard"})
MAX_JSON = 2 * 1024 * 1024


def _sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class ProjectFinish:
    def __init__(self, manager):
        self.manager = manager

    @staticmethod
    def _inside(root, path):
        return path == root or root in path.parents

    def _workspace(self, project):
        for parent in (project, *project.parents):
            marker = parent / ".roadmusic"
            if marker.is_dir() and not marker.is_symlink() and (parent / "Output").is_dir() and not (parent / "Output").is_symlink() and is_workspace(parent):
                return parent
        raise StorageError("Road Music 작업 폴더 안의 프로젝트만 완료 정리할 수 있습니다.", "unsafe_project")

    def _project(self, registry, project_id):
        project, raw = self.manager._project(registry, project_id)
        root = raw.resolve(strict=True)
        workspace = self._workspace(root)
        work = workspace / ".roadmusic" / "work"
        if not self._inside(work, root) or root == work or root.is_symlink():
            raise StorageError("private work 프로젝트만 완료 정리할 수 있습니다.", "unsafe_project")
        if project.get("state") not in {"completed", "archived"}:
            raise StorageError("완료 또는 보관 프로젝트만 정리할 수 있습니다.", "project_active")
        if self.manager._busy(registry, project_id):
            raise StorageError("진행 중인 제작 lease가 있습니다.", "busy")
        if any(entry.get("pinned") for entry in project.get("entries", {}).values()):
            raise StorageError("보존 핀 항목이 있어 완료 정리할 수 없습니다.", "pinned")
        return project, root, workspace

    def _studio_media(self, root):
        path = root / "studio-project.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
            raise StorageError("완료 프로젝트의 studio-project.json이 필요합니다.", "missing_proof")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StorageError("완료 프로젝트 정보를 읽을 수 없습니다.", "missing_proof") from error
        media = value.get("media") if isinstance(value, dict) else None
        if not isinstance(media, list) or not media:
            raise StorageError("완료 프로젝트 미디어 정보가 필요합니다.", "missing_proof")
        result = []
        for item in media:
            if not isinstance(item, dict) or item.get("kind") not in FINAL_KINDS or not isinstance(item.get("path"), str):
                continue
            raw = Path(item["path"])
            path = raw if raw.is_absolute() else root / raw
            try:
                path = path.resolve(strict=True)
            except OSError as error:
                raise StorageError("완료 프로젝트 미디어를 확인할 수 없습니다.", "missing_proof") from error
            if raw.is_symlink() or path.is_symlink() or not path.is_file():
                raise StorageError("완료 프로젝트 symlink 미디어는 정리하지 않습니다.", "unsafe_path")
            digest, size = _sha256(path), path.stat().st_size
            if item.get("sha256") not in {None, digest} or item.get("size") not in {None, size}:
                raise StorageError("완료 프로젝트 미디어가 변경됐습니다.", "changed_proof")
            result.append({"kind": item["kind"], "path": str(path), "sha256": digest, "bytes": size})
        if not result:
            raise StorageError("검증할 완료 프로젝트 미디어가 없습니다.", "missing_proof")
        return value, result

    def _canonical(self, workspace, media):
        database = workspace / ".roadmusic" / "history.sqlite3"
        if database.is_symlink() or not database.is_file():
            raise StorageError("SQLite 납품 이력이 필요합니다.", "missing_proof")
        try:
            connection = sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True)
            rows = [dict(zip(("kind", "path", "originalPath", "sha256", "bytes"), row)) for row in connection.execute("SELECT kind,path,original_path,sha256,bytes FROM delivery_files")]
        except sqlite3.Error as error:
            raise StorageError("SQLite 납품 이력을 읽을 수 없습니다.", "missing_proof") from error
        finally:
            try: connection.close()
            except UnboundLocalError: pass
        canonical = []
        for item in media:
            matched = next((row for row in rows if row["kind"] == item["kind"] and item["path"] in {row["path"], row["originalPath"]} and row["sha256"] == item["sha256"] and row["bytes"] == item["bytes"]), None)
            if matched is None:
                raise StorageError("모든 완료 미디어의 canonical 납품본이 필요합니다.", "missing_delivery")
            path = Path(matched["path"])
            try:
                actual = path.resolve(strict=True)
            except OSError as error:
                raise StorageError("canonical 납품본을 확인할 수 없습니다.", "missing_delivery") from error
            if path.is_symlink() or actual.is_symlink() or not actual.is_file() or not self._inside(workspace / "Output", actual) or actual.stat().st_size != item["bytes"] or _sha256(actual) != item["sha256"]:
                raise StorageError("canonical 납품본이 변경됐습니다.", "changed_delivery")
            canonical.append({"kind": item["kind"], "path": str(actual), "sha256": item["sha256"], "bytes": item["bytes"]})
        return canonical

    def _inventory(self, root):
        files = []
        for base, directories, names in os.walk(root, followlinks=False):
            for name in directories:
                if (Path(base) / name).is_symlink():
                    raise StorageError("프로젝트 폴더 symlink는 완료 정리하지 않습니다.", "unsafe_path")
            for name in names:
                path = Path(base) / name
                if path.is_symlink() or not path.is_file():
                    raise StorageError("프로젝트 파일 symlink는 완료 정리하지 않습니다.", "unsafe_path")
                stat = path.stat(follow_symlinks=False)
                files.append({"relativePath": str(path.relative_to(root)), "dev": stat.st_dev, "inode": stat.st_ino, "bytes": stat.st_size, "mtimeNs": stat.st_mtime_ns, "allocatedBytes": stat.st_blocks * 512})
        return sorted(files, key=lambda item: item["relativePath"])

    def _artifacts(self, root, studio):
        library = WorkLibrary(self.manager.data_dir / "video-studio-library.json")
        workspace = self._workspace(root)
        registered = [item for group in library._read().get("groups", {}).values() if isinstance(group, dict) for item in group.get("artifacts", []) if isinstance(item, dict)]
        result = []
        for item in studio.get("media", []):
            if not isinstance(item, dict) or item.get("kind") != "artifact" or not isinstance(item.get("path"), str):
                continue
            raw = Path(item["path"]); path = raw if raw.is_absolute() else root / raw
            try: path = path.resolve(strict=True)
            except OSError as error: raise StorageError("검수 artifact를 확인할 수 없습니다.", "missing_proof") from error
            inside_root = self._inside(root / ".roadmusic" / "history", path)
            inside_workspace_control = self._inside(workspace / ".roadmusic", path)
            if raw.is_symlink() or path.is_symlink() or not path.is_file() or not (inside_root or inside_workspace_control) or path.suffix.lower() not in {".json", ".md", ".txt"} or path.stat().st_size > MAX_JSON:
                raise StorageError("완료 정리에 보존할 수 없는 artifact가 있습니다.", "unsafe_artifact")
            digest, size = _sha256(path), path.stat().st_size
            if item.get("sha256") not in {None, digest} or item.get("size") not in {None, size} or not any(entry.get("path") == str(path) and entry.get("sha256") == digest and entry.get("size") == size for entry in registered):
                raise StorageError("WorkLibrary artifact 등록을 확인할 수 없습니다.", "missing_proof")
            result.append({"relativePath": str(path.relative_to(root)) if inside_root else None, "path": str(path), "sha256": digest, "bytes": size, "entry": {key: item[key] for key in ("id", "kind", "name", "artifactType") if key in item}})
        for entry in registered:
            if not isinstance(entry.get("path"), str) or entry.get("kind") != "artifact":
                continue
            path = Path(entry["path"])
            try: path = path.resolve(strict=True)
            except OSError: continue
            if not self._inside(root / ".roadmusic" / "history", path) or path.is_symlink() or not path.is_file() or path.suffix.lower() not in {".json", ".md", ".txt"} or path.stat().st_size > MAX_JSON:
                continue
            digest, size = _sha256(path), path.stat().st_size
            if entry.get("sha256") != digest or entry.get("size") != size:
                raise StorageError("WorkLibrary artifact 등록이 변경됐습니다.", "changed_proof")
            if not any(item["path"] == str(path) for item in result):
                result.append({"relativePath": str(path.relative_to(root)), "path": str(path), "sha256": digest, "bytes": size, "entry": {key: entry[key] for key in ("id", "kind", "name", "artifactType") if key in entry}})
        if sum(item["bytes"] for item in result) > MAX_JSON:
            raise StorageError("보존할 등록 artifact 총량이 너무 큽니다.", "artifact_limit")
        return result

    def _retained(self, root, studio, canonical, artifacts):
        by_key = {(item["kind"], item["sha256"]): item for item in canonical}
        media = []
        for item in studio.get("media", []):
            if not isinstance(item, dict) or item.get("kind") not in FINAL_KINDS or not isinstance(item.get("sha256"), str):
                continue
            canonical_item = by_key.get((item["kind"], item["sha256"]))
            if canonical_item is None:
                continue
            media.append({key: item[key] for key in ("id", "kind", "name", "styleLabel", "styleId", "sourceMusicSha256", "producedAt", "forVideoSha256", "artifactType") if key in item})
            media[-1].update({"path": canonical_item["path"], "sha256": canonical_item["sha256"], "size": canonical_item["bytes"]})
        for artifact in artifacts:
            media.append({**artifact["entry"], "path": artifact["path"], "sha256": artifact["sha256"], "size": artifact["bytes"]})
        result = {"studio-project.json": {"schemaVersion": 1, **{key: studio[key] for key in ("name", "projectName", "mode") if key in studio}, "media": media}}
        for name in ("selection.json", "feedback.json"):
            path = root / name
            if not path.exists():
                continue
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
                raise StorageError("선택·피드백 최소 이력 파일이 안전하지 않습니다.", "unsafe_path")
            try: value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise StorageError("선택·피드백 최소 이력 파일을 읽을 수 없습니다.", "missing_proof") from error
            if not isinstance(value, dict):
                raise StorageError("선택·피드백 최소 이력 형식이 안전하지 않습니다.", "unsafe_path")
            result[name] = value
        return result

    def _plan_path(self, workspace, plan_id):
        return workspace / ".roadmusic" / "project-finish-plans" / (plan_id + ".json")

    def _finished_receipt(self, workspace, project_id, canonical, root, files):
        path = workspace / ".roadmusic" / "finished" / (project_id + ".json")
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
            raise StorageError("완료 프로젝트 이력 파일이 안전하지 않습니다.", "unsafe_path")
        value = _json_read(path, {})
        retained, artifacts = value.get("retained"), value.get("artifacts", [])
        if value.get("schemaVersion") != 1 or value.get("projectId") != project_id or value.get("canonical") != canonical:
            raise StorageError("완료 프로젝트 이력이 현재 canonical 납품본과 다릅니다.", "changed_proof")
        artifact_paths = {item.get("relativePath") for item in artifacts if isinstance(item, dict) and item.get("relativePath") is not None}
        if not isinstance(retained, dict) or not all(isinstance(item, dict) for item in artifacts) or {item["relativePath"] for item in files} != set(retained) | artifact_paths:
            raise StorageError("완료 뒤 새 작업 파일이 있어 기존 최소 이력을 덮어쓰지 않습니다.", "already_finished_changed")
        for name, expected in retained.items():
            try: current = json.loads((root / name).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise StorageError("완료 프로젝트 최소 이력이 변경됐습니다.", "changed_proof") from error
            if current != expected:
                raise StorageError("완료 프로젝트 최소 이력이 변경됐습니다.", "changed_proof")
        for item in artifacts:
            artifact_path = Path(item["path"])
            if artifact_path.is_symlink() or not artifact_path.is_file() or artifact_path.stat().st_size != item.get("bytes") or _sha256(artifact_path) != item.get("sha256"):
                raise StorageError("완료 프로젝트 artifact 최소 이력이 변경됐습니다.", "changed_proof")
        return path

    @staticmethod
    def _only_retained(files, artifacts=()):
        return {item["relativePath"] for item in files}.issubset({"studio-project.json", "selection.json", "feedback.json", *(item["relativePath"] for item in artifacts if item.get("relativePath") is not None)})

    @staticmethod
    def _safe_dir(path):
        path = Path(path)
        if path.exists() and (path.is_symlink() or not path.is_dir()):
            raise StorageError("완료 정리 이력 폴더가 안전하지 않습니다.", "unsafe_path")
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise StorageError("완료 정리 이력 폴더가 안전하지 않습니다.", "unsafe_path")
        return path

    def preview(self, params):
        if not isinstance(params, dict) or set(params) != {"projectId"} or not isinstance(params.get("projectId"), str):
            raise StorageError("projectId가 필요합니다.", "invalid_request")
        with self.manager._write_lock():
            registry = self.manager._read(); project, root, workspace = self._project(registry, params["projectId"])
            studio, media = self._studio_media(root); canonical = self._canonical(workspace, media); artifacts = self._artifacts(root, studio); files = self._inventory(root)
            receipt = self._finished_receipt(workspace, params["projectId"], canonical, root, files)
            if receipt is not None:
                if project.get("state") != "archived" or project.get("entries") or not self._only_retained(files, artifacts):
                    raise StorageError("완료 뒤 새 작업 파일이 있어 기존 최소 이력을 덮어쓰지 않습니다.", "already_finished_changed")
                return {"planId": None, "expiresAt": None, "alreadyFinished": True, "summary": {"fileCount": 0, "allocatedBytes": 0, "canonicalFiles": len(canonical)}, "retainedHistoryPath": str(receipt), "blocked": [], "message": "최종본과 최소 이력만 남아 있어 추가 정리가 필요하지 않습니다."}
            plan_id = secrets.token_hex(24); now = int(time.time())
            self._safe_dir(workspace / ".roadmusic" / "project-finish-plans")
            history = workspace / ".roadmusic" / "finished" / (params["projectId"] + ".json")
            retained = self._retained(root, studio, canonical, artifacts)
            plan = {"schemaVersion": 1, "id": plan_id, "state": "ready", "createdAt": now, "expiresAt": now + PLAN_TTL,
                    "projectId": params["projectId"], "project": project, "root": str(root), "workspace": str(workspace), "files": files,
                    "canonical": canonical, "retained": retained, "artifacts": artifacts, "studio": {key: studio.get(key) for key in ("name", "projectName", "mode", "selection", "feedback") if key in studio}, "historyPath": str(history)}
            _atomic_json(self._plan_path(workspace, plan_id), plan)
        return {"planId": plan_id, "expiresAt": plan["expiresAt"], "summary": {"fileCount": len(files), "allocatedBytes": sum(item["allocatedBytes"] for item in files), "canonicalFiles": len(canonical)}, "retainedHistoryPath": str(history), "blocked": []}

    def cleanup(self, params):
        if not isinstance(params, dict) or set(params) != {"planId", "confirm"} or params.get("confirm") is not True or not isinstance(params.get("planId"), str):
            raise StorageError("같은 planId와 confirm:true가 필요합니다.", "confirm_required")
        with self.manager._write_lock():
            registry = self.manager._read(); candidates = [Path(project["path"]) for project in registry["projects"].values() if isinstance(project, dict) and isinstance(project.get("path"), str)]
            workspace = None
            for candidate in candidates:
                try: possible = self._workspace(candidate.resolve(strict=True))
                except (OSError, StorageError): continue
                if (possible / ".roadmusic" / "project-finish-plans" / (params["planId"] + ".json")).is_file():
                    workspace = possible; break
            if workspace is None:
                raise StorageError("완료 정리 계획을 찾을 수 없습니다.", "stale_plan")
            plan = _json_read(self._plan_path(workspace, params["planId"]), {})
            if plan.get("state") != "ready" or plan.get("expiresAt", 0) < time.time():
                raise StorageError("만료되었거나 사용한 완료 정리 계획입니다.", "stale_plan")
            project, root, _ = self._project(registry, plan.get("projectId"))
            if plan.get("project") != project or plan.get("root") != str(root) or self._inventory(root) != plan.get("files"):
                raise StorageError("프로젝트 파일 또는 정책이 계획 뒤 변경됐습니다.", "stale_plan")
            studio, media = self._studio_media(root); canonical = self._canonical(workspace, media); artifacts = self._artifacts(root, studio)
            if canonical != plan.get("canonical"):
                raise StorageError("canonical 납품본이 계획 뒤 변경됐습니다.", "stale_plan")
            history = Path(plan["historyPath"])
            if history.is_absolute() is False or not self._inside(workspace / ".roadmusic" / "finished", history) or history.exists() or history.is_symlink():
                raise StorageError("최소 이력 경로가 안전하지 않습니다.", "unsafe_path")
            self._safe_dir(history.parent)
            retained = plan.get("retained")
            if not isinstance(retained, dict) or "studio-project.json" not in retained or not set(retained).issubset({"studio-project.json", "selection.json", "feedback.json"}) or not all(isinstance(value, dict) for value in retained.values()):
                raise StorageError("최소 프로젝트 이력 계획이 안전하지 않습니다.", "unsafe_plan")
            if artifacts != plan.get("artifacts"):
                raise StorageError("artifact 등록이 계획 뒤 변경됐습니다.", "stale_plan")
            _atomic_json(history, {"schemaVersion": 1, "projectId": plan["projectId"], "finishedAt": int(time.time()), "canonical": canonical, "retained": retained, "artifacts": artifacts, "project": {key: studio.get(key) for key in ("name", "projectName", "mode", "selection", "feedback") if key in studio}})
            for name, value in retained.items():
                _atomic_json(root / name, value)
            removed = freed = 0
            for item in plan["files"]:
                if item["relativePath"] in retained or item["relativePath"] in {artifact["relativePath"] for artifact in artifacts if artifact.get("relativePath") is not None}:
                    continue
                path = root / item["relativePath"]; stat = path.stat(follow_symlinks=False)
                if path.is_symlink() or (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != (item["dev"], item["inode"], item["bytes"], item["mtimeNs"]):
                    raise StorageError("삭제 직전 프로젝트 파일이 변경됐습니다.", "stale_plan")
                path.unlink(); removed += 1
                if stat.st_nlink == 1: freed += item["allocatedBytes"]
            for base, _, _ in os.walk(root, topdown=False, followlinks=False):
                if not os.listdir(base): os.rmdir(base)
            registry["projects"][plan["projectId"]]["state"] = "archived"; registry["projects"][plan["projectId"]]["entries"] = {}; registry["leases"].pop(plan["projectId"], None); self.manager._save(registry)
            plan = {"schemaVersion": 1, "id": plan["id"], "state": "used", "projectId": plan["projectId"], "workspace": plan["workspace"], "historyPath": str(history), "summary": {"removedFiles": removed, "freedAllocatedBytes": freed, "canonicalFiles": len(canonical)}}
            _atomic_json(self._plan_path(workspace, params["planId"]), plan)
        self.manager._audit(workspace, "project-finish", {"projectId": plan["projectId"], "removedFiles": removed, "freedAllocatedBytes": freed, "canonicalFiles": len(canonical)})
        return {"removedFiles": removed, "freedAllocatedBytes": freed, "retainedHistoryPath": str(history), "retainedProjectFiles": len(retained), "canonicalFiles": len(canonical)}
