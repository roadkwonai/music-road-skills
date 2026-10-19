"""Music-source grouped storage overview; listing never grants deletion authority."""
from __future__ import annotations

import os
from pathlib import Path
import re
import unicodedata
import gzip
import json
import time

from storage_manager import MAX_JSON, StorageError, _json_read
from storage_packaging import TRUSTED_ROOT, is_workspace
from storage_scan import WorkspaceScan, _classification, _claim_covers, _private_work
from work_library import WorkLibrary


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SYNTHETIC_MARKERS = ("시험 신호", "test-tone", "qa-tone", "silent-style-preview", "custom-smoke", "full-source", "showreel-input", "storage-live-validation")
METADATA_MARKERS = frozenset({"studio-project.json", "production.json", "native-production.json", "playlist.json", "source-verification.json", "input.json", "source-provenance.json", "final-render-command.json"})
PACKAGE_SUFFIXES = frozenset({".zip", ".dmg", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"})


def _path_key(value):
    """Compare recorded paths without resolving external symlinks."""
    return os.path.normcase(os.path.normpath(value)) if isinstance(value, str) and value else None


def _workspace_relative(root, value):
    """Return a lexical in-workspace path without resolving links outside it."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return str(Path(value).relative_to(root))
    except ValueError:
        return None


def _valid_sha(value):
    return value.lower() if isinstance(value, str) and SHA256.fullmatch(value.lower()) else None


def _source_record(value, title=None):
    if not isinstance(value, dict):
        return None
    digest = value.get("sha256")
    path = value.get("path")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest.lower()) or not isinstance(path, str) or not Path(path).is_absolute():
        return None
    # Track titles frequently describe a cut/review segment; the original filename names the music.
    return {"sourceSha256": digest.lower(), "sourcePath": path, "title": unicodedata.normalize("NFC", Path(path).stem)}


def _synthetic_group(group):
    values = [str(group.get("title") or ""), str(group.get("sourcePath") or "")]
    values.extend(str(row.get("sourcePath") or "") for row in group.get("mvProjects", []))
    source_path = group.get("sourcePath")
    parts = [part.casefold() for part in Path(source_path).parts] if isinstance(source_path, str) else []
    if isinstance(source_path, str) and Path(source_path).stem.casefold() == "music" and "audio" in parts and "music" in parts:
        return "내부 제작·검증 입력음원"
    return "검증·테스트 입력음원" if any(token in value.casefold() for value in values for token in SYNTHETIC_MARKERS) else None


def _sources_from_project(row):
    """Read recorded source identities only; never hash arbitrary media while listing."""
    raw = row.get("path")
    if not isinstance(raw, str) or not raw:
        return []
    project = Path(raw)
    marker = project / "studio-project.json"
    if marker.is_file() and not marker.is_symlink() and marker.stat().st_size <= MAX_JSON:
        try:
            value = _json_read(marker, None)
        except StorageError:
            value = None
        if isinstance(value, dict) and isinstance(value.get("media"), list):
            music = next((item for item in value["media"] if isinstance(item, dict) and item.get("id") == "music" and item.get("kind") == "music"), None)
            record = _source_record(music, value.get("name"))
            if record:
                return [record]
    for marker in ("production.json", "native-production.json"):
        try:
            production = _json_read(project / marker, None)
        except StorageError:
            production = None
        source = production.get("source") if isinstance(production, dict) else None
        if isinstance(source, dict) and source.get("kind") != "playlist-audio":
            record = _source_record(source, production.get("title"))
            if record:
                return [record]
    try:
        playlist = _json_read(project / "playlist.json", None)
    except StorageError:
        playlist = None
    records = []
    if isinstance(playlist, dict) and isinstance(playlist.get("tracks"), list):
        for track in playlist["tracks"]:
            if not isinstance(track, dict):
                continue
            record = _source_record(track.get("source"), track.get("title"))
            if record and all(record["sourceSha256"] != item["sourceSha256"] for item in records):
                records.append(record)
    return records


def _sources_from_metadata(value):
    """Extract only recorded source identities from known producer metadata."""
    records = []

    def add(record):
        if record and all(record["sourceSha256"] != item["sourceSha256"] for item in records):
            records.append(record)

    if not isinstance(value, dict):
        return records
    add(_source_record(value.get("source"), value.get("title") or value.get("name")))
    add(_source_record(value.get("source_audio") or value.get("sourceAudio"), value.get("title") or value.get("name")))
    digest = _valid_sha(value.get("sourceSha256"))
    source_path = value.get("sourcePath") or value.get("sourceAudio")
    if digest and isinstance(source_path, str) and Path(source_path).is_absolute():
        add({"sourceSha256": digest, "sourcePath": source_path, "title": unicodedata.normalize("NFC", Path(source_path).stem)})
    input_digest = _valid_sha(value.get("source_audio_sha256") or value.get("sourceAudioSha256"))
    input_path = value.get("source_audio_path") or value.get("sourceAudioPath")
    if input_digest and isinstance(input_path, str) and Path(input_path).is_absolute():
        add({"sourceSha256": input_digest, "sourcePath": input_path, "title": unicodedata.normalize("NFC", Path(input_path).stem)})
    provenance_path = value.get("userAudio")
    provenance_digest = _valid_sha(value.get("sha256"))
    if provenance_digest and isinstance(provenance_path, str) and Path(provenance_path).is_absolute():
        add({"sourceSha256": provenance_digest, "sourcePath": provenance_path, "title": unicodedata.normalize("NFC", Path(provenance_path).stem)})
    for item in value.get("media", []) if isinstance(value.get("media"), list) else []:
        if isinstance(item, dict) and item.get("id") == "music" and item.get("kind") == "music":
            add(_source_record(item, value.get("name")))
    for item in value.get("tracks", []) if isinstance(value.get("tracks"), list) else []:
        if isinstance(item, dict):
            add(_source_record(item.get("source"), item.get("title")))
    return records


def _jizura_command_audio(value):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    try:
        audio = value[value.index("--audio") + 1]
    except (ValueError, IndexError):
        return None
    return audio if Path(audio).is_absolute() else None


class StorageOverview:
    """Show only known music-source groups and keep unrelated rows separately."""

    def __init__(self, manager, mv_storage_factory=None, workspace_root=None):
        self.manager = manager
        self.mv_storage_factory = mv_storage_factory
        if workspace_root is None and TRUSTED_ROOT is None:
            raise StorageError('현재 설치의 Road Music 작업 폴더를 찾을 수 없습니다.', 'workspace_unavailable')
        self.workspace_root = Path(workspace_root) if workspace_root is not None else Path(TRUSTED_ROOT)

    def _mv_list(self):
        try:
            factory = self.mv_storage_factory
            if factory is None:
                from storage_mv import MVStorage
                factory = MVStorage
            value = factory(self.manager).list({})
            return value if isinstance(value, dict) and isinstance(value.get("projects"), list) else {"projects": [], "blocked": ["AI 영상 프로젝트 목록을 확인할 수 없습니다."]}
        except (ImportError, OSError, ValueError, StorageError) as error:
            return {"projects": [], "blocked": [f"AI 영상 프로젝트 목록을 확인할 수 없습니다: {error}"]}

    def _library_groups(self):
        try:
            library = WorkLibrary(self.manager.data_dir / "video-studio-library.json")
            return {"groups": [library.group(item["groupId"]) for item in library.groups()], "blocked": []}
        except (OSError, ValueError) as error:
            return {"groups": [], "blocked": [f"음악 작업물 보관함을 확인할 수 없습니다: {error}"]}

    @staticmethod
    def _group_sources(groups):
        known, project_to_source = {}, {}
        for group in groups:
            if not isinstance(group, dict):
                continue
            digest = group.get("sourceSha256") or group.get("groupId")
            source = group.get("source")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest.lower()) or not isinstance(source, dict):
                continue
            digest = digest.lower()
            files = []
            for item in [source, *(group.get("files") or []), *(group.get("artifacts") or [])]:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                files.append({key: item.get(key) for key in ("id", "kind", "name", "path", "size", "sha256", "available", "removeDisabled", "protectedReason") if key in item})
            known[digest] = {"groupId": digest, "title": group.get("title") if isinstance(group.get("title"), str) else Path(str(source.get("name") or "음악 작업")).stem,
                             "sourcePath": source.get("path") if isinstance(source.get("path"), str) else None, "files": files}
            candidates = [source, *(source.get("origins") or [])]
            for item in [*(group.get("files") or []), *(group.get("artifacts") or [])]:
                if isinstance(item, dict):
                    candidates.extend([item, *(item.get("origins") or [])])
            for candidate in candidates:
                if isinstance(candidate, dict):
                    key = _path_key(candidate.get("project"))
                    if key and key not in project_to_source:
                        project_to_source[key] = digest
                    elif key and project_to_source[key] != digest:
                        project_to_source[key] = None
        return known, {key: value for key, value in project_to_source.items() if value is not None}

    @staticmethod
    def _claim(claims, path, source, role):
        key = _path_key(path)
        if key and source:
            claims.setdefault(key, {}).setdefault(source, set()).add(role)

    @staticmethod
    def _metadata_root(relative):
        return str(Path(relative).parent)

    @staticmethod
    def _output_owner(relative):
        parts = Path(relative).parts
        return str(Path(parts[0], parts[1])) if len(parts) >= 2 and parts[0].casefold() == "output" else None

    @staticmethod
    def _unattributed_folder(relative):
        parts = Path(relative).parts
        if _private_work(relative):
            return str(Path(*parts[:3]))
        return str(Path(parts[0], parts[1])) if len(parts) >= 2 and parts[0].casefold() == "output" else (parts[0] if parts else ".")

    @staticmethod
    def _under(path, root):
        return path == root or path.startswith(root + os.sep)

    @staticmethod
    def _role(roles):
        order = ("registered-project", "ai-mv-project", "library-project", "producer-metadata")
        return next((role for role in order if role in roles), "producer-metadata")

    def _workspace_usage(self, grouped, library_groups, listed, mv, *, refresh_workspace=False):
        """Attribute a cached or explicitly refreshed workspace snapshot once."""
        root = self.workspace_root
        if self.manager.data_dir.is_relative_to(root.resolve()):
            return {"available": False, "workspace": str(root), "allocatedBytes": 0, "fileCount": 0,
                    "unattributedBytes": 0, "systemBytes": 0, "groupBytes": 0, "testInputBytes": 0,
                    "scanId": None, "scanCreatedAt": None, "scanExpiresAt": None, "cacheState": "scan-skipped-profile-inside-workspace",
                    "categories": [], "unattributedCategories": [], "unattributedFolders": [],
                    "warning": "현재 프로필이 작업 폴더 안에 있어 전체 스캔을 생략합니다. 등록된 프로젝트의 관리·정리 정보만 표시합니다."}
        try:
            if TRUSTED_ROOT is not None and root.resolve() == Path(TRUSTED_ROOT).resolve() and not is_workspace(root):
                raise StorageError("현재 신뢰할 수 있는 Road Music 작업 폴더만 스캔할 수 있습니다.", "maintenance_unavailable")
            scanner = WorkspaceScan(root, self.manager.data_dir)
            refresh_failed = False
            warning = None
            if refresh_workspace:
                fresh = scanner.scan()
                if fresh.get("complete"):
                    scan = fresh
                else:
                    scan = scanner.cached()
                    refresh_failed = True
                    warning = "새 작업 폴더 스캔이 완료되지 않았습니다. 이전 완결 스캔을 표시하며 정리 계획에는 사용할 수 없습니다."
            else:
                scan = scanner.cached()
        except StorageError as error:
            return {"available": False, "workspace": str(root), "allocatedBytes": 0, "fileCount": 0,
                    "unattributedBytes": 0, "systemBytes": 0, "groupBytes": 0, "testInputBytes": 0,
                    "scanId": None, "scanCreatedAt": None, "scanExpiresAt": None, "cacheState": "scan-unavailable",
                    "categories": [], "unattributedCategories": [], "unattributedFolders": [], "warning": str(error)}
        if scan is None:
            return {"available": False, "workspace": str(root), "allocatedBytes": 0, "fileCount": 0,
                    "unattributedBytes": 0, "systemBytes": 0, "groupBytes": 0, "testInputBytes": 0,
                    "scanId": None, "scanCreatedAt": None, "scanExpiresAt": None, "cacheState": "refresh-incomplete-no-cache" if refresh_workspace else "scan-required",
                    "categories": [], "unattributedCategories": [], "unattributedFolders": [],
                    **({"warning": warning} if warning else {})}

        direct, roots, managed = {}, {}, {}

        def ensure(source, title=None, source_path=None):
            if source not in grouped:
                grouped[source] = {"groupId": source, "title": title or Path(str(source_path or "음악 작업")).stem,
                                   "sourcePath": source_path, "files": [], "projects": [], "mvProjects": [],
                                   "totalBytes": 0, "reclaimableBytes": 0}

        def direct_claim(path, source):
            relative = _workspace_relative(root, path)
            if relative is not None:
                self._claim(direct, relative, source, "file")

        def root_claim(path, source, role, *, managed_cache=False):
            relative = _workspace_relative(root, path)
            if relative is None or relative in {"", "."}:
                return
            target = managed if managed_cache else roots
            self._claim(target, relative, source, role)

        for group in library_groups:
            if not isinstance(group, dict):
                continue
            source = _valid_sha(group.get("sourceSha256") or group.get("groupId"))
            if not source:
                continue
            source_item = group.get("source") if isinstance(group.get("source"), dict) else {}
            ensure(source, group.get("title"), source_item.get("path"))
            for item in [source_item, *(source_item.get("origins") or []), *(group.get("files") or []), *(group.get("artifacts") or [])]:
                if not isinstance(item, dict):
                    continue
                direct_claim(item.get("path"), source)
                root_claim(item.get("project"), source, "library-project")
                for origin in item.get("origins") or []:
                    if isinstance(origin, dict):
                        direct_claim(origin.get("path"), source)
                        root_claim(origin.get("project"), source, "library-project")

        for row in listed.get("projects", []):
            if not isinstance(row, dict):
                continue
            identities = _sources_from_project(row)
            for identity in identities:
                source = identity["sourceSha256"]
                ensure(source, identity.get("title"), identity.get("sourcePath"))
                direct_claim(identity.get("sourcePath"), source)
                if row.get("origin") != "road-music-workspace":
                    root_claim(row.get("path"), source, "registered-project")
                    root_claim(str(Path(row["path"]) / ".roadmusic") if isinstance(row.get("path"), str) else None, source, "registered-project", managed_cache=True)

        for row in mv.get("projects", []):
            source = _valid_sha(row.get("sourceSha256")) if isinstance(row, dict) else None
            if not source:
                continue
            ensure(source, row.get("title"), row.get("sourcePath"))
            direct_claim(row.get("sourcePath"), source)
            root_claim(row.get("path"), source, "ai-mv-project")

        records = [record for record in scanner.cached_records() if record["type"] == "file"]
        metadata = scanner.cached_metadata()
        jizura_commands, metadata_owners = {}, {}
        for relative, value in metadata.items():
            if Path(relative).name == "final-render-command.json":
                audio = _jizura_command_audio(value)
                if audio:
                    jizura_commands[self._metadata_root(relative)] = audio
        ownership = self.manager.management_db.paths(workspace=str(root))
        for claim in ownership:
            source = _valid_sha(claim.get("groupId"))
            if source:
                ensure(source)
                root_claim(claim["path"], source, "registered-project")
        system_claims = [item for item in ownership if not item.get("groupId") and item.get("role") in {"managed", "tooling", "program", "git", "model", "road-music-management", "review-tooling", "orchestration-tooling", "workspace-tooling", "producer-work", "project"}]

        for relative, value in metadata.items():
            if Path(relative).name == "final-render-command.json":
                continue
            if Path(relative).name == "source-provenance.json":
                audio = value.get("userAudio") if isinstance(value, dict) else None
                if jizura_commands.get(self._metadata_root(relative)) != audio:
                    continue
            for identity in _sources_from_metadata(value):
                source = identity["sourceSha256"]
                ensure(source, identity.get("title"), identity.get("sourcePath"))
                direct_claim(identity.get("sourcePath"), source)
                root_claim(str(root / self._metadata_root(relative)), source, "producer-metadata")
                owner = self._output_owner(relative)
                if owner:
                    metadata_owners.setdefault(_path_key(owner), set()).add(source)

        # A top-level output may hold many songs. Only widen a metadata claim to
        # its owner when every recorded producer under that owner has one source.
        for owner, sources in metadata_owners.items():
            if len(sources) == 1:
                root_claim(str(root / owner), next(iter(sources)), "producer-metadata")
            else:
                roots.pop(owner, None)

        per_inode = {}
        for record in records:
            inode = (record.get("dev"), record.get("inode"))
            if not all(isinstance(value, int) for value in inode):
                continue
            per_inode.setdefault(inode, []).append(record)
        root_keys = sorted(roots, key=lambda value: (len(Path(value).parts), value), reverse=True)
        managed_keys = sorted(managed, key=lambda value: (len(Path(value).parts), value), reverse=True)
        group_stats, producer_stats = {}, {}
        system, unattributed = {}, {}
        unattributed_folders = {}
        group_bytes = group_files = system_bytes = unattributed_bytes = 0
        for inode_records in per_inode.values():
            allocated = max(int(item.get("allocatedBytes") or 0) for item in inode_records)
            candidates, owners, is_managed = set(), [], False
            direct_matches = []
            for record in inode_records:
                path = _path_key(record["relativePath"])
                exact = direct.get(path, {})
                if exact:
                    for source in exact:
                        candidates.add(source)
                        direct_matches.append((path, source))
                else:
                    matches = [key for key in root_keys if _claim_covers(root, root / path, {"path": str(root / key), "kind": "directory"})]
                    if matches:
                        depth = max(len(Path(key).parts) for key in matches)
                        for key in (key for key in matches if len(Path(key).parts) == depth):
                            for source, roles in roots[key].items():
                                candidates.add(source)
                                owners.append((key, source, roles))
                for key in managed_keys:
                    if self._under(path, key):
                        is_managed = True
            source = next(iter(candidates)) if len(candidates) == 1 else None
            if source:
                stats = group_stats.setdefault(source, {"bytes": 0, "fileCount": 0, "managedBytes": 0, "ambiguousBytes": 0})
                stats["bytes"] += allocated; stats["fileCount"] += 1
                if is_managed: stats["managedBytes"] += allocated
                own = [item for item in owners if item[1] == source]
                if own:
                    key, _source, roles = sorted(own, key=lambda item: (len(Path(item[0]).parts), item[0]), reverse=True)[0]
                    entry = producer_stats.setdefault((source, key), {"path": str(root / key), "bytes": 0, "fileCount": 0, "role": self._role(roles)})
                    entry["bytes"] += allocated; entry["fileCount"] += 1
                else:
                    path = sorted(path for path, owner in direct_matches if owner == source)[0]
                    entry = producer_stats.setdefault((source, path), {"path": str(root / path), "bytes": 0, "fileCount": 0, "role": "recorded-file"})
                    entry["bytes"] += allocated; entry["fileCount"] += 1
                group_bytes += allocated; group_files += 1
                continue
            relative = inode_records[0]["relativePath"]
            suffix = Path(relative).suffix.casefold()
            classified, label, _reason = _classification(relative)
            owned = next((claim for record in inode_records for claim in system_claims if _claim_covers(root, root / record["relativePath"], claim)), None)
            kind = "package" if suffix in PACKAGE_SUFFIXES and not _private_work(relative) else classified
            if owned and owned["role"] in {"producer-work", "project"}:
                kind, label = "pending-production", "음악 연결 대기 작업"
            target = system if kind in {"model", "program", "git", "package"} or owned else unattributed
            entry = target.setdefault(kind, {"kind": kind, "label": label if kind != "package" else "압축·설치 파일", "allocatedBytes": 0, "fileCount": 0})
            entry["allocatedBytes"] += allocated; entry["fileCount"] += 1
            if target is system: system_bytes += allocated
            else:
                unattributed_bytes += allocated
                folder = self._unattributed_folder(min(item["relativePath"] for item in inode_records))
                folder_entry = unattributed_folders.setdefault(folder, {"path": folder, "allocatedBytes": 0, "fileCount": 0})
                folder_entry["allocatedBytes"] += allocated; folder_entry["fileCount"] += 1

        for source, group in grouped.items():
            stats = group_stats.get(source, {"bytes": 0, "fileCount": 0, "managedBytes": 0, "ambiguousBytes": 0})
            group["workspaceBytes"] = stats["bytes"]
            group["workspaceFileCount"] = stats["fileCount"]
            group["managedWorkspaceBytes"] = stats["managedBytes"]
            group["unmanagedBytes"] = max(0, stats["bytes"] - stats["managedBytes"])
            group["ambiguousWorkspaceBytes"] = stats["ambiguousBytes"]
            group["producerProjects"] = sorted((value for (owner, _key), value in producer_stats.items() if owner == source), key=lambda value: (-value["bytes"], value["path"]))

        return {"available": not refresh_failed, "workspace": str(root), "allocatedBytes": scan["totals"]["allocatedBytes"],
                "fileCount": scan["totals"]["uniqueFileCount"], "unattributedBytes": unattributed_bytes,
                "systemBytes": system_bytes, "groupBytes": group_bytes, "testInputBytes": 0,
                "scanId": scan["scanId"], "scanCreatedAt": scan["createdAt"], "scanExpiresAt": scan["expiresAt"],
                "cacheState": "refresh-incomplete-cache" if refresh_failed else ("refreshed" if refresh_workspace else ("expired-cache" if scan["expiresAt"] <= int(time.time()) else "cached")),
                "categories": sorted(system.values(), key=lambda value: (-value["allocatedBytes"], value["kind"])),
                "unattributedCategories": sorted(unattributed.values(), key=lambda value: (-value["allocatedBytes"], value["kind"])),
                "unattributedFolders": sorted(unattributed_folders.values(), key=lambda value: (-value["allocatedBytes"], value["path"]))[:20],
                **({"warning": warning} if warning else {})}

    def list(self, params):
        if not isinstance(params, dict) or set(params) - {"refreshWorkspace"} or "refreshWorkspace" in params and type(params["refreshWorkspace"]) is not bool:
            raise StorageError("음악별 저장공간 목록은 refreshWorkspace 여부만 받을 수 있습니다.")
        listed = self.manager.list({})
        library = self._library_groups()
        known, paths = self._group_sources(library["groups"])
        grouped = {digest: {**value, "projects": [], "mvProjects": [], "totalBytes": 0, "reclaimableBytes": 0} for digest, value in known.items()}
        other = []
        for row in listed.get("projects", []):
            identities = []
            source = paths.get(_path_key(row.get("path")))
            if source:
                identities.append({"sourceSha256": source})
            else:
                identities = _sources_from_project(row)
            identities = [item for item in identities if isinstance(item, dict) and isinstance(item.get("sourceSha256"), str)]
            if not identities:
                if row.get("origin") == "road-music-workspace":
                    continue
                other.append({"kind": "project", **row})
                continue
            for identity in identities:
                source = identity["sourceSha256"]
                if source not in grouped:
                    grouped[source] = {"groupId": source, "title": identity.get("title") or Path(str(identity.get("sourcePath") or row.get("name") or "음악 작업")).stem,
                                       "sourcePath": identity.get("sourcePath"), "files": [], "projects": [], "mvProjects": [], "totalBytes": 0, "reclaimableBytes": 0}
                grouped[source]["projects"].append(row)
                grouped[source]["totalBytes"] += row.get("totalBytes", 0)
                grouped[source]["reclaimableBytes"] += row.get("reclaimableBytes", 0)
        mv = self._mv_list()
        for row in mv.get("projects", []):
            source = row.get("sourceSha256")
            source = source.lower() if isinstance(source, str) and SHA256.fullmatch(source.lower()) else None
            if source not in grouped:
                source_path = row.get("sourcePath")
                if source and isinstance(source_path, str) and Path(source_path).is_absolute():
                    grouped[source] = {"groupId": source, "title": row.get("title") if isinstance(row.get("title"), str) and row["title"].strip() else Path(source_path).stem,
                                       "sourcePath": source_path, "files": [], "projects": [], "mvProjects": [], "totalBytes": 0, "reclaimableBytes": 0}
                else:
                    other.append({"kind": "ai-mv", **row})
                    continue
            grouped[source]["mvProjects"].append(row)
            grouped[source]["totalBytes"] += row.get("allocatedBytes", row.get("bytes", 0))
            grouped[source]["reclaimableBytes"] += row.get("reclaimableBytes", 0)
        workspace = self._workspace_usage(grouped, library["groups"], listed, mv, refresh_workspace=params.get("refreshWorkspace", False))
        for group in grouped.values():
            group.setdefault("workspaceBytes", 0)
            group.setdefault("workspaceFileCount", 0)
            group.setdefault("managedWorkspaceBytes", 0)
            group.setdefault("unmanagedBytes", 0)
            group.setdefault("ambiguousWorkspaceBytes", 0)
            group.setdefault("producerProjects", [])
            group.setdefault("files", [])
        groups, synthetic = [], []
        for group in grouped.values():
            if not (group["projects"] or group["mvProjects"] or group["workspaceBytes"]):
                continue
            reason = _synthetic_group(group)
            if reason:
                for row in [*group["projects"], *group["mvProjects"]]:
                    synthetic.append({"kind": "synthetic-input", "reason": reason, "workspaceBytes": group["workspaceBytes"],
                                      "workspaceFileCount": group["workspaceFileCount"], **row})
            else:
                groups.append(group)
        other.extend(synthetic)
        groups.sort(key=lambda item: (item["title"].casefold(), item["groupId"]))
        if workspace.get("available"):
            visible_bytes = sum(group["workspaceBytes"] for group in groups)
            synthetic_bytes = sum({group["groupId"]: group["workspaceBytes"] for group in grouped.values() if _synthetic_group(group)}.values())
            workspace["groupBytes"] = visible_bytes
            workspace["testInputBytes"] = synthetic_bytes
            workspace["unattributedBytes"] += max(0, workspace["allocatedBytes"] - visible_bytes - synthetic_bytes - workspace["systemBytes"] - workspace["unattributedBytes"])
            workspace["accountedBytes"] = visible_bytes + synthetic_bytes + workspace["systemBytes"] + workspace["unattributedBytes"]
        # A playlist project can deliberately appear under more than one song, so
        # global totals use each registered row once rather than summed group cards.
        total = listed.get("totals", {}).get("totalBytes", 0)
        reclaimable = listed.get("totals", {}).get("reclaimableBytes", 0)
        seen_mv = set()
        for row in mv.get("projects", []):
            marker = row.get("id")
            if marker in seen_mv:
                continue
            seen_mv.add(marker)
            total += row.get("allocatedBytes", row.get("bytes", 0))
            reclaimable += row.get("reclaimableBytes", 0)
        return {"groups": groups, "otherProjects": other, "disk": listed.get("disk", {}), "overall": {"workspace": workspace},
                "totals": {"totalBytes": total, "reclaimableBytes": reclaimable, "groupCount": len(groups), "otherProjectCount": len(other),
                           "workspaceAllocatedBytes": workspace.get("allocatedBytes", 0)},
                "blocked": [*library.get("blocked", []), *mv.get("blocked", [])],
                "note": "음악 원음 SHA-256 또는 제작 메타데이터가 확인된 파일만 음악별 그룹에 귀속합니다. 캐시 스캔 값은 생성 시각을 함께 표시하며, 미연결·모호한 파일은 별도 항목으로 남겨 삭제 권한을 만들지 않습니다."}
