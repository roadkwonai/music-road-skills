"""Narrow, proof-based adoption of legacy producer cache into managed cache."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import time
from contextlib import contextmanager

from storage_manager import MAX_TRACK_FILES, StorageError, _atomic_json, _bounded_files, _id, _json_read, _snapshot


NAME = re.compile(r'(.+)-picture(?:\.mp4|\.parts)\Z')
PLAN_TTL = 15 * 60
MAX_REFERENCE_FILE_BYTES = 16 * 1024 * 1024
MAX_REFERENCE_BYTES = 64 * 1024 * 1024


def _probe(path):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(path)], capture_output=True, text=True, timeout=8, check=True)
        value = json.loads(result.stdout); streams = {item.get('codec_type') for item in value.get('streams', [])}
        return {'video': 'video' in streams, 'audio': 'audio' in streams, 'duration': float(value.get('format', {}).get('duration', 0))}
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
        return {'video': False, 'audio': False, 'duration': 0}


def _open(path):
    try:
        result = subprocess.run(['lsof', '-t', '--', str(path)], capture_output=True, text=True, timeout=3, check=False)
        return result.returncode not in {0, 1} or bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return True


def _open_tree(path):
    try:
        result = subprocess.run(['lsof', '-t', '+D', str(path)], capture_output=True, text=True, timeout=6, check=False)
        return result.returncode not in {0, 1} or bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return True


def _hash_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def producer_profile(root):
    production, playlist = _json_read(root / 'production.json', None), _json_read(root / 'playlist.json', None)
    if isinstance(production, dict) and production.get('schemaVersion') == 1:
        if isinstance(playlist, dict) and playlist.get('schemaVersion') == 1:
            return {'name': 'production+playlist', 'proofs': [root / 'production.json', root / 'playlist.json']}
        preset = _json_read(root / 'preset.json', None)
        if isinstance(preset, dict) and preset.get('schemaVersion') == 1 and isinstance(preset.get('id'), str) and production.get('presetId') == preset['id'] and production.get('presetSha256') == _hash_file(root / 'preset.json'):
            return {'name': 'production+preset', 'proofs': [root / 'production.json', root / 'preset.json']}
    state, project = _json_read(root / 'production-state.json', None), _json_read(root / 'project.json', None)
    if isinstance(project, dict) and all(type(project.get(key)) in {int, float} and project[key] > 0 for key in ('width', 'height', 'fps', 'duration')) and isinstance(state, dict) and state.get('status') == 'complete' and state.get('finalQa') == 'pass' and state.get('delivery') == 'pass' and state.get('pending') == []:
        return {'name': 'native-complete-parts', 'duration': project['duration'], 'proofs': [root / 'project.json', root / 'production-state.json', root / 'qa/delivery-check.json']}
    return None


class StorageLegacy:
    def __init__(self, manager, probe=None, open_check=None):
        self.manager = manager
        self.probe = probe or _probe
        self.open_check = open_check

    def _project(self, project_id):
        with self.manager._write_lock():
            data = self.manager._read(); return self.manager._project(data, project_id)

    @staticmethod
    def _valid_marker(root):
        return producer_profile(root) is not None

    def _candidate(self, project_id, root, source):
        from storage_packaging import is_workspace, PackagingStorage
        if is_workspace(root):
            try:
                closed = (lambda path: not self.open_check(path)) if self.open_check else None
                return PackagingStorage(root, open_check=closed).candidate(project_id, source)
            except (OSError, StorageError): return None
        match = NAME.fullmatch(source.name)
        if not match or source.parent != root / 'out' or (root / 'out').is_symlink() or source.is_symlink(): return None
        profile = producer_profile(root)
        if profile is None: return None
        if profile['name'] == 'production+preset' and not source.is_file(): return None
        if profile['name'] == 'native-complete-parts' and not source.is_dir(): return None
        final = root / 'out' / f'{match[1]}.mp4'
        delivery_snapshots = []
        if profile['name'] == 'native-complete-parts':
            receipt = _json_read(root / 'qa/delivery-check.json', None)
            if not (isinstance(receipt, dict) and receipt.get('pass') is True and receipt.get('sourceUnchanged') is True and receipt.get('lyricsUnchanged') is True and receipt.get('decodeXerror') == 'pass' and isinstance(receipt.get('files'), dict) and 2 <= len(receipt['files']) <= 16): return None
            deliveries = []
            for item in receipt['files'].values():
                if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not isinstance(item.get('sha256'), str) or type(item.get('bytes')) is not int: return None
                candidate = Path(item['path'])
                try:
                    if candidate.parent != root / 'out' or candidate.suffix.lower() != '.mp4': return None
                    before = _snapshot(candidate)
                    if before['bytes'] != item['bytes'] or _hash_file(candidate) != item['sha256'] or _snapshot(candidate) != before: return None
                    media = self.probe(candidate)
                    if not (media.get('video') and media.get('audio') and abs(media.get('duration', -1) - profile['duration']) <= 1): return None
                    deliveries.append(candidate); delivery_snapshots.append(before)
                except (OSError, StorageError): return None
            if len(set(deliveries)) != len(deliveries): return None
            final = deliveries[0]
        if not final.is_file() or final.is_symlink(): return None
        check = self.probe(final)
        if not (check.get('video') and check.get('audio') and isinstance(check.get('duration'), (int, float)) and check['duration'] > 0): return None
        try: final_snapshot = _snapshot(final)
        except StorageError: return None
        protected = self.manager._protected_paths(root)
        if any(source == item or item in source.parents for item in protected): return None
        if self._text_references(root, source): return None
        try: leaves = _bounded_files(source)
        except StorageError: return None
        if not leaves or any(item.is_symlink() for item in leaves): return None
        if self.open_check:
            if any(self.open_check(item) for item in leaves): return None
        elif (_open_tree(source) if source.is_dir() else _open(source)): return None
        try:
            files = []
            aggregate = source if source.is_file() else source.parent / f'{match[1]}-picture.mp4'
            if not aggregate.is_file() or aggregate.is_symlink(): return None
            aggregate_snapshot = _snapshot(aggregate)
            picture = self.probe(aggregate)
            if not (picture.get('video') and not picture.get('audio') and isinstance(picture.get('duration'), (int, float)) and picture['duration'] > 0 and abs(picture['duration'] - check['duration']) <= 1): return None
            segment_names = set()
            for item in leaves:
                if item.stat(follow_symlinks=False).st_mode & 0o111: return None
                if source.is_dir() and (item.suffix.casefold() not in {'.mp4', '.txt', '.json'} or (item.suffix.casefold() == '.txt' and item.name != 'concat.txt') or (item.suffix.casefold() == '.json' and item.name != 'settings.json')): return None
                if source.is_dir() and item.suffix.casefold() == '.mp4':
                    if not re.fullmatch(r'seg_\d{6}_\d{6}\.mp4', item.name): return None
                    segment_names.add(item.name)
                value = _snapshot(item); value['relativePath'] = str(item.relative_to(root)); value['leafPath'] = str(item.relative_to(source.parent)); files.append(value)
            if source.is_dir() and not self._valid_parts_manifest(source, segment_names): return None
        except (OSError, StorageError): return None
        try: proof_digest = _id('\0'.join(_hash_file(path) for path in profile['proofs']) + json.dumps(delivery_snapshots, sort_keys=True))
        except OSError: return None
        fingerprint = _id(project_id + '\0' + str(source.relative_to(root)) + '\0' + proof_digest + '\0' + f"{final_snapshot['dev']}:{final_snapshot['inode']}:{final_snapshot['bytes']}:{final_snapshot['mtimeNs']}:{aggregate_snapshot['dev']}:{aggregate_snapshot['inode']}:{aggregate_snapshot['bytes']}:{aggregate_snapshot['mtimeNs']}:{check['duration']}:{picture['duration']}" + '\0' + '\0'.join(f"{item['inode']}:{item['bytes']}:{item['mtimeNs']}" for item in files))
        return {'id': fingerprint, 'projectId': project_id, 'relativePath': str(source.relative_to(root)), 'bytes': sum(item['bytes'] for item in files), 'fileCount': len(files), 'description': '검증된 기존 picture 렌더 캐시', 'evidence': {'final': str(final.relative_to(root)), 'duration': check['duration'], 'producer': profile['name']}, 'files': files, 'final': final_snapshot}

    @staticmethod
    def _valid_parts_manifest(source, segments):
        try:
            settings = json.loads((source / 'settings.json').read_text(encoding='utf-8'))
            required = {'scale', 'sub', 'shutter', 'format', 'crf', 'fps', 'W', 'H', 'code'}
            if not isinstance(settings, dict) or set(settings) != required: return False
            if not isinstance(settings['scale'], (int, float)) or not isinstance(settings['sub'], int) or not isinstance(settings['shutter'], (int, float)) or not isinstance(settings['format'], str) or not isinstance(settings['crf'], str) or not isinstance(settings['fps'], (int, float)) or not isinstance(settings['W'], int) or not isinstance(settings['H'], int) or not isinstance(settings['code'], str): return False
            names = []
            for line in (source / 'concat.txt').read_text(encoding='utf-8').splitlines():
                value = line.strip()
                if value.startswith('file '): value = value[5:].strip().strip("'\"")
                if not value: continue
                item = Path(value)
                if item.is_absolute():
                    resolved = item.resolve(strict=True)
                    if resolved.parent != source: return False
                    value = resolved.name
                elif item.name != value or '/' in value or '\\' in value: return False
                names.append(value)
            return bool(names) and len(names) == len(set(names)) and set(names) == segments
        except (OSError, ValueError, json.JSONDecodeError): return False

    @staticmethod
    def _text_references(root, source):
        needles = [str(source.relative_to(root)).encode(), str(source).encode()]
        seen = used = 0
        for path in root.rglob('*'):
            seen += 1
            if seen > MAX_TRACK_FILES: return True
            if '.roadmusic' in path.relative_to(root).parts: continue
            if path == source or source in path.parents: continue
            if not path.is_file() or path.is_symlink() or path.suffix.casefold() not in {'.json', '.txt', '.concat', '.js', '.mjs', '.cjs', '.py', '.html', '.css', '.md', '.sh', '.yaml', '.yml'}: continue
            try:
                size = path.stat().st_size
                if size > MAX_REFERENCE_FILE_BYTES or used + size > MAX_REFERENCE_BYTES: return True
                read_bytes = 0; tail = b''
                with path.open('rb') as stream:
                    while chunk := stream.read(65536):
                        read_bytes += len(chunk); used += len(chunk)
                        if read_bytes > MAX_REFERENCE_FILE_BYTES or used > MAX_REFERENCE_BYTES: return True
                        data = tail + chunk
                        if any(needle in data for needle in needles): return True
                        tail = data[-max(len(item) for item in needles):]
            except OSError: return True
        return False

    @staticmethod
    def _open_child(directory, name, create=False):
        flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        if create:
            try: os.mkdir(name, 0o700, dir_fd=directory)
            except FileExistsError: pass
        return os.open(name, flags, dir_fd=directory)

    @contextmanager
    def _rename_target(self, root, relative, candidate_id):
        """Atomically move one verified producer root through no-follow directory FDs."""
        nofollow = getattr(os, 'O_NOFOLLOW', 0)
        root_fd = os.open(root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | nofollow)
        source_fd = legacy_fd = target_fd = None
        parts = Path(relative).parts
        try:
            source_fd = root_fd
            for name in parts[:-1]:
                next_fd = self._open_child(source_fd, name)
                if source_fd != root_fd: os.close(source_fd)
                source_fd = next_fd
            legacy_fd = root_fd
            for name in ('.roadmusic', 'cache', 'legacy'):
                next_fd = self._open_child(legacy_fd, name, create=True)
                if legacy_fd != root_fd: os.close(legacy_fd)
                legacy_fd = next_fd
            target_fd = self._open_child(legacy_fd, candidate_id, create=True)
            source_name = parts[-1]
            if os.stat(source_name, dir_fd=source_fd, follow_symlinks=False).st_mode & 0o170000 not in {0o100000, 0o040000}: raise StorageError('legacy 원본 종류가 안전하지 않습니다', 'unsafe_path')
            try: os.stat(source_name, dir_fd=target_fd, follow_symlinks=False); raise StorageError('legacy 대상이 이미 존재합니다', 'unsafe_path')
            except FileNotFoundError: pass
            os.rename(source_name, source_name, src_dir_fd=source_fd, dst_dir_fd=target_fd)
            target = root / '.roadmusic/cache/legacy' / candidate_id
            try:
                yield target
            except Exception:
                os.rename(source_name, source_name, src_dir_fd=target_fd, dst_dir_fd=source_fd)
                raise
        finally:
            for descriptor in {item for item in (target_fd, legacy_fd, source_fd, root_fd) if item is not None}:
                try: os.close(descriptor)
                except OSError: pass

    def _sources(self, root):
        from storage_packaging import is_workspace, PackagingStorage
        if is_workspace(root):
            closed = (lambda path: not self.open_check(path)) if self.open_check else None
            return [item[0] for item in PackagingStorage(root, open_check=closed).sources()]
        out = root / 'out'
        if not out.is_dir() or out.is_symlink(): return []
        return [source for source in sorted(out.iterdir()) if NAME.fullmatch(source.name)]

    def legacy(self, params):
        project, root = self._project(params.get('projectId'))
        blocked, candidates = [], []
        for source in self._sources(root):
            candidate = self._candidate(params['projectId'], root, source)
            if candidate: candidates.append(candidate)
            else: blocked.append({'relativePath': str(source.relative_to(root)), 'reason': '완성본·producer 근거·안전 검증을 통과하지 못했습니다'})
        return {'candidates': [{key: value for key, value in item.items() if key != 'files'} for item in candidates], 'blocked': blocked}

    def _plan_path(self, plan_id):
        return self.manager._plan_path(plan_id)

    def _track_locked(self, data, project_id, project, root, target, description='검증된 legacy picture 캐시'):
        relative = str(target.relative_to(root))
        raw, resolved = self.manager._managed_path(root, relative, allow_dir=True)
        files = self.manager._entry_files(root, raw, resolved, self.manager._protected_paths(root))
        entry_id = _id(project_id + '\0' + relative + '\0cache')
        for other_id, other in project['entries'].items():
            if other_id == entry_id: continue
            other_path = Path(other['relativePath']); target_path = Path(relative)
            if target_path == other_path or target_path in other_path.parents or other_path in target_path.parents: raise StorageError('서로 겹치는 관리 항목은 중복 등록할 수 없습니다', 'overlapping_entry')
        previous = project['entries'].get(entry_id, {})
        entry = {'id': entry_id, 'relativePath': relative, 'kind': 'cache', 'description': description, 'reproducible': True, 'pinned': bool(previous.get('pinned')), 'isDirectory': resolved.is_dir(), 'files': files, 'lastUsedAt': int(time.time())}
        project['entries'][entry_id] = entry
        try:
            self.manager._audit(root, 'track', {'entryId': entry_id, 'kind': 'cache', 'files': len(files)})
            self.manager._save(data)
        except Exception:
            if previous: project['entries'][entry_id] = previous
            else: project['entries'].pop(entry_id, None)
            raise
        return next(item for item in self.manager._project_public(data, project_id, project, root)['entries'] if item['id'] == entry_id)

    def adopt_preview(self, params):
        selected = params.get('candidateIds')
        if not isinstance(selected, list) or not selected or not all(isinstance(item, str) for item in selected): raise StorageError('candidateIds가 필요합니다')
        # Rebuild private snapshots only for the selected opaque IDs.
        _, root = self._project(params['projectId']); detailed = []
        for source in self._sources(root):
            candidate = self._candidate(params['projectId'], root, source)
            if candidate and candidate['id'] in selected: detailed.append(candidate)
        found = {item['id'] for item in detailed}; blocked = [{'id': item, 'reason': '현재 검증된 legacy 후보가 아닙니다'} for item in selected if item not in found]
        plan_id = os.urandom(24).hex(); plan = {'schemaVersion': 1, 'type': 'legacy-adopt', 'id': plan_id, 'state': 'ready', 'expiresAt': int(time.time()) + PLAN_TTL, 'projectId': params['projectId'], 'candidates': detailed}
        _atomic_json(self._plan_path(plan_id), plan)
        entries = [{'id': item['id'], 'source': item['relativePath'], 'target': f".roadmusic/cache/legacy/{item['id']}", 'bytes': item['bytes'], 'fileCount': item['fileCount']} for item in detailed]
        return {'planId': plan_id, 'entries': entries, 'bytes': sum(item['bytes'] for item in detailed), 'fileCount': sum(item['fileCount'] for item in detailed), 'blocked': blocked, 'expiresAt': plan['expiresAt']}

    def adopt(self, params):
        if params.get('confirm') is not True: raise StorageError('adopt에는 confirm:true가 필요합니다', 'confirmation_required')
        plan_id = params.get('planId')
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id): raise StorageError('planId가 올바르지 않습니다')
        path = self._plan_path(plan_id)
        with self.manager._write_lock():
            plan = _json_read(path, None)
            if not isinstance(plan, dict) or plan.get('type') != 'legacy-adopt' or plan.get('id') != plan_id or plan.get('state', 'ready') != 'ready' or plan.get('expiresAt', 0) < time.time(): raise StorageError('유효한 legacy 이전 계획이 아닙니다', 'invalid_plan')
            data = self.manager._read(); project, root = self.manager._project(data, plan['projectId'])
            if self.manager._busy(data, plan['projectId']): raise StorageError('진행 중인 제작 lease가 있습니다', 'busy')
            self.manager._audit(root, 'legacy-adopt-intent', {'planId': plan_id, 'entries': [{'relativePath': item['relativePath'], 'kind': 'cache'} for item in plan['candidates']]})
            plan['state'] = 'in-progress'; _atomic_json(path, plan)
            moved, skipped, targets, warnings = 0, [], [], []
            try:
                for candidate in sorted(plan['candidates'], key=lambda item: (not item['relativePath'].endswith('.parts'), item['relativePath'])):
                    current = self._candidate(plan['projectId'], root, root / candidate['relativePath'])
                    if current is None or current['id'] != candidate['id']:
                        skipped.append({'relativePath': candidate['relativePath'], 'reason': '계획 뒤 후보가 변경되었습니다'}); continue
                    try:
                        with self._rename_target(root, candidate['relativePath'], candidate['id']) as target_root:
                            tracked = self._track_locked(data, plan['projectId'], project, root, target_root, candidate['description'])
                        targets.append(tracked); moved += candidate['fileCount']
                    except (OSError, StorageError) as error:
                        skipped.append({'relativePath': candidate['relativePath'], 'reason': str(error)})
                try:
                    self.manager._audit(root, 'legacy-adopt', {'planId': plan_id, 'movedFiles': moved, 'entries': [{'relativePath': item['relativePath'], 'kind': 'cache'} for item in targets]})
                except (StorageError, OSError) as error:
                    warnings.append(f'감사 완료 기록 실패: {error}')
                path.unlink(missing_ok=True)
            except Exception:
                plan['state'] = 'failed'; _atomic_json(path, plan); raise
            return {'movedFiles': moved, 'entries': targets, 'skipped': skipped, 'warnings': warnings, 'auditPath': str(root / '.roadmusic/history.jsonl')}


def main(argv=None):
    # Keep the public JSON envelope and action parser in one place.
    from storage_manager import main as storage_main
    return storage_main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
