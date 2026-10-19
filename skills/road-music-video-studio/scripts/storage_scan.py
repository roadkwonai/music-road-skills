"""Metadata-only, fail-closed snapshots of a Road Music workspace."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time

from management_db import ManagementDB, ManagementDBError
from storage_manager import MAX_JSON, PLAN_TTL, StorageError, _atomic_json, _id, _iso, _json_read


MAX_ENTRIES = 2_000_000
MAX_PUBLIC_ROWS = 100
MAX_EXTERNAL_LINKS = 100
SOURCE_METADATA_MARKERS = frozenset({"studio-project.json", "production.json", "native-production.json", "playlist.json", "source-verification.json", "input.json", "source-provenance.json", "final-render-command.json"})


def _allocated(info):
    return int(getattr(info, 'st_blocks', 0)) * 512


def _private_work(relative):
    return Path(relative).parts[:2] == (".roadmusic", "work")


def _claim_covers(root, path, claim):
    path, owned = Path(path), Path(claim["path"])
    if path != owned and (claim.get("kind") == "file" or owned not in path.parents):
        return False
    work = Path(root) / ".roadmusic/work"
    # The private work namespace requires an owner below its root, never inherited management ownership.
    if path.is_relative_to(work) and (owned == work or not owned.is_relative_to(work)):
        return False
    return True


def _classification(relative):
    """Return a conservative label. Every class remains protected at scan time."""
    parts = [part.casefold() for part in Path(relative).parts]
    if not parts:
        return 'workspace', '작업 폴더', '작업 폴더 전체는 스캔만 합니다'
    first = parts[0]
    if first == '.git': return 'git', 'Git 이력·객체', 'Git refs·이력은 별도 검증 전 보존합니다'
    if first in {'.harness', '.omx', '.omc', '_workspace'}: return 'tooling', '관리·검수 도구 영역', '도구의 상태·검수 이력은 보존합니다'
    if _private_work(relative): return 'unclassified', '소유권 미확인 제작 작업', '명시된 프로젝트·제작 소유권이 없어 보호합니다'
    if first == '.roadmusic': return 'managed', 'Road Music 관리 자료', '공개 저장공간 정책으로만 처리합니다'
    if first in {'models', 'model', 'engines', 'engine'} or any(part in {'models', 'model'} for part in parts):
        return 'model', '현재 모델·엔진', '현재 모델과 엔진은 보존합니다'
    if first in {'node_modules', 'cli', 'app', 'runtime', 'dist', '.agents', '.codex', 'electron', 'renderer', 'python', 'scripts', 'assets', 'build', 'docs', 'tests', 'skills', 'prompts', '.impeccable', 'releases', 'package.json', 'package-lock.json', 'readme.md', 'agents.md', 'design.md', 'claude.md', 'license', '.github', '.gitignore'} or any(part.endswith('.app') for part in parts):
        return 'program', '현재 프로그램·런타임', '현재 프로그램은 보존합니다'
    if any(part in {'final', 'finals', 'published', 'publish', 'delivery', 'deliveries', 'works'} for part in parts):
        return 'final', '음악·영상 최종 결과물', '최종 결과물은 보존합니다'
    if any(part in {'history', 'audit', 'qa', 'review', 'approval', 'approvals', 'preproduction'} for part in parts):
        return 'history', '제작·검수 이력', '필요 이력은 보존합니다'
    if any(part in {'cache', '.cache', 'tmp', 'temp'} for part in parts):
        return 'cache-candidate', '재생성 가능성 점검 대상', '재생성 가능 여부가 검증되기 전에는 보존합니다'
    if first == 'output': return 'output', '제작 출력·실험 자료', '참조·납품 상태를 확인하기 전에는 보존합니다'
    return 'unclassified', '미분류 작업 자료', '용도가 확인되지 않아 보존합니다'


def _ownership_metadata(value):
    """Cache only source identity fields; producer documents and frame lists stay on disk."""
    if isinstance(value, list):
        try:
            audio = value[value.index("--audio") + 1]
        except (ValueError, IndexError):
            return []
        return ["--audio", audio] if isinstance(audio, str) else []
    if not isinstance(value, dict):
        return {}
    fields = {"source", "source_audio", "sourceAudio", "sourceSha256", "sourcePath", "source_audio_sha256", "sourceAudioSha256", "source_audio_path", "sourceAudioPath", "userAudio", "sha256", "title", "name"}
    result = {key: item for key, item in value.items() if key in fields}
    def source(item):
        return {key: entry for key, entry in item.items() if key in {"id", "kind", "sha256", "path", "name"}} if isinstance(item, dict) else item
    for key in ("source", "source_audio", "sourceAudio"):
        if key in result:
            result[key] = source(result[key])
    if isinstance(value.get("media"), list):
        result["media"] = [source(item) for item in value["media"] if isinstance(item, dict) and item.get("id") == "music"]
    if isinstance(value.get("tracks"), list):
        result["tracks"] = [{"title": item.get("title"), "source": source(item.get("source"))} for item in value["tracks"] if isinstance(item, dict)]
    return result


class WorkspaceScan:
    """A bounded snapshot; it never classifies a file as immediately deletable."""

    def __init__(self, root, data_dir):
        raw_root = Path(root)
        raw_data = Path(data_dir)
        if not raw_root.is_absolute() or raw_root.is_symlink():
            raise StorageError('symlink가 아닌 작업 폴더 절대 경로가 필요합니다.', 'unsafe_path')
        if not raw_data.is_absolute() or (raw_data.exists() and raw_data.is_symlink()):
            raise StorageError('symlink가 아닌 앱 데이터 절대 경로가 필요합니다.', 'unsafe_path')
        try:
            self.root = raw_root.resolve(strict=True)
        except OSError as error:
            raise StorageError('작업 폴더를 찾을 수 없습니다.', 'not_found') from error
        if not self.root.is_dir():
            raise StorageError('작업 폴더가 필요합니다.', 'unsafe_path')
        self.data_dir = raw_data.resolve()
        if self.data_dir == self.root or self.root in self.data_dir.parents:
            raise StorageError('스캔 저장소는 작업 폴더 밖에 있어야 합니다.', 'unsafe_path')
        self.scan_dir = self.data_dir / 'storage-maintenance-scans'

    def _directory(self):
        for path in (self.data_dir, self.scan_dir):
            current = Path(path.anchor)
            for part in path.parts[1:]:
                current /= part
                try:
                    info = os.lstat(current)
                except FileNotFoundError:
                    try:
                        os.mkdir(current, 0o700)
                    except FileExistsError:
                        info = os.lstat(current)
                    else:
                        info = os.lstat(current)
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or current.resolve(strict=True) != current:
                    raise StorageError('스캔 저장소 경로가 안전하지 않습니다.', 'unsafe_path')

    @staticmethod
    def _record(relative, info, kind='file', target=None):
        value = {'relativePath': relative, 'path': relative, 'dev': info.st_dev, 'inode': info.st_ino,
                 'size': info.st_size, 'mtimeNs': info.st_mtime_ns, 'ctimeNs': info.st_ctime_ns,
                 'nlink': info.st_nlink, 'allocatedBytes': _allocated(info), 'type': kind}
        if target is not None: value['target'] = target
        return value

    def _paths(self, scan_id):
        if not isinstance(scan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', scan_id):
            raise StorageError('스캔 ID가 올바르지 않습니다.', 'invalid_scan')
        return self.scan_dir / f'{scan_id}.json', self.scan_dir / f'{scan_id}.jsonl.gz'

    @staticmethod
    def _inside(root, path):
        return path == root or root in path.parents

    def _external_link(self, path, target):
        try:
            resolved = (path.parent / target).resolve(strict=False)
        except OSError:
            return True
        return not self._inside(self.root, resolved)

    @staticmethod
    def _digest(path):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _snapshot(path):
        info = path.stat(follow_symlinks=False)
        return {'dev': info.st_dev, 'inode': info.st_ino, 'size': info.st_size,
                'mtimeNs': info.st_mtime_ns, 'ctimeNs': info.st_ctime_ns}

    @staticmethod
    def _public(meta):
        return {key: meta[key] for key in ('id', 'scanId', 'complete', 'createdAt', 'workspace', 'totals',
                                            'folders', 'largestFiles', 'categories', 'errors',
                                            'externalLinksCount', 'externalLinks', 'externalLinksTruncated',
                                            'inventoryPath', 'fingerprint', 'durationSeconds', 'expiresAt')}

    def _active_plan_scans(self):
        plans = self.data_dir / 'storage-maintenance-plans'
        if not plans.exists() or plans.is_symlink() or not plans.is_dir(): return set()
        active = set()
        for path in plans.iterdir():
            if path.is_symlink() or not path.is_file() or not re.fullmatch(r'[0-9a-f]{48}\.json', path.name): continue
            try: value = _json_read(path, None)
            except StorageError: continue
            if isinstance(value, dict) and value.get('state') == 'ready' and value.get('expiresAt', 0) > int(time.time()) and re.fullmatch(r'[0-9a-f]{48}', str(value.get('scanId', ''))):
                active.add(value['scanId'])
        return active

    def _prune(self):
        """Keep a tiny grace window; foreign, broken, and symlinked files are never removed."""
        try:
            active = self._active_plan_scans()
            records = []
            for path in self.scan_dir.iterdir():
                match = re.fullmatch(r'([0-9a-f]{48})\.json', path.name)
                if not match or path.is_symlink() or not path.is_file(): continue
                scan_id = match[1]
                inventory = self.scan_dir / f'{scan_id}.jsonl.gz'
                if inventory.is_symlink() or not inventory.is_file(): continue
                meta = _json_read(path, None)
                if not isinstance(meta, dict) or meta.get('id') != scan_id or meta.get('scanId') != scan_id or meta.get('workspace') != str(self.root): continue
                if meta.get('inventoryPath') != str(inventory) or not isinstance(meta.get('expiresAt'), int): continue
                records.append((meta.get('createdAtNs', 0), scan_id, path, inventory, meta))
            keep = {record[1] for record in sorted(records, reverse=True)[:3]} | active
            now = int(time.time())
            for _created, scan_id, meta_path, inventory_path, meta in records:
                if scan_id in keep or meta['expiresAt'] > now: continue
                if meta_path.is_symlink() or inventory_path.is_symlink(): continue
                meta_path.unlink(); inventory_path.unlink()
        except (OSError, StorageError):
            return

    def scan(self):
        self._directory()
        scan_id = secrets.token_hex(24)
        meta_path, inventory_path = self._paths(scan_id)
        temporary = self.scan_dir / f'.{scan_id}.tmp'
        started = time.monotonic()
        created_at = _iso()
        created_epoch = int(time.time())
        created_ns = time.time_ns()
        totals = {'fileCount': 0, 'directoryCount': 1, 'logicalBytes': 0, 'allocatedBytes': 0,
                  'symlinkCount': 0, 'uniqueFileCount': 0}
        folders, categories, physical, largest = {}, {}, set(), []
        errors, external_links, external_count = [], [], 0
        complete, entries, stopped = True, 0, False

        def error(path, message):
            nonlocal complete
            complete = False
            if len(errors) < MAX_PUBLIC_ROWS:
                errors.append({'path': path, 'message': str(message)[:500]})

        def folder(relative, size, allocated):
            parts = Path(relative).parts
            prefixes = ['.']
            for index in range(1, len(parts)):
                prefixes.append(str(Path(*parts[:index])))
            for prefix in prefixes:
                kind, _label, _reason = _classification(prefix if prefix != '.' else '')
                current = folders.setdefault(prefix, {'path': prefix, 'bytes': 0, 'allocatedBytes': 0,
                                                       'fileCount': 0, 'classification': kind})
                current['bytes'] += size; current['allocatedBytes'] += allocated; current['fileCount'] += 1

        def category(relative, size, allocated, is_physical):
            kind, label, _reason = _classification(relative)
            current = categories.setdefault(kind, {'kind': kind, 'label': label, 'bytes': 0,
                                                    'allocatedBytes': 0, 'fileCount': 0})
            current['bytes'] += size; current['fileCount'] += 1
            if is_physical: current['allocatedBytes'] += allocated

        def largest_file(relative, info, kind, reason):
            item = {'path': relative, 'bytes': info.st_size, 'allocatedBytes': _allocated(info),
                    'classification': kind, 'protectionReason': reason}
            largest.append(item)
            largest.sort(key=lambda value: (value['bytes'], value['path']), reverse=True)
            del largest[MAX_PUBLIC_ROWS:]

        stack = [self.root]
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(descriptor, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as compressed, io.TextIOWrapper(compressed, encoding='utf-8', newline='\n') as inventory:
                while stack and not stopped:
                    directory = stack.pop()
                    try:
                        with os.scandir(directory) as iterator:
                            children = sorted(iterator, key=lambda item: item.name)
                    except OSError as exc:
                        error(str(directory.relative_to(self.root)) if directory != self.root else '.', exc)
                        continue
                    for entry in children:
                        entries += 1
                        if entries > MAX_ENTRIES:
                            error('.', f'스캔 안전 한도({MAX_ENTRIES:,}개 항목)를 초과했습니다.')
                            stopped = True
                            break
                        path = Path(entry.path)
                        relative = str(path.relative_to(self.root))
                        try:
                            info = entry.stat(follow_symlinks=False)
                        except OSError as exc:
                            error(relative, exc)
                            continue
                        if stat.S_ISLNK(info.st_mode):
                            totals['symlinkCount'] += 1
                            try:
                                target = os.readlink(path)
                            except OSError as exc:
                                error(relative, exc); target = '<unreadable>'
                            if self._external_link(path, target):
                                external_count += 1
                                if len(external_links) < MAX_EXTERNAL_LINKS:
                                    external_links.append({'path': relative, 'target': target, 'type': 'symlink'})
                            inventory.write(json.dumps(self._record(relative, info, 'symlink', target), ensure_ascii=False, separators=(',', ':')) + '\n')
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            totals['directoryCount'] += 1
                            stack.append(path)
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        allocated = _allocated(info)
                        inode = (info.st_dev, info.st_ino)
                        is_physical = inode not in physical
                        if is_physical:
                            physical.add(inode); totals['uniqueFileCount'] += 1; totals['allocatedBytes'] += allocated
                        totals['fileCount'] += 1; totals['logicalBytes'] += info.st_size
                        kind, _label, reason = _classification(relative)
                        folder(relative, info.st_size, allocated if is_physical else 0)
                        category(relative, info.st_size, allocated, is_physical)
                        largest_file(relative, info, kind, reason)
                        inventory.write(json.dumps(self._record(relative, info), ensure_ascii=False, separators=(',', ':')) + '\n')
        except OSError as exc:
            error('.', exc)
        finally:
            if not temporary.exists():
                raise StorageError('스캔 인벤토리를 만들 수 없습니다.', 'scan_failed')

        try:
            os.chmod(temporary, 0o600)
            os.replace(temporary, inventory_path)
            inventory_snapshot = self._snapshot(inventory_path)
            inventory_sha = self._digest(inventory_path)
            folders_public = sorted(folders.values(), key=lambda value: (value['bytes'], value['path']), reverse=True)[:MAX_PUBLIC_ROWS]
            categories_public = sorted(categories.values(), key=lambda value: (value['bytes'], value['kind']), reverse=True)
            fingerprint = _id(json.dumps({'workspace': str(self.root), 'createdAt': created_epoch, 'totals': totals,
                'inventorySha256': inventory_sha, 'inventorySnapshot': inventory_snapshot}, sort_keys=True, separators=(',', ':')))
            meta = {'schemaVersion': 1, 'id': scan_id, 'scanId': scan_id, 'complete': complete,
                    'createdAt': created_at, 'createdAtEpoch': created_epoch, 'createdAtNs': created_ns,
                    'expiresAt': created_epoch + PLAN_TTL, 'workspace': str(self.root),
                    'totals': totals, 'folders': folders_public, 'largestFiles': largest,
                    'categories': categories_public, 'errors': errors, 'externalLinksCount': external_count,
                    'externalLinks': external_links, 'externalLinksTruncated': max(0, external_count - len(external_links)),
                    'inventoryPath': str(inventory_path), 'inventorySha256': inventory_sha,
                    'inventorySnapshot': inventory_snapshot, 'fingerprint': fingerprint,
                    'durationSeconds': round(time.monotonic() - started, 3)}
            _atomic_json(meta_path, meta)
            if complete:
                self._store_index(meta)
            self._prune()
            return self._public(meta)
        except OSError as exc:
            inventory_path.unlink(missing_ok=True)
            raise StorageError('스캔 결과를 안전하게 저장할 수 없습니다.', 'scan_failed') from exc

    def _cache_name(self, kind):
        return "workspace-" + kind + ":" + _id(str(self.root))

    def _store_index(self, meta):
        """Persist metadata once per explicit scan; safety plans keep their gzip proof."""
        db = ManagementDB(self.data_dir)
        metadata = {}
        marker_names = SOURCE_METADATA_MARKERS
        try:
            with db.transaction(write=True) as connection, gzip.open(meta["inventoryPath"], "rt", encoding="utf-8") as stream:
                connection.execute("DELETE FROM storage_tracking_files WHERE workspace=?", (str(self.root),))
                batch = []
                for line in stream:
                    record = json.loads(line)
                    relative = record["relativePath"]
                    kind, label, reason = _classification(relative)
                    if Path(relative).name == ".DS_Store":
                        kind, label, reason = "os-residue", "Finder 표시 설정", "확인된 Finder 표시 설정만 정리할 수 있습니다"
                    batch.append((str(self.root), relative, record.get("dev"), record.get("inode"), record.get("size", 0), record.get("allocatedBytes", 0), record.get("mtimeNs"), record.get("ctimeNs"), record.get("nlink"), record["type"], kind, label, reason, meta["createdAtEpoch"], meta["scanId"]))
                    if len(batch) >= 1000:
                        connection.executemany("INSERT INTO storage_tracking_files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch); batch.clear()
                    if record["type"] == "file" and Path(relative).name in marker_names:
                        path = self.root / relative
                        try:
                            if self._snapshot(path) == {key: record[key] for key in ("dev", "inode", "size", "mtimeNs", "ctimeNs")}:
                                metadata[relative] = _ownership_metadata(_json_read(path, None))
                        except (OSError, StorageError):
                            pass
                connection.executemany("INSERT INTO storage_tracking_files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                db.write_document(self._cache_name("scan"), self._public(meta), connection=connection)
                db.write_document(self._cache_name("metadata"), metadata, connection=connection)
                from storage_overview import _sources_from_metadata, _jizura_command_audio, StorageOverview
                source_roots = {}
                commands = {StorageOverview._metadata_root(relative): _jizura_command_audio(value) for relative, value in metadata.items() if Path(relative).name == "final-render-command.json"}
                for relative, value in metadata.items():
                    owner = StorageOverview._metadata_root(relative)
                    if Path(relative).name == "source-provenance.json" and (not isinstance(value, dict) or commands.get(owner) != value.get("userAudio")):
                        continue
                    source_roots.setdefault(owner, set()).update(item["sourceSha256"] for item in _sources_from_metadata(value))
                connection.execute("DELETE FROM management_paths WHERE workspace=? AND role='producer-metadata'", (str(self.root),))
                for relative, sources in source_roots.items():
                    if relative in {"", "."} or len(sources) != 1:
                        continue
                    path = str(self.root / relative)
                    db.claim_path(path, "producer-metadata", project_id=_id(path), group_id=next(iter(sources)), workspace=str(self.root), connection=connection)
                # These classifications identify installed program/tool roots, never unknown files.
                for top in {item.name for item in self.root.iterdir()}:
                    kind = _classification(top)[0]
                    if kind in {"managed", "tooling", "program", "git", "model"}:
                        path = self.root / top
                        db.claim_path(str(path), kind, workspace=str(self.root), kind="directory" if path.is_dir() and not path.is_symlink() else "file", connection=connection)
        except (ManagementDBError, OSError, ValueError) as error:
            raise StorageError("작업 폴더 메타데이터를 SQLite에 기록할 수 없습니다.", "tracking_unavailable") from error

    def cached(self):
        return ManagementDB(self.data_dir).read_document(self._cache_name("scan"), fallback=None)

    def cached_records(self):
        with ManagementDB(self.data_dir).transaction() as connection:
            if connection is None:
                return []
            rows = connection.execute("SELECT relative_path,dev,inode,size,allocated_bytes,mtime_ns,ctime_ns,nlink,file_type FROM storage_tracking_files WHERE workspace=? ORDER BY relative_path", (str(self.root),)).fetchall()
        keys = ("relativePath", "dev", "inode", "size", "allocatedBytes", "mtimeNs", "ctimeNs", "nlink", "type")
        return [dict(zip(keys, row)) for row in rows]

    def cached_metadata(self):
        return ManagementDB(self.data_dir).read_document(self._cache_name("metadata"), fallback={})

    def _load_meta(self, scan_id, *, permit_expired=False):
        meta_path, inventory_path = self._paths(scan_id)
        if meta_path.is_symlink() or inventory_path.is_symlink() or not meta_path.is_file() or not inventory_path.is_file():
            raise StorageError('스캔 결과를 찾을 수 없거나 안전하지 않습니다.', 'invalid_scan')
        meta = _json_read(meta_path, None)
        required = {'schemaVersion', 'id', 'scanId', 'complete', 'createdAt', 'createdAtEpoch', 'createdAtNs', 'expiresAt', 'workspace', 'totals',
                    'folders', 'largestFiles', 'categories', 'errors', 'externalLinksCount', 'externalLinks',
                    'externalLinksTruncated', 'inventoryPath', 'inventorySha256', 'inventorySnapshot', 'fingerprint', 'durationSeconds'}
        if not isinstance(meta, dict) or set(meta) != required or meta.get('schemaVersion') != 1 or meta.get('id') != scan_id or meta.get('scanId') != scan_id:
            raise StorageError('스캔 메타데이터가 손상되었습니다.', 'invalid_scan')
        if meta.get('workspace') != str(self.root) or meta.get('inventoryPath') != str(inventory_path):
            raise StorageError('다른 작업 폴더의 스캔은 사용할 수 없습니다.', 'invalid_scan')
        if not meta.get('complete'):
            raise StorageError('완결되지 않은 스캔은 정리 계획에 사용할 수 없습니다.', 'incomplete_scan')
        if (not isinstance(meta.get('createdAtEpoch'), int) or not isinstance(meta.get('createdAtNs'), int)
                or meta.get('expiresAt') != meta['createdAtEpoch'] + PLAN_TTL or (not permit_expired and meta['expiresAt'] <= int(time.time()))):
            raise StorageError('스캔이 만료되었습니다. 다시 전체 스캔하세요.', 'stale_scan')
        try:
            if self._snapshot(inventory_path) != meta.get('inventorySnapshot') or self._digest(inventory_path) != meta.get('inventorySha256'):
                raise StorageError('스캔 인벤토리가 변경되었습니다.', 'invalid_scan')
        except OSError as exc:
            raise StorageError('스캔 인벤토리를 검증할 수 없습니다.', 'invalid_scan') from exc
        expected = _id(json.dumps({'workspace': str(self.root), 'createdAt': meta['createdAtEpoch'], 'totals': meta['totals'],
            'inventorySha256': meta['inventorySha256'], 'inventorySnapshot': meta['inventorySnapshot']}, sort_keys=True, separators=(',', ':')))
        if meta.get('fingerprint') != expected:
            raise StorageError('스캔 메타데이터가 변경되었습니다.', 'invalid_scan')
        return meta

    def load(self, scan_id):
        self._directory()
        return self._public(self._load_meta(scan_id))

    def latest_complete(self):
        """Read the newest verified snapshot for display without starting a scan.

        An expired snapshot is display-only; planning still requires ``load`` and a
        fresh scan. This keeps overview reads free of hidden workspace mutations.
        """
        if not self.scan_dir.is_dir() or self.scan_dir.is_symlink():
            return None
        candidates = []
        try:
            for path in self.scan_dir.iterdir():
                match = re.fullmatch(r'([0-9a-f]{48})\.json', path.name)
                if not match or path.is_symlink() or not path.is_file():
                    continue
                value = _json_read(path, None)
                if (isinstance(value, dict) and value.get('schemaVersion') == 1 and value.get('id') == match[1]
                        and value.get('scanId') == match[1] and value.get('workspace') == str(self.root)
                        and value.get('complete') is True and isinstance(value.get('createdAtNs'), int)):
                    candidates.append((value['createdAtNs'], match[1]))
        except OSError as exc:
            raise StorageError('스캔 저장소를 읽을 수 없습니다.', 'invalid_scan') from exc
        for _created, scan_id in sorted(candidates, reverse=True):
            try:
                return self._load_meta(scan_id, permit_expired=True)
            except StorageError:
                continue
        return None
