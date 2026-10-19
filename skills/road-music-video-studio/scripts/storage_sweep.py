"""One-use automatic cleanup plan for registered reproducible caches only."""
from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import shutil
from contextlib import contextmanager

from storage_manager import PLAN_TTL, StorageError, _atomic_json, _iso, _json_read, _now, _lock_for
from storage_maintenance import StorageMaintenance
from storage_packaging import TRUSTED_ROOT, is_workspace


SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class StorageSweep:
    """Compose existing safe cache/MV plans; it never discovers arbitrary files."""

    def __init__(self, manager, root=None, mv_storage_factory=None):
        self.manager = manager
        self.root = Path(root) if root is not None else TRUSTED_ROOT
        if self.root is None or not is_workspace(self.root):
            raise StorageError("현재 trusted Road Music 작업 폴더에서만 자동 일괄 정리를 사용할 수 있습니다.", "sweep_unavailable")
        self.plan_dir = manager.data_dir / "storage-sweep-plans"
        self.lock_path = manager.data_dir / ".storage-sweep.lock"
        self._process_lock = _lock_for(self.lock_path)
        self.mv_storage_factory = mv_storage_factory

    @contextmanager
    def _lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._process_lock, self.lock_path.open("a+b") as stream:
            if os.name == "nt":
                import msvcrt
                stream.seek(0); stream.write(b"0"); stream.flush(); stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _path(self, plan_id):
        if not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{48}", plan_id):
            raise StorageError("planId가 올바르지 않습니다.")
        if self.plan_dir.exists() and self.plan_dir.is_symlink():
            raise StorageError("자동 정리 계획 경로가 안전하지 않습니다.", "unsafe_path")
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        return self.plan_dir / f"{plan_id}.json"

    def _prune(self):
        if not self.plan_dir.exists():
            return
        for path in self.plan_dir.iterdir():
            if path.is_symlink() or not path.is_file() or not re.fullmatch(r"[0-9a-f]{48}\.json", path.name):
                continue
            try:
                plan = _json_read(path, None)
            except StorageError:
                continue
            if isinstance(plan, dict) and (plan.get("state") == "used" or plan.get("expiresAt", 0) < _now()):
                path.unlink()

    def _mv(self):
        if self.mv_storage_factory is not None:
            return self.mv_storage_factory(self.manager)
        from storage_mv import MVStorage
        return MVStorage(self.manager)

    @staticmethod
    def _cache_entries(preview, projects):
        descriptions = {(project.get("id"), entry.get("id")): entry.get("description") or entry.get("relativePath") or entry.get("path")
                        for project in projects for entry in project.get("entries", []) if isinstance(entry, dict)}
        return [{"kind": "project-cache", "projectId": item.get("projectId"), "entryId": item.get("id"),
                 "description": descriptions.get((item.get("projectId"), item.get("id")), item.get("relativePath", "재생성 캐시")),
                 "path": item.get("relativePath"), "bytes": item.get("bytes", 0), "fileCount": 1}
                for item in preview.get("entries", [])]

    def preview(self, params):
        if not isinstance(params, dict) or set(params) - {"mvProjectIds"}:
            raise StorageError("자동 일괄 정리는 AI 영상 프로젝트 ID만 지정할 수 있습니다.")
        ids = params.get("mvProjectIds", [])
        if not isinstance(ids, list) or len(ids) > 200 or len(ids) != len(set(ids)) or any(not isinstance(item, str) or not SHA256.fullmatch(item) for item in ids):
            raise StorageError("AI 영상 프로젝트 ID가 올바르지 않습니다.")
        maintenance = StorageMaintenance(self.manager, self.root)
        listing = maintenance.list({})  # A complete whole-workspace scan always precedes a plan.
        scan = listing.get("scan", {})
        if not scan.get("complete") or not isinstance(scan.get("scanId"), str):
            raise StorageError("전체 작업 폴더 스캔을 완료한 뒤 자동 정리 계획을 만드세요.", "scan_required")
        cache = {"planId": None, "entries": [], "blocked": []}
        entries, blocked = [], []
        verification = None
        if not ids:
            # Bulk cleanup follows each project's completed/retention policy; manual
            # project cleanup remains the explicit route for editing caches.
            cache = self.manager.preview({}, automatic=True)
            entries = self._cache_entries(cache, self.manager.list({}).get("projects", []))
            blocked = list(cache.get("blocked", []))
            candidates = listing.get("candidates", [])
            candidate_ids = [item.get("id") for item in candidates if isinstance(item, dict) and item.get("scope") == "verification" and isinstance(item.get("id"), str)]
            if candidate_ids:
                verification = maintenance.preview({"scanId": scan["scanId"], "scope": "verification", "candidateIds": candidate_ids})
                entries.extend({"kind": "verification-copy", "projectId": item.get("id"), "description": item.get("description") or "과거 설치 검증 복제본",
                                "path": item.get("path"), "bytes": item.get("allocatedBytes", item.get("bytes", 0)), "fileCount": item.get("fileCount", 0)}
                               for item in verification.get("entries", []))
                blocked.extend(verification.get("blocked", []))
        mv_preview = None
        if ids:
            mv_preview = self._mv().preview({"scanId": scan["scanId"], "projectIds": ids})
            entries.extend({"kind": "ai-mv-project", "projectId": item.get("id"), "description": item.get("title") or item.get("path") or "AI 영상 프로젝트",
                            "path": item.get("path"), "bytes": item.get("estimatedReclaimableBytes", item.get("bytes", 0)), "fileCount": item.get("fileCount", 0)}
                           for item in mv_preview.get("projects", []))
            blocked.extend(mv_preview.get("blocked", []))
        bytes_ = sum(item.get("bytes", 0) for item in entries)
        files = sum(item.get("fileCount", 0) for item in entries)
        if not cache.get("planId") and not (verification and verification.get("planId")) and not (mv_preview and mv_preview.get("planId")):
            return {"planId": None, "scanId": scan["scanId"], "entries": [], "bytes": 0, "estimatedReclaimableBytes": 0,
                    "fileCount": 0, "blocked": blocked, "excluded": ["원본·완성본·중간본·이력과 원음을 확인할 수 없는 프로젝트는 자동 정리에서 제외됩니다."], "expiresAt": None}
        now = _now(); plan_id = secrets.token_hex(24)
        plan = {"schemaVersion": 1, "planId": plan_id, "workspace": str(self.root), "state": "ready", "createdAt": now,
                "expiresAt": min(now + PLAN_TTL, scan.get("expiresAt", now + PLAN_TTL)),
                "scanId": scan["scanId"], "cachePlanId": cache.get("planId"), "verificationPlanId": verification.get("planId") if verification else None,
                "mvPlanId": mv_preview.get("planId") if mv_preview else None,
                "entries": entries}
        path = self._path(plan_id); self._prune(); _atomic_json(path, plan)
        return {"planId": plan_id, "scanId": scan["scanId"], "entries": entries, "bytes": bytes_, "estimatedReclaimableBytes": bytes_, "fileCount": files,
                "blocked": blocked, "excluded": (["외부 원음·모델·앱과 선택하지 않은 다른 프로젝트는 제외됩니다."] if ids else
                    ["원본·완성본·중간본·이력은 자동 정리하지 않습니다.", "AI 영상 프로젝트 전체 삭제는 명시적으로 선택한 프로젝트만 포함됩니다."]), "expiresAt": _iso(plan["expiresAt"])}

    def cleanup(self, params):
        if not isinstance(params, dict) or params.get("confirm") is not True or set(params) - {"planId", "confirm"}:
            raise StorageError("자동 정리에는 planId와 confirm:true가 필요합니다.", "confirmation_required")
        path = self._path(params.get("planId")); plan = _json_read(path, None)
        if not isinstance(plan, dict) or plan.get("planId") != params["planId"] or plan.get("workspace") != str(self.root) or plan.get("state") != "ready":
            raise StorageError("유효한 자동 정리 계획이 아닙니다.", "invalid_plan")
        if plan.get("expiresAt", 0) < _now():
            raise StorageError("자동 정리 계획이 만료되었습니다.", "plan_expired")
        maintenance = StorageMaintenance(self.manager, self.root)
        disk_before = shutil.disk_usage(self.manager.data_dir).free
        removed = freed = allocated = 0; allocated_known = True; skipped = []; warnings = []; results = []
        # This own-plan lock never nests a child maintenance lock.
        with self._lock():
            plan = _json_read(path, None)
            if not isinstance(plan, dict) or plan.get("state") != "ready":
                raise StorageError("유효한 자동 정리 계획이 아닙니다.", "invalid_plan")
            plan["state"] = "in-progress"; _atomic_json(path, plan)
        try:
            self.manager._audit(self.root, "sweep-intent", {"planId": plan["planId"], "scanId": plan["scanId"], "entries": plan["entries"]})
            if plan.get("cachePlanId"):
                try:
                    result = self.manager.cleanup({"planId": plan["cachePlanId"], "confirm": True})
                    removed += result.get("removedFiles", 0); freed += result.get("freedBytes", 0)
                    allocated_known = False
                    skipped.extend(result.get("skipped", [])); warnings.extend(result.get("warnings", [])); results.append({"kind": "project-cache", **result})
                except (OSError, StorageError) as error:
                    warnings.append(f"프로젝트 캐시 정리 실패: {error}")
            if plan.get("verificationPlanId"):
                try:
                    result = maintenance.cleanup({"planId": plan["verificationPlanId"], "confirm": True})
                    removed += result.get("removedFiles", 0); freed += result.get("freedBytes", 0); allocated += result.get("freedAllocatedBytes", 0)
                    skipped.extend(result.get("skipped", [])); warnings.extend(result.get("warnings", [])); results.append({"kind": "verification-copy", **result})
                except (OSError, StorageError) as error:
                    warnings.append(f"과거 설치 검증 복제본 정리 실패: {error}")
            if plan.get("mvPlanId"):
                try:
                    result = self._mv().cleanup({"planId": plan["mvPlanId"], "confirm": True})
                    removed += result.get("removedFiles", result.get("fileCount", 0)); freed += result.get("freedBytes", result.get("bytes", 0)); allocated += result.get("freedAllocatedBytes", 0)
                    skipped.extend(result.get("skipped", [])); warnings.extend(result.get("warnings", [])); results.append({"kind": "ai-mv-project", **result})
                except (OSError, StorageError) as error:
                    warnings.append(f"AI 영상 프로젝트 정리 실패: {error}")
            with self._lock():
                latest = _json_read(path, None)
                if not isinstance(latest, dict) or latest.get("state") != "in-progress":
                    raise StorageError("자동 정리 계획 상태가 변경되었습니다.", "invalid_plan")
                latest["state"] = "used"; latest["usedAt"] = _now(); _atomic_json(path, latest); path.unlink(missing_ok=True)
        except Exception:
            with self._lock():
                latest = _json_read(path, None)
                if isinstance(latest, dict) and latest.get("state") == "in-progress":
                    latest["state"] = "failed"; _atomic_json(path, latest)
            raise
        disk_delta = shutil.disk_usage(self.manager.data_dir).free - disk_before
        result = {"removedFiles": removed, "freedBytes": freed, "freedAllocatedBytes": allocated if allocated_known else None, "diskFreeDeltaBytes": disk_delta,
                  "skipped": skipped, "warnings": warnings, "results": results, "auditPath": str(self.root / ".roadmusic/history.jsonl")}
        try:
            self.manager._audit(self.root, "sweep-cleanup", {"planId": params["planId"], **{key: result[key] for key in ("removedFiles", "freedBytes", "freedAllocatedBytes", "diskFreeDeltaBytes")}})
        except (OSError, StorageError) as error:
            result["warnings"].append(f"감사 완료 기록 실패: {error}")
        return result
