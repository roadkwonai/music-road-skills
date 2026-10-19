"""Fail-closed removal of explicitly selected, self-contained AI MV work roots."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
from contextlib import contextmanager

from storage_manager import MAX_JSON, PLAN_TTL, StorageError, _atomic_json, _id, _json_read, _now
from storage_packaging import TRUSTED_ROOT, is_workspace
from storage_scan import WorkspaceScan


MAX_MV_FILES = 2_000_000
_HEX = re.compile(r"[0-9a-f]{64}")
_ROADMAPS = frozenset({"production-plan.json", "natural-full-production-plan.json"})
_LOOKDEV = "lumi4-highfashion-lookdev-20261016"
_LOOKDEV_RUNS = (
    ".harness/runs/lumi4-prism-mv-20261017-v8/task-direct/input.md",
    ".harness/runs/lumi4-prism-mv-20261017-v8/task-preflight/input.md",
    ".harness/runs/lumi4-prism-mv-20261017-v8/task-create-keys/input.md",
    ".harness/runs/lumi4-highfashion-cast-review-20261016/task-review-new-cast/result.json",
    ".harness/runs/lumi4-noa-covered-master-review-20261016/task-review-noa/result.json",
)
_SHOWREELS = frozenset({"showreel-lumi4-prism-20261017", "showreel-female-mv-20261016"})


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stat(path):
    item = path.stat(follow_symlinks=False)
    return {"dev": item.st_dev, "inode": item.st_ino, "bytes": item.st_size,
            "mtimeNs": item.st_mtime_ns, "mode": stat.S_IFMT(item.st_mode), "nlink": item.st_nlink,
            "blocks": getattr(item, "st_blocks", 0)}


def _same(path, expected):
    try:
        current = _stat(path)
    except OSError:
        return False
    return all(current.get(key) == expected.get(key) for key in ("dev", "inode", "bytes", "mtimeNs", "mode"))


class MVStorage:
    """Discovers verified harness MV roots and two audited legacy Showreel projects."""

    def __init__(self, manager, root=None):
        self.manager = manager
        self.root = Path(root) if root is not None else TRUSTED_ROOT
        if self.root is None or not is_workspace(self.root):
            raise StorageError("현재 Road Music 작업 폴더에서만 AI 영상 프로젝트 정리를 사용할 수 있습니다.", "mv_unavailable")
        self.root = self.root.resolve(strict=True)
        self.work = self.root / ".harness" / "work"
        self.output = self.root / "Output"
        self.plan_dir = self.manager.data_dir / "storage-mv-plans"

    @contextmanager
    def _lock(self):
        # Share the workspace maintenance lock so Git and MV removal never race.
        from storage_maintenance import StorageMaintenance
        with StorageMaintenance(self.manager, self.root)._lock():
            yield

    def _plan_directory(self):
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        for path in (self.plan_dir, *self.plan_dir.parents):
            if path == self.manager.data_dir.parent:
                break
            if path.is_symlink() or not path.is_dir():
                raise StorageError("AI 영상 프로젝트 정리 계획 경로가 안전하지 않습니다.", "unsafe_path")

    def _inside(self, path):
        return path == self.root or self.root in path.parents

    def _safe_file(self, path):
        try:
            if not self._inside(path.resolve(strict=True)):
                return False
            current = path
            while current != self.root:
                if current.is_symlink():
                    return False
                current = current.parent
            return path.is_file() and path.stat().st_size <= MAX_JSON
        except OSError:
            return False

    def _json(self, path):
        if not self._safe_file(path):
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _json_list(self, path):
        if not self._safe_file(path):
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, list) else None

    def _source(self, project):
        value = self._json(project / "input.json")
        if not isinstance(value, dict):
            return None
        nested = value.get("source_audio")
        if isinstance(nested, dict):
            source, digest = nested.get("audio", nested.get("path")), nested.get("sha256")
            title = nested.get("title") if isinstance(nested.get("title"), str) else nested.get("track_id")
        else:
            source, digest = nested, value.get("source_audio_sha256")
            title = value.get("title") if isinstance(value.get("title"), str) else None
        if not isinstance(source, str) or not Path(source).is_absolute() or not isinstance(digest, str) or not _HEX.fullmatch(digest):
            return None
        path = Path(source)
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return None
        if path.is_symlink() or not resolved.is_file() or self._inside(resolved) and project in resolved.parents:
            return None
        # A source within the workspace is valid only when it is outside the removable root.
        if project == resolved or project in resolved.parents:
            return None
        return {"path": str(resolved), "sha256": digest, "title": title}

    def _showreel_source(self, project):
        """Recognize only the two audited generated-image Showreel MV roots."""
        if project.parent != self.output or project.name not in _SHOWREELS:
            return None
        project_meta = self._json(project / "project.json")
        timeline = self._json(project / "timeline.json")
        verification = self._json(project / "audio" / "source-verification.json")
        if not all(isinstance(value, dict) for value in (project_meta, timeline, verification)):
            return None
        dimensions = ("width", "height", "fps", "duration")
        if any(not isinstance(project_meta.get(key), (int, float)) or project_meta[key] <= 0 for key in dimensions):
            return None
        if any(timeline.get(key) != project_meta.get(key) for key in dimensions):
            return None
        source, digest = verification.get("sourceAudio"), verification.get("sourceSha256")
        if not isinstance(source, str) or not Path(source).is_absolute() or not isinstance(digest, str) or not _HEX.fullmatch(digest):
            return None
        source_path = Path(source)
        try:
            source_path = source_path.resolve(strict=True)
        except OSError:
            return None
        if source_path.is_symlink() or not source_path.is_file() or project in source_path.parents:
            return None
        provenance = self._json_list(project / "assets" / "source-manifest.json") or self._json_list(project / "assets" / "provenance.json")
        generated = self._json_list(project / "assets" / "generation-sources.json")
        if not isinstance(provenance, list) or not provenance or not isinstance(generated, list) or not generated:
            return None
        if not any(isinstance(item, dict) and isinstance(item.get("sha256"), str) and _HEX.fullmatch(item["sha256"]) for item in provenance):
            return None
        if not any(isinstance(item, dict) and isinstance(item.get("source"), str) and item["source"].startswith("/") for item in generated):
            return None
        title = project_meta.get("title") if isinstance(project_meta.get("title"), str) else source_path.stem
        return {"path": str(source_path), "sha256": digest, "title": title}

    def _plan_marker(self, project):
        # Older verified MV runs use the explicitly supported natural-full roadmap.
        for name in _ROADMAPS:
            path = project / name
            value = self._json(path)
            if isinstance(value, dict) and isinstance(value.get("objective"), str) and value["objective"].strip() and isinstance(value.get("tasks"), list):
                return True
        return False

    def _shared_lookdev_source(self, project):
        """Recognize one audited shared-asset root; generic lookdev folders stay protected."""
        if project.name != _LOOKDEV or project != self.work / _LOOKDEV:
            return None
        mv = self.work / "lumi4-selected-mv-20261017-v8"
        source = self._source(mv)
        if source is None:
            return None
        root_text = ".harness/work/" + _LOOKDEV
        for relative in _LOOKDEV_RUNS:
            proof = self.root / relative
            if not self._safe_file(proof):
                return None
            try:
                content = proof.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return None
            if root_text not in content:
                return None
        return source

    def _unsafe_tree(self, project):
        seen = 0
        for base, directories, names in os.walk(project, followlinks=False):
            for name in [*directories, *names]:
                seen += 1
                if seen > MAX_MV_FILES:
                    return "AI 영상 프로젝트 파일 수가 안전 한도를 초과했습니다."
                parts = (Path(base) / name).relative_to(project).parts
                folded = {part.casefold() for part in parts}
                if folded & {".git", "models", "model", "engines", "engine", "node_modules"} or any(part.casefold().endswith(".app") for part in parts):
                    return "프로그램·모델·엔진을 포함한 작업 폴더는 통째 정리하지 않습니다."
        return None

    def _active(self, project):
        try:
            result = subprocess.run(["lsof", "-nP", "+D", str(project)], capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return "사용 중인지 확인할 수 없어 보호합니다."
        if result.returncode not in {0, 1} or result.stderr.strip():
            return "사용 중인지 확인할 수 없어 보호합니다."
        if result.stdout.strip():
            return "열린 파일 또는 실행 중인 제작 프로세스가 있습니다."
        try:
            data = self.manager._read()
            for project_id, record in data.get("projects", {}).items():
                path = record.get("path") if isinstance(record, dict) else None
                if isinstance(path, str) and Path(path).resolve(strict=False) == project and self.manager._busy(data, project_id):
                    return "진행 중인 제작 lease가 있습니다."
        except (StorageError, OSError):
            return "등록된 제작 lease를 확인할 수 없어 보호합니다."
        return None

    def _inventory(self, project):
        entries = []
        for base, directories, names in os.walk(project, topdown=True, followlinks=False):
            directories.sort(); names.sort()
            for name in directories:
                path = Path(base) / name
                kind = "symlink" if path.is_symlink() else "dir"
                entries.append({"relativePath": str(path.relative_to(project)), "type": kind, **_stat(path)})
            for name in names:
                path = Path(base) / name
                kind = "symlink" if path.is_symlink() else "file"
                if kind == "file" and not path.is_file():
                    raise StorageError("일반 파일·폴더·symlink 외 항목은 AI 영상 프로젝트 정리에서 보호합니다.", "unsafe_path")
                entries.append({"relativePath": str(path.relative_to(project)), "type": kind, **_stat(path)})
                if len(entries) > MAX_MV_FILES:
                    raise StorageError("AI 영상 프로젝트 파일 수가 안전 한도를 초과했습니다.", "snapshot_limit")
        if not entries:
            raise StorageError("빈 AI 영상 프로젝트는 정리 후보가 아닙니다.", "empty_project")
        return entries

    @staticmethod
    def _allocated(values):
        """Count an inode only if every one of its links is selected for removal."""
        grouped = {}
        for value in values:
            for item in value["entries"]:
                if item["type"] == "dir":
                    continue
                key = (item["dev"], item["inode"])
                group = grouped.setdefault(key, {"links": 0, "nlink": item["nlink"], "blocks": item["blocks"]})
                group["links"] += 1
        return sum(group["blocks"] * 512 for group in grouped.values() if group["links"] == group["nlink"])

    @staticmethod
    def _cross_root_hardlinks(values):
        owners = {}
        for value in values:
            for item in value["entries"]:
                if item["type"] != "dir":
                    owners.setdefault((item["dev"], item["inode"]), set()).add(value["id"])
        return any(len(value) > 1 for value in owners.values())

    @staticmethod
    def _progress_allocated(plan, removed):
        expected = {}
        for project in plan["projects"]:
            for item in project["entries"]:
                if item["type"] != "dir":
                    key = (item["dev"], item["inode"])
                    group = expected.setdefault(key, {"count": 0, "nlink": item["nlink"], "blocks": item["blocks"]})
                    group["count"] += 1
        completed = {}
        for item in removed:
            key = (item["dev"], item["inode"])
            completed[key] = completed.get(key, 0) + 1
        return sum(group["blocks"] * 512 for key, group in expected.items() if completed.get(key) == group["count"] == group["nlink"])

    def _candidate(self, project):
        legacy_showreel = self._showreel_source(project)
        source = self._source(project) or legacy_showreel or self._shared_lookdev_source(project)
        shared_assets = project.name == _LOOKDEV and source is not None
        reasons = []
        if source is None:
            reasons.append("원본 음원 해시가 있는 input.json을 확인할 수 없습니다.")
        elif not Path(source["path"]).is_file() or _sha256(Path(source["path"])) != source["sha256"]:
            reasons.append("원본 음원 또는 해시가 달라져 보호합니다.")
        if not shared_assets and not legacy_showreel and not self._plan_marker(project):
            reasons.append("검증된 MV 제작 로드맵 표지가 없습니다.")
        unsafe = self._unsafe_tree(project)
        if unsafe: reasons.append(unsafe)
        active = self._active(project)
        if active: reasons.append(active)
        try:
            entries = self._inventory(project)
        except StorageError as error:
            entries = []; reasons.append(str(error))
        path = str(project)
        source = source or {}
        file_entries = [item for item in entries if item["type"] != "dir"]
        result = {"id": _id("ai-mv\0" + path), "kind": "ai-mv-shared-assets" if shared_assets else "ai-showreel-mv" if legacy_showreel else "ai-mv", "title": source.get("title") or project.name,
                "sourceSha256": source.get("sha256"), "sourcePath": source.get("path"), "path": path,
                "fileCount": len(file_entries), "bytes": sum(item["bytes"] for item in file_entries),
                "allocatedBytes": 0,
                "blocked": bool(reasons), "reasons": reasons, "sharedAssets": shared_assets, "entries": entries, "root": _stat(project),
                "fingerprint": _id(json.dumps({"root": _stat(project), "source": source, "entries": entries}, sort_keys=True, separators=(",", ":")))}
        result["allocatedBytes"] = self._allocated([result])
        return result

    def _discover(self):
        if self.work.is_symlink() or not self.work.is_dir():
            return []
        result = []
        for candidate in sorted(self.work.iterdir()):
            if candidate.is_symlink() or not candidate.is_dir():
                continue
            # Discovery requires both source identity and a production-plan, not a project-like name.
            if self._source(candidate) is not None or self._plan_marker(candidate) or candidate == self.work / _LOOKDEV:
                result.append(self._candidate(candidate))
        if self.output.is_dir() and not self.output.is_symlink():
            for name in sorted(_SHOWREELS):
                candidate = self.output / name
                if candidate.is_dir() and not candidate.is_symlink():
                    result.append(self._candidate(candidate))
        return result

    @staticmethod
    def _public(value):
        return {key: value.get(key) for key in ("id", "kind", "title", "sourceSha256", "sourcePath", "path", "fileCount", "bytes", "allocatedBytes", "blocked", "reasons", "sharedAssets")}

    def list(self, params):
        if params:
            raise StorageError("AI 영상 프로젝트 목록은 별도 입력값을 받지 않습니다.")
        projects = self._discover()
        return {"workspace": str(self.root), "projects": [self._public(item) for item in projects],
                "summary": {"projects": len(projects), "ready": sum(not item["blocked"] for item in projects),
                            "bytes": sum(item["bytes"] for item in projects if not item["blocked"]),
                            "allocatedBytes": sum(item["allocatedBytes"] for item in projects if not item["blocked"])} ,
                "protected": ["원본 음원·가사·음악 결과물", "프로그램·모델·엔진·앱", "제작 중 lease 또는 열린 파일", "제작 표지·원본 해시를 확인할 수 없는 폴더"]}

    def _scan(self, scan_id):
        scan = WorkspaceScan(self.root, self.manager.data_dir).load(scan_id)
        if not scan.get("complete"):
            raise StorageError("전체 작업 폴더 스캔을 완료한 뒤 AI 영상 프로젝트 정리 계획을 만드세요.", "scan_required")
        return scan

    def preview(self, params):
        if not isinstance(params, dict) or set(params) != {"scanId", "projectIds"}:
            raise StorageError("scanId와 선택한 AI 영상 프로젝트 ID만 지정할 수 있습니다.")
        scan = self._scan(params.get("scanId"))
        selected = params.get("projectIds")
        if not isinstance(selected, list) or not selected or len(selected) > 100 or len(selected) != len(set(selected)) or any(not isinstance(value, str) or not _HEX.fullmatch(value) for value in selected):
            raise StorageError("서로 다른 AI 영상 프로젝트 ID가 필요합니다.")
        with self._lock():
            current = {item["id"]: item for item in self._discover()}
            if any(value not in current or current[value]["blocked"] for value in selected):
                raise StorageError("프로젝트가 변경됐거나 보호됩니다. 목록을 다시 확인하세요.", "stale_plan")
            values = sorted((current[value] for value in selected), key=lambda value: (not value.get('sharedAssets'), value['path']))
            if self._cross_root_hardlinks(values):
                raise StorageError("서로 다른 AI 영상 프로젝트가 같은 파일 inode를 공유해 통째 정리를 보호합니다. 개별 프로젝트로 다시 점검하세요.", "shared_hardlink")
            allocated = self._allocated(values)
            plan = {"schemaVersion": 1, "planId": secrets.token_hex(24), "state": "ready", "workspace": str(self.root),
                    "scanId": scan.get("scanId"), "scanFingerprint": scan.get("fingerprint"), "createdAt": _now(),
                    "expiresAt": min(_now() + PLAN_TTL, scan.get("expiresAt", _now() + PLAN_TTL)), "projects": values,
                    "estimatedReclaimableAllocatedBytes": allocated}
            self._plan_directory()
            path = self.plan_dir / (plan["planId"] + ".json")
            _atomic_json(path, plan)
            public = [self._public(value) for value in values]
            return {"planId": plan["planId"], "scanId": plan["scanId"], "expiresAt": plan["expiresAt"], "projects": public,
                    "fileCount": sum(value["fileCount"] for value in values), "bytes": sum(value["bytes"] for value in values),
                    "estimatedReclaimableBytes": allocated, "warning": "선택한 AI 영상 프로젝트 폴더 전체(애니매틱·중간본·렌더 포함)를 제거합니다. 원본 음원은 별도 해시 검증 뒤 유지합니다."}

    def _unlink(self, project, root_expected, relative, expected):
        parts = Path(relative).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise StorageError("안전하지 않은 삭제 경로입니다.", "unsafe_path")
        fd = os.open(project, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            root_info = os.fstat(fd)
            if (root_info.st_dev, root_info.st_ino, stat.S_IFMT(root_info.st_mode)) != (root_expected["dev"], root_expected["inode"], root_expected["mode"]):
                raise StorageError("AI 영상 프로젝트 루트가 교체되어 보호합니다.", "stale_plan")
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
                os.close(fd); fd = next_fd
            leaf = parts[-1]
            current = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            actual = {"dev": current.st_dev, "inode": current.st_ino, "bytes": current.st_size,
                      "mtimeNs": current.st_mtime_ns, "mode": stat.S_IFMT(current.st_mode)}
            if any(actual[key] != expected[key] for key in actual):
                raise StorageError("계획 뒤 AI 영상 프로젝트 파일이 변경되었습니다.", "stale_plan")
            os.unlink(leaf, dir_fd=fd)
        finally:
            os.close(fd)

    def _verify_project(self, expected):
        project = Path(expected["path"])
        current = self._candidate(project)
        if current["blocked"] or current["fingerprint"] != expected["fingerprint"]:
            raise StorageError("계획 뒤 AI 영상 프로젝트 또는 보호 상태가 변경됐습니다.", "stale_plan")
        source = Path(expected["sourcePath"])
        if not source.is_file() or _sha256(source) != expected["sourceSha256"]:
            raise StorageError("원본 음원 해시가 변경돼 AI 영상 프로젝트를 보호합니다.", "source_changed")
        for item in expected["entries"]:
            if not _same(project / item["relativePath"], item):
                raise StorageError("계획 뒤 AI 영상 프로젝트 항목이 변경됐습니다.", "stale_plan")

    def _remove_project(self, expected, removed_entries):
        project = Path(expected["path"])
        entries = expected["entries"]
        removed = 0
        for item in sorted((value for value in entries if value["type"] != "dir"), key=lambda value: len(Path(value["relativePath"]).parts), reverse=True):
            self._unlink(project, expected["root"], item["relativePath"], item); removed += 1; removed_entries.append(item)
        for item in sorted((value for value in entries if value["type"] == "dir"), key=lambda value: len(Path(value["relativePath"]).parts), reverse=True):
            path = project / item["relativePath"]
            # Removing a child necessarily changes its parent's mtime; rmdir still refuses new children.
            current = _stat(project)
            if (current["dev"], current["inode"], current["mode"]) != (expected["root"]["dev"], expected["root"]["inode"], expected["root"]["mode"]):
                raise StorageError("AI 영상 프로젝트 루트가 교체되어 보호합니다.", "stale_plan")
            path.rmdir()
        current = _stat(project)
        if (current["dev"], current["inode"], current["mode"]) != (expected["root"]["dev"], expected["root"]["inode"], expected["root"]["mode"]):
            raise StorageError("AI 영상 프로젝트 루트가 교체되어 보호합니다.", "stale_plan")
        project.rmdir()
        return removed

    def cleanup(self, params):
        if not isinstance(params, dict) or set(params) != {"planId", "confirm"} or params.get("confirm") is not True:
            raise StorageError("같은 미리보기 planId와 명시 확인이 필요합니다.", "confirm_required")
        plan_id = params.get("planId")
        if not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{48}", plan_id):
            raise StorageError("AI 영상 프로젝트 정리 계획이 올바르지 않습니다.", "invalid_plan")
        with self._lock():
            self._plan_directory()
            path = self.plan_dir / (plan_id + ".json")
            plan = _json_read(path, None)
            if not isinstance(plan, dict) or plan.get("state") != "ready" or plan.get("workspace") != str(self.root) or plan.get("expiresAt", 0) <= _now():
                raise StorageError("사용되었거나 만료된 AI 영상 프로젝트 정리 계획입니다.", "invalid_plan")
            scan = self._scan(plan.get("scanId"))
            if scan.get("fingerprint") != plan.get("scanFingerprint"):
                raise StorageError("전체 작업 폴더 스캔이 변경됐습니다.", "stale_scan")
            # Validate every selected root and source before the first unlink.
            for item in plan["projects"]:
                self._verify_project(item)
            plan["state"] = "used"; _atomic_json(path, plan)
            intent = {"planId": plan_id, "projects": len(plan["projects"]), "fileCount": sum(value["fileCount"] for value in plan["projects"]), "bytes": sum(value["bytes"] for value in plan["projects"]), "sources": [{"title": value["title"], "sha256": value["sourceSha256"]} for value in plan["projects"]]}
            self.manager._audit(self.root, "mv-project-cleanup-intent", intent)
            before = shutil.disk_usage(self.root).free
            removed = 0
            removed_entries = []
            completed_projects = 0
            try:
                for item in plan["projects"]:
                    # A long earlier removal can leave a later root stale; recheck at its commit point.
                    self._verify_project(item)
                    removed += self._remove_project(item, removed_entries)
                    completed_projects += 1
            except (StorageError, OSError) as error:
                partial = {"status": "partial", "removedProjects": completed_projects, "removedFiles": len(removed_entries),
                           "freedBytes": sum(item["bytes"] for item in removed_entries),
                           "freedAllocatedBytes": self._progress_allocated(plan, removed_entries),
                           "diskFreeDeltaBytes": shutil.disk_usage(self.root).free - before,
                           "skipped": [value["path"] for value in plan["projects"][completed_projects:]], "warnings": [str(error)],
                           "auditPath": str(self.root / ".roadmusic" / "history.jsonl")}
                try:
                    _atomic_json(path, {"schemaVersion": 1, "planId": plan_id, "state": "used", "workspace": str(self.root), "result": partial})
                    self.manager._audit(self.root, "mv-project-cleanup-failed", {"planId": plan_id, **{key: partial[key] for key in ("removedProjects", "removedFiles", "freedBytes", "freedAllocatedBytes", "diskFreeDeltaBytes")}, "message": str(error)[:1000]})
                except (StorageError, OSError) as audit_error:
                    partial["warnings"].append("부분 정리 결과 감사 기록 저장에 실패했습니다: " + str(audit_error))
                return partial
            result = {"removedProjects": len(plan["projects"]), "removedFiles": removed,
                      "freedBytes": sum(value["bytes"] for value in plan["projects"]),
                      "freedAllocatedBytes": plan.get("estimatedReclaimableAllocatedBytes", 0),
                      "diskFreeDeltaBytes": shutil.disk_usage(self.root).free - before, "skipped": [], "warnings": [],
                      "auditPath": str(self.root / ".roadmusic" / "history.jsonl")}
            try:
                self.manager._audit(self.root, "mv-project-cleanup", {"planId": plan_id, **{key: result[key] for key in ("removedProjects", "removedFiles", "freedBytes", "freedAllocatedBytes", "diskFreeDeltaBytes")}})
                _atomic_json(path, {"schemaVersion": 1, "planId": plan_id, "state": "used", "workspace": str(self.root), "result": result})
            except (StorageError, OSError) as error:
                result["warnings"].append("정리는 완료됐으나 결과 감사 기록 저장에 실패했습니다: " + str(error))
            return result
