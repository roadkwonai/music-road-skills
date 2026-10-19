"""Move the one verified legacy YuE2 MLX runtime out of ``Output`` safely.

This module intentionally only recognises the known legacy integration root.  It
never removes that root: the caller may retire it only after this module returns
a verified canonical replacement.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import stat
import subprocess
from urllib.parse import quote, unquote, urlparse

from storage_manager import MAX_JSON, StorageError


LEGACY_ENGINE = Path('Output/yue-mlx-integration-20261017/data/engines/yue-mlx')
LEGACY_ASR = Path('Output/female-ballads-20261016/evaluation/asr/ggml-large-v3-turbo.bin')
WEIGHT_SUFFIXES = frozenset({'.safetensors', '.gguf', '.ggml', '.ckpt', '.pt', '.pth', '.bin', '.onnx', '.h5', '.tflite', '.npz', '.npy'})
TRUSTED_PATH_FIELDS = frozenset({'model', 'vae', 'path', 'root', 'yueMlxRoot', 'yueMlxModels', 'yueMlxVae', 'yueMlxPython', 'yueMlxSrc', 'yueMlxManifest'})
ACTIVATION_FILES = frozenset({'venv/bin/activate', 'venv/bin/activate.bat', 'venv/bin/activate.csh', 'venv/bin/activate.fish', 'venv/bin/activate.nu'})
REQUIRED_MODEL_FILES = frozenset({'conversion.json', 'config.json', 'ar-8bit.safetensors', 'ar-bf16.safetensors', 'nar-bf16.safetensors', 'qwen.tiktoken'})
REQUIRED_VAE_FILES = frozenset({'config.json', 'model.safetensors'})
TEXT_SUFFIXES = frozenset({'.py', '.pyw', '.sh', '.bash', '.zsh', '.fish', '.csh', '.nu', '.bat', '.ps1', '.pth', '.cfg', '.ini', '.json', '.toml', '.yaml', '.yml', '.txt', '.md'})


def _sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _allocated(path):
    return Path(path).stat(follow_symlinks=False).st_blocks * 512


def _inside(path, root):
    return path == root or root in path.parents


class RuntimeRescue:
    """Plans and atomically installs the current YuE2 MLX runtime in app data."""

    def __init__(self, root, data_dir):
        self.root = self._directory(root, '작업 폴더')
        self.data_dir = self._directory(data_dir, '앱 데이터 폴더', allow_missing=True)
        self.source = self.root / LEGACY_ENGINE
        self.target = self.data_dir / 'engines' / 'yue-mlx'

    @staticmethod
    def _directory(value, label, allow_missing=False):
        raw = Path(value)
        if not raw.is_absolute() or raw.is_symlink() or (raw.exists() and not raw.is_dir()):
            raise StorageError(f'{label} 경로가 안전하지 않습니다.', 'unsafe_path')
        if not raw.exists() and not allow_missing:
            raise StorageError(f'{label}을 찾을 수 없습니다.', 'missing_runtime')
        return raw.resolve(strict=not allow_missing)

    def _source_root(self):
        if self.source.is_symlink() or not self.source.is_dir() or self.source.resolve(strict=True) != self.source:
            raise StorageError('검증된 레거시 YuE2 MLX 설치만 이전할 수 있습니다.', 'unsafe_runtime')
        if self.target.exists() or self.target.is_symlink():
            raise StorageError('현재 앱 데이터에 YuE2 MLX 설치가 이미 있어 이전하지 않습니다.', 'target_exists')
        return self.source

    def _runtime_entries(self):
        standalone = self.root / LEGACY_ASR
        return {'source': self.source.exists() or self.source.is_symlink(),
                'target': self.target.exists() or self.target.is_symlink(),
                'standalone': standalone.exists() or standalone.is_symlink()}

    def _not_required_plan(self):
        entries = self._runtime_entries()
        if any(entries.values()):
            raise StorageError('부분 YuE2 MLX 설치는 자동으로 건너뛰지 않습니다.', 'partial_runtime')
        return {'schema': 1, 'source': str(self.source), 'target': str(self.target), 'items': [], 'moves': [],
                'preservedModels': [], 'activeProcesses': [], 'notRequired': True, 'runtimeEntries': entries}

    def _standalone_model(self):
        source = self.root / LEGACY_ASR
        if not source.exists():
            return None
        if source.is_symlink() or not source.is_file() or source.suffix.lower() not in WEIGHT_SUFFIXES:
            raise StorageError('독립 음성 인식 모델 경로가 안전하지 않습니다.', 'unsafe_runtime')
        target = self.data_dir / 'models' / 'asr' / source.name
        if target.exists() or target.is_symlink():
            raise StorageError('현재 앱 데이터에 음성 인식 모델이 이미 있어 이전하지 않습니다.', 'target_exists')
        return {'relativePath': str(LEGACY_ASR), 'source': str(source), 'target': str(target), 'snapshot': self._snapshot(source)}

    def _manifest(self, source, allowed_root=None):
        path = source / 'paths.json'
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
            raise StorageError('YuE2 MLX 경로 정보가 안전하지 않습니다.', 'unsafe_runtime')
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StorageError('YuE2 MLX 경로 정보를 읽을 수 없습니다.', 'unsafe_runtime') from error
        if not isinstance(value, dict) or value.get('schema') != 1:
            raise StorageError('검증된 YuE2 MLX 경로 정보가 아닙니다.', 'unsafe_runtime')
        for key in ('model', 'vae'):
            raw = value.get(key)
            if not isinstance(raw, str):
                raise StorageError('YuE2 MLX 모델 경로가 없습니다.', 'unsafe_runtime')
            try:
                actual = Path(raw).resolve(strict=True)
            except OSError as error:
                raise StorageError('YuE2 MLX 모델 경로가 유효하지 않습니다.', 'unsafe_runtime') from error
            if not _inside(actual, allowed_root or self.root) or not actual.is_dir():
                raise StorageError('작업 폴더 밖의 YuE2 MLX 모델은 이전하지 않습니다.', 'unsafe_runtime')
        return value

    @staticmethod
    def _snapshot(path):
        entry = Path(path).lstat()
        if not stat.S_ISREG(entry.st_mode):
            raise StorageError('일반 파일이 아닌 YuE2 MLX 항목은 이전하지 않습니다.', 'unsafe_runtime')
        return {'bytes': entry.st_size, 'mtimeNs': entry.st_mtime_ns, 'dev': entry.st_dev, 'inode': entry.st_ino, 'mode': stat.S_IMODE(entry.st_mode), 'sha256': _sha256(path)}

    @staticmethod
    def _regenerable_pyc(path):
        path = Path(path)
        if path.suffix != '.pyc':
            return False
        try: source = Path(importlib.util.source_from_cache(str(path)))
        except (ValueError, NotImplementedError): return False
        return source.is_file() and not source.is_symlink()

    def _items(self, source):
        items, skipped, generated, seen = [], [], [], set()
        for base, directories, names in os.walk(source, followlinks=False):
            base_path = Path(base)
            for directory in list(directories):
                item = base_path / directory
                if item.is_symlink():
                    relative = item.relative_to(source).as_posix()
                    if relative == 'hf-cache' or relative.startswith('hf-cache/'):
                        directories.remove(directory)
                        skipped.append(relative)
                        continue
                    raise StorageError('YuE2 MLX 폴더 symlink는 이전하지 않습니다.', 'unsafe_runtime')
            for name in names:
                item = base_path / name
                relative = item.relative_to(source).as_posix()
                if relative in seen:
                    raise StorageError('YuE2 MLX 파일 목록이 중복됐습니다.', 'unsafe_runtime')
                seen.add(relative)
                if self._regenerable_pyc(item):
                    generated.append(relative)
                    continue
                if item.is_symlink():
                    try:
                        actual = item.resolve(strict=True)
                    except OSError as error:
                        # The old profile's HF cache is already broken and runtime
                        # loading uses the verified local models/ and vae/ trees.
                        if relative == 'hf-cache' or relative.startswith('hf-cache/'):
                            skipped.append(relative)
                            continue
                        raise StorageError('끊긴 YuE2 MLX symlink는 이전하지 않습니다.', 'unsafe_runtime') from error
                    if not actual.is_file() or actual.is_symlink():
                        raise StorageError('일반 파일이 아닌 YuE2 MLX symlink는 이전하지 않습니다.', 'unsafe_runtime')
                    materialize = _inside(actual, self.root)
                    if not materialize and not _inside(actual, self.data_dir):
                        raise StorageError('앱 데이터 밖 YuE2 MLX 실행 링크는 이전하지 않습니다.', 'unsafe_runtime')
                    snapshot = self._snapshot(actual)
                    items.append({'relativePath': relative, 'kind': 'materialize' if materialize else 'link',
                                  'link': os.readlink(item), 'resolved': str(actual), 'snapshot': snapshot})
                else:
                    value = {'relativePath': relative, 'kind': 'file', 'snapshot': self._snapshot(item)}
                    rebase = self._rebase_kind(item, relative, source)
                    if rebase:
                        value['rebaseKind'] = rebase
                        value['rebase'] = self._content_snapshot(self._rebased_bytes(value, item.read_bytes(), source), value['snapshot']['mode'])
                    items.append(value)
        if not items:
            raise StorageError('YuE2 MLX 설치에 파일이 없습니다.', 'missing_runtime')
        return sorted(items, key=lambda item: item['relativePath']), sorted(skipped), sorted(generated)

    @staticmethod
    def _content_snapshot(value, mode=None):
        result = {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
        if mode is not None:
            result['mode'] = mode
        return result

    def _rebase_kind(self, path, relative, source):
        editable_candidate = Path(relative).name == '_editable_impl_mlx_yue.pth'
        direct_candidate = relative == 'venv/lib/python3.12/site-packages/mlx_yue-0.1.0.dist-info/direct_url.json'
        if relative not in ACTIVATION_FILES and not relative.startswith('venv/bin/') and not editable_candidate and not direct_candidate:
            return None
        data = Path(path).read_bytes()
        source_root = str(source).encode('utf-8')
        if relative in ACTIVATION_FILES:
            return 'activation' if data.count(str(source / 'venv').encode('utf-8')) == 1 else None
        if relative.startswith('venv/bin/'):
            lines = data.splitlines(keepends=True)
            interpreters = {b'#!' + str(source / 'venv/bin' / name).encode('utf-8') for name in ('python', 'python3', 'python3.12')}
            if lines and lines[0].rstrip(b'\r\n') in interpreters and source_root not in b''.join(lines[1:]):
                return 'console'
        parent = Path(relative).parent
        if editable_candidate and len(parent.parts) >= 4 and parent.parts[:2] == ('venv', 'lib') and parent.parts[-1] == 'site-packages':
            lines = [line for line in data.splitlines() if line]
            if lines and all(line.startswith(source_root + b'/') and b'\x00' not in line and (source / line.decode('utf-8').removeprefix(str(source) + '/')).is_dir() for line in lines):
                return 'editable'
        if direct_candidate:
            try: value = json.loads(data.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError): return None
            parsed = urlparse(value.get('url', '')) if isinstance(value, dict) else None
            expected = {'url': f"file://{quote(str(source / 'src'))}", 'dir_info': {'editable': True}}
            if value == expected and parsed.scheme == 'file' and not parsed.netloc and Path(unquote(parsed.path)) == source / 'src':
                return 'direct-url'
        return None

    def _rebased_bytes(self, item, original, source):
        source_venv, target_venv = str(source / 'venv').encode('utf-8'), str(self.target / 'venv').encode('utf-8')
        kind = item.get('rebaseKind')
        if kind == 'activation':
            rebased = original.replace(source_venv, target_venv)
        elif kind == 'console':
            first, *rest = original.splitlines(keepends=True)
            interpreter = first.rstrip(b'\r\n').removeprefix(b'#!' + source_venv + b'/bin/')
            if interpreter not in {b'python', b'python3', b'python3.12'}:
                raise StorageError(f"콘솔 실행 파일 인터프리터가 안전하지 않습니다: {item['relativePath']}", 'unsafe_runtime')
            command = shlex.quote(str(self.target / 'venv/bin' / interpreter.decode('ascii'))).encode('utf-8')
            header = b"#!/bin/sh\n" + b"'''exec' " + command + b' "$0" "$@"\n' + b"' '''\n"
            rebased = header + b''.join(rest)
        elif kind == 'editable':
            rebased = original.replace(str(source).encode('utf-8') + b'/', str(self.target).encode('utf-8') + b'/')
        elif kind == 'direct-url':
            rebased = json.dumps({'url': f"file://{quote(str(self.target / 'src'))}", 'dir_info': {'editable': True}}, separators=(',', ':')).encode('utf-8')
        else:
            raise StorageError(f"경로 재작성 종류가 안전하지 않습니다: {item['relativePath']}", 'unsafe_runtime')
        if str(source).encode('utf-8') in rebased:
            raise StorageError(f"경로 재작성에 실패했습니다: {item['relativePath']}", 'unsafe_runtime')
        return rebased

    def _active_processes(self, source):
        try:
            result = subprocess.run(['ps', '-axo', 'pid=,command='], text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, check=False, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return []
        needle = str(source)
        matches = []
        for row in result.stdout.splitlines():
            if needle in row:
                pid, _, command = row.strip().partition(' ')
                if pid.isdigit(): matches.append({'pid': int(pid), 'command': command[:500]})
        return matches

    def plan(self):
        entries = self._runtime_entries()
        if not any(entries.values()):
            return self._not_required_plan()
        if entries['source'] and entries['target']:
            return self._canonical_plan(source=self.source)
        if not entries['source'] and entries['target']:
            return self._canonical_plan()
        if not entries['source']:
            raise StorageError('YuE2 MLX 모델만 남은 부분 설치는 자동으로 건너뛰지 않습니다.', 'partial_runtime')
        source = self._source_root()
        manifest = self._manifest(source)
        items, skipped, generated = self._items(source)
        models = []
        for item in items:
            resolved = Path(item.get('resolved') or source / item['relativePath'])
            if resolved.suffix.lower() in WEIGHT_SUFFIXES:
                models.append({'relativePath': item['relativePath'], 'sha256': item['snapshot']['sha256'], 'bytes': item['snapshot']['bytes']})
        source_manifest = self._snapshot(source / 'paths.json')
        standalone = self._standalone_model()
        if standalone:
            models.append({'relativePath': str(Path('models/asr') / LEGACY_ASR.name), 'sha256': standalone['snapshot']['sha256'], 'bytes': standalone['snapshot']['bytes']})
        moves = [{'source': str(source / item['relativePath']), 'target': str(self.target / item['relativePath'])} for item in items]
        if standalone: moves.append({'source': standalone['source'], 'target': standalone['target']})
        return {'schema': 1, 'source': str(source), 'target': str(self.target), 'sourceManifest': source_manifest,
                'items': items, 'preservedModels': models, 'activeProcesses': self._active_processes(source),
                'metadata': {'model': manifest['model'], 'vae': manifest['vae']}, 'discardedBrokenCacheLinks': skipped,
                'discardedRegenerablePythonCaches': generated, 'standaloneModel': standalone, 'moves': moves}

    def _tree_hashes(self, directory, allow_symlinks=False):
        result = {}
        if directory.is_symlink() or not directory.is_dir():
            raise StorageError('YuE2 MLX 모델 폴더가 안전하지 않습니다.', 'unsafe_runtime')
        for base, directories, names in os.walk(directory, followlinks=False):
            for name in directories:
                if (Path(base) / name).is_symlink():
                    raise StorageError('YuE2 MLX 모델 폴더 symlink는 안전하지 않습니다.', 'unsafe_runtime')
            for name in names:
                path = Path(base) / name
                if path.is_symlink():
                    if not allow_symlinks:
                        raise StorageError('YuE2 MLX 모델 파일 symlink는 안전하지 않습니다.', 'unsafe_runtime')
                    try: path = path.resolve(strict=True)
                    except OSError as error: raise StorageError('YuE2 MLX 모델 파일 symlink가 끊겼습니다.', 'unsafe_runtime') from error
                if path.is_file():
                    result[str((Path(base) / name).relative_to(directory))] = self._content_snapshot(path.read_bytes()) if path.stat().st_size <= MAX_JSON else {'bytes': path.stat().st_size, 'sha256': _sha256(path)}
        return result

    def _manifest_bytes(self, source):
        value = self._rebase_manifest(self._manifest(source), source, self.target)
        value['model'], value['vae'] = str(self.target / 'models'), str(self.target / 'vae')
        encoded = (json.dumps(value, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
        if len(encoded) > MAX_JSON:
            raise StorageError('YuE2 MLX 경로 정보가 너무 큽니다.', 'unsafe_runtime')
        return encoded

    def _target_inventory(self):
        entries = []
        for base, directories, names in os.walk(self.target, followlinks=False):
            for name in directories:
                if (Path(base) / name).is_symlink():
                    raise StorageError('현재 YuE2 MLX 설치에 폴더 symlink가 있습니다.', 'unsafe_runtime')
            for name in names:
                path = Path(base) / name
                relative = path.relative_to(self.target).as_posix()
                if self._regenerable_pyc(path):
                    continue
                if path.is_symlink():
                    try: resolved = path.resolve(strict=True)
                    except OSError as error: raise StorageError('현재 YuE2 MLX 설치에 끊긴 링크가 있습니다.', 'unsafe_runtime') from error
                    if _inside(resolved, self.root):
                        raise StorageError('현재 YuE2 MLX 설치가 Output 경로를 계속 참조합니다.', 'unsafe_runtime')
                    entries.append({'relativePath': relative, 'kind': 'link', 'link': os.readlink(path), 'resolved': str(resolved), 'snapshot': self._snapshot(resolved)})
                elif path.is_file():
                    entries.append({'relativePath': relative, 'kind': 'file', 'snapshot': self._snapshot(path)})
        return sorted(entries, key=lambda item: item['relativePath'])

    def _verify_existing_canonical(self, source, items):
        inventory = self._target_inventory()
        expected = {item['relativePath'] for item in items}
        if {item['relativePath'] for item in inventory} != expected:
            raise StorageError('현재 앱 데이터 YuE2 MLX 설치 파일 목록이 레거시 설치와 다릅니다.', 'target_conflict')
        inventory_by_path = {item['relativePath']: item for item in inventory}
        for item in items:
            target = self.target / item['relativePath']
            actual = inventory_by_path[item['relativePath']]
            if item['relativePath'] == 'paths.json':
                if target.read_bytes() != self._manifest_bytes(source):
                    raise StorageError('현재 앱 데이터 YuE2 MLX 경로 정보가 레거시 설치와 다릅니다.', 'target_conflict')
            elif item['kind'] == 'link':
                if actual['kind'] != 'link' or actual['link'] != item['link'] or _inside(Path(actual['resolved']), self.root) or actual['snapshot']['bytes'] != item['snapshot']['bytes'] or actual['snapshot']['sha256'] != item['snapshot']['sha256']:
                    raise StorageError('현재 앱 데이터 YuE2 MLX 실행 링크가 레거시 설치와 다릅니다.', 'target_conflict')
            elif actual['kind'] != 'file' or not self._matches_content(target, item['rebase'] if 'rebase' in item else item['snapshot']):
                raise StorageError('현재 앱 데이터 YuE2 MLX 파일이 레거시 설치와 다릅니다.', 'target_conflict')
        return inventory

    def _canonical_plan(self, source=None):
        if self.target.is_symlink() or not self.target.is_dir():
            raise StorageError('이전할 YuE2 MLX 설치를 찾을 수 없습니다.', 'missing_runtime')
        manifest = self._manifest(self.target, self.target)
        required = [self.target / 'venv/bin/python', self.target / 'src/pyproject.toml', self.target / 'src/uv.lock', self.target / 'src/src/lyra/cli.py',
                    *(self.target / 'models' / name for name in REQUIRED_MODEL_FILES), *(self.target / 'vae' / name for name in REQUIRED_VAE_FILES)]
        if not all(path.exists() for path in required):
            raise StorageError('현재 YuE2 MLX 설치가 완전하지 않습니다.', 'unsafe_runtime')
        inventory = self._target_inventory()
        if source is not None:
            source = self._source_root_for_compare(source)
            self._manifest(source)
            source_items, _, _ = self._items(source)
            inventory = self._verify_existing_canonical(source, source_items)
            self._no_legacy_references(self.target, source)
            asr_source = self.root / LEGACY_ASR
            asr_target = self.data_dir / 'models' / 'asr' / asr_source.name
            if asr_source.exists() and (asr_source.is_symlink() or not self._matches_digest(asr_target, self._snapshot(asr_source))):
                raise StorageError('현재 앱 데이터 음성 인식 모델이 레거시 모델과 다릅니다.', 'target_conflict')
        models = []
        for base, _, names in os.walk(self.target, followlinks=False):
            for name in names:
                path = Path(base) / name
                if path.is_file() and not path.is_symlink() and path.suffix.lower() in WEIGHT_SUFFIXES:
                    models.append({'relativePath': str(path.relative_to(self.target)), 'sha256': _sha256(path), 'bytes': path.stat().st_size})
        asr = self.data_dir / 'models' / 'asr' / LEGACY_ASR.name
        if asr.is_file() and not asr.is_symlink():
            models.append({'relativePath': str(asr.relative_to(self.data_dir)), 'sha256': _sha256(asr), 'bytes': asr.stat().st_size})
        return {'schema': 1, 'source': str(self.source), 'target': str(self.target), 'items': [], 'moves': [],
                'preservedModels': sorted(models, key=lambda item: item['relativePath']), 'activeProcesses': [],
                'metadata': {'model': manifest['model'], 'vae': manifest['vae']}, 'discardedBrokenCacheLinks': [], 'discardedRegenerablePythonCaches': [],
                'standaloneModel': None, 'canonicalItems': inventory, 'alreadyCanonical': True}

    def _source_root_for_compare(self, source):
        source = Path(source)
        if source != self.source or source.is_symlink() or not source.is_dir() or source.resolve(strict=True) != source:
            raise StorageError('검증된 레거시 YuE2 MLX 설치만 비교할 수 있습니다.', 'unsafe_runtime')
        return source

    @staticmethod
    def _matches(path, snapshot):
        try:
            current = RuntimeRescue._snapshot(path)
        except (OSError, StorageError):
            return False
        return current == snapshot

    @staticmethod
    def _matches_content(path, snapshot):
        try:
            path = Path(path)
            info = path.stat()
            return path.is_file() and not path.is_symlink() and info.st_size == snapshot.get('bytes') and _sha256(path) == snapshot.get('sha256') and ('mode' not in snapshot or stat.S_IMODE(info.st_mode) == snapshot['mode'])
        except OSError:
            return False

    @staticmethod
    def _matches_digest(path, snapshot):
        try:
            path = Path(path)
            return path.is_file() and not path.is_symlink() and path.stat().st_size == snapshot['bytes'] and _sha256(path) == snapshot['sha256']
        except OSError:
            return False

    def _validate_plan(self, plan):
        if not isinstance(plan, dict) or plan.get('schema') != 1:
            raise StorageError('YuE2 MLX 이전 계획이 안전하지 않습니다.', 'invalid_plan')
        if plan.get('notRequired'):
            if plan.get('source') != str(self.source) or plan.get('target') != str(self.target) or any(self._runtime_entries().values()):
                raise StorageError('YuE2 MLX 설치 상태가 계획 뒤 변경됐습니다.', 'changed_runtime')
            return self._not_required_plan()
        if plan.get('alreadyCanonical'):
            current = self._canonical_plan(source=self.source) if self.source.exists() else self._canonical_plan()
            if current['preservedModels'] != plan.get('preservedModels') or current['canonicalItems'] != plan.get('canonicalItems'):
                raise StorageError('현재 YuE2 MLX 설치가 계획 뒤 변경됐습니다.', 'changed_runtime')
            return current
        source = self._source_root()
        if plan.get('source') != str(source) or plan.get('target') != str(self.target):
            raise StorageError('YuE2 MLX 이전 계획의 대상이 달라졌습니다.', 'invalid_plan')
        if plan.get('activeProcesses'):
            raise StorageError('실행 중인 YuE2 MLX 프로필은 이전하지 않습니다.', 'runtime_active')
        current = self.plan()
        if current['activeProcesses']:
            raise StorageError('실행 중인 YuE2 MLX 프로필은 이전하지 않습니다.', 'runtime_active')
        if current['sourceManifest'] != plan.get('sourceManifest') or current['items'] != plan.get('items') or current.get('standaloneModel') != plan.get('standaloneModel'):
            raise StorageError('YuE2 MLX 설치가 계획 뒤 변경됐습니다.', 'changed_runtime')
        return current

    def _rebase_manifest(self, value, source, target, key=None):
        if isinstance(value, dict):
            return {name: self._rebase_manifest(item, source, target, name) for name, item in value.items()}
        if isinstance(value, list):
            return [self._rebase_manifest(item, source, target, key) for item in value]
        if key in TRUSTED_PATH_FIELDS and isinstance(value, str):
            source_text, target_text = str(source), str(target)
            if value == source_text or value.startswith(source_text + os.sep):
                return target_text + value[len(source_text):]
        return value

    @staticmethod
    def _link_or_copy(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)

    def _write_stage(self, plan, stage):
        source = Path(plan['source'])
        for item in plan['items']:
            destination = stage / item['relativePath']
            actual = Path(item.get('resolved') or source / item['relativePath'])
            if not self._matches(actual, item['snapshot']):
                raise StorageError('YuE2 MLX 파일이 이전 중 변경됐습니다.', 'changed_runtime')
            if item['kind'] == 'link':
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(item['link'], destination)
            else:
                self._link_or_copy(actual, destination)
                if not self._matches_digest(destination, item['snapshot']):
                    raise StorageError('복사한 YuE2 MLX 파일 검증에 실패했습니다.', 'copy_failed')
        for item in plan['items']:
            if 'rebase' not in item: continue
            destination = stage / item['relativePath']
            original = destination.read_bytes()
            if not self._matches_content(destination, item['snapshot']):
                raise StorageError(f"YuE2 MLX 경로 재작성 대상이 계획과 다릅니다: {item['relativePath']}", 'changed_runtime')
            updated = self._rebased_bytes(item, original, source)
            temporary = destination.with_name(f'.{destination.name}.{secrets.token_hex(8)}.tmp')
            with temporary.open('wb') as stream:
                stream.write(updated); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary, item['snapshot']['mode'])
            os.replace(temporary, destination)
            if not self._matches_content(destination, item['rebase']):
                raise StorageError(f"YuE2 MLX 경로 재작성 검증에 실패했습니다: {item['relativePath']}", 'copy_failed')
        manifest_path = stage / 'paths.json'
        encoded = self._manifest_bytes(source)
        temporary = manifest_path.with_name(f'.{manifest_path.name}.{secrets.token_hex(8)}.tmp')
        temporary.write_bytes(encoded)
        os.replace(temporary, manifest_path)

    def _verify_target(self, plan):
        target = self.target
        if target.is_symlink() or not target.is_dir():
            raise StorageError('새 YuE2 MLX 설치 경로가 안전하지 않습니다.', 'copy_failed')
        for item in plan['items']:
            path = target / item['relativePath']
            if item['relativePath'] == 'paths.json':
                continue  # Canonical model/VAE paths are deliberately rebased below.
            if item['kind'] == 'link':
                if not path.is_symlink() or _inside(path.resolve(strict=True), self.root):
                    raise StorageError('새 YuE2 MLX 외부 실행 링크 검증에 실패했습니다.', 'copy_failed')
            elif path.is_symlink() or not (self._matches_content(path, item['rebase']) if 'rebase' in item else self._matches_digest(path, item['snapshot'])):
                raise StorageError('새 YuE2 MLX 파일 검증에 실패했습니다.', 'copy_failed')
        manifest = self._manifest(target, target)
        if Path(manifest['model']).resolve(strict=True) != (target / 'models').resolve(strict=True) or Path(manifest['vae']).resolve(strict=True) != (target / 'vae').resolve(strict=True):
            raise StorageError('새 YuE2 MLX 모델 경로 검증에 실패했습니다.', 'copy_failed')
        self._no_legacy_references(target, Path(plan['source']))

    @staticmethod
    def _no_legacy_references(root, source):
        needle = str(source)
        for base, _, names in os.walk(root, followlinks=False):
            for name in names:
                path = Path(base) / name
                relative = path.relative_to(root).as_posix()
                if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON or path.suffix == '.pyc':
                    continue
                if path.suffix.lower() not in TEXT_SUFFIXES and not relative.startswith('venv/bin/'):
                    continue
                try: text = path.read_text(encoding='utf-8')
                except (OSError, UnicodeDecodeError): continue
                if '\x00' not in text and needle in text:
                    raise StorageError(f'새 YuE2 MLX 설치가 과거 Output 경로를 계속 참조합니다: {relative}', 'copy_failed')

    def _stage_standalone(self, item):
        if not item: return None
        source, target = Path(item['source']), Path(item['target'])
        if not _inside(source, self.root) or not _inside(target, self.data_dir) or target.exists() or target.is_symlink() or not self._matches(source, item['snapshot']):
            raise StorageError('독립 음성 인식 모델이 이전 계획과 다릅니다.', 'changed_runtime')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink():
            raise StorageError('독립 음성 인식 모델 경로가 안전하지 않습니다.', 'unsafe_path')
        stage = target.with_name(f'.{target.name}.stage-{secrets.token_hex(12)}')
        self._link_or_copy(source, stage)
        if not self._matches(stage, item['snapshot']):
            stage.unlink(missing_ok=True)
            raise StorageError('독립 음성 인식 모델 복사 검증에 실패했습니다.', 'copy_failed')
        return stage

    def apply(self, plan):
        current = self._validate_plan(plan)
        if current.get('notRequired'):
            return {'mappings': [], 'preservedModels': [], 'movedAllocatedBytes': 0, 'notRequired': True}
        if current.get('alreadyCanonical'):
            return {'mappings': [], 'preservedModels': current['preservedModels'], 'movedAllocatedBytes': 0}
        parent = self.target.parent
        if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
            raise StorageError('앱 엔진 폴더가 안전하지 않습니다.', 'unsafe_path')
        parent.mkdir(parents=True, exist_ok=True)
        stage = parent / f'.yue-mlx.stage-{secrets.token_hex(12)}'
        standalone_stage = None
        installed = False
        standalone_installed = False
        try:
            self._write_stage(current, stage)
            self._verify_stage(stage, current)
            standalone_stage = self._stage_standalone(current.get('standaloneModel'))
            os.replace(stage, self.target)
            installed = True
            self._verify_target(current)
            if standalone_stage:
                os.replace(standalone_stage, Path(current['standaloneModel']['target']))
                standalone_installed = True
                if not self._matches(Path(current['standaloneModel']['target']), current['standaloneModel']['snapshot']):
                    raise StorageError('독립 음성 인식 모델 이전 검증에 실패했습니다.', 'copy_failed')
        except Exception:
            if stage.exists() and not stage.is_symlink(): shutil.rmtree(stage)
            if standalone_stage and standalone_stage.exists(): standalone_stage.unlink(missing_ok=True)
            if installed and self.target.exists() and not self.target.is_symlink(): shutil.rmtree(self.target)
            if standalone_installed:
                Path(current['standaloneModel']['target']).unlink(missing_ok=True)
            raise
        mappings = [{'source': str(self.source / item['relativePath']), 'target': str(self.target / item['relativePath'])} for item in current['items']]
        if current.get('standaloneModel'):
            mappings.append({'source': current['standaloneModel']['source'], 'target': current['standaloneModel']['target']})
        moved = sum(_allocated(self.target / item['relativePath']) for item in current['items'] if item['kind'] != 'link')
        if current.get('standaloneModel'): moved += _allocated(current['standaloneModel']['target'])
        return {'mappings': mappings, 'preservedModels': current['preservedModels'], 'movedAllocatedBytes': moved}

    def _verify_stage(self, stage, plan):
        if stage.is_symlink() or not stage.is_dir():
            raise StorageError('준비 중인 YuE2 MLX 설치 경로가 안전하지 않습니다.', 'copy_failed')
        for item in plan['items']:
            path = stage / item['relativePath']
            if item['relativePath'] == 'paths.json':
                continue
            if item['kind'] == 'link':
                if not path.is_symlink() or _inside(path.resolve(strict=True), self.root):
                    raise StorageError('준비 중인 YuE2 MLX 실행 링크 검증에 실패했습니다.', 'copy_failed')
            elif path.is_symlink() or not (self._matches_content(path, item['rebase']) if 'rebase' in item else self._matches_digest(path, item['snapshot'])):
                raise StorageError('준비 중인 YuE2 MLX 파일 검증에 실패했습니다.', 'copy_failed')
        try:
            manifest = json.loads((stage / 'paths.json').read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StorageError('준비 중인 YuE2 MLX 경로 정보를 읽을 수 없습니다.', 'copy_failed') from error
        if manifest.get('model') != str(self.target / 'models') or manifest.get('vae') != str(self.target / 'vae'):
            raise StorageError('준비 중인 YuE2 MLX 모델 경로 검증에 실패했습니다.', 'copy_failed')
        self._no_legacy_references(stage, Path(plan['source']))

