"""Fail-closed discovery for two historic local package-verification ZIPs only."""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path
from storage_manager import MAX_JSON, StorageError, _id, _snapshot

TRUSTED_ROOT = None
PLAYLIST_SHA256 = "95094e36f66ebb9e8e7392ce2af4fcb301faf12f1293d9f2feccd6c705dda80b"
TOMORROW_SHA256 = "fa473c28dbe747194b48d8d0e3921b580af49ff9449d96f3fba39051d3787ff8"
ARCHIVE_NAME = re.compile(r"MusicRoad-Skills-\d+\.\d+\.\d+\.zip\Z")

def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()

def _regular(path):
    try: return path.is_file() and not path.is_symlink()
    except OSError: return False

def _json(path):
    if not _regular(path) or path.stat().st_size > MAX_JSON: raise StorageError("패키지 receipt가 안전하지 않습니다", "unsafe_receipt")
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise StorageError("패키지 receipt를 읽을 수 없습니다", "unsafe_receipt") from error
    if not isinstance(value, dict): raise StorageError("패키지 receipt 형식이 올바르지 않습니다", "unsafe_receipt")
    return value

def _json_value(path):
    if not _regular(path) or path.stat().st_size > MAX_JSON: raise StorageError("공개 receipt가 안전하지 않습니다", "unsafe_receipt")
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise StorageError("공개 receipt를 읽을 수 없습니다", "unsafe_receipt") from error

def _closed(path):
    """True means lsof confirmed that this exact regular file is not open."""
    try:
        result = subprocess.run(["lsof", "-t", "--", str(path)], capture_output=True, text=True, timeout=3, check=False)
        return result.returncode in {0, 1} and not result.stdout.strip()
    except (OSError, subprocess.SubprocessError): return False

def _raw_under(root, raw):
    if not raw.is_absolute() or raw.is_symlink(): return None
    try: relative = raw.relative_to(root)
    except ValueError: return None
    current = root
    try:
        for part in relative.parts:
            current /= part
            if current.is_symlink(): return None
        resolved = raw.resolve(strict=True)
    except OSError: return None
    return resolved if resolved == raw else None

def delivery_workspace(value):
    """Accept only a completed, final-only workspace; never follow an alias."""
    if not isinstance(value, str) or not value:
        return None
    root = Path(value)
    try:
        if not root.is_absolute() or root.is_symlink() or root.resolve(strict=True) != root:
            return None
        for relative in ("package.json", "cli/road-music.js", "AGENTS.md", ".roadmusic/structure.json", "Output"):
            if _raw_under(root, root / relative) is None:
                return None
        if not (root / "Output").is_dir() or not all(_regular(root / name) for name in ("package.json", "cli/road-music.js", "AGENTS.md", ".roadmusic/structure.json")):
            return None
        metadata, structure = _json(root / "package.json"), _json(root / ".roadmusic/structure.json")
        if (metadata.get("name") == "road-music" and metadata.get("bin", {}).get("road-music") == "cli/road-music.js" and
                structure.get("schemaVersion") == 1 and structure.get("owner") == "road-music" and
                structure.get("policy") == "final-only" and structure.get("phase") == "completed" and
                structure.get("workspace") == str(root) and isinstance(structure.get("planId"), str) and
                re.fullmatch(r"[0-9a-f]{48}", structure["planId"])):
            return root
    except (OSError, ValueError, TypeError, AttributeError, StorageError):
        pass
    return None


def discover_trusted_root(module_file=__file__, env=None):
    """Keep a configured workspace separate from the installed program kit."""
    environment = os.environ if env is None else env
    if environment.get('ROADMUSIC_DELIVERY_ROOT'):
        return delivery_workspace(environment['ROADMUSIC_DELIVERY_ROOT'])
    profile = environment.get('ROADMUSIC_DATA_DIR')
    if profile:
        try:
            raw = Path(profile)
            if not raw.is_absolute() or raw.is_symlink():
                return None
            settings = raw.resolve() / 'settings.json'
            if settings.exists():
                value = _json(settings)
                if value.get('deliveryRoot'):
                    return delivery_workspace(value['deliveryRoot'])
        except (OSError, ValueError, StorageError):
            return None
    source = Path(module_file).resolve()
    hint = environment.get('ROADMUSIC_CLI_ROOT')
    roots = (Path(hint),) if hint else (source.parent, *source.parents)
    for root in roots:
        try:
            if not root.is_absolute() or root.is_symlink() or root.resolve() != root:
                continue
            package, cli, agents = root / "package.json", root / "cli" / "road-music.js", root / "AGENTS.md"
            if _raw_under(root, package) is None or _raw_under(root, cli) is None or _raw_under(root, agents) is None:
                continue
            metadata = _json(package)
            if metadata.get("name") == "road-music" and isinstance(metadata.get("bin"), dict) and metadata["bin"].get("road-music") == "cli/road-music.js":
                return root
        except (OSError, StorageError):
            continue
    return None

def git_available(root):
    """Git is an optional capability; storage safety never requires a repository."""
    git = Path(root) / ".git"
    return git.exists() and not git.is_symlink()

def is_workspace(root):
    root = Path(root)
    if TRUSTED_ROOT is None or root.is_symlink() or root.resolve() != TRUSTED_ROOT.resolve() or _raw_under(root, root / "package.json") is None: return False
    try: package = _json(root / "package.json")
    except StorageError: return False
    return (package.get("name") == "road-music" and isinstance(package.get("bin"), dict) and package["bin"].get("road-music") == "cli/road-music.js" and
            _regular(root / "cli/road-music.js") and _regular(root / "AGENTS.md") and
            _raw_under(root, root / "cli" / "road-music.js") is not None and _raw_under(root, root / "AGENTS.md") is not None)

TRUSTED_ROOT = discover_trusted_root()

class PackagingStorage:
    def __init__(self, root, open_check=None): self.root, self.open_check = Path(root), open_check or _closed

    def _published(self):
        paths = [self.root / "Output/skills-release-review-20261018/published-release.json", self.root / "Output/skills-release-review-20261018/github-releases.json"]
        try:
            if any(_raw_under(self.root, path) is None for path in paths): return None
            stack = [_json_value(path) for path in paths]
            self.publisher_proofs = {str(path.relative_to(self.root)): _sha256(path) for path in paths}
        except (StorageError, OSError): return None
        digests = set()
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                digest = item.get("digest")
                if isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest): digests.add(digest[7:])
                stack.extend(item.values())
            elif isinstance(item, list): stack.extend(item)
        return digests or None

    def _profiles(self):
        # shortcut: only these historical receipts are trusted; add future build producers after auditing their receipts.
        output = self.root / "Output"
        if not output.is_dir() or output.is_symlink(): return
        yield output / "showreel-playlist-rebuild-20261018/package-check/MusicRoad-Skills-0.1.1.zip", output / "showreel-playlist-rebuild-20261018/package-audit.json", output / "showreel-playlist-rebuild-20261018/validation.json", PLAYLIST_SHA256, "playlist"
        yield output / "showreel-tomorrow-full-rebuild-20261018/package-check-v2/MusicRoad-Skills-0.1.1.zip", output / "showreel-tomorrow-full-rebuild-20261018/qa/package-audit.json", output / "showreel-tomorrow-full-rebuild-20261018/qa/delivery-audit.json", TOMORROW_SHA256, "tomorrow"

    def _verify(self, archive, receipt, corroboration, digest, kind, published):
        output = self.root / "Output"
        if digest in published or _raw_under(self.root, archive) is None or not ARCHIVE_NAME.fullmatch(archive.name): return None
        if any(part.casefold() in {"runtime", "node_modules", "models", "model", "engines", "engine"} or part.casefold().endswith(".app") for part in archive.relative_to(output).parts): return None
        try:
            checksum = archive.parent / "SHA256SUMS.txt"
            if any(_raw_under(self.root, path) is None for path in (receipt, corroboration, checksum)): return None
            data, extra = _json(receipt), _json(corroboration)
            declared = data.get("sha256") if kind == "playlist" else data.get("archiveSha256")
            if _raw_under(self.root, Path(data.get("archive", ""))) != archive or declared != digest: return None
            valid = (data.get("purpose") == "local verification only; not published" and extra.get("status") == "complete-local-not-published") if kind == "playlist" else (data.get("pass") is True and data.get("finalized") is True and data.get("published") is False and extra.get("published") is False)
            before = _snapshot(archive)
            if archive.stat(follow_symlinks=False).st_mode & 0o111: return None
            if not valid or not _regular(checksum) or f"{digest}  {archive.name}" not in checksum.read_text(encoding="utf-8") or _sha256(archive) != digest or not self.open_check(archive): return None
            with zipfile.ZipFile(archive) as content:
                if content.testzip() is not None: return None
            after = _snapshot(archive)
            if any(before[key] != after[key] for key in ("dev", "inode", "bytes", "mtimeNs")): return None
            return {"receipts": {str(path.relative_to(self.root)): _sha256(path) for path in (receipt, corroboration, checksum)}, "snapshot": after}
        except (OSError, ValueError, StorageError, zipfile.BadZipFile): return None

    def sources(self):
        if not is_workspace(self.root): raise StorageError("현재 trusted Road Music workspace가 필요합니다", "invalid_workspace")
        published = self._published()
        if published is None: return []
        found = []
        for archive, receipt, corroboration, digest, kind in self._profiles() or ():
            proof = self._verify(archive, receipt, corroboration, digest, kind, published)
            if proof is not None: found.append((archive, receipt, corroboration, digest, kind, proof))
        return found

    def candidate(self, project_id, source, open_check=None):
        raw = Path(source)
        if _raw_under(self.root, raw) is None: raise StorageError("안전한 workspace ZIP 경로가 필요합니다", "unsafe_path")
        for archive, receipt, corroboration, digest, kind, proof in self.sources():
            if archive != raw: continue
            if open_check is not None and not open_check(archive): raise StorageError("열린 ZIP은 채택할 수 없습니다", "busy")
            snapshot = proof["snapshot"].copy(); relative = str(archive.relative_to(self.root)); snapshot.update({"relativePath": relative, "leafPath": archive.name})
            evidence = {"receipts": proof["receipts"], "publishers": self.publisher_proofs, "sha256": digest, "classification": "local-verification", "kind": kind}
            identity = "\0".join([project_id, relative, digest, str(snapshot["dev"]), str(snapshot["inode"]), str(snapshot["bytes"]), str(snapshot["mtimeNs"]), json.dumps(evidence, sort_keys=True)])
            return {"id": _id(identity), "projectId": project_id, "relativePath": relative, "files": [snapshot], "description": "로컬 패키지 검증 ZIP", "evidence": evidence, "bytes": snapshot["bytes"], "fileCount": 1, "origin": "packaging-verification", "usageScope": "managed-cache"}
        raise StorageError("채택 가능한 local verification ZIP이 아닙니다", "not_local_verification")
