"""Fail-closed Git object maintenance for a verified Road Music workspace.

This module intentionally knows nothing about the storage registry.  Its caller
must prove that ``root`` is the trusted workspace before exposing it in the CLI.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import selectors
import signal
import shutil
import subprocess
import tempfile
import threading
import time

from storage_manager import StorageError, _id


MINIMUM_OBJECT_AGE = 24 * 60 * 60
_MAX_ERROR = 1200
_OBJECT_TIMEOUT = 300
_GC_TIMEOUT = 600
def _digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _file_digest(path):
    if path.is_symlink() or not path.is_file():
        if not path.exists(): return None
        raise StorageError('Git 관리 파일 경로가 안전하지 않습니다', 'unsafe_git')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _trusted_git_environment(root):
    """Load only the nearest trusted .envrc; never print its environment."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    envrc = next((path / '.envrc' for path in (root, *root.parents) if (path / '.envrc').exists() or (path / '.envrc').is_symlink()), None)
    if envrc is None: return environment
    if envrc.is_symlink() or not envrc.is_file(): raise StorageError('신뢰할 수 없는 .envrc 경로입니다', 'unsafe_environment')
    try:
        result = subprocess.run(['/bin/zsh', '-f', '-c', 'set -a; source "$1" >/dev/null 2>&1 || exit 97; env -0', 'zsh', str(envrc)], capture_output=True, timeout=12, check=False, env=environment)
    except (OSError, subprocess.SubprocessError) as error:
        raise StorageError('Git 실행 환경을 준비할 수 없습니다', 'unsafe_environment') from error
    if result.returncode:
        raise StorageError('신뢰 환경을 불러올 수 없습니다', 'unsafe_environment')
    for item in result.stdout.split(b'\0'):
        key, separator, value = item.partition(b'=')
        if separator:
            try: environment[key.decode()] = value.decode()
            except UnicodeDecodeError: continue
    return {key: value for key, value in environment.items() if not key.startswith('GIT_')}


def _allocated_bytes(root):
    """Use filesystem allocation, which is intentionally separate from object sizes."""
    total = 0
    for base, directories, names in os.walk(root, followlinks=False):
        for name in [*directories, *names]:
            path = Path(base) / name
            try:
                status = path.stat(follow_symlinks=False)
            except OSError:
                continue
            if path.is_symlink():
                raise StorageError('Git objects 아래 symlink는 정리하지 않습니다', 'unsafe_git')
            if status.st_mode & 0o170000 == 0o100000:
                total += getattr(status, 'st_blocks', 0) * 512
    return total


class GitMaintenance:
    """Read first, then call Git's own GC with a fixed minimum age."""

    def __init__(self, root, now=None, runner=None, lsof=None):
        raw = Path(root)
        if not raw.is_absolute() or raw.is_symlink():
            raise StorageError('Git workspace 절대 경로가 필요합니다', 'unsafe_git')
        self.root = raw.resolve(strict=True)
        self.env = _trusted_git_environment(self.root)
        self.now = now or time.time
        self._runner = runner
        self._lsof = lsof
        self.git = shutil.which('git', path=self.env.get('PATH'))
        if not self.git:
            raise StorageError('Git 실행 파일을 찾을 수 없습니다', 'git_unavailable')

    def _run(self, args, cwd=None, check=True, timeout=90):
        command = [self.git, '-C', str(cwd or self.root), *args]
        try:
            if self._runner is not None:
                result = self._runner(command, cwd or self.root, timeout)
            else:
                result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False, env=self.env)
        except (OSError, subprocess.SubprocessError) as error:
            raise StorageError('Git 명령을 실행할 수 없습니다', 'git_unavailable') from error
        if check and result.returncode:
            raise StorageError('Git 검사 명령이 실패했습니다', 'git_failed')
        return result

    def _gc(self, args):
        """Run GC in its own process group so caller timeouts cannot orphan it."""
        command = [self.git, '-C', str(self.root), *args]
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, env=self.env)
        except OSError as error:
            raise StorageError('Git 정리를 시작할 수 없습니다', 'git_unavailable') from error
        old_handlers = {}
        def stop_child(signum, _frame):
            try: os.killpg(process.pid, signum)
            except ProcessLookupError: pass
            raise KeyboardInterrupt
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                old_handlers[signum] = signal.signal(signum, stop_child)
        try:
            _, _ = process.communicate(timeout=_GC_TIMEOUT)
        except subprocess.TimeoutExpired as error:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()
            raise StorageError('Git 정리가 시간 제한을 초과했습니다', 'git_timeout') from error
        except KeyboardInterrupt:
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()
            raise
        finally:
            for signum, handler in old_handlers.items(): signal.signal(signum, handler)
            if process.stdout: process.stdout.close()
            if process.stderr: process.stderr.close()
        if process.returncode:
            raise StorageError('Git 정리 명령이 실패했습니다', 'git_failed')

    def _path(self, value, cwd=None):
        path = Path(value.strip())
        if not path.is_absolute(): path = Path(cwd or self.root) / path
        if path.is_symlink() or path.resolve() != path:
            raise StorageError('Git 메타데이터 경로 alias는 허용하지 않습니다', 'unsafe_git')
        return path

    def _layout(self):
        inside = self._run(['rev-parse', '--is-inside-work-tree']).stdout.strip()
        if inside != 'true':
            raise StorageError('Git 작업 트리가 아닙니다', 'not_git_repository')
        common = self._path(self._run(['rev-parse', '--git-common-dir']).stdout)
        git_dir = self._path(self._run(['rev-parse', '--git-dir']).stdout)
        if any(path.is_symlink() or not path.is_dir() for path in (common, git_dir)):
            raise StorageError('Git 메타데이터 경로가 안전하지 않습니다', 'unsafe_git')
        objects = common / 'objects'
        if objects.is_symlink() or not objects.is_dir():
            raise StorageError('Git objects 경로가 안전하지 않습니다', 'unsafe_git')
        return common, git_dir, objects

    def _worktrees(self, common):
        result = self._run(['worktree', 'list', '--porcelain'])
        blocks, current, reasons = [], {}, []
        for line in result.stdout.splitlines() + ['']:
            if not line:
                if current:
                    blocks.append(current); current = {}
                continue
            key, separator, value = line.partition(' ')
            if key not in {'worktree', 'HEAD', 'branch', 'detached', 'bare', 'prunable', 'locked'} or (key in {'worktree', 'HEAD', 'branch', 'prunable', 'locked'} and not separator):
                reasons.append('worktree 목록 형식이 올바르지 않습니다'); continue
            if key in current:
                reasons.append('worktree 목록에 중복 필드가 있습니다'); continue
            current[key] = value
        found = []
        for item in blocks:
            raw = item.get('worktree')
            if not raw or item.get('prunable') or item.get('bare'):
                reasons.append('정리 대상이 아닌 누락·prunable worktree가 있습니다'); continue
            path = Path(raw)
            if not path.is_absolute() or path.is_symlink() or not path.is_dir():
                reasons.append('등록된 worktree 경로를 확인할 수 없습니다'); continue
            try:
                git_dir = self._path(self._run(['rev-parse', '--git-dir'], path).stdout, path)
                index = self._path(self._run(['rev-parse', '--git-path', 'index'], path).stdout, path)
                if git_dir.is_symlink() or not git_dir.is_dir() or index.is_symlink():
                    reasons.append('worktree Git 메타데이터 경로가 안전하지 않습니다'); continue
                found.append({'path': str(path.resolve()), 'gitDir': str(git_dir), 'index': str(index), 'locked': item.get('locked') or None, 'head': self._run(['rev-parse', '--verify', 'HEAD'], path, check=False).stdout.strip() or None, 'indexHash': _file_digest(index), 'headFileHash': _file_digest(git_dir / 'HEAD'), 'reflogHash': _file_digest(git_dir / 'logs/HEAD'), 'configWorktreeHash': _file_digest(git_dir / 'config.worktree')})
            except StorageError:
                reasons.append('worktree 메타데이터를 읽을 수 없습니다')
        if len({item['path'] for item in found}) != len(found): reasons.append('중복된 worktree 경로가 있습니다')
        if not found:
            reasons.append('유효한 worktree가 없습니다')
        return found, reasons

    @staticmethod
    def _lock_paths(common, worktrees, ignore_maintenance_lock=False):
        found = [common / name for name in ('gc.pid', 'gc.log', 'packed-refs.lock', 'HEAD.lock', 'index.lock')]
        if not ignore_maintenance_lock:
            found.append(common / 'road-music-gc.lock')
        for base in (common / 'objects' / 'pack', common / 'refs', common / 'logs', common / 'worktrees'):
            if base.exists() and not base.is_symlink():
                found.extend(path for path in base.rglob('*.lock') if not path.is_symlink())
        for item in worktrees:
            index = Path(item['index']); found.append(index.with_name(index.name + '.lock'))
        return [str(path) for path in found if path.exists()]

    def _open_writers(self, common):
        if self._lsof is not None:
            return self._lsof(common)
        try:
            result = subprocess.run(['lsof', '-t', '+D', str(common)], capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode not in {0, 1}:
            return None
        return [value for value in result.stdout.split() if value.isdigit()]

    def _unsupported_reasons(self, common):
        reasons = []
        alternates, grafts, shallow = common / 'objects/info/alternates', common / 'info/grafts', common / 'shallow'
        for path, message in ((alternates, 'alternate object store'), (grafts, 'grafts'), (shallow, 'shallow clone')):
            if path.exists() or path.is_symlink():
                if path.is_symlink() or not path.is_file() or path.stat().st_size: reasons.append(f'{message} 저장소는 자동 정리하지 않습니다')
        replace = common / 'refs/replace'
        if replace.exists() or replace.is_symlink():
            if replace.is_symlink() or any(replace.iterdir()): reasons.append('replace refs 저장소는 자동 정리하지 않습니다')
        for args, message in ((['config', '--get', 'extensions.partialClone'], 'partial clone'), (['config', '--get-regexp', r'^remote\..*\.promisor$'], 'partial clone'), (['config', '--get-all', 'gc.recentObjectsHook'], 'gc recentObjects hook'), (['config', '--get', 'gc.repackFilter'], 'gc repack filter'), (['config', '--get', 'gc.repackFilterTo'], 'gc repack filter')):
            result = self._run(args, check=False)
            if result.returncode == 0 and result.stdout.strip(): reasons.append(f'{message} 설정 저장소는 자동 정리하지 않습니다')
        return reasons

    def _state(self, common, worktrees):
        refs = self._run(['for-each-ref', '--format=%(refname) %(objectname)']).stdout.encode()
        config = common / 'config'
        reflogs = []
        logs = common / 'logs'
        if logs.exists():
            if logs.is_symlink(): raise StorageError('Git reflog 경로가 안전하지 않습니다', 'unsafe_git')
            for path in sorted(logs.rglob('*')):
                if path.is_symlink(): raise StorageError('Git reflog symlink는 정리하지 않습니다', 'unsafe_git')
                if path.is_file(): reflogs.append((str(path.relative_to(common)), _file_digest(path)))
        return {'root': str(self.root), 'commonDir': str(common), 'configHash': _file_digest(config), 'refsHash': _digest_bytes(refs), 'reflogs': reflogs, 'worktrees': worktrees}

    def _reachable(self, worktrees):
        reachable = set()
        for item in worktrees:
            result = self._run(['rev-list', '--objects', '--all', '--reflog', '--indexed-objects'], Path(item['path']))
            for line in result.stdout.splitlines():
                object_id = line.partition(' ')[0]
                if len(object_id) in {40, 64} and all(character in '0123456789abcdef' for character in object_id): reachable.add(object_id)
            # External gitlink IDs are harmless here: they never match a local object
            # unless another protected ref or index genuinely names that same object.
        return reachable, _digest_bytes(('\n'.join(sorted(reachable)) + '\n').encode())

    def _objects(self, objects, reachable, cutoff):
        command = [self.git, '-C', str(self.root), 'cat-file', '--batch-all-objects', '--batch-check=%(objectname) %(objecttype) %(objectsize) %(objectsize:disk)']
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
        except OSError as error:
            raise StorageError('Git object 목록을 읽을 수 없습니다', 'git_unavailable') from error
        total = logical = disk = unreachable = unreachable_logical = old_loose_logical = 0
        object_hash = hashlib.sha256()
        assert process.stdout is not None and process.stderr is not None
        selector, pending, stderr = selectors.DefaultSelector(), bytearray(), bytearray()
        selector.register(process.stdout, selectors.EVENT_READ, 'stdout'); selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
        deadline = time.monotonic() + _OBJECT_TIMEOUT
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise TimeoutError
                events = selector.select(remaining)
                if not events: raise TimeoutError
                for key, _ in events:
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block:
                        selector.unregister(key.fileobj); continue
                    if key.data == 'stderr':
                        stderr.extend(block[:max(0, _MAX_ERROR - len(stderr))]); continue
                    pending.extend(block)
                    while b'\n' in pending:
                        raw, _, rest = pending.partition(b'\n'); pending = bytearray(rest)
                        parts = raw.decode('ascii', 'strict').split(' ')
                        if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit(): raise ValueError
                        oid, _, size, on_disk = parts; size, on_disk = int(size), int(on_disk)
                        total += 1; logical += size; disk += on_disk; object_hash.update((oid + '\n').encode())
                        if oid not in reachable:
                            unreachable += 1; unreachable_logical += size
                            loose = objects / oid[:2] / oid[2:]
                            try:
                                if loose.is_file() and not loose.is_symlink() and loose.stat().st_mtime <= cutoff: old_loose_logical += size
                            except OSError: pass
            if pending: raise ValueError
            if process.wait(timeout=5) != 0: raise RuntimeError
        except TimeoutError as error:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
            raise StorageError('Git object 목록 검사가 시간 제한을 초과했습니다', 'git_timeout') from error
        except (UnicodeDecodeError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            if process.poll() is None: process.kill(); process.wait()
            raise StorageError('Git object 목록 검사에 실패했습니다', 'git_failed') from error
        finally:
            selector.close(); process.stdout.close(); process.stderr.close()
        return {'count': total, 'logicalBytes': logical, 'diskBytes': disk, 'unreachableCount': unreachable, 'unreachableLogicalBytes': unreachable_logical, 'oldLooseUnreachableLogicalBytes': old_loose_logical, 'fingerprint': object_hash.hexdigest()}

    def inspect(self, _ignore_maintenance_lock=False):
        common, _, objects = self._layout()
        cutoff = int(self.now()) - MINIMUM_OBJECT_AGE
        worktrees, reasons = self._worktrees(common)
        reasons.extend(self._unsupported_reasons(common))
        locks = self._lock_paths(common, worktrees, _ignore_maintenance_lock)
        if locks: reasons.append('Git 잠금 파일이 있습니다')
        writers = self._open_writers(common)
        if writers is None: reasons.append('열린 Git 파일을 안전하게 확인할 수 없습니다')
        elif [pid for pid in writers if pid != str(os.getpid())]: reasons.append('Git 파일을 사용하는 프로세스가 있습니다')
        state = self._state(common, worktrees)
        reachable, reachability = self._reachable(worktrees) if not reasons else (set(), None)
        state['reachabilityFingerprint'] = reachability
        objects_summary = self._objects(objects, reachable, cutoff) if not reasons else {'count': 0, 'logicalBytes': 0, 'diskBytes': 0, 'unreachableCount': 0, 'unreachableLogicalBytes': 0, 'oldLooseUnreachableLogicalBytes': 0, 'fingerprint': None}
        state['fingerprint'] = _id(__import__('json').dumps(state, sort_keys=True, separators=(',', ':')))
        fingerprint = _id(__import__('json').dumps({'state': state, 'objectFingerprint': objects_summary['fingerprint']}, sort_keys=True, separators=(',', ':')))
        free = shutil.disk_usage(self.root).free
        return {'schemaVersion': 1, 'root': str(self.root), 'fingerprint': fingerprint, 'state': state, 'objectsBytesAllocated': _allocated_bytes(objects), 'freeBytes': free, 'estimatedReclaimableLogicalBytes': objects_summary['oldLooseUnreachableLogicalBytes'], 'objects': objects_summary, 'blocked': bool(reasons), 'reasons': reasons, 'locks': locks, 'writerPids': [pid for pid in (writers or []) if pid != str(os.getpid())], 'cutoff': datetime.fromtimestamp(cutoff, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}

    @contextmanager
    def _maintenance_lock(self, common):
        path = common / 'road-music-gc.lock'
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise StorageError('Road Music Git 정리가 이미 진행 중입니다', 'busy') from error
        try:
            os.write(descriptor, f'{os.getpid()}\n'.encode()); yield
        finally:
            os.close(descriptor); path.unlink(missing_ok=True)

    def cleanup(self, expected_state):
        expected = expected_state.get('fingerprint') if isinstance(expected_state, dict) else expected_state
        if not isinstance(expected, str) or len(expected) != 64:
            raise StorageError('검사 결과 fingerprint가 필요합니다', 'stale_plan')
        before = self.inspect()
        if before['blocked']:
            raise StorageError('; '.join(before['reasons']), 'busy')
        if before['fingerprint'] != expected:
            raise StorageError('검사 뒤 Git 상태가 변경되었습니다', 'stale_plan')
        common = Path(before['state']['commonDir'])
        cutoff = expected_state.get('cutoff') if isinstance(expected_state, dict) else None
        if not isinstance(cutoff, str) or not cutoff.endswith('Z'):
            raise StorageError('검사 결과의 고정 cutoff가 필요합니다', 'stale_plan')
        with self._maintenance_lock(common):
            recheck = self.inspect(True)
            if recheck['blocked'] or recheck['fingerprint'] != expected:
                raise StorageError('정리 직전 Git 상태가 변경되었습니다', 'stale_plan')
            with tempfile.TemporaryDirectory(prefix='road-music-empty-git-hooks-') as hooks:
                self._gc(['-c', 'gc.auto=0', '-c', 'gc.packRefs=false', '-c', 'gc.reflogExpire=never', '-c', 'gc.reflogExpireUnreachable=never', '-c', 'gc.worktreePruneExpire=never', '-c', 'gc.rerereResolved=never', '-c', 'gc.rerereUnresolved=never', '-c', 'gc.writeCommitGraph=false', '-c', 'gc.pruneExpire=' + cutoff, '-c', 'core.hooksPath=' + hooks, 'gc', '--no-detach', '--quiet', '--prune=' + cutoff])
        after = self.inspect()
        if after['blocked']:
            raise StorageError('정리 후 Git 상태를 검증할 수 없습니다: ' + '; '.join(after['reasons']), 'git_failed')
        if after['state']['fingerprint'] != before['state']['fingerprint']:
            raise StorageError('Git refs·reflog·index 또는 worktree 상태가 변경되어 보존 검증에 실패했습니다', 'preservation_failed')
        fsck = self._run(['fsck', '--connectivity-only', '--no-dangling'], check=False, timeout=180)
        if fsck.returncode:
            raise StorageError('정리 후 Git 연결성 검증에 실패했습니다', 'preservation_failed')
        freed = max(0, before['objectsBytesAllocated'] - after['objectsBytesAllocated'])
        return {'beforeRepoObjectAllocatedBytes': before['objectsBytesAllocated'], 'afterRepoObjectAllocatedBytes': after['objectsBytesAllocated'], 'freedAllocatedBytes': freed, 'diskFreeDeltaBytes': after['freeBytes'] - before['freeBytes'], 'removedObjects': max(0, before['objects']['count'] - after['objects']['count']), 'removedLogicalBytes': max(0, before['objects']['logicalBytes'] - after['objects']['logicalBytes']), 'preservation': {'passed': True, 'stateFingerprint': after['state']['fingerprint'], 'reachableObjectsBefore': before['objects']['count'] - before['objects']['unreachableCount'], 'reachableObjectsAfter': after['objects']['count'] - after['objects']['unreachableCount']}, 'warnings': ['pack 안의 미참조 객체는 사전 논리 추정치에 포함하지 않았습니다'] if before['objects']['unreachableLogicalBytes'] > before['objects']['oldLooseUnreachableLogicalBytes'] else []}
