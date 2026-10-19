"""Fail-closed cleanup for the audited, historical install-verification copies only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil

from storage_manager import MAX_JSON, StorageError, StorageManager, _bounded_files, _id, _snapshot


# These are the only historical verification copies audited for this migration.
PROFILES = (
    ("forward-installed", "Output/music-road-skills-publish-20261018/forward-test/installed-project", "skill-install-copy", "Output/music-road-skills-publish-20261018/forward-test/install-project.json", "Output/music-road-skills-publish-20261018/forward-test/release-build.json", ".agents/skills/.music-road-skills/managed.json"),
    ("forward-clean", "Output/music-road-skills-publish-20261018/forward-test/clean-installed", "skill-install-copy", "Output/music-road-skills-publish-20261018/forward-test/clean-install.json", "Output/music-road-skills-publish-20261018/forward-test/release-build.json", ".agents/skills/.music-road-skills/managed.json"),
    ("forward-extracted", "Output/music-road-skills-publish-20261018/forward-test/release-extracted", "skill-release-extract", "Output/music-road-skills-publish-20261018/forward-test/release-build.json", "Output/music-road-skills-publish-20261018/forward-test/verification-summary.json", "MusicRoad-Skills-0.1.0/manifest.json"),
    ("cli-e2e", "Output/music-road-skills-publish-20261018/cli-kit-e2e", "cli-install-copy", "Output/music-road-skills-publish-20261018/cli-kit-e2e-report.json", "Output/music-road-skills-publish-20261018/cli-live-release-0.1.1/SHA256SUMS.txt", "RoadMusic-CLI-0.1.1/package.json"),
    ("cli-installed-skills", "Output/music-road-skills-publish-20261018/cli-kit-installed-skills", "skill-install-copy", "Output/music-road-skills-publish-20261018/live-skills-install.json", "Output/music-road-skills-publish-20261018/live-skills-check.json", ".music-road-skills/managed.json"),
    ("live-release-skills", "Output/music-road-skills-publish-20261018/live-release-skills", "skill-install-copy", "Output/music-road-skills-publish-20261018/live-skills-install.json", "Output/music-road-skills-publish-20261018/live-skills-check.json", ".music-road-skills/managed.json"),
    ("local-cli-kit", "Output/skills-review-20261018/cli-kit-local", "cli-install-copy", "Output/skills-review-20261018/local-kit-e2e.json", "Output/skills-review-20261018/cli-package.log", "RoadMusic-CLI-0.1.2/package.json"),
)
DMG_SHA256 = "5297e714bb97627ea5425571d230185a63417cd2b8ceb10b26bdf928d6a3af55"
DMG_BYTES = 102948379
DMG_DOWNLOAD = "dist/.release-verify-HGUiMR/mac-app/updates/RoadMusic-1.4.0-mac-arm64.dmg.download"
DMG_ROOTS = (
    ".",
    "Output/female-ballads-20261016/runtime/ace/turbo-2b-lm-0.6b-lowcache/road-music",
    "Output/female-ballads-20261016/runtime/ace/turbo-2b-lm-1.7b-lowcache/road-music",
    "Output/female-ballads-optimized-20261016/runtime/ace/turbo-2b-lm-0.6b-locked-lyrics/road-music",
    "Output/female-ballads-optimized-20261016/runtime/ace/turbo-2b-lm-1.7b-locked-lyrics/road-music",
)


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular(path):
    return path.is_file() and not path.is_symlink()


def _json(path):
    if not _regular(path) or path.stat().st_size > MAX_JSON:
        raise StorageError("검증 receipt가 안전하지 않습니다", "unsafe_receipt")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StorageError("검증 receipt를 읽을 수 없습니다", "unsafe_receipt") from error
    if not isinstance(value, (dict, list)):
        raise StorageError("검증 receipt 형식이 올바르지 않습니다", "unsafe_receipt")
    return value


def _contains(value, needle):
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return False


def _allocated(path):
    return getattr(path.stat(follow_symlinks=False), "st_blocks", 0) * 512


class VerificationMaintenance:
    """Only recognizes pre-audited copies; it never discovers arbitrary Output files."""

    def __init__(self, root, *, active_check=None):
        self.root = Path(root).resolve(strict=True)
        self.active_check = active_check or self._active

    def _inside(self, path):
        return path == self.root or self.root in path.parents

    def _path(self, relative):
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise StorageError("검증 경로가 안전하지 않습니다", "unsafe_path")
        path = self.root / relative
        for parent in (path, *path.parents):
            if parent == self.root.parent: break
            if parent.is_symlink():
                raise StorageError("검증 경로가 안전하지 않습니다", "unsafe_path")
        if not self._inside(path.resolve(strict=False)):
            raise StorageError("검증 경로가 안전하지 않습니다", "unsafe_path")
        return path

    def _active(self, path):
        if Path.cwd().resolve() == path or path in Path.cwd().resolve().parents:
            return True
        try:
            references = [Path(value) for name in ('road-music', 'road-music-cli') if (value := shutil.which(name))]
            for base in (Path.home() / '.codex/skills', Path.home() / '.agents/skills'):
                references.extend(item for item in base.glob('road-music*') if item.is_symlink())
            if any((target := reference.resolve()) == path or path in target.parents for reference in references):
                return True
            target = ['+D', str(path)] if path.is_dir() else ['--', str(path)]
            result = subprocess.run(['lsof', '-nP', '-Fp', *target], capture_output=True, text=True, timeout=20, check=False)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            return True
        return result.returncode not in {0, 1} or bool(result.stdout.strip()) or bool(result.stderr.strip())

    def _tree(self, path):
        files = _bounded_files(path)
        if any(item.suffix.casefold() in {".safetensors", ".gguf", ".ggml", ".ckpt", ".pth", ".pt"} or any(part.casefold().endswith(".app") for part in item.relative_to(path).parts) for item in files):
            raise StorageError("모델 또는 앱 번들을 포함한 검증 복제본은 정리하지 않습니다", "protected")
        return files

    def _archive(self, receipt):
        record = _json(receipt)
        archive, digest = record.get("archive"), record.get("sha256")
        if not isinstance(archive, str) or not isinstance(digest, str) or len(digest) != 64:
            raise StorageError("원본 archive checksum receipt가 올바르지 않습니다", "missing_receipt")
        source = Path(archive)
        if not source.is_absolute() or source.is_symlink() or not self._inside(source.resolve(strict=False)) or not _regular(source) or _digest(source) != digest:
            raise StorageError("원본 archive checksum을 확인할 수 없습니다", "missing_receipt")
        return {"path": str(source), "sha256": digest}

    def _source_not_current(self, marker, candidate):
        if not isinstance(marker, dict): return
        source = marker.get("source")
        if not isinstance(source, str) or not source.startswith("/"): return
        raw = Path(source)
        if raw.exists() and not raw.is_symlink() and raw.resolve() == self.root:
            raise StorageError("현재 소스 작업 폴더를 가리키는 복제본은 정리하지 않습니다", "protected")
        if raw.exists() and raw.resolve() == candidate:
            raise StorageError("자기 자신을 현재 소스로 가리키는 복제본은 정리하지 않습니다", "protected")

    def _proof(self, name, path, marker_path, receipts):
        marker = _json(marker_path) if marker_path.suffix == ".json" else {}
        self._source_not_current(marker, path)
        if name in {"forward-installed", "forward-clean"}:
            install, release = map(_json, receipts)
            target = path / ".agents/skills"
            if install.get("ok") is not True or install.get("result", {}).get("target") != str(target) or install.get("result", {}).get("version") != "0.1.0":
                raise StorageError("설치 상태 receipt가 검증 복제본과 일치하지 않습니다", "missing_receipt")
            archive = self._archive(receipts[1])
            if marker.get("repository") != "roadkwonai/music-road-skills" or marker.get("version") != release.get("version") or marker.get("version") != "0.1.0":
                raise StorageError("설치 표지와 원본 archive 버전이 일치하지 않습니다", "missing_receipt")
            return {"archive": archive}
        if name == "forward-extracted":
            release = _json(receipts[0]); archive = self._archive(receipts[0])
            if marker.get("name") != "music-road-skills" or marker.get("version") != release.get("version") or _json(receipts[1]).get("verdict") not in {"PARTIAL", "PASS"}:
                raise StorageError("릴리스 추출 상태가 원본 archive와 일치하지 않습니다", "missing_receipt")
            return {"archive": archive}
        if name == "cli-e2e":
            report = _json(receipts[0])
            archive = self._path("Output/music-road-skills-publish-20261018/cli-live-release-0.1.1/RoadMusic-CLI-0.1.1.zip")
            checksum = receipts[1].read_text(encoding="utf-8")
            package = _json(marker_path)
            if report.get("version", {}).get("cliVersion") != "0.1.1" or report.get("sourceMusicPreserved") is not True or package.get("name") != "road-music" or not _regular(archive) or f"{_digest(archive)}  {archive.name}" not in checksum:
                raise StorageError("CLI 설치 검증 receipt와 원본 archive가 일치하지 않습니다", "missing_receipt")
            return {"archive": {"path": str(archive), "sha256": _digest(archive)}}
        if name == "cli-installed-skills":
            source = marker.get("source")
            expected = self._path("Output/music-road-skills-publish-20261018/cli-kit-e2e/RoadMusic-CLI-0.1.1/skills/music-road-skills")
            if marker.get("repository") != "roadkwonai/music-road-skills" or marker.get("version") != "0.1.0" or source != str(expected):
                raise StorageError("설치된 스킬의 원본 source receipt가 일치하지 않습니다", "missing_receipt")
            return self._proof("cli-e2e", self._path("Output/music-road-skills-publish-20261018/cli-kit-e2e"), self._path("Output/music-road-skills-publish-20261018/cli-kit-e2e/RoadMusic-CLI-0.1.1/package.json"), [self._path("Output/music-road-skills-publish-20261018/cli-kit-e2e-report.json"), self._path("Output/music-road-skills-publish-20261018/cli-live-release-0.1.1/SHA256SUMS.txt")])
        if name == "live-release-skills":
            install, check = map(_json, receipts)
            verification = self._path("Output/music-road-skills-publish-20261018/release-final-use-time-check/verification.json")
            archive = self._archive(verification)
            if install.get("result", {}).get("target") != str(path) or check.get("result", {}).get("target") != str(path) or marker.get("repository") != "roadkwonai/music-road-skills" or marker.get("version") != "0.1.0":
                raise StorageError("공개 릴리스 설치 상태가 원본 archive와 일치하지 않습니다", "missing_receipt")
            return {"archive": archive}
        if name == "local-cli-kit":
            e2e = _json(receipts[0]); package = _json(marker_path); log = receipts[1].read_text(encoding="utf-8")
            if e2e.get("publicationPerformed") is not False or e2e.get("restoredTestTargetClean") is not True or not isinstance(e2e.get("archiveSha256"), str) or package.get("name") != "road-music" or "RoadMusic-CLI-0.1.2.zip" not in log:
                raise StorageError("로컬 CLI 설치 검증 상태가 안전하지 않습니다", "missing_receipt")
            return {"archive": {"path": "external local test archive", "sha256": e2e["archiveSha256"]}}
        raise StorageError("알 수 없는 검증 복제본 profile입니다", "missing_receipt")

    def _evidence(self, receipts):
        values = []
        for receipt in receipts:
            values.append({"path": str(receipt.relative_to(self.root)), "sha256": _digest(receipt), "snapshot": _snapshot(receipt)})
        return values

    def _candidate(self, profile):
        name, relative, kind, receipt_one, receipt_two, marker = profile
        path = self._path(relative)
        if not path.is_dir() or path.is_symlink() or self.active_check(path):
            raise StorageError("현재 사용 중이거나 안전하지 않은 설치 검증 복제본입니다", "active_or_unsafe")
        marker_path = path / marker
        if not _regular(marker_path):
            raise StorageError("설치 상태 표지가 없습니다", "missing_receipt")
        receipts = [self._path(receipt_one), self._path(receipt_two)]
        if any(not _regular(receipt) for receipt in receipts):
            raise StorageError("설치 검증 receipt가 없습니다", "missing_receipt")
        proof = self._proof(name, path, marker_path, receipts)
        files = self._tree(path)
        snapshots = []
        for item in files:
            snapshot = _snapshot(item)
            snapshot["relativePath"] = str(item.relative_to(self.root))
            snapshots.append(snapshot)
        if not snapshots:
            raise StorageError("빈 설치 검증 복제본은 정리 후보가 아닙니다", "missing_receipt")
        evidence = self._evidence(receipts)
        fingerprint = _id(json.dumps({"files": snapshots, "receipts": evidence, "proof": proof}, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        return {
            "id": _id(name + "\0" + relative), "path": relative, "absolutePath": str(path), "kind": kind,
            "description": "현재 설치·모델·결과물과 분리된 과거 설치 검증 복제본",
            "fileCount": len(snapshots), "bytes": sum(item["bytes"] for item in snapshots),
            "allocatedBytes": sum(_allocated(self.root / item["relativePath"]) for item in snapshots),
            "evidence": {"receipts": evidence, "marker": str(marker_path.relative_to(self.root)), **proof},
            "fingerprint": fingerprint, "files": snapshots,
        }

    def _dmg_candidate(self, relative):
        path = self._path(relative)
        receipt = path.parent / "update-state.json"
        if not _regular(path) or not _regular(receipt) or self.active_check(path.parent.parent.parent):
            raise StorageError("현재 사용 중이거나 안전하지 않은 업데이트 캐시입니다", "active_or_unsafe")
        state = _json(receipt)
        asset = state.get("asset") if isinstance(state, dict) else None
        if not isinstance(asset, dict) or asset.get("sha256") != DMG_SHA256 or asset.get("size") != DMG_BYTES or asset.get("name") != path.name.removesuffix(".download"):
            raise StorageError("업데이트 receipt가 다운로드 캐시와 일치하지 않습니다", "missing_receipt")
        if path.stat().st_size != DMG_BYTES or _digest(path) != DMG_SHA256:
            raise StorageError("업데이트 다운로드 캐시 hash가 일치하지 않습니다", "missing_receipt")
        snapshot = _snapshot(path); snapshot["relativePath"] = str(path.relative_to(self.root))
        evidence = self._evidence([receipt])
        fingerprint = _id(json.dumps({"files": [snapshot], "receipts": evidence}, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        return {"id": _id("dmg\0" + relative), "path": relative, "absolutePath": str(path), "kind": "installer-download-cache",
                "description": "과거 ACE 실험 복제본의 동일한 완료 DMG 다운로드 캐시", "fileCount": 1,
                "bytes": snapshot["bytes"], "allocatedBytes": _allocated(path), "evidence": {"receipts": evidence},
                "fingerprint": fingerprint, "files": [snapshot]}

    def inspect(self):
        candidates, blocked = [], []
        for profile in PROFILES:
            target = self.root / profile[1]
            if not target.exists() and not target.is_symlink(): continue
            try:
                candidates.append(self._candidate(profile))
            except StorageError as error:
                blocked.append({"path": profile[1], "reason": str(error), "code": error.code})
        for root in DMG_ROOTS:
            download = Path(root) / DMG_DOWNLOAD
            target = self.root / download
            if not target.exists() and not target.is_symlink(): continue
            try:
                candidates.append(self._dmg_candidate(str(download)))
            except StorageError as error:
                blocked.append({"path": str(download), "reason": str(error), "code": error.code})
        return {"candidates": candidates, "blocked": blocked}

    def _remove_empty(self, relative):
        path = self.root / relative
        for directory, _, _ in os.walk(path, topdown=False, followlinks=False):
            try:
                # macOS rmdir can silently remove directories containing only unselected AppleDouble files.
                if os.listdir(directory): continue
                os.rmdir(directory)
            except OSError:
                pass

    def cleanup(self, candidateSnapshots):
        if not isinstance(candidateSnapshots, list) or not candidateSnapshots:
            raise StorageError("검증된 정리 후보가 필요합니다")
        current = {item["id"]: item for item in self.inspect()["candidates"]}
        selected = []
        for requested in candidateSnapshots:
            if not isinstance(requested, dict) or requested.get("id") not in current:
                raise StorageError("검증되지 않은 정리 후보입니다", "invalid_plan")
            candidate = current[requested["id"]]
            if requested.get("fingerprint") != candidate["fingerprint"]:
                raise StorageError("정리 계획 뒤 후보가 변경되었습니다", "invalid_plan")
            selected.append(candidate)
        # Re-check every selected plan before any unlink, so a changed/active item cannot cause a partial cleanup.
        for candidate in selected:
            if self.active_check(Path(candidate["absolutePath"])):
                raise StorageError("정리 중 설치 검증 복제본이 사용되기 시작했습니다", "active_or_unsafe")
        removed = freed = allocated = 0
        skipped, warnings = [], []
        for candidate in selected:
            try:
                for item in candidate["files"]:
                    expected = (item["dev"], item["inode"], item["bytes"], item["mtimeNs"])
                    allocated_before = _allocated(self.root / item["relativePath"])
                    StorageManager._unlink_verified(self.root, item["relativePath"], expected)
                    removed += 1; freed += item["bytes"]
                    allocated += allocated_before
                self._remove_empty(candidate["path"])
            except (OSError, StorageError) as error:
                skipped.append({"id": candidate["id"], "path": candidate["path"], "reason": str(error)})
        # allocated blocks are captured before unlink; APFS may reclaim a different physical amount.
        return {"removedFiles": removed, "freedBytes": freed, "freedAllocatedBytes": allocated,
                "skipped": skipped, "warnings": warnings,
                "audit": {"action": "verification-cleanup", "candidateIds": [item["id"] for item in selected]}}
