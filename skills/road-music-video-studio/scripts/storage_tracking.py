"""SQLite-backed ownership index for the trusted Road Music workspace.

The index is descriptive: it does not turn an unknown path into a cache and it
only removes a verified Finder ``.DS_Store`` residue through a one-use plan.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import stat
import time

from management_db import ManagementDBError
from storage_manager import StorageError
from storage_packaging import TRUSTED_ROOT, git_available, is_workspace
from storage_scan import WorkspaceScan, _classification, _claim_covers, _private_work


PLAN_SECONDS = 15 * 60


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _tracking_classification(relative):
    parts = Path(relative).parts
    first = parts[0].casefold() if parts else ""
    if Path(relative).name == ".DS_Store":
        return "os-residue", "Finder 표시 설정", "프로젝트 자료가 아닌 Finder 표시 설정만 확인 후 정리할 수 있습니다"
    if first in {".harness", ".omx", ".omc", "_workspace"}:
        return "tooling", "관리·검수 도구 영역", "제작 도구의 상태·검수 이력으로 보호합니다"
    return _classification(relative)


class StorageTracking:
    """Use an explicit refresh to index metadata; ordinary reads never walk disk."""

    def __init__(self, manager, workspace_root=None):
        self.manager = manager
        self.db = manager.management_db
        self.root = Path(workspace_root) if workspace_root is not None else TRUSTED_ROOT

    def _workspace(self):
        if self.root is None or not is_workspace(self.root):
            raise StorageError("현재 설치에는 신뢰할 수 있는 Road Music 작업 폴더가 없습니다.", "workspace_unavailable")
        return self.root.resolve()

    def _status(self):
        root = self.root
        workspace = bool(root is not None and is_workspace(root))
        root_path = str(root.resolve()) if workspace else None
        scan_available = workspace and not self.manager.data_dir.is_relative_to(Path(root_path))
        git = workspace and git_available(root)
        checks = [
            {"id": "ownershipIndex", "label": "SQLite 소유권 색인", "enabled": workspace,
             "reason": None if workspace else "신뢰할 수 있는 Road Music 작업 폴더가 없습니다.", "required": True, "available": workspace},
            {"id": "workspaceScan", "label": "작업 폴더 메타데이터 스캔", "enabled": scan_available,
             "reason": None if scan_available else ("현재 프로필이 작업 폴더 안에 있어 전체 스캔을 생략합니다." if workspace else "신뢰할 수 있는 Road Music 작업 폴더가 없습니다."), "required": True, "available": scan_available},
            {"id": "git", "label": "Git 저장공간", "enabled": git,
             "reason": None if git else "Git 저장소가 없어 Git 저장공간 관리를 비활성화했습니다.", "required": False, "available": git},
        ]
        return {"workspace": root_path, "ready": workspace, "checks": checks,
                "database": {"path": str(self.db.path), "kind": "sqlite-metadata", "mediaStored": False}}

    def status(self, params):
        return self.list(params)

    def _claims(self, root):
        try:
            values = self.db.paths(workspace=str(root))
        except ManagementDBError as error:
            raise StorageError(str(error), "tracking_unavailable") from error
        return [item for item in values if isinstance(item.get("path"), str)]

    @staticmethod
    def _owner_for(root, path, claims):
        for candidate in (path, *path.parents):
            claim = claims.get(str(candidate))
            if claim is not None and _claim_covers(root, path, claim):
                return claim
        return None

    def _rows(self, root):
        try:
            with self.db.transaction() as connection:
                if connection is None:
                    return []
                return connection.execute(
                    "SELECT relative_path,dev,inode,size,allocated_bytes,mtime_ns,ctime_ns,nlink,file_type,classification,label,protection_reason,indexed_at,scan_id "
                    "FROM storage_tracking_files WHERE workspace=? ORDER BY relative_path", (str(root),)
                ).fetchall()
        except ManagementDBError as error:
            raise StorageError(str(error), "tracking_unavailable") from error

    def _summary(self, root):
        rows = self._rows(root)
        claims = self._claims(root)
        claims_by_path = {claim["path"]: claim for claim in claims}
        known, unknown, protected, seen = {}, {}, {}, set()
        for row in rows:
            relative, dev, inode, _size, allocated, *_tail = row
            key = (dev, inode)
            if key in seen:
                continue
            seen.add(key)
            absolute = root / relative
            owner = self._owner_for(root, absolute, claims_by_path)
            bucket = known if owner else unknown
            parts = Path(relative).parts
            top = str(Path(*parts[:3])) if _private_work(relative) else (str(parts[0]) if parts else ".")
            item = bucket.setdefault(top if owner is None else owner["path"], {"path": top if owner is None else owner["path"], "bytes": 0, "fileCount": 0, **({"role": owner["role"], "label": "음악 연결 대기 작업" if owner["role"] in {"producer-work", "project"} and not owner.get("groupId") else owner["role"]} if owner else {})})
            item["bytes"] += int(allocated or 0); item["fileCount"] += 1
            if owner is None:
                classification, label, reason = _tracking_classification(relative)
                protected.setdefault(classification, {"kind": classification, "label": label, "reason": reason, "bytes": 0, "fileCount": 0})
                protected[classification]["bytes"] += int(allocated or 0); protected[classification]["fileCount"] += 1
        return {"knownOwnership": {"paths": len(claims), "bytes": sum(value["bytes"] for value in known.values()), "items": sorted(known.values(), key=lambda item: (-item["bytes"], item["path"]))},
                "unknown": {"folders": sorted(unknown.values(), key=lambda item: (-item["bytes"], item["path"])), "bytes": sum(value["bytes"] for value in unknown.values())},
                "protected": sorted(protected.values(), key=lambda item: (-item["bytes"], item["kind"])),
                "indexedFiles": len(rows), "lastIndexedAt": _iso(max((row[12] for row in rows), default=0)) if rows else None}

    def _index(self, root):
        scan = WorkspaceScan(root, self.manager.data_dir).scan()
        if not scan.get("complete"):
            raise StorageError("완결되지 않은 작업 폴더 스캔은 SQLite 색인으로 사용할 수 없습니다.", "incomplete_scan")
        return scan

    def list(self, params):
        if not isinstance(params, dict) or set(params) - {"refreshWorkspace"} or ("refreshWorkspace" in params and type(params["refreshWorkspace"]) is not bool):
            raise StorageError("refreshWorkspace true/false만 지정할 수 있습니다.")
        status = self._status()
        if not status["ready"]:
            return {"workspace": None, "status": status["checks"], "tracking": None, "knownOwnership": {"paths": 0, "bytes": 0}, "unknown": {"folders": [], "bytes": 0}, "cacheState": "unavailable"}
        root = self._workspace()
        scan_available = not self.manager.data_dir.is_relative_to(root)
        if not scan_available:
            scan = None
            cache_state = "scan-skipped-profile-inside-workspace"
        elif params.get("refreshWorkspace", False):
            scan = self._index(root)
            cache_state = "refreshed"
        else:
            scan = None
            cache_state = "cached" if WorkspaceScan(root, self.manager.data_dir).cached() is not None else "scan-required"
        summary = self._summary(root)
        summary["scanRequired"] = cache_state == "scan-required"
        if summary["scanRequired"]:
            summary["knownOwnership"]["bytes"] = None
            summary["unknown"]["bytes"] = None
        return {"workspace": str(root), "status": status["checks"], "ready": True, "checks": status["checks"], "database": status["database"], "tracking": summary, **summary, "cacheState": cache_state,
                **({"warning": "현재 프로필이 작업 폴더 안에 있어 전체 스캔을 생략합니다. 등록된 프로젝트 관리와 확인 가능한 정리만 사용할 수 있습니다."} if not scan_available else {}),
                **({"scan": {key: scan[key] for key in ("scanId", "createdAt", "durationSeconds", "totals")}} if scan else {})}

    def preview(self, params):
        if params != {}:
            raise StorageError("정리 미리보기는 입력값을 받지 않습니다.")
        root = self._workspace()
        rows = self._rows(root)
        now = int(time.time())
        files = []
        for row in rows:
            relative, dev, inode, size, allocated, mtime, ctime, nlink, file_type, classification, *_ = row
            if classification != "os-residue" or file_type != "file" or Path(relative).name != ".DS_Store":
                continue
            files.append({"relativePath": relative, "dev": dev, "inode": inode, "size": size, "allocatedBytes": allocated, "mtimeNs": mtime, "ctimeNs": ctime, "nlink": nlink})
        plan_id = secrets.token_hex(24)
        plan = {"workspace": str(root), "createdAt": now, "expiresAt": now + PLAN_SECONDS, "state": "ready", "files": files}
        try:
            self.db.write_document("tracking-plan:" + plan_id, plan)
        except ManagementDBError as error:
            raise StorageError(str(error), "tracking_unavailable") from error
        scan_available = not self.manager.data_dir.is_relative_to(root)
        return {"planId": plan_id, "expiresAt": _iso(plan["expiresAt"]), "candidates": files,
                "summary": {"fileCount": len(files), "allocatedBytes": sum(item["allocatedBytes"] for item in files)}, "blocked": [], "warnings": [] if scan_available and WorkspaceScan(root, self.manager.data_dir).cached() is not None else ["현재 프로필이 작업 폴더 안에 있어 전체 스캔을 생략합니다." if not scan_available else "소유권 색인이 없습니다. 먼저 명시적으로 새로 고침하세요."],
                "protected": "미분류·도구 상태·원본·모델·완성 결과물은 이 정리 대상에 포함하지 않습니다."}

    def cleanup(self, params):
        if not isinstance(params, dict) or set(params) != {"planId", "confirm"} or not isinstance(params.get("planId"), str) or params.get("confirm") is not True:
            raise StorageError("planId와 confirm:true가 필요합니다.")
        root = self._workspace()
        try:
            with self.db.transaction(write=True) as connection:
                plan = self.db.read_document("tracking-plan:" + params["planId"], fallback=None, connection=connection)
                if not isinstance(plan, dict) or plan.get("state") != "ready" or plan.get("workspace") != str(root) or plan.get("expiresAt", 0) <= int(time.time()):
                    raise StorageError("정리 계획이 없거나 만료되었습니다.", "stale_plan")
                plan["state"] = "used"; plan["usedAt"] = int(time.time())
                self.db.write_document("tracking-plan:" + params["planId"], plan, connection=connection)
        except ManagementDBError as error:
            raise StorageError(str(error), "tracking_unavailable") from error
        removed, skipped, warnings = [], [], []
        for item in plan.get("files", []):
            relative = item.get("relativePath") if isinstance(item, dict) else None
            descriptors = []
            try:
                parts = Path(relative).parts if isinstance(relative, str) else ()
                if not parts or Path(relative).is_absolute() or any(part in {".", ".."} for part in parts) or parts[-1] != ".DS_Store":
                    raise ValueError("안전한 Finder 잔재 경로가 아닙니다.")
                descriptors.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
                for part in parts[:-1]:
                    descriptors.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptors[-1]))
                info = os.stat(parts[-1], dir_fd=descriptors[-1], follow_symlinks=False)
                same = stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and all(int(getattr(info, key)) == item[value] for key, value in (("st_dev", "dev"), ("st_ino", "inode"), ("st_size", "size"), ("st_mtime_ns", "mtimeNs"), ("st_ctime_ns", "ctimeNs"), ("st_nlink", "nlink")))
                if not same:
                    raise ValueError("파일이 계획 후 변경되었거나 안전하게 확인할 수 없습니다.")
                os.unlink(parts[-1], dir_fd=descriptors[-1])
                removed.append({"path": relative, "allocatedBytes": item["allocatedBytes"]})
            except (OSError, TypeError, KeyError, ValueError) as error:
                skipped.append({"path": relative, "reason": str(error)})
            finally:
                for descriptor in reversed(descriptors):
                    os.close(descriptor)
        try:
            with self.db.transaction(write=True) as connection:
                connection.executemany("DELETE FROM storage_tracking_files WHERE workspace=? AND relative_path=?", [(str(root), item["path"]) for item in removed])
                self.db.record_event("tracking-cleanup", path=str(root), after={"removedFiles": len(removed), "skippedFiles": len(skipped)}, reason="verified Finder .DS_Store residue", connection=connection)
        except ManagementDBError as error:
            warnings.append("정리는 실행했으나 결과 색인·이력 저장에 실패했습니다. 명시적으로 새로 고침하세요: " + str(error))
        return {"planId": params["planId"], "removed": removed, "skipped": skipped, "warnings": warnings,
                "removedFiles": len(removed), "freedAllocatedBytes": sum(item["allocatedBytes"] for item in removed)}
