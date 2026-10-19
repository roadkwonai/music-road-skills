"""Fail-closed member-content history for retired distribution ZIPs.

The original ZIP container is deliberately not recreated byte-for-byte.  A verified
manifest instead records every regular member and either references the protected
canonical ZIP or stores the unique member bytes by SHA-256.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import zipfile

from storage_artifacts import ARCHIVE
from storage_manager import MAX_JSON, StorageError, _snapshot
from storage_verification import _allocated


MAX_ENTRIES = 20_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 ** 3
MAX_MEMBER_JSON = 1024 * 1024
WEIGHT_SUFFIXES = {'.safetensors', '.gguf', '.ggml', '.ckpt', '.pt', '.pth', '.bin', '.onnx', '.h5', '.tflite', '.pkl', '.pickle'}
COMPRESSIONS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA}


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class ArchiveHistory:
    def __init__(self, root, canonical_relative=ARCHIVE):
        raw = Path(root)
        if not raw.is_absolute() or raw.is_symlink() or not raw.is_dir():
            raise StorageError('symlink가 아닌 절대 작업 폴더가 필요합니다.', 'unsafe_root')
        self.root = raw.resolve(strict=True)
        relative = Path(canonical_relative)
        if relative.is_absolute() or not relative.parts or '..' in relative.parts:
            raise StorageError('canonical ZIP 경로가 안전하지 않습니다.', 'unsafe_path')
        self.canonical_relative = relative
        self._canonical_cache = None

    def _inside(self, path):
        return path == self.root or self.root in path.parents

    def _regular(self, path):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise StorageError('symlink가 아닌 일반 ZIP 파일만 보관할 수 있습니다.', 'unsafe_path')
        raw_parent = path.parent
        while raw_parent != self.root.parent:
            if raw_parent.is_symlink():
                raise StorageError('ZIP 상위 경로의 symlink는 허용하지 않습니다.', 'unsafe_path')
            if raw_parent == raw_parent.parent:
                raise StorageError('작업 폴더 밖 파일은 보관할 수 없습니다.', 'unsafe_path')
            raw_parent = raw_parent.parent
        resolved = path.resolve(strict=True)
        if not self._inside(resolved):
            raise StorageError('작업 폴더 밖 파일은 보관할 수 없습니다.', 'unsafe_path')
        return resolved

    def _source_path(self, value):
        raw = Path(value)
        path = raw if raw.is_absolute() else self.root / raw
        path = self._regular(path)
        if path.suffix.lower() != '.zip':
            raise StorageError('배포 ZIP 파일만 보관할 수 있습니다.', 'unsafe_archive')
        if any(token in path.stem.casefold() for token in ('model', 'weight')):
            raise StorageError('모델 가중치 ZIP은 보관 정리하지 않습니다.', 'protected')
        if path == self._canonical_path():
            raise StorageError('보호된 canonical ZIP은 보관 대상으로 만들 수 없습니다.', 'protected')
        return path

    def _canonical_path(self):
        return self._regular(self.root / self.canonical_relative)

    @staticmethod
    def _cache_key(path):
        value = _snapshot(path)
        return (value['dev'], value['inode'], value['bytes'], value['mtimeNs'], path.stat(follow_symlinks=False).st_ctime_ns)

    def _canonical_archive(self):
        path = self._canonical_path(); key = self._cache_key(path)
        if self._canonical_cache is not None and self._canonical_cache[0] == key:
            canonical, members = self._canonical_cache[1]
            return dict(canonical), [dict(item) for item in members]
        canonical, members, _ = self._archive(path)
        if self._cache_key(path) != key:
            canonical, members, _ = self._archive(path); key = self._cache_key(path)
        self._canonical_cache = (key, (dict(canonical), [dict(item) for item in members]))
        return canonical, members

    @staticmethod
    def _safe_member_name(name):
        value = PurePosixPath(name)
        if not name or '\\' in name or value.is_absolute() or not value.parts or any(part in {'', '.', '..'} for part in value.parts):
            raise StorageError('ZIP 내부 경로가 안전하지 않습니다.', 'unsafe_archive')
        return name

    @staticmethod
    def _member_name(info):
        return ArchiveHistory._safe_member_name(info.filename)

    @staticmethod
    def _member_safe(info):
        ArchiveHistory._member_name(info)
        if info.flag_bits & 0x1:
            raise StorageError('암호화된 ZIP 멤버는 보관할 수 없습니다.', 'unsafe_archive')
        if info.compress_type not in COMPRESSIONS:
            raise StorageError('지원하지 않는 ZIP 압축 형식입니다.', 'unsafe_archive')
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise StorageError('ZIP 내부 symlink는 보관할 수 없습니다.', 'unsafe_archive')
        if not info.is_dir() and (Path(info.filename).suffix.lower() in WEIGHT_SUFFIXES or any(part.casefold() in {'models', 'model', 'engines', 'engine'} for part in PurePosixPath(info.filename).parts)):
            raise StorageError('모델 또는 엔진을 담은 ZIP은 보관 정리하지 않습니다.', 'protected')

    def _archive(self, path):
        path = self._regular(path)
        before = _snapshot(path)
        source_hash = _digest(path)
        members, names, total, product = [], set(), 0, None
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_ENTRIES:
                    raise StorageError('ZIP 멤버 수 안전 한도를 초과했습니다.', 'archive_limit')
                for info in infos:
                    self._member_safe(info)
                    name = self._member_name(info)
                    if name in names:
                        raise StorageError('중복 이름의 ZIP 멤버는 보관할 수 없습니다.', 'unsafe_archive')
                    names.add(name)
                    if info.is_dir():
                        continue
                    total += info.file_size
                    if total > MAX_UNCOMPRESSED_BYTES:
                        raise StorageError('ZIP 압축 해제 용량 안전 한도를 초과했습니다.', 'archive_limit')
                    digest = hashlib.sha256(); size = 0
                    with archive.open(info, 'r') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            size += len(block)
                            if size > info.file_size:
                                raise StorageError('ZIP 멤버 길이가 일치하지 않습니다.', 'unsafe_archive')
                            digest.update(block)
                    if size != info.file_size:
                        raise StorageError('ZIP 멤버 길이가 일치하지 않습니다.', 'unsafe_archive')
                    item = {'name': name, 'size': size, 'sha256': digest.hexdigest(), 'external_attr': info.external_attr}
                    members.append(item)
                    if product is None and info.file_size <= MAX_MEMBER_JSON and Path(name).name in {'manifest.json', 'package.json'}:
                        try:
                            value = json.loads(archive.read(info).decode('utf-8-sig'))
                            if isinstance(value, dict) and isinstance(value.get('name'), str):
                                product = {'member': name, 'name': value['name'], **({'version': value['version']} if isinstance(value.get('version'), str) else {})}
                        except (UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile):
                            pass
        except StorageError:
            raise
        except (OSError, zipfile.BadZipFile, NotImplementedError) as error:
            raise StorageError('ZIP 멤버를 안전하게 읽을 수 없습니다.', 'unsafe_archive') from error
        if before != _snapshot(path) or source_hash != _digest(path):
            raise StorageError('ZIP이 검증 중 변경됐습니다.', 'changed_source')
        return {'path': str(path.relative_to(self.root)), 'sha256': source_hash, 'bytes': before['bytes'], 'snapshot': before}, members, product

    def plan(self, path):
        source_path = self._source_path(path)
        source, members, product = self._archive(source_path)
        canonical, canonical_members = self._canonical_archive()
        index = {}
        for item in canonical_members:
            index.setdefault((item['size'], item['sha256']), item['name'])
        result = []
        for item in members:
            value = dict(item); canonical_member = index.get((item['size'], item['sha256']))
            if canonical_member is not None:
                value['canonicalMember'] = canonical_member
            result.append(value)
        return {'source': source, 'canonical': canonical, 'members': result, **({'product': product} if product else {})}

    def _history_root(self, create=False):
        target = self.root / '.roadmusic' / 'maintenance' / 'retirement-content'
        if not create:
            return target
        current = self.root
        for part in ('.roadmusic', 'maintenance', 'retirement-content'):
            current = current / part
            if current.exists():
                if current.is_symlink() or not current.is_dir():
                    raise StorageError('보관 경로가 안전하지 않습니다.', 'unsafe_path')
            else:
                current.mkdir()
        for name in ('blobs', 'manifests'):
            child = current / name
            if child.exists():
                if child.is_symlink() or not child.is_dir():
                    raise StorageError('보관 경로가 안전하지 않습니다.', 'unsafe_path')
            else:
                child.mkdir()
        return target

    @staticmethod
    def _fsync_directory(path):
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _blob_relative(self, digest):
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest):
            raise StorageError('멤버 해시가 안전하지 않습니다.', 'unsafe_archive')
        return Path('.roadmusic/maintenance/retirement-content/blobs') / (digest + '.gz')

    def _safe_history_file(self, relative):
        raw = self.root / relative
        if raw.is_symlink() or not self._inside(raw.resolve(strict=False)):
            raise StorageError('보관 파일 경로가 안전하지 않습니다.', 'unsafe_path')
        parent = raw.parent
        while parent != self.root.parent:
            if parent.is_symlink():
                raise StorageError('보관 파일 상위 경로가 안전하지 않습니다.', 'unsafe_path')
            parent = parent.parent
        return raw

    def _verify_blob(self, relative, digest, size):
        path = self._safe_history_file(relative)
        if not path.is_file() or path.is_symlink():
            raise StorageError('고유 멤버 보관 파일이 없습니다.', 'missing_history')
        current = hashlib.sha256(); count = 0
        try:
            with gzip.open(path, 'rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    count += len(block)
                    if count > size:
                        raise StorageError('고유 멤버 보관 길이가 다릅니다.', 'corrupt_history')
                    current.update(block)
        except StorageError:
            raise
        except (OSError, EOFError, gzip.BadGzipFile) as error:
            raise StorageError('고유 멤버 보관 파일을 읽을 수 없습니다.', 'corrupt_history') from error
        if count != size or current.hexdigest() != digest:
            raise StorageError('고유 멤버 보관 해시가 다릅니다.', 'corrupt_history')
        return path

    def _write_blob(self, source, member):
        relative = self._blob_relative(member['sha256']); target = self._safe_history_file(relative)
        if target.exists():
            self._verify_blob(relative, member['sha256'], member['size'])
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / ('.' + target.name + '.' + secrets.token_hex(8) + '.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            actual = hashlib.sha256(); count = 0
            with os.fdopen(descriptor, 'wb', closefd=True) as raw:
                descriptor = None
                with zipfile.ZipFile(source) as archive, archive.open(member['name'], 'r') as original, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as compressed:
                    for block in iter(lambda: original.read(1024 * 1024), b''):
                        count += len(block)
                        if count > member['size']:
                            raise StorageError('ZIP 멤버 길이가 변경됐습니다.', 'changed_source')
                        actual.update(block); compressed.write(block)
                raw.flush(); os.fsync(raw.fileno())
            if count != member['size'] or actual.hexdigest() != member['sha256']:
                raise StorageError('ZIP 멤버 해시가 변경됐습니다.', 'changed_source')
            if target.exists():
                temporary.unlink(missing_ok=True); self._verify_blob(relative, member['sha256'], member['size']); return False
            os.replace(temporary, target); self._fsync_directory(target.parent)
            self._verify_blob(relative, member['sha256'], member['size'])
            return True
        finally:
            if descriptor is not None:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def _manifest_relative(self, source):
        key = hashlib.sha256((source['path'] + '\0' + source['sha256']).encode()).hexdigest()
        return Path('.roadmusic/maintenance/retirement-content/manifests') / (key + '.json')

    def _write_manifest(self, relative, value):
        path = self._safe_history_file(relative)
        existed = path.exists()
        encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
        if len(encoded) > MAX_JSON:
            raise StorageError('보관 manifest가 너무 큽니다.', 'state_too_large')
        temporary = path.parent / ('.' + path.name + '.' + secrets.token_hex(8) + '.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, 'wb', closefd=True) as stream:
                descriptor = None; stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path); self._fsync_directory(path.parent)
        finally:
            if descriptor is not None: os.close(descriptor)
            temporary.unlink(missing_ok=True)
        return not existed

    @staticmethod
    def _core_members(members):
        keys = ('name', 'size', 'sha256', 'external_attr', 'canonicalMember')
        return [{key: item[key] for key in keys if key in item} for item in members]

    def _source_record(self, source):
        if not isinstance(source, dict) or set(source) != {'path', 'sha256', 'bytes', 'snapshot'}:
            raise StorageError('archive 원본 기록 형식이 올바르지 않습니다.', 'corrupt_history')
        relative = Path(source['path'])
        if relative.is_absolute() or not relative.parts or '..' in relative.parts or source['path'] != str(relative):
            raise StorageError('archive 원본 경로가 안전하지 않습니다.', 'unsafe_path')
        if not isinstance(source['sha256'], str) or len(source['sha256']) != 64 or any(char not in '0123456789abcdef' for char in source['sha256']):
            raise StorageError('archive 원본 해시가 올바르지 않습니다.', 'corrupt_history')
        if not isinstance(source['bytes'], int) or source['bytes'] < 0 or not isinstance(source['snapshot'], dict) or source['snapshot'].get('bytes') != source['bytes']:
            raise StorageError('archive 원본 snapshot이 올바르지 않습니다.', 'corrupt_history')
        path = self.root / relative
        parent = path.parent
        while parent != self.root.parent:
            if parent.is_symlink():
                raise StorageError('archive 원본 상위 경로가 안전하지 않습니다.', 'unsafe_path')
            parent = parent.parent
        if path.is_symlink():
            raise StorageError('archive 원본 경로가 안전하지 않습니다.', 'unsafe_path')
        return path

    def _manifest_members(self, members):
        if not isinstance(members, list) or len(members) > MAX_ENTRIES:
            raise StorageError('archive 멤버 목록이 올바르지 않습니다.', 'corrupt_history')
        names, total, result = set(), 0, []
        for item in members:
            if not isinstance(item, dict):
                raise StorageError('archive 멤버 형식이 올바르지 않습니다.', 'corrupt_history')
            allowed = {'name', 'size', 'sha256', 'external_attr', 'canonicalMember', 'blob'}
            if not {'name', 'size', 'sha256', 'external_attr'} <= set(item) or set(item) - allowed:
                raise StorageError('archive 멤버 형식이 올바르지 않습니다.', 'corrupt_history')
            name = self._safe_member_name(item['name'])
            if name in names:
                raise StorageError('중복 이름의 archive 멤버는 허용하지 않습니다.', 'corrupt_history')
            names.add(name)
            if not isinstance(item['size'], int) or item['size'] < 0 or not isinstance(item['sha256'], str) or len(item['sha256']) != 64 or any(char not in '0123456789abcdef' for char in item['sha256']) or not isinstance(item['external_attr'], int):
                raise StorageError('archive 멤버 값이 올바르지 않습니다.', 'corrupt_history')
            if Path(name).suffix.lower() in WEIGHT_SUFFIXES or any(part.casefold() in {'models', 'model', 'engines', 'engine'} for part in PurePosixPath(name).parts):
                raise StorageError('모델 또는 엔진 archive 멤버는 허용하지 않습니다.', 'protected')
            if stat.S_ISLNK(item['external_attr'] >> 16):
                raise StorageError('archive symlink 멤버는 허용하지 않습니다.', 'unsafe_archive')
            total += item['size']
            if total > MAX_UNCOMPRESSED_BYTES:
                raise StorageError('archive 멤버 길이 한도를 초과했습니다.', 'archive_limit')
            if ('canonicalMember' in item) == ('blob' in item):
                raise StorageError('archive 멤버 복구 근거가 올바르지 않습니다.', 'corrupt_history')
            result.append(dict(item))
        return result

    def _fresh_plan(self, spec):
        if not isinstance(spec, dict) or not isinstance(spec.get('source'), dict) or not isinstance(spec['source'].get('path'), str):
            raise StorageError('검증된 archive 계획이 필요합니다.', 'invalid_plan')
        fresh = self.plan(self.root / spec['source']['path'])
        if fresh['source'] != spec.get('source') or fresh['canonical'] != spec.get('canonical') or self._core_members(fresh['members']) != self._core_members(spec.get('members', [])):
            raise StorageError('archive 계획 뒤 ZIP 또는 canonical 근거가 변경됐습니다.', 'changed_source')
        return fresh

    def prepare(self, specs):
        if not isinstance(specs, list) or not specs:
            raise StorageError('하나 이상의 archive 계획이 필요합니다.', 'invalid_plan')
        fresh = [self._fresh_plan(spec) for spec in specs]
        if len({item['source']['path'] for item in fresh}) != len(fresh):
            raise StorageError('같은 archive 계획을 중복 준비할 수 없습니다.', 'invalid_plan')
        self._history_root(create=True)
        created = set(); manifests = []
        for plan in fresh:
            source = self.root / plan['source']['path']; members = []
            for member in plan['members']:
                value = dict(member)
                if 'canonicalMember' not in value:
                    relative = self._blob_relative(value['sha256'])
                    if self._write_blob(source, value): created.add(self.root / relative)
                    value['blob'] = str(relative)
                members.append(value)
            value = {'schemaVersion': 1, 'source': plan['source'], 'canonical': plan['canonical'], 'members': members,
                     **({'product': plan['product']} if plan.get('product') else {})}
            relative = self._manifest_relative(plan['source'])
            if self._write_manifest(relative, value): created.add(self.root / relative)
            manifest = {'path': str(relative), 'sha256': _digest(self.root / relative), 'sourceSha256': plan['source']['sha256']}
            self.verify(manifest); manifests.append(manifest)
        return {'manifests': manifests, 'storedBytes': sum(path.stat().st_size for path in created),
                'storedAllocatedBytes': sum(_allocated(path) for path in created)}

    def _manifest(self, spec):
        if isinstance(spec, (str, Path)):
            value = {'path': str(spec)}
        elif isinstance(spec, dict) and 'members' not in spec:
            value = spec
        elif isinstance(spec, dict):
            relative = self._manifest_relative(spec.get('source', {}))
            value = {'path': str(relative), 'sourceSha256': spec.get('source', {}).get('sha256')}
        else:
            raise StorageError('archive manifest가 올바르지 않습니다.', 'invalid_plan')
        relative = Path(value.get('path', ''))
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:
            raise StorageError('archive manifest 경로가 안전하지 않습니다.', 'unsafe_path')
        path = self._safe_history_file(relative)
        if not path.is_file() or path.is_symlink():
            raise StorageError('archive manifest를 찾을 수 없습니다.', 'missing_history')
        actual = _digest(path)
        if value.get('sha256') is not None and actual != value['sha256']:
            raise StorageError('archive manifest 해시가 다릅니다.', 'corrupt_history')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StorageError('archive manifest를 읽을 수 없습니다.', 'corrupt_history') from error
        if data.get('schemaVersion') != 1 or not isinstance(data.get('source'), dict) or not isinstance(data.get('canonical'), dict) or not isinstance(data.get('members'), list):
            raise StorageError('archive manifest 형식이 올바르지 않습니다.', 'corrupt_history')
        if value.get('sourceSha256') is not None and data['source'].get('sha256') != value['sourceSha256']:
            raise StorageError('archive manifest 원본 해시가 다릅니다.', 'corrupt_history')
        return data

    def verify(self, spec):
        data = self._manifest(spec)
        source_path = self._source_record(data['source'])
        members = self._manifest_members(data['members'])
        canonical, canonical_members = self._canonical_archive()
        if canonical != data['canonical']:
            raise StorageError('canonical ZIP 근거가 변경됐습니다.', 'changed_source')
        canonical_index = {item['name']: item for item in canonical_members}
        if source_path.exists():
            fresh = self.plan(source_path)
            if fresh['source'] != data['source'] or fresh['canonical'] != data['canonical'] or self._core_members(fresh['members']) != self._core_members(members):
                raise StorageError('archive 또는 canonical 근거가 변경됐습니다.', 'changed_source')
        for member in members:
            canonical_member = member.get('canonicalMember')
            if canonical_member is not None:
                expected = canonical_index.get(canonical_member)
                if not isinstance(canonical_member, str) or expected is None or expected['size'] != member['size'] or expected['sha256'] != member['sha256']:
                    raise StorageError('canonical archive 멤버가 변경됐습니다.', 'changed_source')
                continue
            expected = self._blob_relative(member['sha256'])
            if member['blob'] != str(expected):
                raise StorageError('archive 보관 멤버 경로가 안전하지 않습니다.', 'unsafe_path')
            self._verify_blob(expected, member['sha256'], member['size'])
        return {'sourceSha256': data['source']['sha256'], 'memberCount': len(data['members'])}
