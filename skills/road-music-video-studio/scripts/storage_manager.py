"""Fail-closed storage management for registered Road Music projects only."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import shutil
import sys
import tempfile
import threading
import time

from html_design import studio_session_file
from management_db import ManagementDB, ManagementDBError


MAX_JSON = 16 * 1024 * 1024
PLAN_TTL = 15 * 60
MAX_LIST_SCAN_FILES = 10000
MAX_TRACK_FILES = 10000
KINDS = frozenset({'cache', 'intermediate', 'history'})
STATES = frozenset({'editing', 'completed', 'archived'})
_locks_guard = threading.Lock()
_locks = {}


class StorageError(ValueError):
    def __init__(self, message, code='invalid_request'):
        super().__init__(message)
        self.code = code


def _lock_for(path):
    with _locks_guard:
        return _locks.setdefault(str(path), threading.RLock())


def _now():
    return int(time.time())


def _iso(value=None):
    return datetime.fromtimestamp(value if value is not None else time.time(), timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _json_read(path, fallback):
    path = Path(path)
    if not path.exists():
        return fallback
    try:
        if path.is_symlink() or path.stat().st_size > MAX_JSON:
            raise StorageError('저장공간 관리 데이터가 안전하지 않습니다', 'corrupt_state')
        value = json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, StorageError):
            raise
        raise StorageError('저장공간 관리 데이터를 읽을 수 없습니다', 'corrupt_state') from error
    return value


def _atomic_json(path, value):
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if len(encoded) > MAX_JSON:
        raise StorageError('저장공간 관리 데이터가 너무 큽니다', 'state_too_large')
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('wb', dir=path.parent, prefix=f'.{path.name}.', delete=False) as stream:
        stream.write(encoded); stream.flush(); os.fsync(stream.fileno()); temporary = Path(stream.name)
    try:
        os.chmod(temporary, 0o600); os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _id(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _snapshot(path):
    stat = path.stat(follow_symlinks=False)
    if not path.is_file() or path.is_symlink():
        raise StorageError('symlink가 아닌 일반 파일만 관리할 수 있습니다', 'unsafe_path')
    return {'path': str(path), 'relativePath': None, 'dev': stat.st_dev, 'inode': stat.st_ino,
            'bytes': stat.st_size, 'mtimeNs': stat.st_mtime_ns, 'nlink': stat.st_nlink}


def _bounded_files(root):
    """Return regular leaves without materializing an unbounded recursive glob."""
    if root.is_file(): return [root]
    files, seen = [], 0
    for base, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(directories)
        for name in directories:
            seen += 1
            if seen > MAX_TRACK_FILES: raise StorageError('관리 폴더 항목 수가 안전 한도를 초과했습니다', 'snapshot_limit')
            if (Path(base) / name).is_symlink(): raise StorageError('폴더 안의 symlink는 관리할 수 없습니다', 'unsafe_path')
        for name in sorted(names):
            seen += 1
            if seen > MAX_TRACK_FILES: raise StorageError('관리 폴더 파일 수가 안전 한도를 초과했습니다', 'snapshot_limit')
            item = Path(base) / name
            if item.is_symlink(): raise StorageError('폴더 안의 symlink는 관리할 수 없습니다', 'unsafe_path')
            if item.is_file(): files.append(item)
    return files


class StorageManager:
    """Registry-backed manager. It deliberately never discovers deletable files."""

    def __init__(self, data_dir=None):
        raw = Path(data_dir) if data_dir is not None else studio_session_file().parent
        if not raw.is_absolute():
            raise StorageError('데이터 경로는 절대 경로여야 합니다')
        if raw.is_symlink():
            raise StorageError('데이터 경로 symlink는 허용하지 않습니다', 'unsafe_path')
        self.data_dir = raw.resolve()
        self.registry_path = self.data_dir / 'storage-registry.json'
        self.management_db = ManagementDB(self.data_dir)
        self.plan_dir = self.data_dir / 'storage-plans'
        self.lock_path = self.data_dir / '.storage-registry.lock'
        self._lock = _lock_for(self.lock_path)

    def _plan_path(self, plan_id):
        if self.plan_dir.exists() and self.plan_dir.is_symlink(): raise StorageError('정리 계획 경로가 안전하지 않습니다', 'unsafe_path')
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        return self.plan_dir / f'{plan_id}.json'

    def _prune_plans(self):
        if not self.plan_dir.exists(): return
        if self.plan_dir.is_symlink(): raise StorageError('정리 계획 경로가 안전하지 않습니다', 'unsafe_path')
        for path in self.plan_dir.iterdir():
            if path.is_symlink() or not path.is_file() or not re.fullmatch(r'[0-9a-f]{48}\.json', path.name): continue
            try: plan = _json_read(path, None)
            except StorageError: continue
            if isinstance(plan, dict) and (plan.get('state') == 'used' or plan.get('expiresAt', 0) < _now()): path.unlink()

    @staticmethod
    def _empty():
        return {'schemaVersion': 1, 'projects': {}, 'leases': {}}

    @contextmanager
    def _write_lock(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self._lock, self.lock_path.open('a+b') as stream:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _read(self):
        try:
            value = self.management_db.read_document('storage-registry', self.registry_path, self._empty(), self._validate_registry)
        except ManagementDBError as error:
            raise StorageError(str(error), 'corrupt_state') from error
        return value

    @staticmethod
    def _validate_registry(value):
        if not isinstance(value, dict) or set(value) != {'schemaVersion', 'projects', 'leases'} or value['schemaVersion'] != 1 or not isinstance(value['projects'], dict) or not isinstance(value['leases'], dict):
            raise StorageError('저장공간 레지스트리가 손상되었습니다', 'corrupt_state')

    def _save(self, value, connection=None):
        self._validate_registry(value)
        try:
            self.management_db.write_document('storage-registry', value, self.registry_path, self._validate_registry, connection=connection)
        except ManagementDBError as error:
            raise StorageError(str(error), 'corrupt_state') from error

    def migrate_management_metadata(self):
        from work_library import WorkLibrary
        library = WorkLibrary(self.data_dir / 'video-studio-library.json')
        try:
            with self._write_lock(), library._write_lock():
                self._read(); library._read()
                with self.management_db.transaction(write=True) as connection:
                    registry = self.management_db.migrate_legacy('storage-registry', self.registry_path, self._empty(), self._validate_registry, connection=connection)
                    works = self.management_db.migrate_legacy('work-library', library.path, library._empty(), library._validate_document, connection=connection)
                    library._sync_file_ownership(works, connection)
                    from storage_packaging import TRUSTED_ROOT, is_workspace
                    from storage_lifecycle import _production_group_id
                    for project_id, project in registry['projects'].items():
                        raw = project.get('path') if isinstance(project, dict) else None
                        if not isinstance(raw, str) or not Path(raw).is_absolute():
                            continue
                        root = Path(raw)
                        if root.is_symlink() or root.resolve(strict=False) != root or is_workspace(root):
                            continue
                        workspace = TRUSTED_ROOT if TRUSTED_ROOT is not None and root.is_relative_to(TRUSTED_ROOT) else root
                        self.management_db.claim_path(str(root), 'project', project_id=project_id, group_id=_production_group_id(root), workspace=str(workspace), connection=connection)
        except (ManagementDBError, ValueError) as error:
            raise StorageError(str(error), 'corrupt_state') from error
        return {'registry': {'migrated': True, 'projects': len(registry['projects'])}, 'library': {'migrated': True, 'groups': len(works['groups'])}, 'dbPath': str(self.management_db.path)}

    @staticmethod
    def _project_id(path):
        return _id(str(path))

    def _unsafe_root(self, path):
        from storage_packaging import TRUSTED_ROOT, is_workspace
        repo_root = TRUSTED_ROOT
        blocked = (Path.home().resolve(), self.data_dir)
        if path in blocked:
            return True
        if repo_root is not None and path == repo_root and not is_workspace(path): return True
        # A verified project below a user/repository root is valid; only immutable install trees are not.
        return any(part.casefold() in {'engines', 'engine', 'models', 'model', 'node_modules', 'bin', 'runtime'} or part.casefold().endswith('.app') for part in path.parts)

    def _project_path(self, value):
        if not isinstance(value, str) or not value:
            raise StorageError('프로젝트 절대 경로가 필요합니다')
        raw = Path(value)
        if not raw.is_absolute() or raw.is_symlink():
            raise StorageError('symlink가 아닌 프로젝트 절대 경로가 필요합니다', 'unsafe_path')
        try:
            path = raw.resolve(strict=True)
        except OSError as error:
            raise StorageError('프로젝트 폴더를 찾을 수 없습니다') from error
        if not path.is_dir() or self._unsafe_root(path):
            raise StorageError('이 경로는 프로젝트로 등록할 수 없습니다', 'unsafe_project')
        return path

    @staticmethod
    def _marker_json(path):
        value = _json_read(path, None)
        return isinstance(value, dict) and value.get('schemaVersion') == 1

    def _valid_project(self, path):
        from storage_packaging import is_workspace
        if is_workspace(path): return True
        studio = _json_read(path / 'studio-project.json', None)
        if isinstance(studio, dict) and studio.get('schemaVersion') == 1 and isinstance(studio.get('media'), list):
            return True
        if self._marker_json(path / 'production.json') and self._marker_json(path / 'playlist.json'):
            return True
        if self._marker_json(path / 'native-production.json') and self._marker_json(path / 'playlist.json'):
            return True
        if self._marker_json(path / 'input.json') and self._marker_json(path / 'plan.json'):
            return True
        mv_input = _json_read(path / 'input.json', None)
        mv_plan = _json_read(path / 'production-plan.json', None)
        if (isinstance(mv_input, dict) and mv_input.get('schema_version') == 1 and
                isinstance(mv_input.get('source_audio'), str) and Path(mv_input['source_audio']).is_absolute() and
                isinstance(mv_input.get('source_audio_sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', mv_input['source_audio_sha256']) and
                isinstance(mv_plan, dict) and isinstance(mv_plan.get('objective'), str) and isinstance(mv_plan.get('tasks'), list)):
            return True
        from storage_legacy import producer_profile
        if producer_profile(path) is not None:
            return True
        meta = _json_read(path / 'meta.json', None)
        audio = [item for item in path.iterdir() if item.is_file() and not item.is_symlink() and item.suffix.casefold() in {'.wav', '.mp3', '.flac', '.m4a', '.ogg', '.opus'}]
        return isinstance(meta, dict) and any(isinstance(meta.get(key), str) and meta[key].strip() for key in ('title', 'style', 'engine', 'engineId')) and bool(audio)

    @staticmethod
    def _inside(root, path):
        return path == root or root in path.parents

    def _managed_path(self, project, relative, allow_dir=False):
        if not isinstance(relative, str) or not relative or '\x00' in relative:
            raise StorageError('상대 경로가 필요합니다')
        candidate = Path(relative)
        if candidate.is_absolute() or '..' in candidate.parts:
            raise StorageError('프로젝트 내부 상대 경로만 허용합니다', 'unsafe_path')
        raw = project / candidate
        parent = raw
        while parent != project.parent:
            if parent.is_symlink():
                raise StorageError('중간 경로의 symlink는 관리할 수 없습니다', 'unsafe_path')
            parent = parent.parent
        if raw.is_symlink():
            raise StorageError('symlink는 관리할 수 없습니다', 'unsafe_path')
        try:
            resolved = raw.resolve(strict=True)
        except OSError as error:
            raise StorageError('관리할 파일을 찾을 수 없습니다') from error
        if not self._inside(project, resolved) or (not allow_dir and not resolved.is_file()) or (allow_dir and not (resolved.is_file() or resolved.is_dir())):
            raise StorageError('프로젝트 내부 일반 파일 또는 폴더가 필요합니다', 'unsafe_path')
        return raw, resolved

    @staticmethod
    def _unlink_verified(root, relative, expected):
        """Resolve every parent through a no-follow descriptor before unlinking one leaf."""
        parts = Path(relative).parts
        if not parts or any(part in {'', '.', '..'} for part in parts):
            raise StorageError('안전하지 않은 삭제 경로입니다', 'unsafe_path')
        nofollow = getattr(os, 'O_NOFOLLOW', 0)
        directory = os.open(root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | nofollow)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | nofollow, dir_fd=directory)
                os.close(directory); directory = next_fd
            stat = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != expected:
                raise StorageError('계획 뒤 파일이 변경되었습니다')
            os.unlink(parts[-1], dir_fd=directory)
        finally:
            os.close(directory)

    def _protected_paths(self, project):
        protected = {project / name for name in ('studio-project.json', 'selection.json', 'feedback.json', 'manifest.json', 'production.json', 'native-production.json', 'playlist.json', 'input.json', 'plan.json', 'production-plan.json', 'meta.json', 'score.abc', '.backups')}
        meta = _json_read(project / 'meta.json', None)
        if isinstance(meta, dict):
            protected.update(item for item in project.iterdir() if item.is_file() and item.suffix.casefold() in {'.wav', '.mp3', '.flac', '.m4a', '.ogg', '.opus'})
        markers = {item for item in protected if item.suffix.casefold() == '.json'}
        from storage_packaging import is_workspace
        search_root = project / '.roadmusic' if is_workspace(project) else project
        for candidate in search_root.rglob('*.json'):
            if len(markers) >= 1000: break
            name = candidate.name.casefold()
            if any(token in name for token in ('manifest', 'approved', 'selection', 'feedback', 'history')): markers.add(candidate)
        try:
            library = self.management_db.read_document('work-library', self.data_dir / 'video-studio-library.json', {'schemaVersion': 1, 'groups': {}})
        except ManagementDBError as error:
            raise StorageError(str(error), 'corrupt_state') from error
        values = [_json_read(marker, None) for marker in markers]
        values.append(library)
        for value in values:
            def visit(item):
                if isinstance(item, str):
                    if not item.strip(): return
                    candidate = Path(item)
                    raw = candidate if candidate.is_absolute() else project / candidate
                    try:
                        resolved = raw.resolve(strict=True)
                        if resolved != project and self._inside(project, resolved): protected.add(resolved)
                    except OSError: pass
                elif isinstance(item, dict):
                    for child in item.values(): visit(child)
                elif isinstance(item, list):
                    for child in item: visit(child)
            visit(value)
        protected.add(project / '.roadmusic' / 'history.jsonl')
        return protected

    def _protected_reason(self, project, path, protected=None):
        try: resolved = path.resolve(strict=True)
        except OSError: return '파일을 확인할 수 없습니다'
        if path.is_symlink() or any(parent.is_symlink() for parent in (path, *path.parents) if self._inside(project, parent)):
            return 'symlink 경로는 보호됩니다'
        protected = self._protected_paths(project) if protected is None else protected
        if any(resolved == item or item in resolved.parents for item in protected): return '프로젝트 원본·manifest·승인 자산은 보호됩니다'
        names = {part.casefold() for part in resolved.relative_to(project).parts}
        if names & {'publish', 'library', 'models', 'model', 'output', 'out', 'deliverables', 'exports', 'inputs', 'reel', 'completed', 'final', 'engines', 'node_modules'} or any(part.endswith('.app') for part in names):
            return '완성·라이브러리·모델 경로는 보호됩니다'
        if resolved.suffix.casefold() in {'.safetensors', '.gguf', '.ggml', '.ckpt', '.pth', '.pt', '.bin', '.js', '.py', '.html', '.css'}:
            return '프로그램·모델 파일은 보호됩니다'
        if path.stat(follow_symlinks=False).st_mode & 0o111:
            return '실행 가능한 프로그램 파일은 보호됩니다'
        if resolved.suffix.lower() in {'.mp3', '.wav', '.flac', '.m4a', '.mp4', '.mov'} and any(token in resolved.stem.casefold() for token in ('original', 'source', 'input')):
            return '원본 자산은 보호됩니다'
        return None

    def _entry_files(self, project, raw, resolved, protected=None):
        candidates = _bounded_files(resolved)
        files = []
        for item in candidates:
            if item.is_symlink(): raise StorageError('폴더 안의 symlink는 관리할 수 없습니다', 'unsafe_path')
            if not item.is_file(): continue
            reason = self._protected_reason(project, item, protected)
            if reason: raise StorageError(reason, 'protected')
            value = _snapshot(item); value['relativePath'] = str(item.relative_to(project)); files.append(value)
        if not files: raise StorageError('관리할 일반 파일이 없습니다')
        return files

    def _project(self, data, project_id):
        if not isinstance(project_id, str) or len(project_id) != 64:
            raise StorageError('등록된 프로젝트 ID가 필요합니다')
        project = data['projects'].get(project_id)
        if not isinstance(project, dict): raise StorageError('등록된 프로젝트가 아닙니다', 'not_found')
        path = self._project_path(project.get('path'))
        if self._project_id(path) != project_id or not self._valid_project(path):
            raise StorageError('등록 프로젝트 검증에 실패했습니다', 'unsafe_project')
        return project, path

    @staticmethod
    def _lease_alive(lease):
        if not isinstance(lease, dict) or not isinstance(lease.get('pid'), int) or lease['pid'] < 1: return False
        try: os.kill(lease['pid'], 0)
        except ProcessLookupError: return False
        except PermissionError: return True
        return True

    def _busy(self, data, project_id):
        lease = data['leases'].get(project_id)
        if lease and not self._lease_alive(lease): data['leases'].pop(project_id, None); lease = None
        return bool(lease)

    def _project_public(self, data, project_id, project, root):
        busy = self._busy(data, project_id)
        managed_bytes = reclaimable = cache_bytes = cache_files = 0
        entries = []
        known = set()
        changed_files = {}
        managed_inodes = set()
        for entry in project['entries'].values():
            files = entry.get('files', [])
            live, changed = [], False
            for item in files:
                try:
                    current = (root / item['relativePath']).stat(follow_symlinks=False)
                    same = (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) == (item['dev'], item['inode'], item['bytes'], item['mtimeNs'])
                    if same:
                        live.append((item, current)); known.add(item['relativePath'])
                        key = (current.st_dev, current.st_ino)
                        if key not in managed_inodes: managed_inodes.add(key); managed_bytes += current.st_size
                    else:
                        changed = True
                        if stat.S_ISREG(current.st_mode): changed_files[item['relativePath']] = current
                except OSError: changed = True
            size = sum(current.st_size for _, current in live); count = len(live)
            if entry['kind'] == 'cache': cache_bytes += size; cache_files += count
            reason = '보존 핀' if entry.get('pinned') else None
            if busy: reason = reason or '진행 중인 제작 lease가 있습니다'
            if entry['kind'] in {'intermediate', 'history'} and project['preserveHistory']: reason = reason or '히스토리 보존 정책입니다'
            if changed: reason = reason or '등록 뒤 파일이 변경되었거나 없습니다'
            if not reason and not busy:
                for _, current in live:
                    if current.st_nlink <= 1: reclaimable += current.st_size
            entries.append({'id': entry['id'], 'path': entry['relativePath'], 'relativePath': entry['relativePath'], 'kind': entry['kind'], 'description': entry.get('description', ''), 'bytes': size, 'fileCount': count, 'protected': bool(reason), 'reason': reason, 'manualOnly': entry['kind'] != 'cache', 'pinned': bool(entry.get('pinned'))})
        from storage_scan import WorkspaceScan
        scanner = WorkspaceScan(root, self.data_dir) if not self.data_dir.is_relative_to(root) else None
        indexed = scanner.cached() if scanner is not None else None
        unknown_files = dict(changed_files)
        for row in scanner.cached_records() if indexed else []:
            relative = row['relativePath']
            if row.get('type') != 'file' or relative in known:
                continue
            if project.get('origin') == 'road-music-workspace' and not relative.startswith('.roadmusic/'):
                continue
            item = root / relative
            try:
                info = item.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode): unknown_files[relative] = info
            except OSError:
                continue
        unknown = sorted(unknown_files.items(), key=lambda item: item[1].st_size, reverse=True)
        warnings = []
        if cache_bytes > project['maxCacheBytes']: warnings.append('캐시 용량 예산을 초과했습니다')
        if cache_files > project['maxCacheFiles']: warnings.append('캐시 파일 수 예산을 초과했습니다')
        if indexed is None: warnings.append('미등록 파일 사용량은 소유권 색인 갱신 후 확인할 수 있습니다')
        visible_unknown = [{'relativePath': relative, 'bytes': info.st_size, 'reason': '미등록 파일: 보호됨'} for relative, info in unknown[:100]]
        unknown_inodes = {(info.st_dev, info.st_ino): info.st_size for _, info in unknown}
        unknown_bytes = sum(size for key, size in unknown_inodes.items() if key not in managed_inodes) if indexed else None
        return {'id': project_id, 'name': project.get('name') or root.name, 'path': str(root), 'origin': project.get('origin', 'production'), 'usageScope': 'managed-cache' if project.get('origin') == 'road-music-workspace' else 'project', 'state': project['state'], 'preserveHistory': project['preserveHistory'], 'autoCleanup': project['autoCleanup'], 'retainDays': project['retainDays'], 'maxCacheBytes': project['maxCacheBytes'], 'maxCacheFiles': project['maxCacheFiles'], 'busy': busy, 'totalBytes': managed_bytes + (unknown_bytes or 0), 'managedBytes': managed_bytes, 'reclaimableBytes': reclaimable, 'fileCount': sum(item['fileCount'] for item in entries), 'readonlyUnknownFiles': len(unknown) if indexed else None, 'readonlyUnknownBytes': unknown_bytes, 'unknownScanRequired': indexed is None, 'usageSource': 'indexed' if indexed else 'managed-metadata', 'indexedAt': indexed.get('createdAt') if indexed else None, 'totalBytesPartial': indexed is None, 'unmanagedEntries': visible_unknown, 'unknownTruncated': max(0, len(unknown) - len(visible_unknown)), 'unknownScanTruncated': False, 'budgetExceeded': bool(warnings), 'warnings': warnings, 'entries': entries}

    def _audit(self, root, action, detail, connection=None, before=None):
        try:
            self.management_db.record_event(action, project_id=detail.get('projectId') or self._project_id(root), before=before, after=detail, path=str(root), connection=connection)
        except ManagementDBError as error:
            raise StorageError(str(error), 'corrupt_state') from error

    def project_register_managed_dirs(self, project_id):
        """Create only the three project-local managed roots after registry validation."""
        with self._write_lock():
            data = self._read(); _, root = self._project(data, project_id)
            managed = root / '.roadmusic'
            if managed.is_symlink(): raise StorageError('.roadmusic symlink는 허용하지 않습니다', 'unsafe_path')
            for name in ('cache', 'intermediate', 'history'):
                path = managed / name
                if path.exists() and (path.is_symlink() or not path.is_dir()): raise StorageError(f'.roadmusic/{name} 경로가 안전하지 않습니다', 'unsafe_path')
                path.mkdir(parents=True, exist_ok=True)
            return {'projectId': project_id, 'paths': {name: str(managed / name) for name in ('cache', 'intermediate', 'history')}}

    def register(self, params):
        root = self._project_path(params.get('project'))
        if not self._valid_project(root): raise StorageError('studio-project.json 또는 검증된 제작 마커가 필요합니다', 'invalid_project')
        project_id = self._project_id(root)
        with self._write_lock():
            data = self._read(); project = data['projects'].get(project_id)
            new_project = project is None
            if new_project:
                project = {'path': str(root), 'name': root.name, 'state': 'editing', 'preserveHistory': True, 'autoCleanup': True, 'retainDays': 7, 'maxCacheBytes': 2 * 1024 ** 3, 'maxCacheFiles': 20000, 'entries': {}}
                from storage_packaging import is_workspace
                if is_workspace(root):
                    project.update({'origin': 'road-music-workspace', 'name': root.name + ' 패키지 검증'})
                managed = root / '.roadmusic'
                if managed.is_symlink(): raise StorageError('.roadmusic symlink는 허용하지 않습니다', 'unsafe_path')
                for name in ('cache', 'intermediate', 'history'):
                    path = managed / name
                    if path.exists() and (path.is_symlink() or not path.is_dir()): raise StorageError(f'.roadmusic/{name} 경로가 안전하지 않습니다', 'unsafe_path')
                    path.mkdir(parents=True, exist_ok=True)
                data['projects'][project_id] = project
                with self.management_db.transaction(write=True) as connection:
                    self._save(data, connection=connection)
                    self._audit(root, 'register', {'projectId': project_id}, connection=connection)
                    if not is_workspace(root):
                        from storage_lifecycle import _production_group_id
                        from storage_packaging import TRUSTED_ROOT
                        workspace = TRUSTED_ROOT if TRUSTED_ROOT is not None and root.is_relative_to(TRUSTED_ROOT) else root
                        self.management_db.claim_path(str(root), 'project', project_id=project_id, group_id=_production_group_id(root), workspace=str(workspace), connection=connection)
            from storage_scan import WorkspaceScan
            if new_project and not self.data_dir.is_relative_to(root): WorkspaceScan(root, self.data_dir).scan()
            return self._project_public(data, project_id, project, root)

    def track(self, params):
        kind = params.get('kind'); project_id = params.get('projectId')
        if kind not in KINDS: raise StorageError('cache/intermediate/history 종류만 허용합니다')
        if kind == 'cache' and params.get('reproducible') is not True: raise StorageError('cache는 reproducible=true가 필요합니다')
        with self._write_lock():
            data = self._read(); project, root = self._project(data, project_id)
            raw, resolved = self._managed_path(root, params.get('path'), allow_dir=True)
            kind_root = root / '.roadmusic' / kind
            if not (resolved == kind_root or kind_root in resolved.parents):
                raise StorageError(f'{kind}는 .roadmusic/{kind} 내부에서만 등록할 수 있습니다', 'unsafe_path')
            files = self._entry_files(root, raw, resolved, self._protected_paths(root))
            relative = str(raw.relative_to(root)); entry_id = _id(project_id + '\0' + relative + '\0' + kind)
            target = Path(relative)
            for other_id, other in project['entries'].items():
                if other_id == entry_id: continue
                other_path = Path(other['relativePath'])
                if target == other_path or target in other_path.parents or other_path in target.parents:
                    raise StorageError('서로 겹치는 관리 항목은 중복 등록할 수 없습니다', 'overlapping_entry')
            description = params.get('description', '')
            if not isinstance(description, str) or len(description) > 400: raise StorageError('description이 올바르지 않습니다')
            previous = project['entries'].get(entry_id, {})
            entry = {'id': entry_id, 'relativePath': relative, 'kind': kind, 'description': description, 'reproducible': kind == 'cache', 'pinned': bool(previous.get('pinned')), 'isDirectory': resolved.is_dir(), 'files': files, 'lastUsedAt': _now()}
            project['entries'][entry_id] = entry
            with self.management_db.transaction(write=True) as connection:
                self._save(data, connection=connection)
                self._audit(root, 'track', {'projectId': project_id, 'entryId': entry_id, 'kind': kind, 'files': len(files)}, connection=connection)
            return next(item for item in self._project_public(data, project_id, project, root)['entries'] if item['id'] == entry_id)

    def policy(self, params):
        transitioned = False
        with self._write_lock():
            data = self._read(); project, root = self._project(data, params.get('projectId'))
            old_state = project['state']
            previous = {key: project.get(key) for key in ('state', 'preserveHistory', 'autoCleanup', 'retainDays', 'maxCacheBytes', 'maxCacheFiles')}
            for key in ('state', 'preserveHistory', 'autoCleanup', 'retainDays', 'maxCacheBytes', 'maxCacheFiles'):
                if key not in params: continue
                value = params[key]
                if key == 'state' and value not in STATES: raise StorageError('state가 올바르지 않습니다')
                if key in {'preserveHistory', 'autoCleanup'} and not isinstance(value, bool): raise StorageError(f'{key}: true/false가 필요합니다')
                if key == 'retainDays' and (not isinstance(value, int) or not 0 <= value <= 3650): raise StorageError('retainDays: 0..3650 정수가 필요합니다')
                if key in {'maxCacheBytes', 'maxCacheFiles'} and (not isinstance(value, int) or value < 0): raise StorageError(f'{key}: 0 이상의 정수가 필요합니다')
                project[key] = value
            if all(project.get(key) == value for key, value in previous.items()):
                return self._project_public(data, params['projectId'], project, root)
            if project['state'] == 'completed':
                transitioned = old_state != 'completed'
                if transitioned: project['completedAt'] = _now()
            with self.management_db.transaction(write=True) as connection:
                self._save(data, connection=connection)
                self._audit(root, 'policy', {'projectId': params['projectId'], **{key: project.get(key) for key in previous}}, connection=connection, before=previous)
            result = self._project_public(data, params['projectId'], project, root)
        if transitioned:
            try: result['cleanup'] = self.maybe_cleanup(params['projectId'])
            except StorageError as error: result['cleanupWarning'] = str(error)
        return result

    def pin(self, params):
        with self._write_lock():
            data = self._read(); project, root = self._project(data, params.get('projectId')); entry = project['entries'].get(params.get('entryId'))
            if not isinstance(entry, dict) or not isinstance(params.get('pinned'), bool): raise StorageError('등록 항목과 pinned true/false가 필요합니다')
            previous = entry.get('pinned', False)
            if previous == params['pinned']:
                return next(item for item in self._project_public(data, params['projectId'], project, root)['entries'] if item['id'] == entry['id'])
            entry['pinned'] = params['pinned']
            with self.management_db.transaction(write=True) as connection:
                self._save(data, connection=connection)
                self._audit(root, 'pin', {'projectId': params['projectId'], 'entryId': entry['id'], 'pinned': entry['pinned']}, connection=connection, before={'pinned': previous})
            return next(item for item in self._project_public(data, params['projectId'], project, root)['entries'] if item['id'] == entry['id'])

    def _preview(self, data, project_ids, entry_ids=None, kinds=None, automatic=False):
        selected, blocked, files = [], [], []
        now = _now()
        for project_id in project_ids:
            try: project, root = self._project(data, project_id)
            except StorageError as error:
                if len(project_ids) == 1: raise
                blocked.append({'projectId': project_id, 'reason': str(error)})
                continue
            busy = self._busy(data, project_id)
            allowed_ids = set(project['entries']) if entry_ids is None else set(entry_ids)
            if entry_ids is not None and not allowed_ids.issubset(project['entries']): raise StorageError('등록되지 않은 항목 ID입니다')
            for entry in project['entries'].values():
                if entry['id'] not in allowed_ids or (kinds and entry['kind'] not in kinds): continue
                reason = None
                if busy: reason = '진행 중인 제작 lease가 있습니다'
                elif entry.get('pinned'): reason = '보존 핀 항목입니다'
                elif automatic and (project['state'] not in {'completed', 'archived'} or not project['autoCleanup'] or entry['kind'] != 'cache' or not entry.get('reproducible') or not entry['relativePath'].startswith('.roadmusic/cache/')): reason = '자동 정리 정책 대상이 아닙니다'
                elif automatic and now - max(entry.get('lastUsedAt', 0), project.get('completedAt', 0)) < project['retainDays'] * 86400: reason = '보존 기간이 남았습니다'
                elif not automatic and entry['kind'] in {'intermediate', 'history'} and (project['preserveHistory'] or not entry_ids): reason = '중간본·히스토리는 보존 해제 뒤 명시 항목만 정리할 수 있습니다'
                if reason:
                    blocked.append({'projectId': project_id, 'entryId': entry['id'], 'reason': reason}); continue
                for item in entry.get('files', []):
                    files.append({'projectId': project_id, 'entryId': entry['id'], **item})
                    selected.append(entry['id'])
        plan_id = secrets.token_hex(24)
        plan = {'schemaVersion': 1, 'id': plan_id, 'createdAt': now, 'expiresAt': now + PLAN_TTL, 'state': 'ready', 'automatic': automatic, 'explicitEntries': entry_ids is not None, 'files': files, 'entryIds': sorted(set(selected))}
        if automatic and not files:
            return {'planId': None, 'entries': [], 'fileCount': 0, 'bytes': 0, 'blocked': blocked, 'expiresAt': None}
        _atomic_json(self._plan_path(plan_id), plan)
        bytes_ = 0
        for item in files:
            try:
                _, root = self._project(data, item['projectId'])
                if (root / item['relativePath']).stat(follow_symlinks=False).st_nlink <= 1: bytes_ += item['bytes']
            except (OSError, StorageError): pass
        return {'planId': plan_id, 'entries': [{'id': item['entryId'], 'projectId': item['projectId'], 'relativePath': item['relativePath'], 'bytes': item['bytes']} for item in files], 'fileCount': len(files), 'bytes': bytes_, 'blocked': blocked, 'expiresAt': _iso(plan['expiresAt'])}

    def preview(self, params, automatic=False):
        supplied_kinds = params.get('kinds')
        entry_ids = params.get('entryIds')
        kinds = supplied_kinds if supplied_kinds is not None else (None if entry_ids is not None else ['cache'])
        if kinds is None: kinds = list(KINDS)
        if not isinstance(kinds, list) or not kinds or any(kind not in KINDS for kind in kinds): raise StorageError('kinds가 올바르지 않습니다')
        if entry_ids is not None and (not isinstance(entry_ids, list) or not all(isinstance(item, str) for item in entry_ids)): raise StorageError('entryIds가 올바르지 않습니다')
        with self._write_lock():
            self._prune_plans()
            data = self._read(); project_id = params.get('projectId')
            ids = [project_id] if project_id else list(data['projects'])
            if not ids: return self._preview(data, [], entry_ids, kinds, automatic)
            return self._preview(data, ids, entry_ids, kinds, automatic)

    @staticmethod
    def _same_files(left, right):
        fields = ('relativePath', 'dev', 'inode', 'bytes', 'mtimeNs')
        return sorted(tuple(item.get(field) for field in fields) for item in left) == sorted(tuple(item.get(field) for field in fields) for item in right)

    def _entry_still_safe(self, root, entry, protected):
        raw, resolved = self._managed_path(root, entry['relativePath'], allow_dir=True)
        current = self._entry_files(root, raw, resolved, protected)
        return self._same_files(entry.get('files', []), current)

    def cleanup(self, params):
        if params.get('confirm') is not True: raise StorageError('cleanup에는 confirm:true가 필요합니다', 'confirmation_required')
        plan_id = params.get('planId')
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id): raise StorageError('planId가 올바르지 않습니다')
        plan_path = self._plan_path(plan_id)
        with self._write_lock():
            self._prune_plans()
            plan = _json_read(plan_path, None)
            if not isinstance(plan, dict) or plan.get('id') != plan_id or plan.get('state') != 'ready': raise StorageError('유효한 정리 계획이 아닙니다', 'invalid_plan')
            if plan.get('expiresAt', 0) < _now(): raise StorageError('정리 계획이 만료되었습니다', 'plan_expired')
            plan['state'] = 'in-progress'; _atomic_json(plan_path, plan)
            data = self._read(); removed = freed = 0; skipped = []; warnings = []; audited = set(); removed_records = []
            try:
                audit_roots = {}; entry_summaries = {}
                for item in plan.get('files', []):
                    project, root = self._project(data, item['projectId'])
                    audit_roots[item['projectId']] = root
                    entry = project['entries'].get(item['entryId'])
                    if isinstance(entry, dict): entry_summaries[(item['projectId'], item['entryId'])] = {'relativePath': entry['relativePath'], 'kind': entry['kind'], 'description': entry.get('description', '')}
                for project_id, root in audit_roots.items():
                    entries = [summary for (owner, _), summary in entry_summaries.items() if owner == project_id]
                    self._audit(root, 'cleanup-intent', {'planId': plan_id, 'fileCount': sum(1 for item in plan['files'] if item['projectId'] == project_id), 'entries': entries})
                checked = set(); protected_sets = {}
                for item in plan.get('files', []):
                    try:
                        project, root = self._project(data, item['projectId'])
                        if self._busy(data, item['projectId']): raise StorageError('진행 중인 제작 lease가 있습니다')
                        entry = project['entries'].get(item['entryId'])
                        registered = next((candidate for candidate in (entry or {}).get('files', []) if isinstance(candidate, dict) and candidate.get('relativePath') == item.get('relativePath') and candidate.get('inode') == item.get('inode') and candidate.get('dev') == item.get('dev')), None)
                        if not isinstance(entry, dict) or entry.get('pinned') or registered is None: raise StorageError('계획 뒤 등록 상태가 변경되었습니다')
                        protected = protected_sets.setdefault(item['projectId'], self._protected_paths(root))
                        if (item['projectId'], item['entryId']) not in checked:
                            if not self._entry_still_safe(root, entry, protected): raise StorageError('계획 뒤 폴더 내용 또는 등록 파일이 변경되었습니다')
                            checked.add((item['projectId'], item['entryId']))
                        if plan.get('automatic') and (project['state'] not in {'completed', 'archived'} or not project['autoCleanup'] or entry['kind'] != 'cache' or not entry.get('reproducible') or not entry['relativePath'].startswith('.roadmusic/cache/') or _now() - max(entry.get('lastUsedAt', 0), project.get('completedAt', 0)) < project['retainDays'] * 86400): raise StorageError('계획 뒤 자동 정리 정책이 변경되었습니다')
                        if not plan.get('automatic') and entry['kind'] in {'intermediate', 'history'} and (project['preserveHistory'] or not plan.get('explicitEntries')): raise StorageError('계획 뒤 보존 정책이 변경되었습니다')
                        raw, path = self._managed_path(root, item['relativePath'])
                        if self._protected_reason(root, path, protected): raise StorageError('보호 경로는 삭제하지 않습니다')
                        stat = path.stat(follow_symlinks=False)
                        if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != (item['dev'], item['inode'], item['bytes'], item['mtimeNs']): raise StorageError('계획 뒤 파일이 변경되었습니다')
                        reclaim = stat.st_size if stat.st_nlink <= 1 else 0
                        self._unlink_verified(root, item['relativePath'], (item['dev'], item['inode'], item['bytes'], item['mtimeNs']))
                        removed += 1; freed += reclaim; audited.add((item['projectId'], root)); removed_records.append((item['projectId'], item['entryId'], item['relativePath'], item['inode'], item['dev'], reclaim))
                    except (OSError, StorageError) as error:
                        skipped.append({'projectId': item.get('projectId'), 'relativePath': item.get('relativePath'), 'reason': str(error)})
                for project_id, entry_id, relative, inode, dev, reclaim in removed_records:
                    entry = data['projects'][project_id]['entries'].get(entry_id)
                    if not entry: continue
                    entry['files'] = [file for file in entry['files'] if not (file.get('relativePath') == relative and file.get('inode') == inode and file.get('dev') == dev)]
                    if not entry['files']: data['projects'][project_id]['entries'].pop(entry_id, None)
                self._save(data)
                for project_id, root in audited:
                    records = [record for record in removed_records if record[0] == project_id]
                    entries = [entry_summaries[(project_id, record[1])] for record in records if (project_id, record[1]) in entry_summaries]
                    try:
                        self._audit(root, 'cleanup', {'planId': plan_id, 'removedFiles': len(records), 'freedBytes': sum(record[5] for record in records), 'skippedCount': sum(1 for item in skipped if item.get('projectId') == project_id), 'entries': entries})
                    except (StorageError, OSError) as error:
                        warnings.append(f'감사 완료 기록 실패: {error}')
                plan['state'] = 'used'; plan['usedAt'] = _now(); _atomic_json(plan_path, plan); plan_path.unlink(missing_ok=True)
            except Exception:
                plan['state'] = 'failed'; _atomic_json(plan_path, plan); raise
        return {'removedFiles': removed, 'freedBytes': freed, 'skipped': skipped, 'warnings': warnings, 'auditPath': str(self.management_db.path) if audited else None}

    def history(self, params):
        with self._lock:
            data = self._read(); _, root = self._project(data, params.get('projectId'))
            try:
                result = self.management_db.events(project_id=params['projectId'], limit=500)
                result['events'] = [{**(event['after'] if isinstance(event.get('after'), dict) else {}), **event} for event in result['events']]
                legacy = root / '.roadmusic' / 'history.jsonl'
                if legacy.is_file() and not legacy.is_symlink():
                    if legacy.stat().st_size > MAX_JSON:
                        raise StorageError('기존 프로젝트 이력이 안전 한도를 초과했습니다.', 'history_unavailable')
                    rows = [json.loads(line) for line in legacy.read_text(encoding='utf-8').splitlines() if line.strip()]
                    result['events'].extend(reversed([row for row in rows if isinstance(row, dict)][-500:]))
                    result['events'] = result['events'][:500]
                return result
            except (ManagementDBError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise StorageError(str(error), 'corrupt_state') from error

    def lease(self, params):
        operation = params.get('operation'); project_id = params.get('projectId')
        released = None
        with self._write_lock():
            data = self._read(); self._project(data, project_id); current = data['leases'].get(project_id)
            if current and not self._lease_alive(current): data['leases'].pop(project_id, None); current = None
            if operation == 'acquire':
                if current: raise StorageError('이미 진행 중인 제작 lease가 있습니다', 'busy')
                pid = params.get('pid', os.getpid())
                if not isinstance(pid, int) or pid < 1 or not self._lease_alive({'pid': pid}): raise StorageError('실행 중인 pid가 필요합니다')
                value = {'pid': pid, 'token': secrets.token_urlsafe(32), 'createdAt': _now()}; data['leases'][project_id] = value; self._save(data)
                return {'projectId': project_id, **value}
            if operation == 'release':
                if not current or not isinstance(params.get('token'), str) or not secrets.compare_digest(current.get('token', ''), params['token']): raise StorageError('같은 lease token이 필요합니다', 'invalid_lease')
                data['leases'].pop(project_id, None); self._save(data); released = {'projectId': project_id, 'released': True}
            elif operation != 'acquire': raise StorageError('lease operation은 acquire/release만 허용합니다')
        if released is not None:
            try: released['cleanup'] = self.maybe_cleanup(project_id)
            except (StorageError, OSError) as error: released['cleanupWarning'] = str(error)
            return released

    def maybe_cleanup(self, project_id=None):
        with self._write_lock():
            self._prune_plans()
            data = self._read(); ids = [project_id] if project_id else list(data['projects'])
            skipped = []
            valid = []
            for item in ids:
                if item not in data['projects']: continue
                try: self._project(data, item); valid.append(item)
                except StorageError as error: skipped.append({'projectId': item, 'reason': str(error)})
            if not valid: return {'removedFiles': 0, 'freedBytes': 0, 'skipped': skipped, 'auditPath': None}
            preview = self._preview(data, valid, None, ['cache'], True)
        if not preview['fileCount']: return {'removedFiles': 0, 'freedBytes': 0, 'skipped': [*skipped, *preview['blocked']], 'auditPath': None}
        result = self.cleanup({'planId': preview['planId'], 'confirm': True}); result['skipped'] = [*skipped, *result['skipped']]; return result

    def dispatch(self, action, params):
        if not isinstance(action, str) or not isinstance(params, dict): raise StorageError('action과 JSON 객체가 필요합니다')
        if action == 'events':
            if set(params) - {'projectId', 'groupId', 'limit', 'cursor'}:
                raise StorageError('이력은 음악·프로젝트 ID와 페이지 범위만 지정합니다.')
            for key in ('projectId', 'groupId'):
                if key in params and (not isinstance(params[key], str) or not re.fullmatch(r'[a-f0-9]{64}', params[key])):
                    raise StorageError('이력의 음악·프로젝트 ID가 올바르지 않습니다.')
            limit = params.get('limit', 50)
            if type(limit) is not int or not 1 <= limit <= 100:
                raise StorageError('이력은 한 번에 1~100개 조회합니다.')
            cursor = params.get('cursor')
            if cursor is not None and (type(cursor) is not int or cursor < 1):
                raise StorageError('이력 페이지 커서가 올바르지 않습니다.')
            return self.management_db.events(project_id=params.get('projectId'), group_id=params.get('groupId'), limit=limit, cursor=cursor)
        if action in {'tracking', 'reconcile-preview', 'reconcile-cleanup'}:
            from storage_tracking import StorageTracking
            tracking = StorageTracking(self)
            return {'tracking': tracking.list, 'reconcile-preview': tracking.preview, 'reconcile-cleanup': tracking.cleanup}[action](params)
        if action in {'project-remove-preview', 'group-remove-preview', 'entity-remove', 'entity-recover'}:
            from storage_entity_removal import StorageEntityRemoval
            removal = StorageEntityRemoval(self)
            return {'project-remove-preview': removal.preview_project, 'group-remove-preview': removal.preview_group, 'entity-remove': removal.cleanup, 'entity-recover': removal.recover}[action](params)
        if action == 'status':
            from storage_maintenance import StorageMaintenance
            if params: raise StorageError('저장공간 상태 조회에는 입력값이 없습니다.')
            return StorageMaintenance.status(self)
        if action == 'migrate':
            if params:
                raise StorageError('저장공간 메타데이터 이전에는 입력값이 없습니다.')
            return self.migrate_management_metadata()
        if action in {'versions', 'version-diff'}:
            from delivery_store import DeliveryStore
            from storage_packaging import TRUSTED_ROOT
            store = DeliveryStore(Path(os.environ.get('ROADMUSIC_DELIVERY_ROOT', TRUSTED_ROOT)))
            return {'versions': store.versions, 'version-diff': store.diff}[action](params)
        if action in {'file-remove-preview', 'file-remove'}:
            from storage_file_removal import StorageFileRemoval
            from storage_packaging import TRUSTED_ROOT
            removal = StorageFileRemoval(self, Path(os.environ.get('ROADMUSIC_DELIVERY_ROOT', TRUSTED_ROOT)))
            return {'file-remove-preview': removal.preview, 'file-remove': removal.cleanup}[action](params)
        if action in {'project-finish-preview', 'project-finish'}:
            from storage_project_finish import ProjectFinish
            finish = ProjectFinish(self)
            return {'project-finish-preview': finish.preview, 'project-finish': finish.cleanup}[action](params)
        if action in {'restructure-status', 'restructure-preview', 'restructure-cleanup'}:
            from storage_restructure import StorageRestructure
            restructure = StorageRestructure(self)
            return {'restructure-status': restructure.status, 'restructure-preview': restructure.preview,
                    'restructure-cleanup': restructure.cleanup}[action](params)
        if action == 'overview':
            from storage_overview import StorageOverview
            return StorageOverview(self).list(params)
        if action in {'mv-list', 'mv-preview', 'mv-cleanup'}:
            from storage_mv import MVStorage
            storage = MVStorage(self)
            return {'mv-list': storage.list, 'mv-preview': storage.preview, 'mv-cleanup': storage.cleanup}[action](params)
        if action in {'sweep-preview', 'sweep-cleanup'}:
            from storage_sweep import StorageSweep
            sweep = StorageSweep(self)
            return {'sweep-preview': sweep.preview, 'sweep-cleanup': sweep.cleanup}[action](params)
        if action in {'maintenance-list', 'maintenance-preview', 'maintenance-cleanup', 'maintenance-history'}:
            from storage_maintenance import StorageMaintenance
            maintenance = StorageMaintenance(self)
            return {'maintenance-list': maintenance.list, 'maintenance-preview': maintenance.preview, 'maintenance-cleanup': maintenance.cleanup, 'maintenance-history': maintenance.history}[action](params)
        if action in {'legacy', 'adopt-preview', 'adopt'}:
            from storage_legacy import StorageLegacy
            legacy = StorageLegacy(self)
            return {'legacy': legacy.legacy, 'adopt-preview': legacy.adopt_preview, 'adopt': legacy.adopt}[action](params)
        methods = {'list': self.list, 'register': self.register, 'track': self.track, 'policy': self.policy, 'pin': self.pin, 'preview': self.preview, 'cleanup': self.cleanup, 'history': self.history, 'lease': self.lease, 'maybe_cleanup': lambda _: self.maybe_cleanup(params.get('projectId'))}
        if action not in methods: raise StorageError('지원하지 않는 storage action입니다', 'unknown_action')
        return methods[action](params)

    def list(self, params):
        with self._lock:
            data = self._read(); wanted = params.get('projectId')
            ids = [wanted] if wanted else list(data['projects']); projects = []
            for project_id in ids:
                project = data['projects'].get(project_id)
                if not isinstance(project, dict):
                    if wanted: raise StorageError('등록된 프로젝트가 아닙니다', 'not_found')
                    continue
                try:
                    current, root = self._project(data, project_id); projects.append(self._project_public(data, project_id, current, root))
                except StorageError as error:
                    projects.append({'id': project_id, 'name': project.get('name') or Path(project.get('path', '')).name, 'path': project.get('path'), 'availability': False, 'protected': True, 'error': str(error), 'state': project.get('state', 'editing'), 'preserveHistory': project.get('preserveHistory', True), 'autoCleanup': project.get('autoCleanup', True), 'retainDays': project.get('retainDays', 7), 'busy': False, 'totalBytes': 0, 'managedBytes': 0, 'reclaimableBytes': 0, 'entries': [], 'warnings': ['프로젝트 경로를 확인할 수 없어 보호합니다']})
            if wanted and not projects: raise StorageError('등록된 프로젝트가 아닙니다', 'not_found')
            disk_root = self.data_dir
            while not disk_root.exists(): disk_root = disk_root.parent
            disk = shutil.disk_usage(disk_root)
            return {'projects': projects, 'totals': {'totalBytes': sum(item['totalBytes'] for item in projects), 'reclaimableBytes': sum(item['reclaimableBytes'] for item in projects)}, 'disk': {'totalBytes': disk.total, 'freeBytes': disk.free}}


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument('action'); parser.add_argument('--json', required=True); parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args(argv)
    try:
        params = json.loads(args.json)
        if not isinstance(params, dict): raise StorageError('--json은 객체여야 합니다')
        if args.confirm: params['confirm'] = True
        result = StorageManager().dispatch(args.action, params); print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False, allow_nan=False)); return 0
    except (StorageError, json.JSONDecodeError, OSError, ValueError) as error:
        code = error.code if isinstance(error, StorageError) else 'invalid_request'
        print(json.dumps({'ok': False, 'error': {'code': code, 'message': str(error)}}, ensure_ascii=False, allow_nan=False)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
