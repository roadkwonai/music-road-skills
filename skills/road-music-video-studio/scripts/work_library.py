"""Persistent, source-audio grouped index for registered Road Music deliverables."""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing, contextmanager
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sqlite3
import tempfile
import threading
import unicodedata
import sys
import zipfile

from html_design import studio_session_file
from management_db import ManagementDB, ManagementDBError


PROJECT_FILE = 'studio-project.json'
MAX_LIBRARY_JSON = 16 * 1024 * 1024
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
COMPLETED_KINDS = frozenset({'music', 'video', 'lyrics', 'captions', 'storyboard'})
ARTIFACT_TYPES = frozenset({'native-project', 'direction', 'analysis', 'plan', 'validation', 'cues', 'compose', 'report', 'source-archive'})
MEDIA_EXTENSIONS = {
    'source': {'.aac', '.aif', '.aiff', '.flac', '.m4a', '.mp3', '.oga', '.ogg', '.opus', '.wav', '.webm'},
    'music': {'.aac', '.aif', '.aiff', '.flac', '.m4a', '.mp3', '.oga', '.ogg', '.opus', '.wav', '.webm'},
    'video': {'.m4v', '.mov', '.mp4', '.webm'},
    'captions': {'.ass', '.lrc', '.srt', '.vtt'},
    'lyrics': {'.md', '.txt'},
    'storyboard': {'.avif', '.gif', '.jpeg', '.jpg', '.png', '.webp'},
    'artifact': {'.jizura', '.json', '.md', '.txt', '.zip'},
}
MODE_LABELS = {
    'showreel-cd': 'Road Music Showreel CD',
    'showreel-mv': 'Road Music 쇼릴 MV',
    'jizura': 'JIZURA 음악 스튜디오',
    'showreel-motion': 'Showreel 음악 모션그래픽',
}
_locks_guard = threading.Lock()
_locks = {}
_technical_cache = {}
_technical_lock = threading.Lock()


def _lock_for(path):
    with _locks_guard:
        return _locks.setdefault(str(path), threading.RLock())


def _json_load(path, fallback):
    path = Path(path)
    if not path.exists():
        return deepcopy(fallback)
    if path.stat().st_size > MAX_LIBRARY_JSON:
        raise ValueError('작업물 라이브러리 JSON이 너무 큽니다')
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'허용하지 않는 JSON 값: {value}')))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('작업물 라이브러리 JSON을 읽을 수 없습니다') from error


def _atomic_json(path, value):
    path = Path(path)
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(encoded) > MAX_LIBRARY_JSON:
        raise ValueError('작업물 라이브러리 JSON이 너무 큽니다')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('wb', dir=path.parent, prefix=f'.{path.name}.', delete=False) as stream:
        stream.write(encoded)
        temporary = Path(stream.name)
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _file_id(kind, digest):
    return hashlib.sha256(f'{kind}\0{digest}'.encode()).hexdigest()


def _valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    return True


def _safe_path(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label}: 절대 파일 경로가 필요합니다')
    raw = Path(value)
    if not raw.is_absolute():
        raise ValueError(f'{label}: 절대 파일 경로가 필요합니다')
    path = raw.resolve(strict=True)
    if not path.is_file() or raw.is_symlink() or path.is_symlink():
        raise ValueError(f'{label}: symlink가 아닌 일반 파일이 필요합니다')
    return path


def _safe_name(value, path):
    if not isinstance(value, str) or not value or '\x00' in value or Path(value).name != value or len(value) > 255:
        return path.name
    return value


def _empty_technical():
    return {'durationSeconds': None, 'width': None, 'height': None, 'fps': None, 'videoCodec': None, 'audioCodec': None}


def _technical(path, stat):
    """Best-effort local probe. A missing ffprobe never blocks publication."""
    if path.suffix.lower() not in MEDIA_EXTENSIONS['video'] | MEDIA_EXTENSIONS['music']:
        return _empty_technical()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    with _technical_lock:
        cached = _technical_cache.get(key)
    if cached is not None:
        return deepcopy(cached)
    result = _empty_technical()
    try:
        completed = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,codec_name,width,height,r_frame_rate', '-of', 'json', str(path)],
            check=False, capture_output=True, text=True, timeout=3,
        )
        if completed.returncode == 0:
            payload = json.loads(completed.stdout)
            duration = payload.get('format', {}).get('duration')
            try:
                result['durationSeconds'] = round(float(duration), 3) if duration is not None else None
            except (TypeError, ValueError):
                pass
            for stream in payload.get('streams', []):
                if stream.get('codec_type') == 'video' and result['videoCodec'] is None:
                    result['videoCodec'] = stream.get('codec_name') if isinstance(stream.get('codec_name'), str) else None
                    result['width'] = stream.get('width') if isinstance(stream.get('width'), int) and stream['width'] > 0 else None
                    result['height'] = stream.get('height') if isinstance(stream.get('height'), int) and stream['height'] > 0 else None
                    rate = stream.get('r_frame_rate')
                    if isinstance(rate, str) and '/' in rate:
                        numerator, denominator = rate.split('/', 1)
                        try:
                            result['fps'] = round(float(numerator) / float(denominator), 3) if float(denominator) else None
                        except ValueError:
                            pass
                if stream.get('codec_type') == 'audio' and result['audioCodec'] is None:
                    result['audioCodec'] = stream.get('codec_name') if isinstance(stream.get('codec_name'), str) else None
    except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
        pass
    with _technical_lock:
        _technical_cache[key] = deepcopy(result)
    return result


def _origin(project, mode, style_label, style_id, selection, feedback, registered_at):
    return {
        'project': str(project), 'mode': mode, 'styleLabel': style_label, 'styleId': style_id,
        'registeredAt': registered_at, 'selection': deepcopy(selection) if isinstance(selection, dict) else {},
        'feedback': deepcopy(feedback) if isinstance(feedback, dict) else {},
    }


def _origin_key(origin):
    """A repeated publish of an unchanged snapshot keeps the first actual registration time."""
    return json.dumps({key: origin.get(key) for key in ('project', 'mode', 'styleLabel', 'styleId', 'selection', 'feedback')},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _registered_at(items):
    origins = [origin for item in items if isinstance(item, dict) for origin in item.get('origins', []) if isinstance(origin, dict)]
    if not origins or any(origin.get('registeredAt') is None for origin in origins):
        return None
    return min(origin['registeredAt'] for origin in origins)


def _entry(item, kind, project, mode, fallback_style, selection, feedback, registered_at):
    path = _safe_path(item.get('path'), kind)
    if path.suffix.lower() not in MEDIA_EXTENSIONS[kind]:
        raise ValueError(f'{kind}: 지원하지 않는 파일 형식입니다')
    artifact_type = item.get('artifactType') if kind == 'artifact' else None
    if kind == 'artifact' and artifact_type not in ARTIFACT_TYPES:
        raise ValueError('artifact: artifactType이 올바르지 않습니다')
    before = path.stat()
    expected = item.get('sha256')
    if not isinstance(expected, str) or not SHA256.fullmatch(expected.lower()):
        raise ValueError(f'{kind}: SHA-256이 올바르지 않습니다')
    actual = _sha256(path)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError(f'{kind}: 등록 중 파일이 변경되었습니다')
    if actual != expected.lower():
        raise ValueError(f'{kind}: 등록 뒤 파일이 변경되었습니다')
    stat = after
    timestamp = getattr(stat, 'st_birthtime', None)
    source = 'file-created' if timestamp is not None else 'file-modified'
    if timestamp is None:
        timestamp = stat.st_mtime
    style_label = item.get('styleLabel') if isinstance(item.get('styleLabel'), str) and item['styleLabel'].strip() else None
    style_id = item.get('styleId') if isinstance(item.get('styleId'), str) and item['styleId'].strip() else None
    if style_id is None and isinstance(selection.get('styleId'), str) and selection['styleId'].strip() and kind != 'source':
        style_id = selection['styleId']
    if not style_label:
        style_label = style_id or fallback_style
    produced_at = item.get('producedAt')
    if produced_at is not None and not _valid_timestamp(produced_at):
        raise ValueError(f'{kind}: producedAt 시각이 올바르지 않습니다')
    caption_video = item.get('forVideoSha256') if kind == 'captions' else None
    if caption_video is not None and (not isinstance(caption_video, str) or not SHA256.fullmatch(caption_video.lower())):
        raise ValueError('captions: forVideoSha256이 올바르지 않습니다')
    result = {
        'id': _file_id(kind, actual), 'kind': kind, 'name': _safe_name(item.get('name'), path), 'path': str(path),
        'size': stat.st_size, 'sha256': actual, 'createdAt': _iso(timestamp), 'timestampSource': source,
        'styleLabel': style_label, 'styleId': style_id, 'mode': mode, 'project': str(project),
        'statSize': stat.st_size, 'statMtimeNs': stat.st_mtime_ns,
        'producedAt': produced_at, 'technical': _technical(path, stat),
        'origins': [_origin(project, mode, style_label, style_id, selection, feedback, registered_at)],
    }
    if kind == 'artifact':
        result['artifactType'] = artifact_type
    if kind == 'captions' and caption_video is not None:
        result['forVideoSha256'] = caption_video
    return result


class WorkLibrary:
    """Read and atomically extend a local archive of published studio outputs."""

    def __init__(self, path=None):
        target = Path(path) if path is not None else studio_session_file().parent / 'video-studio-library.json'
        if not target.is_absolute():
            raise ValueError('작업물 라이브러리 경로는 절대 경로여야 합니다')
        if target.is_symlink() or target.parent.is_symlink():
            raise ValueError('작업물 라이브러리 symlink는 허용하지 않습니다')
        self.path = target.resolve()
        self.management_db = ManagementDB(self.path.parent)
        self._lock = _lock_for(self.path)

    @staticmethod
    def _empty():
        return {'schemaVersion': 1, 'groups': {}}

    def _read(self):
        try:
            value = self.management_db.read_document('work-library', self.path, self._empty(), self._validate_document)
        except ManagementDBError as error:
            raise ValueError(str(error)) from error
        return value

    @classmethod
    def _validate_document(cls, value):
        if not isinstance(value, dict) or value.get('schemaVersion') != 1 or not isinstance(value.get('groups'), dict):
            raise ValueError('지원하지 않는 작업물 라이브러리입니다')
        for group_id, group in value['groups'].items():
            cls._validate_group(group_id, group)

    def _sync_delivery_ownership(self, group_ids, connection):
        from storage_packaging import TRUSTED_ROOT
        live = {}
        if group_ids and TRUSTED_ROOT is not None:
            root = Path(TRUSTED_ROOT)
            history = root / '.roadmusic' / 'history.sqlite3'
            if history.parent.is_symlink() or any(path.is_symlink() for path in (history, history.with_name(history.name + '-wal'), history.with_name(history.name + '-shm'))):
                raise ValueError('납품 이력 symlink는 소유권 색인에 사용할 수 없습니다')
            if history.is_file():
                try:
                    with closing(sqlite3.connect(history.as_uri() + '?mode=ro', uri=True)) as delivery:
                        delivery.execute('BEGIN')
                        required = {'delivery_files': {'version_id', 'kind', 'path', 'name', 'sha256', 'bytes'}, 'delivery_versions': {'id', 'group_id', 'project_id'}, 'delivery_projects': {'project_id', 'group_id', 'logical_project_id'}}
                        if all(columns.issubset({row[1] for row in delivery.execute('PRAGMA table_info(' + table + ')')}) for table, columns in required.items()):
                            tombstone_columns = {row[1] for row in delivery.execute('PRAGMA table_info(delivery_file_tombstones)')}
                            tombstones = ''
                            if {'version_id', 'kind', 'name', 'path'}.issubset(tombstone_columns):
                                tombstones = " AND NOT EXISTS (SELECT 1 FROM delivery_file_tombstones t WHERE t.version_id=f.version_id AND t.kind=f.kind AND t.name=f.name AND t.path=f.path" + (" AND t.state='applied'" if 'state' in tombstone_columns else '') + ')'
                            rows = delivery.execute('SELECT f.path,f.sha256,f.bytes,f.kind,v.group_id,p.logical_project_id FROM delivery_files f JOIN delivery_versions v ON v.id=f.version_id JOIN delivery_projects p ON p.project_id=v.project_id AND p.group_id=v.group_id WHERE v.group_id IN (' + ','.join('?' for _ in group_ids) + ')' + tombstones, tuple(group_ids))
                            for path, digest, size, kind, group_id, project_id in rows:
                                if not isinstance(path, str) or kind not in COMPLETED_KINDS or not all(isinstance(value, str) and SHA256.fullmatch(value) for value in (digest, group_id, project_id)) or type(size) is not int or size < 0:
                                    continue
                                raw = Path(path)
                                try:
                                    if not raw.is_absolute() or not raw.is_relative_to(root / 'Output') or raw.is_symlink() or raw.resolve(strict=True) != raw or not raw.is_file() or raw.stat().st_size != size:
                                        continue
                                except OSError:
                                    continue
                                live[path] = (group_id, project_id, str(root))
                except sqlite3.Error as error:
                    raise ValueError('납품 이력 DB에서 파일 소유권을 확인할 수 없습니다') from error
        stale = connection.execute("SELECT path FROM management_paths WHERE kind='file' AND role='delivery-final'").fetchall()
        connection.executemany('DELETE FROM management_paths WHERE path=?', [(path,) for (path,) in stale if path not in live])
        for path, (group_id, project_id, workspace) in live.items():
            self.management_db.claim_path(path, 'delivery-final', group_id=group_id, project_id=project_id, workspace=workspace, kind='file', connection=connection)

    def _sync_file_ownership(self, value, connection):
        from storage_packaging import TRUSTED_ROOT
        self._sync_delivery_ownership(set(value['groups']), connection)
        references = {}
        priority = {'source': 3, 'final': 2, 'artifact': 1}
        for group_id, group in sorted(value['groups'].items()):
            for role, items in (('source', [group['source']]), ('final', group['files']), ('artifact', group.get('artifacts', []))):
                for item in items:
                    path = item['path']
                    previous = references.get(path)
                    if previous is not None and priority[previous[0]] >= priority[role]:
                        continue
                    references[path] = (role, group_id, item['project'])
        stale = connection.execute("SELECT path FROM management_paths WHERE kind='file' AND role IN ('source','final','artifact')").fetchall()
        connection.executemany("DELETE FROM management_paths WHERE path=?", [(path,) for (path,) in stale if path not in references])
        for path, (role, group_id, project) in references.items():
            workspace = str(TRUSTED_ROOT) if TRUSTED_ROOT is not None and Path(path).is_relative_to(TRUSTED_ROOT) else None
            self.management_db.claim_path(path, role, group_id=group_id, project_id=hashlib.sha256(project.encode('utf-8')).hexdigest(), workspace=workspace, kind='file', connection=connection)

    def _save(self, value, connection=None):
        self._validate_document(value)
        try:
            with self.management_db._connection(connection, write=True) as writer:
                self.management_db.write_document('work-library', value, self.path, self._validate_document, connection=writer)
                self._sync_file_ownership(value, writer)
        except ManagementDBError as error:
            raise ValueError(str(error)) from error

    def migrate_management_metadata(self):
        try:
            self._read()
            with self.management_db.transaction(write=True) as connection:
                value = self.management_db.migrate_legacy('work-library', self.path, self._empty(), self._validate_document, connection=connection)
                self._sync_file_ownership(value, connection)
        except ManagementDBError as error:
            raise ValueError(str(error)) from error
        return {'migrated': True, 'groups': len(value['groups']), 'dbPath': str(self.management_db.path)}

    def _structure_busy(self):
        settings = self.path.parent / 'settings.json'
        if not settings.exists():
            return
        if settings.is_symlink() or not settings.is_file():
            raise ValueError('구조 이전 설정 파일을 확인할 수 없습니다')
        value = _json_load(settings, {})
        root = value.get('deliveryRoot') if isinstance(value, dict) else None
        if not isinstance(root, str) or not root:
            return
        raw_path = Path(root)
        if not raw_path.is_absolute() or raw_path.is_symlink():
            raise ValueError('구조 이전 출력 경로를 확인할 수 없습니다')
        path = raw_path.resolve(strict=True)
        marker = path / '.roadmusic' / 'structure.json'
        if not marker.exists():
            return
        if marker.is_symlink() or not marker.is_file():
            raise ValueError('구조 이전 상태 파일을 확인할 수 없습니다')
        state = _json_load(marker, {})
        if isinstance(state, dict) and state.get('phase') in {'preparing', 'prepared'} and state.get('owner') == 'road-music' and state.get('workspace') in {str(raw_path), str(path)}:
            raise ValueError('작업 폴더 구조 이전이 진행 중입니다. 완료 뒤 다시 등록하세요')

    @staticmethod
    def _validate_entry(item, allowed_kinds):
        required = {'id', 'kind', 'name', 'path', 'size', 'sha256', 'createdAt', 'timestampSource', 'styleLabel', 'styleId', 'mode', 'project', 'statSize', 'statMtimeNs', 'sourceStatus'}
        optional = {'origins', 'producedAt', 'technical', 'forVideoSha256', 'artifactType'}
        if not isinstance(item, dict) or not required.issubset(item) or set(item) - required - optional:
            raise ValueError('작업물 라이브러리 파일 메타데이터가 올바르지 않습니다')
        if not isinstance(item['id'], str) or not SHA256.fullmatch(item['id']) or item['kind'] not in allowed_kinds:
            raise ValueError('작업물 라이브러리 파일 ID가 올바르지 않습니다')
        if not isinstance(item['sha256'], str) or not SHA256.fullmatch(item['sha256']) or not isinstance(item['path'], str) or not Path(item['path']).is_absolute():
            raise ValueError('작업물 라이브러리 파일 경로가 올바르지 않습니다')
        if not isinstance(item['name'], str) or Path(item['name']).name != item['name'] or not item['name']:
            raise ValueError('작업물 라이브러리 파일명이 올바르지 않습니다')
        if not all(isinstance(item[key], int) and item[key] >= 0 for key in ('size', 'statSize', 'statMtimeNs')):
            raise ValueError('작업물 라이브러리 파일 크기가 올바르지 않습니다')
        if not _valid_timestamp(item['createdAt']) or item['timestampSource'] not in {'file-created', 'file-modified'}:
            raise ValueError('작업물 라이브러리 파일 시각이 올바르지 않습니다')
        if not isinstance(item['styleLabel'], str) or not isinstance(item['mode'], str) or not isinstance(item['project'], str) or not isinstance(item['styleId'], (str, type(None))):
            raise ValueError('작업물 라이브러리 파일 스타일이 올바르지 않습니다')
        if item['sourceStatus'] not in {'source', 'current', 'unverified-source'}:
            raise ValueError('작업물 라이브러리 원음 상태가 올바르지 않습니다')
        if 'origins' not in item:
            item['origins'] = [_origin(item['project'], item['mode'], item['styleLabel'], item['styleId'], {}, {}, None)]
        origins = item['origins']
        if not isinstance(origins, list) or not origins:
            raise ValueError('작업물 라이브러리 원본 이력이 올바르지 않습니다')
        seen_origins = set()
        for origin in origins:
            expected = {'project', 'mode', 'styleLabel', 'styleId', 'registeredAt', 'selection', 'feedback'}
            if not isinstance(origin, dict) or set(origin) != expected:
                raise ValueError('작업물 라이브러리 원본 이력이 올바르지 않습니다')
            if not isinstance(origin['project'], str) or not Path(origin['project']).is_absolute() or not isinstance(origin['mode'], str):
                raise ValueError('작업물 라이브러리 원본 이력이 올바르지 않습니다')
            if not isinstance(origin['styleLabel'], str) or not isinstance(origin['styleId'], (str, type(None))) or not isinstance(origin['selection'], dict) or not isinstance(origin['feedback'], dict):
                raise ValueError('작업물 라이브러리 원본 이력이 올바르지 않습니다')
            if origin['registeredAt'] is not None and not _valid_timestamp(origin['registeredAt']):
                raise ValueError('작업물 라이브러리 원본 이력이 올바르지 않습니다')
            marker = _origin_key(origin)
            if marker in seen_origins:
                raise ValueError('작업물 라이브러리 원본 이력이 중복되었습니다')
            seen_origins.add(marker)
        if 'producedAt' not in item:
            item['producedAt'] = None
        if item['producedAt'] is not None and not _valid_timestamp(item['producedAt']):
            raise ValueError('작업물 라이브러리 제작 시각이 올바르지 않습니다')
        if 'technical' not in item:
            item['technical'] = _empty_technical()
        technical = item['technical']
        if not isinstance(technical, dict) or set(technical) != set(_empty_technical()):
            raise ValueError('작업물 라이브러리 기술 정보가 올바르지 않습니다')
        def finite_number(value, minimum=0):
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= minimum
        if technical['durationSeconds'] is not None and not finite_number(technical['durationSeconds']):
            raise ValueError('작업물 라이브러리 기술 정보가 올바르지 않습니다')
        if any(technical[key] is not None and (not isinstance(technical[key], int) or isinstance(technical[key], bool) or technical[key] <= 0) for key in ('width', 'height')):
            raise ValueError('작업물 라이브러리 기술 정보가 올바르지 않습니다')
        if technical['fps'] is not None and not finite_number(technical['fps'], minimum=0.001):
            raise ValueError('작업물 라이브러리 기술 정보가 올바르지 않습니다')
        if any(technical[key] is not None and not isinstance(technical[key], str) for key in ('videoCodec', 'audioCodec')):
            raise ValueError('작업물 라이브러리 기술 정보가 올바르지 않습니다')
        if item['kind'] == 'captions':
            if 'forVideoSha256' in item and (not isinstance(item['forVideoSha256'], str) or not SHA256.fullmatch(item['forVideoSha256'])):
                raise ValueError('작업물 라이브러리 자막 연결이 올바르지 않습니다')
        elif 'forVideoSha256' in item:
            raise ValueError('작업물 라이브러리 자막 연결이 올바르지 않습니다')
        if item['kind'] == 'artifact':
            if item.get('artifactType') not in ARTIFACT_TYPES:
                raise ValueError('작업물 라이브러리 제작 자료가 올바르지 않습니다')
        elif 'artifactType' in item:
            raise ValueError('작업물 라이브러리 제작 자료가 올바르지 않습니다')

    @classmethod
    def _validate_group(cls, group_id, group):
        if not isinstance(group_id, str) or not SHA256.fullmatch(group_id) or not isinstance(group, dict):
            raise ValueError('작업물 라이브러리 그룹이 올바르지 않습니다')
        if not isinstance(group, dict) or set(group) - {'groupId', 'title', 'sourceSha256', 'source', 'files', 'artifacts'} or not {'groupId', 'title', 'sourceSha256', 'source', 'files'}.issubset(group) or group.get('groupId') != group_id or group.get('sourceSha256') != group_id:
            raise ValueError('작업물 라이브러리 그룹이 올바르지 않습니다')
        group.setdefault('artifacts', [])
        if not isinstance(group['title'], str) or not group['title'] or not isinstance(group['files'], list) or not isinstance(group['artifacts'], list):
            raise ValueError('작업물 라이브러리 그룹 메타데이터가 올바르지 않습니다')
        cls._validate_entry(group['source'], {'source'})
        seen = set()
        for item in group['files']:
            cls._validate_entry(item, COMPLETED_KINDS)
            key = (item['kind'], item['sha256'])
            if key in seen:
                raise ValueError('작업물 라이브러리 파일이 중복되었습니다')
            seen.add(key)
        for item in group['artifacts']:
            cls._validate_entry(item, {'artifact'})
            key = (item['kind'], item['sha256'])
            if key in seen:
                raise ValueError('작업물 라이브러리 파일이 중복되었습니다')
            seen.add(key)

    @contextmanager
    def _write_lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(f'.{self.path.name}.lock')
        with self._lock, lock_path.open('a+b') as stream:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
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

    @staticmethod
    def _project(project):
        raw = Path(project)
        if not raw.is_absolute():
            raise ValueError('프로젝트는 절대 경로여야 합니다')
        path = raw.resolve(strict=True)
        if not path.is_dir():
            raise ValueError('프로젝트 폴더가 필요합니다')
        return path

    @staticmethod
    def _selection(project):
        selection = _json_load(project / 'selection.json', {})
        return selection if isinstance(selection, dict) else {}

    def _snapshot(self, project):
        data = _json_load(project / PROJECT_FILE, None)
        if not isinstance(data, dict) or data.get('schemaVersion') != 1 or not isinstance(data.get('media'), list):
            raise ValueError('지원하지 않는 제작실 프로젝트입니다')
        music = next((item for item in data['media'] if isinstance(item, dict) and item.get('id') == 'music' and item.get('kind') == 'music'), None)
        if music is None:
            raise ValueError('그룹화할 입력 원음이 등록되지 않았습니다')
        mode = data.get('mode') if data.get('mode') in MODE_LABELS else 'showreel-motion'
        selection = self._selection(project)
        feedback = _json_load(project / 'feedback.json', {})
        feedback = feedback if isinstance(feedback, dict) else {}
        registered_at = _now()
        selected_style = selection.get('styleId') if isinstance(selection.get('styleId'), str) and selection['styleId'].strip() else None
        fallback = selected_style or f'{MODE_LABELS[mode]} · 세부 스타일 미기록'
        source = _entry(music, 'source', project, mode, '사용한 원음', selection, feedback, registered_at)
        source['styleLabel'] = '사용한 원음'
        source['styleId'] = None
        source['sourceStatus'] = 'source'
        files, artifacts = [], []
        skipped_different_source = 0
        for item in data['media']:
            if not isinstance(item, dict) or item.get('id') == 'music' or item.get('kind') not in COMPLETED_KINDS | {'artifact'}:
                continue
            claimed_source = item.get('sourceMusicSha256')
            if claimed_source is None:
                source_status = 'unverified-source'
            elif not isinstance(claimed_source, str) or not SHA256.fullmatch(claimed_source.lower()):
                raise ValueError('결과 파일의 sourceMusicSha256이 올바르지 않습니다')
            elif claimed_source.lower() != source['sha256']:
                skipped_different_source += 1
                continue
            else:
                source_status = 'current'
            entry = _entry(item, item['kind'], project, mode, fallback, selection, feedback, registered_at)
            entry['sourceStatus'] = source_status
            (artifacts if item['kind'] == 'artifact' else files).append(entry)
        if not files:
            raise ValueError('현재 원음과 연결된 완성 파일이 없습니다')
        return source, files, artifacts, skipped_different_source

    @staticmethod
    def _merge_entry(previous, incoming):
        """Keep the newest verified location while retaining every prior production origin."""
        merged = deepcopy(incoming)
        try:
            previous_path = _safe_path(previous.get('path'), '작업물 파일')
            previous_stat = previous_path.stat()
            previous_valid = _sha256(previous_path) == previous.get('sha256')
        except (OSError, ValueError):
            previous_valid = False
        if previous_valid:
            # A still-verifiable representative stays stable; provenance contains the newer project snapshot.
            merged.update({
                'name': previous.get('name', previous_path.name), 'path': str(previous_path),
                'size': previous_stat.st_size, 'createdAt': previous.get('createdAt'),
                'timestampSource': previous.get('timestampSource'),
                'statSize': previous_stat.st_size, 'statMtimeNs': previous_stat.st_mtime_ns,
            })
        for key in ('producedAt', 'forVideoSha256', 'artifactType'):
            before, after = previous.get(key), incoming.get(key)
            if before is not None and after is not None and before != after:
                raise ValueError(f'같은 파일의 {key} 메타데이터가 충돌합니다')
            if before is not None and after is None:
                merged[key] = before
        origins, seen = [], set()
        for candidate in [*(previous.get('origins', []) if isinstance(previous, dict) else []), *incoming.get('origins', [])]:
            if not isinstance(candidate, dict):
                continue
            marker = _origin_key(candidate)
            if marker not in seen:
                origins.append(deepcopy(candidate))
                seen.add(marker)
        merged['origins'] = origins
        return merged

    @classmethod
    def _merge_entries(cls, destination, incoming):
        positions = {(item.get('kind'), item.get('sha256')): index for index, item in enumerate(destination) if isinstance(item, dict)}
        for item in incoming:
            key = (item['kind'], item['sha256'])
            if key in positions:
                destination[positions[key]] = cls._merge_entry(destination[positions[key]], item)
            else:
                destination.append(item)
                positions[key] = len(destination) - 1

    def register(self, project):
        """Atomically merge one fully verified project snapshot into its source group."""
        project = self._project(project)
        with self._write_lock():
            # Recheck after acquiring the library lock so a queued old session cannot publish a stale snapshot after migration starts.
            self._structure_busy()
            source, incoming, incoming_artifacts, skipped_different_source = self._snapshot(project)  # Validate every included file before writing anything.
            group_id = source['sha256']
            title = unicodedata.normalize('NFC', Path(source['name']).stem)
            value = self._read()
            groups = value['groups']
            existing = groups.get(group_id)
            if existing is None:
                existing = {'groupId': group_id, 'title': title, 'sourceSha256': group_id, 'source': source, 'files': [], 'artifacts': []}
            else:
                if not isinstance(existing, dict) or existing.get('groupId') != group_id or not isinstance(existing.get('files'), list):
                    raise ValueError('작업물 라이브러리 그룹이 올바르지 않습니다')
                existing['source'] = self._merge_entry(existing['source'], source)
                existing.setdefault('title', title)
                existing['sourceSha256'] = group_id
            self._merge_entries(existing['files'], incoming)
            self._merge_entries(existing['artifacts'], incoming_artifacts)
            video_shas = {item['sha256'] for item in existing['files'] if isinstance(item, dict) and item.get('kind') == 'video'}
            for caption in (item for item in existing['files'] if isinstance(item, dict) and item.get('kind') == 'captions'):
                if caption.get('forVideoSha256') is not None and caption['forVideoSha256'] not in video_shas:
                    raise ValueError('자막 연결 영상이 같은 음악 그룹에 없습니다')
            groups[group_id] = existing
            self._save(value)
        result = self.group(group_id)
        result['skippedDifferentSource'] = skipped_different_source
        return result

    def refresh_project_paths(self, project):
        """Point one project's verified entries at its canonical delivery copies."""
        project = self._project(project)
        source, incoming, _, _ = self._snapshot(project)
        group_id = source['sha256']
        with self._write_lock():
            value = self._read(); group = value['groups'].get(group_id)
            if not isinstance(group, dict):
                raise ValueError('등록된 작업물 그룹이 아닙니다')
            targets = {('source', source['sha256']): ('source', source)}
            targets.update({(item['kind'], item['sha256']): ('files', item) for item in incoming})
            for key, (section, replacement) in targets.items():
                existing = group['source'] if section == 'source' else next((item for item in group['files'] if (item.get('kind'), item.get('sha256')) == key), None)
                if not isinstance(existing, dict) or not any(origin.get('project') == str(project) for origin in existing.get('origins', []) if isinstance(origin, dict)):
                    continue
                merged = deepcopy(replacement)
                merged['origins'] = []
                seen = set()
                for origin in [*existing.get('origins', []), *replacement.get('origins', [])]:
                    if isinstance(origin, dict) and _origin_key(origin) not in seen:
                        merged['origins'].append(origin); seen.add(_origin_key(origin))
                if section == 'source': group['source'] = merged
                else:
                    index = group['files'].index(existing); group['files'][index] = merged
            self._save(value)
        return self.group(group_id)

    @staticmethod
    def _availability(item):
        try:
            raw = Path(item['path'])
            path = raw.resolve(strict=True)
            if not raw.is_absolute() or raw.is_symlink() or path.is_symlink() or not path.is_file():
                return False
            stat = path.stat()
            return stat.st_size == item.get('statSize') and stat.st_mtime_ns == item.get('statMtimeNs')
        except (OSError, RuntimeError):
            return False

    @classmethod
    def _public_file(cls, item):
        result = {key: item.get(key) for key in ('id', 'kind', 'name', 'path', 'size', 'sha256', 'createdAt', 'timestampSource', 'styleLabel', 'styleId', 'mode', 'project', 'sourceStatus', 'origins', 'producedAt', 'technical', 'forVideoSha256', 'artifactType') if key in item}
        result['registeredAt'] = _registered_at([item])
        result['available'] = cls._availability(item)
        return result

    def _group_data(self, group_id):
        if not isinstance(group_id, str) or not SHA256.fullmatch(group_id):
            raise ValueError('그룹 ID가 올바르지 않습니다')
        with self._lock:
            group = self._read()['groups'].get(group_id)
        if not isinstance(group, dict) or group.get('groupId') != group_id or not isinstance(group.get('source'), dict) or not isinstance(group.get('files'), list):
            raise ValueError('등록된 작업물 그룹이 아닙니다')
        return deepcopy(group)

    @classmethod
    def _public_group(cls, group, detail=False, favorite=None):
        source = cls._public_file(group['source'])
        files = [cls._public_file(item) for item in group['files'] if isinstance(item, dict)]
        artifacts = [cls._public_file(item) for item in group.get('artifacts', []) if isinstance(item, dict)]
        source['removeDisabled'] = True; source['protectedReason'] = '현재 원음은 개별 제거할 수 없습니다.'
        for item in files:
            item['removeDisabled'] = False
        for item in artifacts:
            item['removeDisabled'] = True; item['protectedReason'] = '제작 자료는 버전 이력에서 보존합니다.'
        listening_files = [source, *files]
        all_files = [*listening_files, *artifacts]
        dates = [item['createdAt'] for item in files]
        videos = [item for item in files if item.get('kind') == 'video']
        style_origins = [origin for item in videos for origin in item.get('origins', []) if isinstance(origin, dict)]
        styles = sorted({origin['styleLabel'] for origin in style_origins if isinstance(origin.get('styleLabel'), str) and not origin['styleLabel'].endswith('세부 스타일 미기록')})
        unknown = [item for item in videos if not any(isinstance(origin, dict) and isinstance(origin.get('styleLabel'), str) and not origin['styleLabel'].endswith('세부 스타일 미기록') for origin in item.get('origins', []))]
        storyboards = [item for item in files if item.get('kind') == 'storyboard']
        preview = next((item for item in videos if item['available']), None)
        result = {
            'groupId': group['groupId'], 'title': group['title'], 'sourceSha256': group['sourceSha256'], 'source': source,
            'fileCount': len(files), 'artifactCount': len(artifacts), 'videoCount': len(videos), 'storyboardCount': len(storyboards), 'styleCount': len(styles), 'unclassifiedStyleCount': len(unknown), 'styles': styles,
            'size': sum(item.get('size', 0) for item in all_files if isinstance(item.get('size'), int)),
            'createdAt': min(dates) if dates else None, 'updatedAt': max(dates) if dates else None, 'createdTimes': sorted(set(dates)), 'registeredAt': _registered_at([group['source'], *group['files'], *group.get('artifacts', [])]),
            'previewVideo': preview, 'available': all(item['available'] for item in listening_files), 'productionAvailable': all(item['available'] for item in all_files),
            'favorite': bool(favorite), 'likedAt': favorite.get('likedAt') if favorite else None,
        }
        if detail:
            result['files'] = files
            result['artifacts'] = artifacts
        return result

    def groups(self, favorites_only=False):
        if type(favorites_only) is not bool:
            raise ValueError('favoritesOnly는 boolean이어야 합니다')
        with self._lock:
            values = list(self._read()['groups'].values())
        favorites = self.management_db.favorites({group.get('groupId') for group in values if isinstance(group, dict) and isinstance(group.get('groupId'), str)})
        groups = [self._public_group(group, favorite=favorites.get(group.get('groupId'))) for group in values if isinstance(group, dict) and (not favorites_only or group.get('groupId') in favorites)]
        return sorted(groups, key=lambda group: (group['updatedAt'] or '', group['groupId']), reverse=True)

    def group(self, group_id):
        group = self._group_data(group_id)
        return self._public_group(group, detail=True, favorite=self.management_db.favorites({group_id}).get(group_id))

    def set_favorite(self, group_id, favorite):
        if not isinstance(group_id, str) or not SHA256.fullmatch(group_id) or type(favorite) is not bool:
            raise ValueError('좋아요 요청이 올바르지 않습니다')
        with self._write_lock():
            if group_id not in self._read()['groups']:
                raise ValueError('등록된 작업물 그룹이 아닙니다')
            try:
                return self.management_db.set_favorite(group_id, favorite)
            except ManagementDBError as error:
                raise ValueError(str(error)) from error

    def _trusted(self, group_id, file_id):
        if not isinstance(file_id, str) or not SHA256.fullmatch(file_id):
            raise ValueError('파일 ID가 올바르지 않습니다')
        group = self._group_data(group_id)
        candidates = [group['source'], *group['files'], *group.get('artifacts', [])]
        item = next((candidate for candidate in candidates if isinstance(candidate, dict) and candidate.get('id') == file_id), None)
        if item is None:
            raise ValueError('등록된 작업물 파일이 아닙니다')
        try:
            path = _safe_path(item.get('path'), '작업물 파일')
        except OSError as error:
            raise ValueError('등록된 작업물 파일을 찾을 수 없습니다') from error
        stat = path.stat()
        # Size and mtime are only quick UI hints; serving always validates the recorded bytes.
        if _sha256(path) != item.get('sha256'):
            raise ValueError('등록 뒤 파일이 변경되어 제공하지 않습니다')
        if stat.st_size != item.get('statSize') or stat.st_mtime_ns != item.get('statMtimeNs'):
            item['statSize'], item['statMtimeNs'] = stat.st_size, stat.st_mtime_ns
            self._refresh_observed(group_id, item)
        return {**self._public_file(item), 'path': path}

    def _refresh_observed(self, group_id, changed):
        with self._write_lock():
            value = self._read(); group = value['groups'].get(group_id)
            if not isinstance(group, dict):
                raise ValueError('등록된 작업물 그룹이 아닙니다')
            items = [group.get('source'), *(group.get('files') or []), *(group.get('artifacts') or [])]
            target = next((item for item in items if isinstance(item, dict) and item.get('id') == changed['id']), None)
            if target is None:
                raise ValueError('등록된 작업물 파일이 아닙니다')
            target['statSize'], target['statMtimeNs'] = changed['statSize'], changed['statMtimeNs']
            self._save(value)

    def file(self, group_id, file_id):
        return self._trusted(group_id, file_id)

    def archive(self, group_id, include_artifacts=False):
        group = self._group_data(group_id)
        # Validate every member first so a missing/changed item never yields a partial archive.
        candidates = [group['source'], *group['files']]
        if include_artifacts:
            candidates.extend(group.get('artifacts', []))
        members = [self._trusted(group_id, item['id']) for item in candidates if isinstance(item, dict)]
        stream = tempfile.TemporaryFile()
        names, digests = set(), set()
        try:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
                for item in members:
                    if item['sha256'] in digests:
                        continue
                    base = Path(item['name'].replace('\\', '/')).name
                    if base in {'', '.', '..'}:base = 'download'
                    stem, suffix = Path(base).stem, Path(base).suffix
                    name, number = base, 2
                    while name.casefold() in names:
                        name = f'{stem} ({number}){suffix}'
                        number += 1
                    names.add(name.casefold()); digests.add(item['sha256'])
                    digest = hashlib.sha256()
                    with item['path'].open('rb') as source, archive.open(name, 'w', force_zip64=True) as output:
                        while block := source.read(64 * 1024):
                            digest.update(block)
                            output.write(block)
                    if digest.hexdigest() != item['sha256']:
                        raise ValueError('등록 뒤 파일이 변경되어 묶음 파일을 만들지 않습니다')
            stream.seek(0)
            return stream
        except Exception:
            stream.close()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('list', 'favorite'))
    parser.add_argument('--data-dir', required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--json')
    source.add_argument('--stdin', action='store_true')
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1).decode('utf-8') if args.stdin else args.json
        if len(raw.encode('utf-8')) > 1024 * 1024: raise ValueError('입력 JSON이 안전 한도를 초과했습니다')
        params = json.loads(raw)
        if not isinstance(params, dict): raise ValueError('JSON 객체가 필요합니다')
        data_dir = Path(args.data_dir)
        if not data_dir.is_absolute() or data_dir.is_symlink(): raise ValueError('data-dir는 안전한 절대 경로여야 합니다')
        library = WorkLibrary(data_dir / 'video-studio-library.json')
        if args.action == 'list':
            if set(params) - {'favoritesOnly'} or ('favoritesOnly' in params and type(params['favoritesOnly']) is not bool): raise ValueError('list 요청이 올바르지 않습니다')
            result = {'groups': library.groups(params.get('favoritesOnly', False))}
        else:
            if set(params) != {'groupId', 'favorite'}: raise ValueError('favorite 요청이 올바르지 않습니다')
            result = library.set_favorite(params['groupId'], params['favorite'])
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, ManagementDBError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(json.dumps({'ok': False, 'error': {'code': 'work_library_error', 'message': str(error)}}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
