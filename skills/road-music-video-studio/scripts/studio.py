#!/usr/bin/env python3
"""Token-protected loopback desk for choosing and reviewing local music-video work."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sys
import subprocess
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from html_design import ASSET_ROOT as DESIGN_ASSETS, FONT_FILES, css_text, add_navigation, studio_session_file, open_page
from guide_content import guide_media_file, markdown_source, render_guide, guide_for_engine
from storage_manager import StorageManager
from storage_tracking import StorageTracking
from storage_lifecycle import complete_published_project, working_project_path
from studio_status import status_snapshot, reference_snapshot, recipe_snapshot
from production_runtime import read_runtime_queue
from work_library import WorkLibrary
from delivery_store import DeliveryStore
from management_db import ManagementDB, ManagementDBError
from production_ledger import ProductionLedger, ProductionLedgerError
from result_records import ARTIFACT_TYPES, ARTIFACT_EXTENSIONS, validate_sync_checks, feedback_history
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT.parent
PLAYLIST_ROOT = SKILLS_ROOT / 'road-music-showreel-playlist'
PRESET_ROOT = PLAYLIST_ROOT / 'assets' / 'presets'
JIZURA_SCRIPT = SKILLS_ROOT / 'road-music-jizura-playlist' / 'scripts' / 'studio.py'
DEFAULT_JIZURA_ROOT = Path.home() / '.local/share/roadmusic-video-tools/jizura'
TEMPLATE = ROOT / 'assets' / 'studio.html'
RESULTS_TEMPLATE = ROOT / 'assets' / 'results.html'
REVIEW_TEMPLATE = ROOT / 'assets' / 'review.html'
WORKS_TEMPLATE = ROOT / 'assets' / 'works.html'
WORK_DETAIL_TEMPLATE = ROOT / 'assets' / 'work-detail.html'
STORAGE_TEMPLATE = ROOT / 'assets' / 'storage.html'
DASHBOARD_TEMPLATE = ROOT / 'assets' / 'dashboard.html'
EXAMPLES = ROOT / 'assets' / 'examples.json'
PROJECT_FILE = 'studio-project.json'
SELECTION_FILE = 'selection.json'
FEEDBACK_FILE = 'feedback.json'
REQUEST_FILE = 'production-request.json'
SHOWREEL_REQUEST_FILE = 'showreel-request.json'
MAX_JSON = 64 * 1024
MAX_UPLOAD = 512 * 1024 * 1024
MAX_LYRICS_TEXT = 256 * 1024
MAX_SHARED_CACHE_OUTPUT = 1024 * 1024
SHARED_CACHE_TIMEOUT = 30
MAX_MAINTENANCE_OUTPUT = 16 * 1024 * 1024
MAINTENANCE_TIMEOUTS = {'maintenance-list': 180, 'maintenance-preview': 180, 'maintenance-history': 180, 'maintenance-cleanup': 900,
                        'status': 30,
                        'overview': 180, 'versions': 180, 'version-diff': 180,
                        'restructure-status': 180, 'restructure-preview': 180, 'restructure-cleanup': 900,
                        'mv-list': 180, 'mv-preview': 180, 'mv-cleanup': 900, 'sweep-preview': 180, 'sweep-cleanup': 900}
MODES = {
    'showreel-cd': ('Road Music Showreel CD', '실제 CD 프리셋으로 플레이리스트 영상을 준비합니다.'),
    'showreel-mv': ('Road Music 쇼릴 MV', '스토리보드와 리듬 편집 방향을 저장합니다.'),
    'jizura': ('JIZURA 음악 스튜디오', '별도 JIZURA 편집기에 전달할 제작 방향을 저장합니다.'),
    'showreel-motion': ('Showreel 음악 모션그래픽', '이미지·타이포·리듬 모션 방향을 저장합니다.'),
}
HOSTS = {'codex', 'claude', 'antigravity', 'antigravity-cli'}
MEDIA_EXTENSIONS = {
    'music': {'.aac', '.aif', '.aiff', '.flac', '.m4a', '.mp3', '.oga', '.ogg', '.opus', '.wav', '.webm'},
    'video': {'.m4v', '.mov', '.mp4', '.webm'},
    'storyboard': {'.avif', '.gif', '.jpeg', '.jpg', '.png', '.webp'},
    'captions': {'.ass', '.lrc', '.srt', '.vtt'},
    'lyrics': {'.md', '.txt'},
    'artifact': set(ARTIFACT_EXTENSIONS),
}
SAFE_ID = re.compile(r'[a-z][a-z0-9-]{0,80}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


def completed_zip(session):
    """Archive published deliverables only, leaving registered source files untouched."""
    selected = [
        item for item in session.media().values()
        if item.get('id') != 'music' and item.get('kind') in {'video', 'music', 'lyrics', 'captions'}
    ]
    if not selected:
        raise ValueError('내려받을 완성 파일이 없습니다')
    stream = tempfile.TemporaryFile()
    used = set()
    try:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            for item in selected:
                source = item['path']
                base = Path(item['name'].replace('\\', '/')).name
                if base in {'', '.', '..'}:base = 'download'
                stem, suffix = Path(base).stem, Path(base).suffix
                name, number = base, 2
                while name.casefold() in used:
                    name = f'{stem} ({number}){suffix}'
                    number += 1
                used.add(name.casefold())
                with source.open('rb') as original, archive.open(name, 'w', force_zip64=True) as destination:
                    while block := original.read(64 * 1024):
                        destination.write(block)
        stream.seek(0)
        return stream
    except Exception:
        stream.close()
        raise


def json_load(raw):
    return json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'JSON 값 {x}은 허용되지 않습니다')))


def atomic_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix=f'.{path.name}.', delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        temporary = Path(stream.name)
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def file_snapshots(paths):
    """Keep a few small metadata files reversible when the SQLite ledger rejects a change."""
    saved = {}
    for raw in paths:
        path = Path(raw)
        saved[path] = path.read_bytes() if path.is_file() and not path.is_symlink() else None
    return saved


def restore_file_snapshots(saved):
    for path, raw in saved.items():
        if raw is None:
            path.unlink(missing_ok=True)
            continue
        with tempfile.NamedTemporaryFile('wb', dir=path.parent, prefix=f'.{path.name}.', delete=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        try:
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def absolute_file(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label}: 절대 파일 경로가 필요합니다')
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f'{label}: 절대 파일 경로가 필요합니다')
    if path.is_symlink():
        raise ValueError(f'{label}: 심볼릭 링크는 등록할 수 없습니다')
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f'{label}: 일반 파일이 필요합니다')
    return path


def allowed_media(path, kind):
    path = Path(path)
    if path.suffix.lower() not in MEDIA_EXTENSIONS[kind]:
        raise ValueError(f'{kind}: 지원하지 않는 파일 형식입니다')
    return path


def lyrics_text(path, label="가사"):
    """Return a bounded UTF-8 lyric source, with an optional BOM removed."""
    path = Path(path)
    if path.stat().st_size > MAX_LYRICS_TEXT:
        raise ValueError(f'{label} 파일이 너무 큽니다')
    with path.open('rb') as stream:
        raw = stream.read(MAX_LYRICS_TEXT + 1)
    if len(raw) > MAX_LYRICS_TEXT:
        raise ValueError(f'{label} 파일이 너무 큽니다')
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError(f'{label} 파일은 UTF-8이어야 합니다') from error


def descriptor(path, kind, identifier='music'):
    path = allowed_media(Path(path), kind).resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValueError('일반 파일만 등록할 수 있습니다')
    if kind == 'lyrics':
        lyrics_text(path)
    return {'id': identifier, 'kind': kind, 'path': str(path), 'name': path.name,
            'size': path.stat().st_size, 'sha256': sha256(path)}


def empty_selection(mode='showreel-motion', host='codex'):
    return {'schemaVersion': 1, 'host': host, 'mode': mode, 'styleId': None,
            'display': {'showSpectrum': None, 'showQueue': None, 'showNowPlaying': None, 'channelName': None}}


def image_policy(host):
    if host not in HOSTS:
        raise ValueError('지원하지 않는 작업 호스트입니다')
    return {'provider': 'gpt-image' if host == 'claude' else 'image_gen' if host == 'codex' else 'antigravity-native', 'allowPaidModels': False}


def validate_selection(value, previous):
    if not isinstance(value, dict) or set(value) - {'host', 'mode', 'styleId', 'display', 'request'}:
        raise ValueError('선택에는 host/mode/styleId/display와 선택 request만 포함할 수 있습니다')
    host = value.get('host')
    if host not in HOSTS:
        raise ValueError('지원하지 않는 작업 호스트입니다')
    mode = value.get('mode')
    if mode not in MODES:
        raise ValueError('지원하지 않는 제작 방식입니다')
    style = value.get('styleId')
    if style is not None and (not isinstance(style, str) or not SAFE_ID.fullmatch(style)):
        raise ValueError('styleId가 올바르지 않습니다')
    if mode == 'showreel-cd' and style is None:
        raise ValueError('CD 제작에는 실제 스타일을 선택해야 합니다')
    if mode in {'showreel-mv', 'jizura'} and style is not None:
        raise ValueError('MV와 JIZURA 제작은 CD 프리셋을 사용하지 않습니다')
    display = value.get('display')
    keys = {'showSpectrum', 'showQueue', 'showNowPlaying', 'channelName'}
    if not isinstance(display, dict) or set(display) != keys:
        raise ValueError('네 화면 표시 항목을 모두 포함해야 합니다')
    old = previous.get('display', {}) if isinstance(previous, dict) else {}
    normalized = {}
    for key in ('showSpectrum', 'showQueue', 'showNowPlaying'):
        item = display[key]
        if item is None:
            normalized[key] = old.get(key)
        elif isinstance(item, bool):
            normalized[key] = item
        else:
            raise ValueError(f'{key}: true/false/SKIP만 가능합니다')
    channel = display['channelName']
    if channel is None:
        normalized['channelName'] = old.get('channelName')
    elif isinstance(channel, str) and 1 <= len(channel.strip()) <= 120:
        normalized['channelName'] = channel.strip()
    else:
        raise ValueError('채널명은 1~120자 또는 SKIP이어야 합니다')
    result = {'schemaVersion': 1, 'host': host, 'mode': mode, 'styleId': style, 'display': normalized}
    if value.get('request') is not None:
        if value['request'] != 'jizura-editor':
            raise ValueError('지원하지 않는 제작 요청입니다')
        result['request'] = 'jizura-editor'
    return result


def load_json(path, fallback):
    path = Path(path)
    if not path.exists():
        return fallback
    raw = path.read_bytes()
    if len(raw) > MAX_JSON:
        raise ValueError(f'{path.name}: JSON이 너무 큽니다')
    return json_load(raw.decode('utf-8-sig'))


def project_path(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('--project: 절대 프로젝트 경로가 필요합니다')
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError('--project: 폴더가 필요합니다')
    return path


def road_music_cli():
    """Return a verified source/package CLI, never a browser-supplied path."""
    from storage_packaging import TRUSTED_ROOT
    candidates = [os.environ.get('ROADMUSIC_CLI_ROOT'), TRUSTED_ROOT]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            root = Path(candidate).resolve(strict=True)
            package, cli = root / 'package.json', root / 'cli' / 'road-music.js'
            if package.is_symlink() or cli.is_symlink() or not package.is_file() or not cli.is_file() or package.stat().st_size > MAX_JSON:
                continue
            metadata = json_load(package.read_text(encoding='utf-8'))
            if metadata.get('name') == 'road-music' and metadata.get('bin', {}).get('road-music') == 'cli/road-music.js':
                return cli
        except (OSError, ValueError, UnicodeDecodeError, AttributeError):
            continue
    raise ValueError('현재 설치의 Road Music 공개 CLI를 찾을 수 없습니다.')


def shared_video_cache(data_dir, action, plan_id=None):
    if action not in {'video:cache', 'video:cache-clear'}:
        raise ValueError('지원하지 않는 공용 캐시 작업입니다.')
    if action == 'video:cache-clear' and (not isinstance(plan_id, str) or not plan_id or len(plan_id) > 128):
        raise ValueError('공용 캐시 정리 계획이 올바르지 않습니다.')
    args = [os.environ.get('ROAD_MUSIC_NODE') or 'node', str(road_music_cli()), action]
    if plan_id is not None:
        args.extend(['--json', json.dumps({'planId': plan_id}, separators=(',', ':')), '--confirm'])
    args.append('--no-start')
    env = {**os.environ, 'ROADMUSIC_DATA_DIR': str(Path(data_dir).resolve())}
    try:
        completed = subprocess.run(args, check=False, shell=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=SHARED_CACHE_TIMEOUT, env=env)
    except subprocess.TimeoutExpired as error:
        raise ValueError('공용 캐시 명령 시간이 초과되었습니다. 잠시 후 다시 시도하세요.') from error
    stdout = completed.stdout or ''
    if len(stdout.encode('utf-8')) > MAX_SHARED_CACHE_OUTPUT:
        raise ValueError('공용 캐시 명령 응답이 너무 큽니다.')
    lines = [line for line in stdout.splitlines() if line]
    if len(lines) != 1:
        raise ValueError('공용 캐시 명령이 올바른 응답을 반환하지 않았습니다.')
    try:
        response = json_load(lines[0])
    except (ValueError, TypeError):
        raise ValueError('공용 캐시 명령이 올바른 JSON을 반환하지 않았습니다.')
    if not isinstance(response, dict) or not isinstance(response.get('ok'), bool):
        raise ValueError('공용 캐시 명령 응답 형식이 올바르지 않습니다.')
    if not response['ok']:
        error = response.get('error') if isinstance(response.get('error'), dict) else {}
        code = error.get('code')
        if code in {'connection', 'SERVICE_STOPPING'}:
            raise ValueError('현재 앱 프로필이 실행 중이 아닙니다. Road Music 앱을 시작한 뒤 다시 시도하세요.')
        if code == 'UNKNOWN_COMMAND':
            raise ValueError('현재 앱에 공용 영상 캐시 점검 기능이 없습니다. 최신 Road Music 앱으로 다시 시작하세요.')
        raise ValueError(str(error.get('message') or '공용 캐시 명령을 처리하지 못했습니다.'))
    if completed.returncode != 0 or not isinstance(response.get('result'), dict):
        raise ValueError('공용 캐시 명령을 처리하지 못했습니다.')
    return response['result']


def maintenance_storage(data_dir, action, params=None, confirm=False):
    """Run only the fixed public maintenance commands against this studio data profile."""
    if action not in MAINTENANCE_TIMEOUTS or not isinstance(params, dict):
        raise ValueError('지원하지 않는 작업 폴더 정리 요청입니다.')
    try:
        cli = road_music_cli()
    except ValueError as error:
        raise ValueError('현재 설치의 Road Music 공개 CLI를 찾을 수 없습니다. CLI와 스킬 설치 상태를 확인하세요.') from error
    args = [os.environ.get('ROAD_MUSIC_NODE') or 'node', str(cli), f'storage:{action}',
            '--json', json.dumps(params, separators=(',', ':')), '--no-start']
    if confirm:
        args.append('--confirm')
    env = {**os.environ, 'ROADMUSIC_DATA_DIR': str(Path(data_dir).resolve())}
    try:
        completed = subprocess.run(args, check=False, shell=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True, timeout=MAINTENANCE_TIMEOUTS[action], env=env)
    except subprocess.TimeoutExpired as error:
        raise ValueError('작업 폴더 정리 명령 시간이 초과되었습니다. 진행 중인 저장공간 작업의 완료 상태를 확인하세요.') from error
    stdout = completed.stdout or ''
    if len(stdout.encode('utf-8')) > MAX_MAINTENANCE_OUTPUT:
        raise ValueError('작업 폴더 정리 명령 응답이 너무 큽니다.')
    lines = [line for line in stdout.splitlines() if line]
    if len(lines) != 1:
        raise ValueError('작업 폴더 정리 명령이 올바른 응답을 반환하지 않았습니다.')
    try:
        response = json_load(lines[0])
    except (ValueError, TypeError):
        raise ValueError('작업 폴더 정리 명령이 올바른 JSON을 반환하지 않았습니다.')
    if not isinstance(response, dict) or not isinstance(response.get('ok'), bool):
        raise ValueError('작업 폴더 정리 명령 응답 형식이 올바르지 않습니다.')
    if not response['ok']:
        error = response.get('error') if isinstance(response.get('error'), dict) else {}
        if error.get('code') == 'UNKNOWN_COMMAND':
            raise ValueError('현재 설치의 Road Music 공개 CLI에는 작업 폴더 정리 기능이 없습니다. Git으로 설치한 최신 소스에서 사용하세요.')
        raise ValueError(str(error.get('message') or '작업 폴더 정리를 처리하지 못했습니다.'))
    if completed.returncode != 0 or not isinstance(response.get('result'), dict):
        raise ValueError('작업 폴더 정리를 처리하지 못했습니다.')
    return response['result']


def preset_cards():
    cards = []
    if not PRESET_ROOT.is_dir():
        return cards
    for directory in sorted(PRESET_ROOT.iterdir()):
        spec_path = directory / 'preset.json'
        if not directory.is_dir() or not spec_path.is_file():
            continue
        try:
            spec = json_load(spec_path.read_text(encoding='utf-8'))
            preview = spec.get('preview', {})
            if not (isinstance(spec.get('id'), str) and SAFE_ID.fullmatch(spec['id']) and preview.get('status') == 'ready'):
                continue
            video, poster = directory / preview.get('video', ''), directory / preview.get('poster', '')
            if video.is_file() and poster.is_file() and not video.is_symlink() and not poster.is_symlink():
                cards.append({'id': spec['id'], 'category': str(spec.get('category', 'cd')), 'name': str(spec.get('name', spec['id'])),
                              'description': str(spec.get('description', '')), 'previewPath': video, 'posterPath': poster})
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return cards


def example_cards(path=EXAMPLES, skills_root=SKILLS_ROOT):
    """Load only registered, in-tree example media; missing examples are an honest empty state."""
    try:
        value = load_json(path, [])
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(value, list) or len(value) > len(MODES):
        return []
    root = Path(skills_root).resolve()
    cards, seen = [], set()
    for item in value:
        try:
            if not isinstance(item, dict) or set(item) != {'mode', 'title', 'summary', 'tags', 'video', 'poster', 'audioNote', 'provenance'}:
                raise ValueError('examples 항목 형식')
            mode = item['mode']
            required = ('title', 'summary', 'video', 'poster', 'audioNote', 'provenance')
            if mode not in MODES or mode in seen or not all(isinstance(item[key], str) and item[key] for key in required):
                raise ValueError('examples 항목 값')
            if not isinstance(item['tags'], list) or not item['tags'] or len(item['tags']) > 12 or not all(isinstance(tag, str) and 1 <= len(tag) <= 40 for tag in item['tags']):
                raise ValueError('examples tags')
            paths = []
            for key, kind in (('video', 'video'), ('poster', 'storyboard')):
                relative = Path(item[key])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('examples 경로')
                raw_candidate = root / relative
                candidate = raw_candidate.resolve(strict=True)
                if root not in candidate.parents or raw_candidate.is_symlink() or not candidate.is_file():
                    raise ValueError('examples 파일')
                allowed_media(candidate, kind)
                paths.append(candidate)
            cards.append({**item, 'videoPath': paths[0], 'posterPath': paths[1]})
            seen.add(mode)
        except (OSError, ValueError):
            continue
    return cards


class Session:
    def __init__(self, project, music=None, host=None, review=False):
        self.project = project_path(project)
        self.library = WorkLibrary()
        self.storage = StorageManager()
        self.management = ManagementDB(self.storage.data_dir)
        self.production = ProductionLedger(self.storage.data_dir)
        self._updates = None
        self._updates_lock = threading.Lock()
        self.tracking = StorageTracking(self.storage)
        self.storage_projects = set()
        self.storage_plans = {}
        self.storage_legacy_plans = set()
        self.shared_cache_plans = set()
        self.storage_maintenance_plans = {}
        self.storage_maintenance_scan_id = None
        self.storage_sweep_plans = set()
        self.storage_restructure_plans = set()
        self.storage_file_remove_plans = set()
        self.storage_project_finish_plans = set()
        self.storage_reconcile_plans = set()
        self.storage_entity_plans = set()
        self.review = review
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.cards = preset_cards()
        self.samples = {card['mode']: card for card in example_cards()}
        self.card_ids = {card['id'] for card in self.cards}
        self.card_categories = {card['id']: card['category'] for card in self.cards}
        self.data = load_json(self.project / PROJECT_FILE, None)
        if not isinstance(self.data, dict) or self.data.get('schemaVersion') != 1:
            raise ValueError(f'{PROJECT_FILE}: 지원하지 않는 프로젝트입니다')
        self.storage_project_id = self.storage.dispatch('register', {'project': str(self.project)})['id']
        self.storage_projects.add(self.storage_project_id)
        self.refresh_storage_projects()
        if host is not None:
            if host not in HOSTS:
                raise ValueError('지원하지 않는 --host입니다')
            self.data['host'] = host
            self.data['imagePolicy'] = image_policy(host)
            atomic_json(self.project / PROJECT_FILE, self.data)
        project_host = self.data.get('host', 'codex')
        self.selection = load_json(self.project / SELECTION_FILE, empty_selection(self.data.get('mode', 'showreel-motion'), project_host))
        if not isinstance(self.selection, dict):
            self.selection = empty_selection(host=project_host)
        if host is not None:
            self.selection['host'] = host
            atomic_json(self.project / SELECTION_FILE, self.selection)
        self.feedback = load_json(self.project / FEEDBACK_FILE, {'schemaVersion': 1, 'status': 'draft', 'note': ''})
        if not isinstance(self.feedback, dict):
            self.feedback = {'schemaVersion': 1, 'status': 'draft', 'note': ''}
        self.has_saved_selection = (self.project / REQUEST_FILE).is_file()
        if music:
            self.set_music(absolute_file(music, '--music'), external=True)

    def updates(self):
        with self._updates_lock:
            if self._updates is None:
                from studio_updates import StudioUpdates
                self._updates = StudioUpdates(self.storage.data_dir, skills_parent=SKILLS_ROOT)
            return self._updates

    def register_library_storage_projects(self):
        """Register only projects already verified by the local work library."""
        for group in self.library.groups():
            detail = self.library.group(group['groupId'])
            for item in [detail['source'], *detail.get('files', [])]:
                project = item.get('project') if isinstance(item, dict) else None
                if not isinstance(project, str):
                    continue
                try:
                    self.storage_projects.add(self.storage.dispatch('register', {'project': project})['id'])
                except (OSError, ValueError):
                    continue

    def refresh_storage_projects(self):
        """Read already-verified CLI registrations without accepting browser paths."""
        try:
            projects = self.storage.dispatch('list', {})['projects']
        except (OSError, ValueError):
            return
        self.storage_projects.update(project['id'] for project in projects)

    def storage_list(self, project_id=None):
        self.refresh_storage_projects()
        if project_id is not None and project_id not in self.storage_projects:
            raise ValueError('현재 제작실 또는 내 작업물에 등록된 프로젝트가 아닙니다')
        project_ids = [project_id] if project_id else sorted(self.storage_projects)
        rows, disk = [], None
        for identifier in project_ids:
            result = self.storage.dispatch('list', {'projectId': identifier})
            rows.extend(result['projects'])
            disk = result['disk']
        return {'currentProjectId': self.storage_project_id, 'projects': rows, 'totals': {'totalBytes': sum(item['totalBytes'] for item in rows),
                                              'reclaimableBytes': sum(item['reclaimableBytes'] for item in rows)},
                'disk': disk or {'totalBytes': 0, 'freeBytes': 0}}

    def storage_project(self, project_id):
        if project_id not in self.storage_projects:
            raise ValueError('현재 제작실 또는 내 작업물에 등록된 프로젝트가 아닙니다')
        return project_id

    def storage_preview(self, params):
        project_id = params.get('projectId')
        project_ids = [self.storage_project(project_id)] if project_id else sorted(self.storage_projects)
        plans, blocked = [], []
        for identifier in project_ids:
            try:
                plans.append(self.storage.dispatch('preview', {**params, 'projectId': identifier}))
            except (OSError, ValueError) as error:
                if project_id:
                    raise
                blocked.append({'projectId': identifier, 'reason': str(error)})
        plan_id = secrets.token_urlsafe(24)
        self.storage_plans[plan_id] = [plan['planId'] for plan in plans]
        return {'planId': plan_id, 'entries': [entry for plan in plans for entry in plan['entries']],
                'fileCount': sum(plan['fileCount'] for plan in plans), 'bytes': sum(plan['bytes'] for plan in plans),
                'blocked': blocked + [entry for plan in plans for entry in plan['blocked']],
                'expiresAt': min((plan['expiresAt'] for plan in plans), default=None)}

    def storage_cleanup(self, plan_id):
        plans = self.storage_plans.pop(plan_id, None)
        if not plans:
            raise ValueError('이 세션에서 만든 정리 계획이 필요합니다')
        results, errors = [], []
        for item in plans:
            try:
                results.append(self.storage.dispatch('cleanup', {'planId': item, 'confirm': True}))
            except (OSError, ValueError) as error:
                errors.append({'planId': item, 'reason': str(error)})
        return {'removedFiles': sum(item['removedFiles'] for item in results), 'freedBytes': sum(item['freedBytes'] for item in results),
                'skipped': [entry for item in results for entry in item['skipped']], 'errors': errors,
                'warnings': [warning for item in results for warning in item.get('warnings', [])],
                'auditPath': next((item['auditPath'] for item in results if item['auditPath']), None)}

    def shared_cache_preview(self):
        result = shared_video_cache(self.storage.data_dir, 'video:cache')
        plan_id = result.get('planId')
        if not isinstance(plan_id, str) or not plan_id or len(plan_id) > 128:
            raise ValueError('공용 캐시 정리 계획이 올바르지 않습니다.')
        self.shared_cache_plans = {plan_id}
        return result

    def shared_cache_cleanup(self, plan_id):
        if plan_id not in self.shared_cache_plans:
            raise ValueError('이 세션에서 만든 공용 캐시 정리 계획이 필요합니다.')
        result = shared_video_cache(self.storage.data_dir, 'video:cache-clear', plan_id)
        self.shared_cache_plans.discard(plan_id)
        return result

    def maintenance_list(self, scope=None):
        if scope not in {None, 'retirement', 'git'}:
            raise ValueError('retirement 또는 git 범위만 점검할 수 있습니다.')
        params = {'includeRetirement': True}
        if scope: params['scope'] = scope
        result = maintenance_storage(self.storage.data_dir, 'maintenance-list', params)
        scan = result.get('scan') if isinstance(result, dict) else None
        scan_id = scan.get('scanId') if isinstance(scan, dict) else None
        if not isinstance(scan_id, str) or not scan_id or scan.get('complete') is not True:
            raise ValueError('작업 폴더 전체 스캔이 완료되지 않았습니다. 다시 점검하세요.')
        self.storage_maintenance_scan_id = scan_id
        self.storage_maintenance_plans = {}
        return result

    def maintenance_history(self):
        return maintenance_storage(self.storage.data_dir, 'maintenance-history', {})

    def storage_status(self):
        return maintenance_storage(self.storage.data_dir, 'status', {})

    def storage_tracking(self, refresh_workspace=False):
        if type(refresh_workspace) is not bool:
            raise ValueError('작업 폴더 새로 고침 여부가 올바르지 않습니다.')
        return self.tracking.list({'refreshWorkspace': refresh_workspace})

    def storage_events(self, project_id=None, group_id=None, limit=50, cursor=None):
        self.refresh_storage_projects()
        if project_id is not None:
            self.storage_project(project_id)
        if group_id is not None:
            self.library.group(group_id)
        try:
            return self.management.events(project_id=project_id, group_id=group_id, limit=limit, cursor=cursor)
        except ManagementDBError as error:
            raise ValueError(f'SQLite 변경 이력을 읽을 수 없습니다: {error}') from error

    def storage_reconcile_preview(self):
        result = self.tracking.preview({})
        plan_id = result.get('planId') if isinstance(result, dict) else None
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id):
            raise ValueError('미연결 자료 정리 계획이 올바르지 않습니다.')
        self.storage_reconcile_plans = {plan_id}
        return result

    def storage_reconcile_cleanup(self, plan_id):
        if not isinstance(plan_id, str) or plan_id not in self.storage_reconcile_plans:
            raise ValueError('이 세션에서 만든 미연결 자료 정리 계획이 필요합니다.')
        self.storage_reconcile_plans.remove(plan_id)
        return self.tracking.cleanup({'planId': plan_id, 'confirm': True})

    def _current_entity_block(self, scope, identifier):
        if scope == 'project':
            return identifier == self.storage_project_id
        group = self.library.group(identifier)
        for item in [group.get('source'), *group.get('files', []), *group.get('artifacts', [])]:
            for origin in item.get('origins', []) if isinstance(item, dict) else []:
                if origin.get('project') == str(self.project):
                    return True
        return False

    def storage_entity_preview(self, scope, identifier):
        if scope not in {'project', 'group'} or not isinstance(identifier, str) or not SHA256.fullmatch(identifier):
            raise ValueError('제거할 프로젝트 또는 음악 그룹 ID가 올바르지 않습니다.')
        if self._current_entity_block(scope, identifier):
            return {'eligible': False, 'planId': None, 'scope': scope,
                    'projectIds': [identifier] if scope == 'project' else [],
                    'groupIds': [identifier] if scope == 'group' else [], 'targets': [], 'preserved': [],
                    'blocked': [{'projectId': self.storage_project_id, 'reason': '현재 열린 제작실 프로젝트는 이 화면에서 전체 제거할 수 없습니다. 다른 제작실에서 확인하세요.'}],
                    'warnings': [], 'summary': {'projectCount': 0, 'groupCount': 0, 'fileCount': 0, 'bytes': 0, 'allocatedBytes': 0, 'versionCount': 0}}
        action = 'project-remove-preview' if scope == 'project' else 'group-remove-preview'
        result = self.storage.dispatch(action, {'projectId' if scope == 'project' else 'groupId': identifier})
        plan_id = result.get('planId') if isinstance(result, dict) else None
        if result.get('eligible') is True:
            if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id):
                raise ValueError('전체 제거 계획이 올바르지 않습니다.')
            self.storage_entity_plans.add(plan_id)
        return result

    def storage_entity_cleanup(self, plan_id):
        if not isinstance(plan_id, str) or plan_id not in self.storage_entity_plans:
            raise ValueError('이 세션에서 만든 전체 제거 계획이 필요합니다.')
        result = self.storage.dispatch('entity-remove', {'planId': plan_id, 'confirm': True})
        self.storage_entity_plans.discard(plan_id)
        return result

    def storage_entity_recover(self, plan_id):
        if not isinstance(plan_id, str) or plan_id not in self.storage_entity_plans:
            raise ValueError('이 세션에서 만든 중단된 전체 제거 계획이 필요합니다.')
        result = self.storage.dispatch('entity-recover', {'planId': plan_id, 'confirm': True})
        self.storage_entity_plans.discard(plan_id)
        return result

    def maintenance_preview(self, value):
        if not isinstance(value, dict) or set(value) - {'scanId', 'scope', 'candidateIds'} or value.get('scope') not in {'git', 'verification', 'artifacts', 'retirement'}:
            raise ValueError('정리 종류는 git, verification, artifacts 또는 retirement만 허용합니다.')
        if not isinstance(value.get('scanId'), str) or value['scanId'] != self.storage_maintenance_scan_id:
            raise ValueError('이 세션에서 완료한 최신 작업 폴더 전체 스캔이 필요합니다.')
        candidate_ids = value.get('candidateIds')
        if value['scope'] != 'git' and candidate_ids is None:
            raise ValueError('이 정리 종류에는 명시 선택한 후보가 필요합니다.')
        if candidate_ids is not None and (not isinstance(candidate_ids, list) or not candidate_ids or len(candidate_ids) > 1000 or len(set(candidate_ids)) != len(candidate_ids) or not all(isinstance(item, str) and 1 <= len(item) <= 200 for item in candidate_ids)):
            raise ValueError('정리 후보가 올바르지 않습니다.')
        result = maintenance_storage(self.storage.data_dir, 'maintenance-preview', value)
        plan_id = result.get('planId')
        if not isinstance(plan_id, str) or not plan_id or len(plan_id) > 128:
            raise ValueError('작업 폴더 정리 계획이 올바르지 않습니다.')
        self.storage_maintenance_plans = {plan_id: value['scope']}
        return result

    def maintenance_cleanup(self, plan_id):
        if not isinstance(plan_id, str) or self.storage_maintenance_plans.pop(plan_id, None) is None:
            raise ValueError('이 세션에서 만든 작업 폴더 정리 계획이 필요합니다.')
        result = maintenance_storage(self.storage.data_dir, 'maintenance-cleanup', {'planId': plan_id}, confirm=True)
        self.storage_maintenance_scan_id = None
        return result

    def storage_overview(self, refresh_workspace=False):
        if type(refresh_workspace) is not bool:
            raise ValueError('작업 폴더 새로 고침 여부가 올바르지 않습니다.')
        return maintenance_storage(self.storage.data_dir, 'overview', {'refreshWorkspace': refresh_workspace})

    def storage_versions(self, group_id, value):
        self.library.group(group_id)
        result = self.storage.dispatch('versions', {'groupId': group_id, **value})
        project_id = value.get('projectId')
        if project_id is not None and (not isinstance(result, dict) or project_id not in {item.get('id') for item in result.get('projects', []) if isinstance(item, dict)}):
            raise ValueError('이 음악에 등록된 버전 프로젝트가 아닙니다.')
        return result

    def storage_version_diff(self, group_id, from_id, to_id):
        self.library.group(group_id)
        result = self.storage.dispatch('version-diff', {'fromId': from_id, 'toId': to_id})
        if not isinstance(result, dict) or result.get('groupId') != group_id:
            raise ValueError('이 음악에 속한 버전만 비교할 수 있습니다.')
        return result

    def storage_file_remove_preview(self, value):
        if not isinstance(value, dict) or set(value) != {'groupId', 'fileId'}:
            raise ValueError('음악 그룹과 등록 파일 ID가 필요합니다.')
        self.library.group(value['groupId'])
        result = self.storage.dispatch('file-remove-preview', value)
        plan_id = result.get('planId') if isinstance(result, dict) else None
        if plan_id is not None:
            if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id):
                raise ValueError('파일 정리 계획이 올바르지 않습니다.')
            self.storage_file_remove_plans = {plan_id}
        return result

    def storage_file_remove(self, plan_id):
        if not isinstance(plan_id, str) or plan_id not in self.storage_file_remove_plans:
            raise ValueError('이 세션에서 만든 파일 정리 계획이 필요합니다.')
        self.storage_file_remove_plans.remove(plan_id)
        return self.storage.dispatch('file-remove', {'planId': plan_id, 'confirm': True})

    def storage_project_finish_preview(self, value):
        if not isinstance(value, dict) or set(value) != {'projectId'}:
            raise ValueError('완료 정리할 프로젝트 ID가 필요합니다.')
        self.storage_project(value['projectId'])
        result = self.storage.dispatch('project-finish-preview', value)
        plan_id = result.get('planId') if isinstance(result, dict) else None
        if isinstance(result, dict) and result.get('alreadyFinished') is True and plan_id is None:
            self.storage_project_finish_plans.clear()
            return result
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id):
            raise ValueError('완료 정리 계획이 올바르지 않습니다.')
        self.storage_project_finish_plans = {plan_id}
        return result

    def storage_project_finish(self, plan_id):
        if not isinstance(plan_id, str) or plan_id not in self.storage_project_finish_plans:
            raise ValueError('이 세션에서 만든 완료 정리 계획이 필요합니다.')
        self.storage_project_finish_plans.remove(plan_id)
        return self.storage.dispatch('project-finish', {'planId': plan_id, 'confirm': True})

    def restructure_status(self):
        return maintenance_storage(self.storage.data_dir, 'restructure-status', {})

    def restructure_preview(self):
        result = maintenance_storage(self.storage.data_dir, 'restructure-preview', {})
        plan_id = result.get('planId') if isinstance(result, dict) else None
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id):
            raise ValueError('Output 구조 전환 계획이 올바르지 않습니다.')
        self.storage_restructure_plans = {plan_id}
        return result

    def restructure_cleanup(self, plan_id):
        if not isinstance(plan_id, str) or plan_id not in self.storage_restructure_plans:
            raise ValueError('이 세션에서 만든 Output 구조 전환 계획이 필요합니다.')
        self.storage_restructure_plans.remove(plan_id)
        return maintenance_storage(self.storage.data_dir, 'restructure-cleanup', {'planId': plan_id}, confirm=True)

    def sweep_preview(self, value):
        if not isinstance(value, dict) or set(value) - {'mvProjectIds'}:
            raise ValueError('일괄 정리에는 명시 선택한 AI M/V ID만 전달할 수 있습니다.')
        identifiers = value.get('mvProjectIds')
        if identifiers is not None:
            if (not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100 or
                    not all(isinstance(item, str) and SHA256.fullmatch(item) for item in identifiers) or len(set(identifiers)) != len(identifiers)):
                raise ValueError('선택한 AI M/V 프로젝트 ID가 올바르지 않습니다.')
        result = maintenance_storage(self.storage.data_dir, 'sweep-preview', value)
        plan_id = result.get('planId')
        if plan_id is None and result.get('fileCount') == 0 and not result.get('entries'):
            self.storage_sweep_plans = set()
            return result
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id):
            raise ValueError('일괄 정리 계획이 올바르지 않습니다.')
        self.storage_sweep_plans = {plan_id}
        return result

    def sweep_cleanup(self, plan_id):
        if plan_id not in self.storage_sweep_plans:
            raise ValueError('이 세션에서 만든 일괄 정리 계획이 필요합니다.')
        self.storage_sweep_plans.remove(plan_id)
        result = maintenance_storage(self.storage.data_dir, 'sweep-cleanup', {'planId': plan_id}, confirm=True)
        self.storage_maintenance_scan_id = None
        return result

    def _refresh_project(self):
        value = load_json(self.project / PROJECT_FILE, None)
        if not isinstance(value, dict) or value.get('schemaVersion') != 1:
            raise ValueError(f'{PROJECT_FILE}: 지원하지 않는 프로젝트입니다')
        self.data = value

    def _management_group_id(self, media=None):
        values = media if isinstance(media, list) else self.data.get('media', [])
        music = next((item for item in values if isinstance(item, dict) and item.get('id') == 'music'), None)
        candidate = music.get('sha256') if isinstance(music, dict) else None
        return candidate if isinstance(candidate, str) and SHA256.fullmatch(candidate) else None

    def _record_management_event(self, action, before=None, after=None, reason='', path=None, media=None):
        try:
            return self.management.record_event(action, project_id=self.storage_project_id,
                                                group_id=self._management_group_id(media), before=before,
                                                after=after, reason=reason, path=str(path or self.project))
        except ManagementDBError as error:
            raise ValueError(f'SQLite 관리 이력을 저장하지 못해 변경을 되돌렸습니다: {error}') from error

    def _registered(self):
        self._refresh_project()
        value = self.data.get('media', [])
        return value if isinstance(value, list) else []

    def _set_registered(self, media, action='media-change'):
        previous = deepcopy(self.data.get('media', []))
        if previous == media:
            return
        snapshot = file_snapshots([self.project / PROJECT_FILE])
        self.data['media'] = media
        try:
            atomic_json(self.project / PROJECT_FILE, self.data)
            self._record_management_event(action, before={'media': previous}, after={'media': media}, media=media)
        except Exception:
            self.data['media'] = previous
            restore_file_snapshots(snapshot)
            raise

    def set_music(self, path, external=False, name=None):
        item = descriptor(path, 'music', 'music')
        if name is not None:
            item['name'] = name
        item['source'] = 'external' if external else 'uploaded'
        with self.lock:
            media = [m for m in self._registered() if not (isinstance(m, dict) and m.get('id') == 'music')]
            media.append(item)
            self._set_registered(media, action='music-change')
        return item

    def upload_music(self, name, stream, length):
        if not isinstance(name, str) or not name or len(name) > 4096:
            raise ValueError('X-File-Name이 필요합니다')
        try:
            name = unquote(name, encoding='utf-8', errors='strict')
        except UnicodeDecodeError as error:
            raise ValueError('X-File-Name UTF-8 인코딩이 올바르지 않습니다') from error
        prefix = f'{secrets.token_hex(12)}-'
        if (not name or len(name) > 180 or Path(name).name != name or '/' in name or '\\' in name or '\x00' in name or
                len((prefix + name).encode('utf-8')) > 255):
            raise ValueError('안전한 파일명만 사용할 수 있습니다')
        allowed_media(Path(name), 'music')
        if not 1 <= length <= MAX_UPLOAD:
            raise ValueError('음원 파일 크기가 올바르지 않습니다')
        target_dir = self.project / 'inputs' / 'music'
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f'{prefix}{name}'
        try:
            with target.open('xb') as out:
                remaining = length
                while remaining:
                    block = stream.read(min(64 * 1024, remaining))
                    if not block:
                        raise ValueError('업로드가 중간에 끝났습니다')
                    out.write(block)
                    remaining -= len(block)
            return self.set_music(target, external=False, name=name)
        except Exception:
            if target.exists():
                target.unlink()
            raise

    def media(self):
        value = {}
        for item in self._registered():
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not isinstance(item.get('path'), str):
                continue
            try:
                path = Path(item['path']).resolve(strict=True)
                if path.is_file() and not path.is_symlink() and sha256(path) == item.get('sha256'):
                    if item.get('kind') == 'lyrics':
                        lyrics_text(path)
                    value[item['id']] = {**item, 'path': path}
            except (OSError, ValueError):
                continue
        return value

    def state(self):
        media = self.media()
        cards = []
        for card in self.cards:
            cards.append({'id': card['id'], 'category': card['category'], 'name': card['name'], 'description': card['description'],
                          'preview': f'/media/preview-{card["id"]}?token={quote(self.token, safe="")}',
                          'poster': f'/media/poster-{card["id"]}?token={quote(self.token, safe="")}'})
        samples = {}
        for mode, sample in self.samples.items():
            samples[mode] = {key: sample[key] for key in ('title', 'summary', 'tags', 'audioNote', 'provenance')}
            samples[mode]['video'] = f'/media/sample-{mode}?token={quote(self.token, safe="")}'
            samples[mode]['poster'] = f'/media/sample-poster-{mode}?token={quote(self.token, safe="")}'
        review = {'storyboard': [], 'videos': [], 'audios': [], 'captions': [], 'lyrics': []}
        current_music = media.get('music')
        for item in media.values():
            if item['id'] == 'music':
                continue
            target = {'storyboard': 'storyboard', 'video': 'videos', 'music': 'audios', 'captions': 'captions', 'lyrics': 'lyrics'}.get(item.get('kind'))
            if target:
                source = item.get('sourceMusicSha256')
                source_status = ('current' if current_music and source == current_music['sha256'] else
                                 'different-source' if isinstance(source, str) else 'unverified-source')
                url = f'/media/{item["id"]}?token={quote(self.token, safe="")}'
                result = {'id': item['id'], 'name': item['name'], 'url': url,
                          'downloadUrl': f'{url}&download=1', 'size': item['size'],
                          'sourceStatus': source_status}
                if item.get('kind') == 'lyrics':
                    result['text'] = lyrics_text(item['path'])
                elif item.get('kind') == 'captions':
                    try:
                        result['text'] = lyrics_text(item['path'], '자막')
                    except ValueError as error:
                        result['previewError'] = str(error)
                review[target].append(result)
        music = current_music
        music_state = None
        if music:
            url = f'/media/music?token={quote(self.token, safe="")}'
            music_state = {'id': 'music', 'name': music['name'], 'sha256': music['sha256'], 'url': url,
                           'downloadUrl': f'{url}&download=1', 'size': music['size'],
                           'sourceStatus': 'current'}
        return {'application':'road-music-video-studio', 'project':str(self.project), 'projectName': self.data.get('name', self.project.name), 'reviewSession': self.review, 'hasSavedSelection': self.has_saved_selection, 'host': self.selection.get('host', self.data.get('host', 'codex')), 'imagePolicy': image_policy(self.selection.get('host', self.data.get('host', 'codex'))), 'mode': self.selection.get('mode', self.data.get('mode', 'showreel-motion')),
                'modeLabel': MODES.get(self.selection.get('mode'), MODES['showreel-motion'])[0],
                'modes': [{'id': key, 'name': name, 'description': desc} for key, (name, desc) in MODES.items()],
                'samples': samples, 'styles': cards, 'selection': self.selection, 'feedback': self.feedback,
                'media': {'music': music_state, 'review': review},
                'publishDiagnostic': load_json(self.project / 'publish-diagnostic.json', None),
                'jizura': {'available': (DEFAULT_JIZURA_ROOT / 'ko' / 'index.html').is_file(), 'script': str(JIZURA_SCRIPT)}}

    def save_selection(self, value):
        selection = validate_selection(value, self.selection)
        if selection['styleId'] is not None and selection['styleId'] not in self.card_ids:
            raise ValueError('등록되지 않은 실제 스타일입니다')
        if selection['mode'] == 'showreel-cd' and self.card_categories.get(selection['styleId']) not in {'cd', 'rhythm-cd'}:
            raise ValueError('CD 제작에는 CD 프리셋만 선택할 수 있습니다')
        showreel_request = None
        if selection['mode'] in {'showreel-cd', 'showreel-motion'}:
            music = self.media().get('music')
            if music is None:
                raise ValueError('Showreel 제작에는 등록된 음악이 필요합니다')
            showreel_request = {
                'schemaVersion': 1,
                'host': selection['host'],
                'styleId': selection['styleId'],
                'display': {
                    'showSpectrum': bool(selection['display']['showSpectrum']),
                    'showQueue': bool(selection['display']['showQueue']),
                    'showNowPlaying': bool(selection['display']['showNowPlaying']),
                    'channelName': selection['display']['channelName'] or '',
                },
                'music': str(music['path']),
            } if selection['styleId'] is not None else None
        with self.lock:
            previous_selection = deepcopy(self.selection)
            previous_data = deepcopy(self.data)
            snapshots = file_snapshots([self.project / PROJECT_FILE, self.project / SELECTION_FILE,
                                        self.project / REQUEST_FILE, self.project / SHOWREEL_REQUEST_FILE])
            self._refresh_project()
            self.data['host'] = selection['host']
            self.data['imagePolicy'] = image_policy(selection['host'])
            atomic_json(self.project / PROJECT_FILE, self.data)
            atomic_json(self.project / SELECTION_FILE, selection)
            request = {'schemaVersion': 1, 'status': 'saved', 'selection': selection, 'imagePolicy': image_policy(selection['host']), 'savedAt': int(time.time())}
            atomic_json(self.project / REQUEST_FILE, request)
            if showreel_request is not None:
                atomic_json(self.project / SHOWREEL_REQUEST_FILE, showreel_request)
            else:
                (self.project / SHOWREEL_REQUEST_FILE).unlink(missing_ok=True)
            try:
                if previous_selection != selection or previous_data.get('host') != self.data.get('host'):
                    self._record_management_event('selection-change', before=previous_selection, after=selection)
                self.selection = selection
                self.has_saved_selection = True
            except Exception:
                self.data = previous_data
                self.selection = previous_selection
                restore_file_snapshots(snapshots)
                raise
        result = {'status': 'saved', 'request': str(self.project / REQUEST_FILE), 'selection': selection}
        if showreel_request is not None:
            result['showreelRequest'] = str(self.project / SHOWREEL_REQUEST_FILE)
        return result

    def save_feedback(self, value):
        if not isinstance(value, dict) or set(value) - {'status', 'note', 'syncChecks'} or not {'status', 'note'} <= set(value):
            raise ValueError('피드백에는 status와 note, 선택적인 syncChecks만 허용합니다')
        if value['status'] not in {'draft', 'needs-revision', 'approved'} or not isinstance(value['note'], str) or len(value['note']) > 12_000:
            raise ValueError('피드백 값이 올바르지 않습니다')
        files = list(self._registered())
        music = next((item for item in files if item.get('id') == 'music'), None)
        if music:
            files = [item for item in files if item.get('id') == 'music' or item.get('sourceMusicSha256') in (None, music.get('sha256'))]
            try:
                group = self.library.group(music['sha256'])
                files = [*files, *group['files']]
            except ValueError:
                pass
        with self.lock:
            previous = load_json(self.project / FEEDBACK_FILE, self.feedback)
            if not isinstance(previous, dict):raise ValueError('기존 검수 기록 형식을 확인하세요. 원본은 유지했습니다')
            result = {**previous, 'schemaVersion': 1, 'status': value['status'], 'note': value['note'].strip(), 'savedAt': int(time.time())}
            if 'syncChecks' in value:
                result['syncChecks'] = validate_sync_checks(value['syncChecks'], files)
            if {key: value for key, value in result.items() if key != 'savedAt'} == {key: value for key, value in previous.items() if key != 'savedAt'}:
                return previous
            snapshots = file_snapshots([self.project / FEEDBACK_FILE])
            atomic_json(self.project / FEEDBACK_FILE, result)
            try:
                self._record_management_event('feedback-change', before=previous, after=result)
                self.feedback = result
            except Exception:
                self.feedback = previous
                restore_file_snapshots(snapshots)
                raise
        return result

    def complete_review(self):
        if not self.review:
            raise ValueError('검수 전용 세션에서만 검수를 마칠 수 있습니다')
        return {'status': 'completed', 'project': str(self.project), 'feedback': str(self.project / FEEDBACK_FILE)}


def initialize_project_metadata(target, music=None, mode='showreel-motion', host='codex', name=None):
    """Add studio metadata once to a producer-owned project folder."""
    if mode not in MODES:
        raise ValueError('지원하지 않는 --mode입니다')
    if host not in HOSTS:
        raise ValueError('지원하지 않는 --host입니다')
    source = absolute_file(music, '--music') if music else None
    if source:
        allowed_media(source, 'music')
    target = Path(target)
    if not target.is_absolute() or target.is_symlink():
        raise ValueError('제작실 메타데이터에는 심볼릭 링크가 아닌 절대 폴더가 필요합니다')
    target = target.resolve(strict=True)
    if not target.is_dir():
        raise ValueError('제작실 메타데이터에는 기존 프로젝트 폴더가 필요합니다')
    files = (PROJECT_FILE, SELECTION_FILE, FEEDBACK_FILE)
    if any((target / file).exists() or (target / file).is_symlink() for file in files):
        raise FileExistsError('기존 제작실 메타데이터를 덮어쓸 수 없습니다')
    project_name = name if isinstance(name, str) and name.strip() else target.name
    if not isinstance(project_name, str) or len(project_name.strip()) > 240 or any(ord(char) < 32 for char in project_name):
        raise ValueError('프로젝트 이름이 올바르지 않습니다')
    media = []
    if source:
        entry = descriptor(source, 'music', 'music')
        entry['source'] = 'external'
        media.append(entry)
    atomic_json(target / PROJECT_FILE, {'schemaVersion': 1, 'name': project_name.strip(), 'host': host, 'imagePolicy': image_policy(host), 'mode': mode, 'media': media})
    atomic_json(target / SELECTION_FILE, empty_selection(mode, host))
    atomic_json(target / FEEDBACK_FILE, {'schemaVersion': 1, 'status': 'draft', 'note': ''})
    (target / '.roadmusic' / 'cache').mkdir(parents=True)


def init_project(out, music=None, mode='showreel-motion', host='codex'):
    if mode not in MODES:
        raise ValueError('지원하지 않는 --mode입니다')
    if host not in HOSTS:
        raise ValueError('지원하지 않는 --host입니다')
    source = absolute_file(music, '--music') if music else None
    if source:
        allowed_media(source, 'music')
    target = Path(out)
    if not target.is_absolute():
        raise ValueError('--out: 새 절대 출력 경로가 필요합니다')
    target = working_project_path(target, sha256(source) if source else None)
    if target.exists():
        raise FileExistsError('--out: 새 폴더여야 합니다')
    target.mkdir(parents=True)
    initialize_project_metadata(target, str(source) if source else None, mode, host)
    return {'status': 'initialized', 'project': str(target), 'music': str(source) if source else None, 'mode': mode, 'host': host}


def prepare_publish(project, value):
    """Validate a complete replacement without constructing a mutable Session."""
    project = project_path(project)
    allowed = {'title', 'changeReason', 'sourceMusicSha256', 'video', 'audio', 'captions', 'lyrics', 'storyboard', 'artifacts', 'producedAt'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('manifest는 title/changeReason/sourceMusicSha256/video/audio/captions/lyrics/storyboard/artifacts/producedAt만 포함합니다')
    data = load_json(project / PROJECT_FILE, None)
    if not isinstance(data, dict) or data.get('schemaVersion') != 1:
        raise ValueError('지원하지 않는 제작실 프로젝트입니다')
    title = value.get('title')
    if title is not None and (not isinstance(title, str) or not 1 <= len(title.strip()) <= 180 or any(ord(char) < 32 for char in title)):
        raise ValueError('title은 제어문자 없는 1~180자 문자열이어야 합니다')
    reason = value.get('changeReason')
    if reason is not None and (not isinstance(reason, str) or len(reason) > 4_000):
        raise ValueError('changeReason은 4,000자 이하 문자열이어야 합니다')
    source_sha = value.get('sourceMusicSha256')
    if source_sha is not None and (not isinstance(source_sha, str) or not SHA256.fullmatch(source_sha.lower())):
        raise ValueError('sourceMusicSha256은 64자리 SHA-256이어야 합니다')
    produced_at = value.get('producedAt')
    if produced_at is not None:
        try:
            stamp = datetime.fromisoformat(produced_at.replace('Z', '+00:00'))
            if stamp.tzinfo is None: raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError('producedAt은 시간대가 있는 실제 제작 완료 ISO 시각이어야 합니다') from None
    old = data.get('media', [])
    registered = [m for m in old if isinstance(m, dict) and m.get('id') == 'music']
    fields = (('video', 'video'), ('audio', 'music'), ('captions', 'captions'), ('lyrics', 'lyrics'), ('storyboard', 'storyboard'), ('artifacts', 'artifact'))
    for key, kind in fields:
        paths = value.get(key, [])
        if paths is None: continue
        if isinstance(paths, str): paths = [paths]
        if not isinstance(paths, list) or len(paths) > 24:
            raise ValueError(f'{key}: 최대 24개 절대 경로 목록이 필요합니다')
        for index, item in enumerate(paths):
            metadata = {}
            if isinstance(item, dict):
                if set(item) - {'path', 'styleLabel', 'styleId', 'forVideoSha256', 'artifactType'}:
                    raise ValueError(f'{key}: 파일 항목의 필드가 올바르지 않습니다')
                for field in ('styleLabel', 'styleId'):
                    if field in item:
                        text = item[field]
                        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 180 or any(ord(char) < 32 for char in text):
                            raise ValueError(f'{field}: 제어문자 없는 1~180자 문자열이어야 합니다')
                        metadata[field] = text.strip()
                if 'forVideoSha256' in item:
                    target = item['forVideoSha256']
                    if kind != 'captions' or not isinstance(target, str) or not SHA256.fullmatch(target):
                        raise ValueError('forVideoSha256은 자막에만 지정하는 영상 SHA-256입니다')
                    metadata['forVideoSha256'] = target
                if kind == 'artifact':
                    if item.get('artifactType') not in ARTIFACT_TYPES:
                        raise ValueError('제작 자료의 artifactType이 올바르지 않습니다')
                    metadata['artifactType'] = item['artifactType']
                elif 'artifactType' in item:
                    raise ValueError('artifactType은 제작 자료에만 지정합니다')
                item = item.get('path')
            elif kind == 'artifact':
                raise ValueError('제작 자료는 path/artifactType 객체가 필요합니다')
            path = absolute_file(item, key)
            entry = {**descriptor(path, kind, f'{kind}-{index}'), **metadata}
            if kind == 'artifact' and path.suffix.lower() in {'.json', '.jizura'}:
                if path.stat().st_size > 16 * 1024 * 1024: raise ValueError('제작 자료 JSON이 너무 큽니다')
                json_load(path.read_text(encoding='utf-8-sig'))
            entry['sourceMusicSha256'] = source_sha.lower() if source_sha else None
            if produced_at is not None: entry['producedAt'] = produced_at
            registered.append(entry)
    video_shas = {m['sha256'] for m in registered if m['kind'] == 'video'}
    if any(m.get('forVideoSha256') not in video_shas for m in registered if 'forVideoSha256' in m):
        raise ValueError('자막의 대응 영상이 이번 등록 목록에 없습니다')
    previous = {(m.get('kind'), m.get('sha256')): m for m in old if isinstance(m, dict) and m.get('id') != 'music'}
    current = {(m['kind'], m['sha256']): m for m in registered if m.get('id') != 'music'}
    plan = {'status': 'preview', 'added': [m['name'] for k, m in current.items() if k not in previous],
            'removed': [m['name'] for k, m in previous.items() if k not in current],
            'retained': [m['name'] for k, m in current.items() if k in previous], 'mediaCount': len(registered),
            'warnings': [] if source_sha else ['원음 SHA 미지정: 원음 연결은 미확인으로 표시됩니다.']}
    return data, registered, plan


def structure_busy(output_root):
    """Reject public publication while the one-shot workspace migration owns Output."""
    root = Path(output_root)
    marker = root / '.roadmusic' / 'structure.json'
    if not marker.exists():
        return
    if marker.is_symlink():
        raise ValueError('구조 이전 상태 파일의 심볼릭 링크는 사용할 수 없습니다')
    value = load_json(marker, None)
    if not isinstance(value, dict):
        raise ValueError('구조 이전 상태 파일을 확인할 수 없습니다')
    if value.get('phase') in {'preparing', 'prepared'} and value.get('owner') == 'road-music' and value.get('workspace') in {str(root), str(root.resolve())}:
        raise ValueError('작업 폴더 구조 이전이 진행 중입니다. 완료 뒤 다시 게시하세요')


def publish(project, manifest, dry_run=False):
    project = project_path(project)
    source = absolute_file(manifest, '--manifest')
    raw = source.read_bytes()
    if len(raw) > MAX_JSON: raise ValueError('--manifest: JSON이 너무 큽니다')
    value = json_load(raw.decode('utf-8-sig'))
    data, registered, plan = prepare_publish(project, value)
    if dry_run: return plan
    session = Session(project)
    source_music = next((item for item in registered if item.get('id') == 'music'), None)
    source_sha = value.get('sourceMusicSha256') or (source_music or {}).get('sha256')
    if not isinstance(source_music, dict) or not isinstance(source_sha, str) or not SHA256.fullmatch(source_sha.lower()):
        raise ValueError('등록된 입력 원음과 sourceMusicSha256이 필요합니다')
    verified_source = descriptor(source_music['path'], 'music')
    if verified_source['sha256'] != source_sha.lower():
        raise ValueError('등록 원음과 sourceMusicSha256이 일치하지 않습니다')
    audio_aliases = [item for item in registered if item.get('id') != 'music' and item.get('kind') == 'music' and item.get('sha256') == verified_source['sha256']]
    delivery_media = registered
    if audio_aliases:
        delivery_media = [item for item in registered if item not in audio_aliases]
        delivery_media[delivery_media.index(source_music)] = {**audio_aliases[0], 'id': 'music'}
    from storage_packaging import TRUSTED_ROOT
    if TRUSTED_ROOT is None and 'ROADMUSIC_DELIVERY_ROOT' not in os.environ:
        raise ValueError('현재 설치의 Road Music 작업 폴더를 찾을 수 없습니다.')
    output_root = Path(os.environ.get('ROADMUSIC_DELIVERY_ROOT', TRUSTED_ROOT))
    structure_busy(output_root)
    delivery = DeliveryStore(output_root).publish(project, delivery_media, source_sha256=source_sha,
        title=value.get('title') or data.get('name') or project.name, reason=value.get('changeReason', ''), created_at=value.get('producedAt'), _allow_source_only=bool(audio_aliases), studio_name=value.get('title'))
    original_by_id = {item.get('id'): item for item in registered if isinstance(item, dict)}
    canonical = [{**{key: value for key, value in original_by_id.get(item.get('id'), {}).items() if key not in {'path', 'name', 'size', 'sha256'}}, **item} for item in delivery['media']]
    if audio_aliases:
        source_canonical = next(item for item in canonical if item.get('id') == 'music')
        canonical.extend({**{key: value for key, value in alias.items() if key not in {'path', 'name', 'size', 'sha256'}},
                          **{key: source_canonical[key] for key in ('kind', 'path', 'name', 'sha256', 'bytes')}, 'id': alias['id']} for alias in audio_aliases)
    canonical.extend(item for item in registered if isinstance(item, dict) and item.get('kind') == 'artifact')
    if value.get('title'): session.data['name'] = value['title'].strip()
    session._set_registered(canonical)
    result = {'status': 'published', 'project': str(project), 'manifest': str(source), 'mediaCount': len(canonical), 'plan': plan, 'savedAt': int(time.time()), 'deliveryVersion': delivery}
    try:
        registration = session.library.register(project)
        registration = session.library.refresh_project_paths(project)
        result['workGroupId'] = registration['groupId']
        if registration.get('skippedDifferentSource'): result['librarySkippedDifferentSource'] = registration['skippedDifferentSource']
        source_project = Path(source_music['path']).parent
        source_project_id = hashlib.sha256(str(source_project).encode()).hexdigest()
        publication = {'deliveryVersionId': delivery['id'], 'producerProjectId': delivery['logicalProjectId']}
        publication_json = json.dumps(publication, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        with session.management.transaction(write=True) as connection:
            recorded_song = connection.execute("SELECT 1 FROM management_events WHERE project_id=? AND action LIKE 'song-%' LIMIT 1", (source_project_id,)).fetchone()
            already_linked = connection.execute("SELECT 1 FROM management_events WHERE project_id=? AND action='song-published' AND after_json=? LIMIT 1", (source_project_id, publication_json)).fetchone()
            if recorded_song and not already_linked:
                session.management.record_event('song-published', project_id=source_project_id, group_id=registration['groupId'], path=str(source_project), after=publication, connection=connection)
    except (OSError, ValueError) as error:
        result['libraryWarning'] = str(error)
    else:
        try:
            completion = complete_published_project(session.storage, project, registered, value.get('sourceMusicSha256'))
            result['storageCompletion'] = completion
            if completion['completed']:
                result['storageCleanup'] = completion['cleanup']
        except (OSError, ValueError) as error:
            result['storageWarning'] = str(error)
    atomic_json(project / 'publish-diagnostic.json', result)
    return result


def make_handler(session):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'RoadMusicVideoStudio/1.0'
        def log_message(self, *_): return
        def origin(self): return f'http://127.0.0.1:{self.server.server_port}'
        def host_ok(self): return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
        def token_ok(self, parsed): return parse_qs(parsed.query).get('token') == [session.token]
        def send_json(self, code, value):
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
        def deny(self, code, message): self.send_json(code, {'error':message})
        def body(self, limit):
            try: length = int(self.headers.get('Content-Length',''))
            except ValueError: raise ValueError('Content-Length가 필요합니다')
            if not 1 <= length <= limit: raise ValueError('요청 본문 크기가 올바르지 않습니다')
            raw=self.rfile.read(length)
            if len(raw)!=length: raise ValueError('요청 본문이 중간에 끝났습니다')
            return raw,length
        def page(self, value):
            raw = value.encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'self'; media-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self' 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'");self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
        def template(self, path, current, group_id=None, guide=None, bootstrap=None):
            if not path.is_file():
                raise ValueError('요청한 페이지 템플릿을 찾지 못했습니다')
            token = quote(session.token, safe='')
            boot = {'token': session.token, **({'groupId': group_id} if group_id else {}), **(bootstrap or {})}
            page = path.read_text(encoding='utf-8').replace('__STUDIO_BOOTSTRAP__', 'window.__STUDIO_BOOTSTRAP__='+json.dumps(boot,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')+';', 1).replace('__DESIGN_TOKEN__',token)
            source = json.dumps(markdown_source(guide or current), ensure_ascii=False).replace('<', '\\u003c')
            page = page.replace('__GUIDE_MARKDOWN__', source)
            return add_navigation(page, current=current, home_url=self.origin()+'/?token='+session.token)
        def production_params(self, values, *, endpoint):
            allowed = {'token', 'projectId', 'groupId', 'groupIds', 'domain', 'engine', 'model', 'taskType', 'status', 'search', 'since', 'until', 'limit', 'offset', 'cursor', 'taskId'}
            if set(values) - allowed:
                raise ValueError('제작 기록에는 지정된 조회 조건만 전달할 수 있습니다.')
            result = {}
            if 'groupIds' in values:
                items = values['groupIds']
                if endpoint != 'dashboard' or len(items) != 1:
                    raise ValueError('그룹 일괄 조회는 대시보드에서만 사용할 수 있습니다.')
                groups = json_load(items[0])
                if not isinstance(groups, list) or not 1 <= len(groups) <= 100 or any(not isinstance(item, str) or not SHA256.fullmatch(item) for item in groups):
                    raise ValueError('groupIds에는 음악 그룹 ID를 1~100개 지정하세요.')
                result['groupIds'] = groups
            for key in ('projectId', 'groupId'):
                items = values.get(key, [])
                if len(items) > 1 or (items and not SHA256.fullmatch(items[0])):
                    raise ValueError(f'{key} 값이 올바르지 않습니다.')
                if items: result[key] = items[0]
            for key in ('domain', 'engine', 'model', 'taskType', 'status', 'search'):
                items = values.get(key, [])
                if len(items) > 1 or (items and (not isinstance(items[0], str) or len(items[0]) > (200 if key == 'search' else 120))):
                    raise ValueError(f'{key} 값이 올바르지 않습니다.')
                if items: result[key] = items[0]
            for key, minimum, maximum in (('limit', 1, 100), ('offset', 0, 10000), ('cursor', 1, None), ('since', 0, None), ('until', 0, None)):
                items = values.get(key, [])
                if len(items) > 1 or (items and (not items[0].isdigit() or int(items[0]) < minimum or (maximum is not None and int(items[0]) > maximum))):
                    raise ValueError(f'{key} 값이 올바르지 않습니다.')
                if items: result[key] = int(items[0])
            items = values.get('taskId', [])
            if len(items) > 1 or (items and not re.fullmatch(r'[0-9a-f]{48}', items[0])):
                raise ValueError('taskId 값이 올바르지 않습니다.')
            if items: result['taskId'] = items[0]
            if endpoint == 'dashboard' and 'cursor' in result:
                raise ValueError('대시보드는 이전 페이지 커서를 지원하지 않습니다.')
            if endpoint != 'activity' and 'offset' in result:
                raise ValueError('offset은 제작 현황에서만 사용할 수 있습니다.')
            return result
        def media(self, path, download_name=None, content_type=None, expected_sha=None):
            # Verify and stream the same open file so a path replacement cannot change the served bytes.
            try:
                with path.open('rb') as stream:
                    if expected_sha and hashlib.file_digest(stream, 'sha256').hexdigest() != expected_sha:
                        raise ValueError('등록 뒤 파일이 변경되어 제공하지 않습니다')
                    size=os.fstat(stream.fileno()).st_size
                    start,end,status=0,size-1,200
                    requested=self.headers.get('Range')
                    if requested:
                        match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested.strip())
                        if not match:
                            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
                        left,right=match.groups()
                        if left:start=int(left);end=min(int(right),size-1) if right else size-1
                        elif right:start=max(0,size-int(right))
                        else:
                            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
                        if start>=size or end<start:
                            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
                        status=206
                    length=end-start+1
                    content_type=content_type or {'.srt': 'application/x-subrip', '.vtt': 'text/vtt'}.get(path.suffix.lower()) or ('text/plain; charset=utf-8' if path.suffix.lower() in MEDIA_EXTENSIONS['lyrics'] else (mimetypes.guess_type(path.name)[0] or 'application/octet-stream'))
                    self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(length));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                    if download_name is not None:self.send_header('Content-Disposition',f'attachment; filename="download"; filename*=UTF-8\'\'{quote(download_name,safe="")}')
                    if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    stream.seek(start);left=length
                    while left:
                        data=stream.read(min(64*1024,left))
                        if not data:break
                        self.wfile.write(data);left-=len(data)
            except (BrokenPipeError,ConnectionResetError):return
        def guide_media(self, name):
            path = guide_media_file(name)
            content_type = {
                '.svg': 'image/svg+xml',
                '.webp': 'image/webp',
            }.get(path.suffix.lower(), mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            return self.media(path, content_type=content_type)
        def work_projects(self, group_id):
            group=session.library.group(group_id)
            paths={origin['project'] for item in [*group['files'], *group.get('artifacts', [])] for origin in item.get('origins', [{'project': item['project']}])}
            return {hashlib.sha256(path.encode()).hexdigest():Path(path) for path in sorted(paths)}
        def work_project(self, group_id, project_id):
            path=self.work_projects(group_id).get(project_id)
            if path is None:raise ValueError('이 음악에 등록된 프로젝트가 아닙니다')
            data=load_json(path/PROJECT_FILE,None)
            if not isinstance(data,dict):raise ValueError('프로젝트 기록을 읽을 수 없습니다')
            source=next((item for item in data.get('media',[]) if isinstance(item,dict) and item.get('id')=='music'),{})
            if source.get('sha256')!=group_id:raise ValueError('프로젝트의 현재 원음이 이 음악과 다릅니다')
            return path,data
        def work_records(self, group_id):
            records=[]
            group=session.library.group(group_id)
            origins=[origin for item in [*group['files'], *group.get('artifacts', [])] for origin in item.get('origins', [])]
            current={}
            for identifier,path in self.work_projects(group_id).items():
                try:
                    path,data=self.work_project(group_id,identifier)
                    selection=load_json(path/SELECTION_FILE,{})
                    feedback=load_json(path/FEEDBACK_FILE,{'status':'draft','note':''})
                    if not isinstance(selection,dict) or not isinstance(feedback,dict):raise ValueError('검수·선택 기록 형식이 올바르지 않습니다')
                    record={'id':identifier,'name':data.get('name',path.name),'mode':data.get('mode'),'host':data.get('host'),
                            'project':str(path),'selection':selection,'feedback':feedback,'feedbackHistory':feedback_history(path, session.management),'available':True}
                    current[str(path)]=record
                    records.append(record)
                except (OSError,ValueError) as error:
                    origin=next((item for item in reversed(origins) if item['project']==str(path)), None)
                    if not origin:
                        records.append({'id':identifier,'name':path.name,'available':False,'error':str(error)})
            seen=set()
            for origin in origins:
                live=current.get(origin['project'])
                snapshot={'selection':origin.get('selection',{}),'feedback':origin.get('feedback',{})}
                if live and snapshot=={'selection':live['selection'],'feedback':live['feedback']}:continue
                if live and not any(snapshot.values()):continue
                marker=json.dumps({'project':origin['project'], **snapshot},sort_keys=True,ensure_ascii=False)
                if marker in seen:continue
                seen.add(marker)
                records.append({'id':hashlib.sha256(marker.encode()).hexdigest(),'name':Path(origin['project']).name+' · 보존 기록',
                                'project':origin['project'],'mode':origin.get('mode'),'host':origin.get('selection',{}).get('host'),
                                **snapshot,'available':True,'historical':True})
            return records
        def work_group(self, group, performance=None, breakdown=None):
            records=self.work_records(group['groupId'])
            live={record.get('project'):record.get('feedback',{}) for record in records if record.get('available') and not record.get('historical')}
            def file(item):
                if not item:return None
                prefix=f'/works/{group["groupId"]}/files/{item["id"]}'
                origins=[{**origin, **({'currentFeedback':live[origin['project']]} if origin['project'] in live else {})} for origin in item.get('origins', [])]
                value={**item,'origins':origins,'url':prefix+'?token='+session.token,'downloadUrl':prefix+'?token='+session.token+'&download=1'}
                if item.get('kind')=='artifact' and item.get('available') and Path(item['path']).suffix.lower() in {'.json','.jizura'} and item.get('size',0)<=256*1024:
                    try:
                        raw=json_load(Path(item['path']).read_text(encoding='utf-8-sig'))
                        if isinstance(raw,dict):value['summary']={key:raw[key] for key in ('title','summary','description','genre','bpm','durationSeconds') if key in raw and isinstance(raw[key],(str,int,float))}
                    except (OSError,ValueError,UnicodeDecodeError):pass
                return value
            value={**group,'source':file(group['source']),'previewVideo':file(group.get('previewVideo')),
                   'performance':performance,
                   'detailUrl':f'/works/{group["groupId"]}/?token='+session.token,
                   'zipUrl':f'/works/{group["groupId"]}/download.zip?token='+session.token,
                   'productionZipUrl':f'/works/{group["groupId"]}/production.zip?token='+session.token}
            value['dates']=sorted({datetime.fromisoformat(stamp.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat() for stamp in group.get('createdTimes',[])},reverse=True)
            if 'files' in group:value['files']=[file(item) for item in group['files']]
            if 'artifacts' in group:value['artifacts']=[file(item) for item in group['artifacts']]
            if breakdown is not None:value['stageBreakdown']=breakdown
            return value
        def completed_download(self, group_id=None, include_artifacts=False):
            group = session.library.group(group_id) if group_id else None
            stream = session.library.archive(group_id, include_artifacts=True) if group_id and include_artifacts else session.library.archive(group_id) if group_id else completed_zip(session)
            try:
                stream.seek(0, os.SEEK_END); length = stream.tell(); stream.seek(0)
                filename = f'{group["title"]}-제작자료포함.zip' if group and include_artifacts else f'{group["title"]}-음악그룹.zip' if group else 'Road-Music-완성-파일.zip'
                self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Length',str(length));self.send_header('Content-Disposition',f'attachment; filename="road-music-complete.zip"; filename*=UTF-8\'\'{quote(filename, safe="")}');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
                while block := stream.read(64 * 1024):
                    self.wfile.write(block)
            except (BrokenPipeError, ConnectionResetError):
                return
            finally:
                stream.close()
        def do_GET(self):
            parsed=urlparse(self.path)
            if not self.host_ok(): return self.deny(421,'허용되지 않은 Host입니다')
            if not self.token_ok(parsed): return self.deny(403,'세션 토큰이 올바르지 않습니다')
            if parsed.path=='/':
                return self.page(self.template(TEMPLATE, 'studio'))
            if parsed.path == '/works/':
                return self.page(self.template(WORKS_TEMPLATE, 'works'))
            if parsed.path == '/dashboard/':
                try:
                    groups = parse_qs(parsed.query).get('groupId', [])
                    if len(groups) > 1 or (groups and not SHA256.fullmatch(groups[0])):
                        raise ValueError('음악 그룹 정보가 올바르지 않습니다.')
                    return self.page(self.template(DASHBOARD_TEMPLATE, 'dashboard', guide='production', bootstrap={'groupId': groups[0] if groups else None}))
                except ValueError as error:
                    return self.deny(422, str(error))
            if parsed.path in {'/recipes/', '/ccm/'}:
                collection = 'ccm' if parsed.path == '/ccm/' else 'general'
                return self.page(self.template(ROOT/'assets'/'recipe-library.html', 'guide', guide='ccm' if collection == 'ccm' else 'reference', bootstrap={'recipeCollection': collection}))
            if parsed.path in {'/api/recipes', '/api/ccm'}:
                return self.send_json(200, recipe_snapshot('ccm' if parsed.path == '/api/ccm' else 'general'))
            if parsed.path in {'/status/', '/reference/'}:
                topic=parsed.path.strip('/')
                return self.page(self.template(ROOT/'assets'/f'{topic}.html', topic, guide=topic))
            if parsed.path in {'/status.js', '/reference.js', '/recipe-library.js'}:
                raw=(ROOT/'assets'/parsed.path.removeprefix('/')).read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();return self.wfile.write(raw)
            if parsed.path in {'/api/status', '/api/reference'}:
                return self.send_json(200,status_snapshot() if parsed.path=='/api/status' else reference_snapshot())

            if parsed.path == '/storage/':
                try:
                    values = parse_qs(parsed.query).get('projectId', [])
                    if len(values) > 1: raise ValueError('projectId는 하나만 허용합니다')
                    project_id = values[0] if values else None
                    if project_id: session.storage_project(project_id)
                    return self.page(self.template(STORAGE_TEMPLATE, 'works', guide='storage', bootstrap={'currentProjectId': project_id}))
                except ValueError as error:return self.deny(422, str(error))
            work = re.fullmatch(r'/works/([0-9a-f]{64})/', parsed.path)
            if work:
                return self.page(self.template(WORK_DETAIL_TEMPLATE, 'works', work[1]))
            if parsed.path == '/works.js':
                raw = (ROOT/'assets/works.js').read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();return self.wfile.write(raw)
            if parsed.path in {'/work-production.js', '/production-ui.js', '/production-activity.js'}:
                raw = (ROOT/'assets'/parsed.path.removeprefix('/')).read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();return self.wfile.write(raw)
            if parsed.path == '/dashboard.js':
                raw = (ROOT/'assets/dashboard.js').read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();return self.wfile.write(raw)
            if parsed.path == '/api/updates/capabilities':
                try:
                    if set(parse_qs(parsed.query)) - {'token'}: raise ValueError('업데이트 상태에는 추가 입력을 전달할 수 없습니다.')
                    return self.send_json(200, session.updates().capabilities())
                except (ValueError, OSError) as error:return self.deny(422, str(error))
            update_job = re.fullmatch(r'/api/updates/jobs/([0-9a-f]{48})', parsed.path)
            if update_job:
                try:return self.send_json(200, session.updates().job(update_job[1]))
                except (ValueError, OSError) as error:return self.deny(422, str(error))
            production = re.fullmatch(r'/api/production/(projects|prompts|tasks|files|dashboard|components|activity)', parsed.path)
            if production:
                try:
                    action = production[1]
                    if action == 'activity':
                        params = self.production_params(parse_qs(parsed.query), endpoint=action)
                        return self.send_json(200, session.production.activity(params, runtime_queue=read_runtime_queue(session.storage.data_dir)))
                    return self.send_json(200, session.production.dispatch(action, self.production_params(parse_qs(parsed.query), endpoint=action)))
                except (ProductionLedgerError, ValueError, OSError) as error:
                    return self.deny(422, str(error))
            if parsed.path == '/storage.js':
                raw = (ROOT/'assets/storage.js').read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();return self.wfile.write(raw)
            if parsed.path == '/api/storage/overview':
                try:
                    values = parse_qs(parsed.query)
                    if set(values) - {'token', 'refreshWorkspace'}: raise ValueError('음악별 목록에는 지정된 새로 고침 입력만 전달할 수 있습니다.')
                    refresh = values.get('refreshWorkspace', [])
                    if len(refresh) > 1 or (refresh and refresh[0] not in {'0', '1'}): raise ValueError('작업 폴더 새로 고침 값이 올바르지 않습니다.')
                    return self.send_json(200, session.storage_overview(refresh == ['1']))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage/tracking':
                try:
                    values = parse_qs(parsed.query)
                    if set(values) - {'token', 'refreshWorkspace'}: raise ValueError('추적 현황에는 지정된 새로 고침 입력만 전달할 수 있습니다.')
                    refresh = values.get('refreshWorkspace', [])
                    if len(refresh) > 1 or (refresh and refresh[0] not in {'0', '1'}): raise ValueError('작업 폴더 새로 고침 값이 올바르지 않습니다.')
                    return self.send_json(200, session.storage_tracking(refresh == ['1']))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage/events':
                try:
                    values = parse_qs(parsed.query)
                    if set(values) - {'token', 'projectId', 'groupId', 'limit', 'cursor'}: raise ValueError('변경 이력에는 지정된 입력만 전달할 수 있습니다.')
                    params = {}
                    for key in ('projectId', 'groupId'):
                        items = values.get(key, [])
                        if len(items) > 1 or (items and not SHA256.fullmatch(items[0])): raise ValueError(f'{key} 값이 올바르지 않습니다.')
                        if items: params['project_id' if key == 'projectId' else 'group_id'] = items[0]
                    items = values.get('limit', [])
                    if len(items) > 1 or (items and (not items[0].isdigit() or not 1 <= int(items[0]) <= 100)): raise ValueError('limit 값이 올바르지 않습니다.')
                    if items: params['limit'] = int(items[0])
                    items = values.get('cursor', [])
                    if len(items) > 1 or (items and (not items[0].isdigit() or int(items[0]) < 1)): raise ValueError('cursor 값이 올바르지 않습니다.')
                    if items: params['cursor'] = int(items[0])
                    return self.send_json(200, session.storage_events(**params))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage/status':
                try:
                    if set(parse_qs(parsed.query)) - {'token'}: raise ValueError('저장공간 상태에는 입력값을 전달할 수 없습니다.')
                    return self.send_json(200, session.storage_status())
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage/restructure-status':
                try:
                    if set(parse_qs(parsed.query)) - {'token'}: raise ValueError('Output 구조 상태에는 입력값을 전달할 수 없습니다.')
                    return self.send_json(200, session.restructure_status())
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage':
                try:
                    values = parse_qs(parsed.query).get('projectId', [])
                    if len(values) > 1: raise ValueError('projectId는 하나만 허용합니다')
                    return self.send_json(200, session.storage_list(values[0] if values else None))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage/history':
                try:
                    values = parse_qs(parsed.query).get('projectId', [])
                    if len(values) != 1: raise ValueError('projectId가 필요합니다')
                    return self.send_json(200, session.storage.dispatch('history', {'projectId': session.storage_project(values[0])}))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage/legacy':
                try:
                    values = parse_qs(parsed.query).get('projectId', [])
                    if len(values) != 1: raise ValueError('projectId가 필요합니다')
                    return self.send_json(200, session.storage.dispatch('legacy', {'projectId': session.storage_project(values[0])}))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage/maintenance':
                try:
                    values = parse_qs(parsed.query)
                    if set(values) - {'token', 'scope'}: raise ValueError('작업 폴더 정리에는 지정된 범위만 전달할 수 있습니다.')
                    scopes = values.get('scope', [])
                    if len(scopes) > 1 or (scopes and scopes[0] not in {'retirement', 'git'}): raise ValueError('retirement 또는 git 범위만 점검할 수 있습니다.')
                    return self.send_json(200, session.maintenance_list(scopes[0] if scopes else None))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/storage/maintenance-history':
                try:
                    if set(parse_qs(parsed.query)) - {'token'}: raise ValueError('작업 폴더 정리 이력에는 입력값을 전달할 수 없습니다.')
                    return self.send_json(200, session.maintenance_history())
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            if parsed.path == '/api/works':
                try:
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    favorite = query.get('favoritesOnly', [])
                    if set(query) - {'token', 'favoritesOnly'} or len(favorite) > 1 or (favorite and favorite[0] not in {'true','false','0','1'}):
                        raise ValueError('좋아요 목록 조건이 올바르지 않습니다.')
                    groups = session.library.groups(favorites_only=bool(favorite and favorite[0] in {'true','1'}))
                    performance = {}
                    for start in range(0, len(groups), 100):
                        for item in session.production.group_summaries([group['groupId'] for group in groups[start:start + 100]]):
                            performance[item['groupId']] = item['performance']
                    return self.send_json(200,{'groups':[self.work_group(group, performance.get(group['groupId'])) for group in groups]})
                except (OSError, ValueError) as error:return self.deny(422,str(error))
            work = re.fullmatch(r'/api/works/([0-9a-f]{64})/records', parsed.path)
            if work:
                try:return self.send_json(200,{'records':self.work_records(work[1])})
                except (OSError,ValueError) as error:return self.deny(404,str(error))
            work = re.fullmatch(r'/api/works/([0-9a-f]{64})/versions', parsed.path)
            if work:
                try:
                    values = parse_qs(parsed.query)
                    if set(values) - {'token', 'projectId', 'limit', 'offset'}: raise ValueError('버전 목록에는 지정된 입력만 전달할 수 있습니다.')
                    params = {}
                    project_ids = values.get('projectId', [])
                    if len(project_ids) > 1 or (project_ids and not SHA256.fullmatch(project_ids[0])): raise ValueError('프로젝트 ID가 올바르지 않습니다.')
                    if project_ids:
                        params['projectId'] = project_ids[0]
                    for key, minimum, maximum in (('limit', 1, 100), ('offset', 0, None)):
                        items = values.get(key, [])
                        if len(items) > 1 or (items and (not items[0].isdigit() or not minimum <= int(items[0]) <= (maximum if maximum is not None else int(items[0])))):
                            raise ValueError(f'{key} 값이 올바르지 않습니다.')
                        if items: params[key] = int(items[0])
                    return self.send_json(200, session.storage_versions(work[1], params))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            work = re.fullmatch(r'/api/works/([0-9a-f]{64})/version-diff', parsed.path)
            if work:
                try:
                    values = parse_qs(parsed.query)
                    if set(values) - {'token', 'fromId', 'toId'}: raise ValueError('버전 비교에는 지정된 입력만 전달할 수 있습니다.')
                    from_ids, to_ids = values.get('fromId', []), values.get('toId', [])
                    if len(from_ids) != 1 or len(to_ids) != 1 or not SHA256.fullmatch(from_ids[0]) or not SHA256.fullmatch(to_ids[0]):
                        raise ValueError('비교할 버전 ID가 올바르지 않습니다.')
                    return self.send_json(200, session.storage_version_diff(work[1], from_ids[0], to_ids[0]))
                except (OSError, ValueError) as error:return self.deny(422, str(error))
            work = re.fullmatch(r'/works/([0-9a-f]{64})/files/([0-9a-f]{64})/text', parsed.path)
            if work:
                try:
                    item=session.library.file(work[1],work[2])
                    if item['kind'] not in {'lyrics','captions','artifact'} or (item['kind']=='artifact' and item['path'].suffix.lower() not in {'.json','.jizura','.txt','.md'}):raise ValueError('가사·자막·텍스트 제작 자료만 미리보기를 제공합니다')
                    return self.send_json(200,{'text':lyrics_text(item['path'])})
                except (OSError,ValueError) as error:return self.deny(404,str(error))
            work = re.fullmatch(r'/api/works/([0-9a-f]{64})', parsed.path)
            if work:
                try:
                    group = session.library.group(work[1])
                    metrics = session.production.dashboard({'groupId': work[1]})
                    performance = next((item['performance'] for item in metrics.get('groupSummaries', []) if item['groupId'] == work[1]), None)
                    return self.send_json(200,self.work_group(group, performance, metrics.get('stageBreakdown', [])))
                except (OSError, ValueError) as error:return self.deny(404,str(error))
            production = re.fullmatch(r'/works/([0-9a-f]{64})/production\.zip', parsed.path)
            if production:
                try:return self.completed_download(production[1],include_artifacts=True)
                except (OSError,ValueError) as error:return self.deny(409,str(error))
            work = re.fullmatch(r'/works/([0-9a-f]{64})/download\.zip', parsed.path)
            if work:
                try:return self.completed_download(work[1])
                except (OSError, ValueError) as error:return self.deny(409,str(error))
            work = re.fullmatch(r'/works/([0-9a-f]{64})/files/([0-9a-f]{64})', parsed.path)
            if work:
                try:
                    item=session.library.file(work[1],work[2])
                    return self.media(item['path'],item['name'] if parse_qs(parsed.query).get('download')==['1'] else None,expected_sha=item['sha256'])
                except (OSError, ValueError) as error:return self.deny(404,str(error))
            if parsed.path == '/results/':
                try:return self.page(self.template(RESULTS_TEMPLATE, 'results'))
                except (OSError, ValueError) as error:return self.deny(404, str(error))
            if parsed.path == '/review/':
                try:return self.page(self.template(REVIEW_TEMPLATE, 'review'))
                except (OSError, ValueError) as error:return self.deny(404, str(error))
            if parsed.path.startswith('/guide/'):
                engine_values = parse_qs(parsed.query, keep_blank_values=True).get('engine', ['YuE'])
                if len(engine_values) != 1 or engine_values[0] not in {'YuE', 'ACE'}:
                    return self.deny(422, '가이드 엔진은 YuE 또는 ACE 하나만 선택하세요.')
                guide_engine = engine_values[0]
            if parsed.path == '/guide/':
                return self.page(add_navigation(render_guide('start', session.token, self.origin()+'/?token='+session.token, engine=guide_engine), current='guide', home_url=self.origin()+'/?token='+session.token))
            guide_media = re.fullmatch(r'/guide-media/([^/]+)', parsed.path)
            if guide_media:
                try:return self.guide_media(guide_media.group(1))
                except (OSError, ValueError):return self.deny(404, '등록된 가이드 이미지가 아닙니다')
            guide = re.fullmatch(r'/guide/([a-z][a-z0-9-]*)/', parsed.path)
            if guide:
                try:
                    return self.page(add_navigation(render_guide(guide_for_engine(guide.group(1), guide_engine), session.token, self.origin()+'/?token='+session.token, engine=guide_engine), current='guide', home_url=self.origin()+'/?token='+session.token))
                except ValueError as error:
                    return self.deny(404, str(error))
            raw_guide = re.fullmatch(r'/guide/([a-z][a-z0-9-]*)\.md', parsed.path)
            if raw_guide:
                try:
                    raw = markdown_source(guide_for_engine(raw_guide.group(1), guide_engine), engine=guide_engine).encode('utf-8')
                except ValueError as error:
                    return self.deny(404, str(error))
                self.send_response(200);self.send_header('Content-Type','text/markdown; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Content-Disposition',f'attachment; filename="guide.md"; filename*=UTF-8\'\'{quote(guide_for_engine(raw_guide.group(1), guide_engine)+"-"+guide_engine.lower()+".md", safe="")}');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();return self.wfile.write(raw)
            if parsed.path == '/catalog/':
                page=(PLAYLIST_ROOT/'assets/catalog.html').read_text(encoding='utf-8')
                token=quote(session.token,safe='')
                page=page.replace('href="road-music-design/styles.css"',f'href="/design.css?token={token}"')
                page=re.sub(r'src="presets/([a-z][a-z0-9-]*)/preview\.mp4"',lambda m:f'src="/media/preview-{m[1]}?token={token}"',page)
                page=re.sub(r'poster="presets/([a-z][a-z0-9-]*)/(?:poster\.jpg|preview\.png)"',lambda m:f'poster="/media/poster-{m[1]}?token={token}"',page)
                page=re.sub(r'href="presets/([a-z][a-z0-9-]*)/preset.json"',lambda m:f'href="/catalog/preset/{m[1]}?token={token}"',page)
                page=add_navigation(page,current='catalog',home_url=self.origin()+'/?token='+session.token).encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(page)));self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; media-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self' 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'");self.send_header('X-Content-Type-Options','nosniff');self.end_headers();return self.wfile.write(page)
            catalog_preset=re.fullmatch(r'/catalog/preset/([a-z][a-z0-9-]{0,80})',parsed.path)
            if catalog_preset:
                card=next((item for item in session.cards if item['id']==catalog_preset[1]),None)
                if not card:return self.deny(404,'등록된 스타일이 아닙니다')
                return self.media(card['previewPath'].parent/'preset.json')
            if parsed.path=='/design.css':
                body=css_text('/design/fonts/',session.token).encode()
                self.send_response(200);self.send_header('Content-Type','text/css; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();return self.wfile.write(body)
            if parsed.path.startswith('/design/fonts/'):
                name=parsed.path.removeprefix('/design/fonts/')
                if name not in FONT_FILES:return self.deny(404,'등록된 글꼴이 아닙니다')
                return self.media(DESIGN_ASSETS/'fonts'/name)
            if parsed.path=='/api/state': return self.send_json(200,session.state())
            if parsed.path == '/downloads/complete.zip':
                try:return self.completed_download()
                except (OSError, ValueError) as error:return self.deny(404, str(error))
            match=re.fullmatch(r'/media/([a-z][a-z0-9-]{0,80})',parsed.path)
            if not match:return self.deny(404,'지원하지 않는 경로입니다')
            identifier=match.group(1)
            sample_match = re.fullmatch(r'sample-(poster-)?(showreel-cd|showreel-mv|jizura|showreel-motion)', identifier)
            if sample_match:
                poster, mode = sample_match.groups()
                sample = session.samples.get(mode)
                if not sample:
                    return self.deny(404, '등록되지 않은 형식 예시입니다')
                return self.media(sample['posterPath'] if poster else sample['videoPath'])
            if identifier.startswith('preview-') or identifier.startswith('poster-'):
                style=identifier.split('-',1)[1]; card=next((c for c in session.cards if c['id']==style),None)
                if not card:return self.deny(404,'등록되지 않은 미리보기입니다')
                return self.media(card['previewPath'] if identifier.startswith('preview-') else card['posterPath'])
            item=session.media().get(identifier)
            if not item:return self.deny(404,'등록되지 않은 파일입니다')
            return self.media(item['path'], item['name'] if parse_qs(parsed.query).get('download') == ['1'] else None)
        def do_POST(self):
            parsed=urlparse(self.path)
            if not self.host_ok() or self.headers.get('Origin')!=self.origin() or self.headers.get('X-Studio-Token')!=session.token or not self.token_ok(parsed):return self.deny(403,'허용되지 않은 요청입니다')
            try:
                if parsed.path == '/api/publish-preview':
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON)
                    return self.send_json(200,prepare_publish(session.project,json_load(raw.decode('utf-8')))[2])
                favorite = re.fullmatch(r'/api/works/([0-9a-f]{64})/favorite', parsed.path)
                if favorite:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(512);value=json_load(raw.decode('utf-8'))
                    if not isinstance(value,dict) or set(value)!={'favorite'} or type(value['favorite']) is not bool:
                        raise ValueError('좋아요는 favorite:true/false만 전달할 수 있습니다.')
                    return self.send_json(200,session.library.set_favorite(favorite[1],value['favorite']))
                updates = re.fullmatch(r'/api/updates/(check|update)', parsed.path)
                if updates:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(1024);value=json_load(raw.decode('utf-8'))
                    required = {'componentId','confirm'} if updates[1]=='update' else {'componentId'}
                    if not isinstance(value,dict) or set(value)!=required or (updates[1]=='update' and value.get('confirm') is not True):
                        raise ValueError('업데이트 실행에는 componentId와 confirm:true가 필요합니다.')
                    return self.send_json(202,session.updates().start(updates[1],value['componentId']))
                if parsed.path == '/api/production/request':
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8'))
                    if not isinstance(value, dict) or set(value) - {'domain', 'intent', 'prompt', 'source', 'title', 'groupId', 'requestId'}:
                        raise ValueError('제작 요청에는 지정된 기록 항목만 전달할 수 있습니다.')
                    value = {**value, 'project': str(session.project)}
                    return self.send_json(201, session.production.dispatch('request', value))
                work=re.fullmatch(r'/api/works/([0-9a-f]{64})/records/([0-9a-f]{64})/feedback',parsed.path)
                if work:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON)
                    project,_=self.work_project(work[1],work[2])
                    return self.send_json(201,Session(project).save_feedback(json_load(raw.decode('utf-8'))))
                if parsed.path=='/api/music':
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/octet-stream':return self.deny(415,'application/octet-stream 요청이 필요합니다')
                    try: length=int(self.headers.get('Content-Length',''))
                    except ValueError: raise ValueError('Content-Length가 필요합니다')
                    if not 1 <= length <= MAX_UPLOAD: raise ValueError('요청 본문 크기가 올바르지 않습니다')
                    return self.send_json(201,session.upload_music(self.headers.get('X-File-Name'),self.rfile,length))
                entity = re.fullmatch(r'/api/storage/(project-remove-preview|group-remove-preview|entity-remove|entity-recover)', parsed.path)
                if entity:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8'))
                    action = entity[1]
                    if action == 'project-remove-preview':
                        if not isinstance(value, dict) or set(value) != {'projectId'}: raise ValueError('projectId만 전달할 수 있습니다.')
                        return self.send_json(200, session.storage_entity_preview('project', value['projectId']))
                    if action == 'group-remove-preview':
                        if not isinstance(value, dict) or set(value) != {'groupId'}: raise ValueError('groupId만 전달할 수 있습니다.')
                        return self.send_json(200, session.storage_entity_preview('group', value['groupId']))
                    if not isinstance(value, dict) or set(value) != {'planId', 'confirm'} or value.get('confirm') is not True or not isinstance(value.get('planId'), str):
                        raise ValueError('이 세션의 planId와 confirm:true가 필요합니다.')
                    return self.send_json(200, session.storage_entity_cleanup(value['planId']) if action == 'entity-remove' else session.storage_entity_recover(value['planId']))
                reconcile = re.fullmatch(r'/api/storage/(reconcile-preview|reconcile-cleanup)', parsed.path)
                if reconcile:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8'))
                    if reconcile[1] == 'reconcile-preview':
                        if value != {}: raise ValueError('미연결 자료 정리 미리보기에는 입력값을 전달할 수 없습니다.')
                        return self.send_json(200, session.storage_reconcile_preview())
                    if not isinstance(value, dict) or set(value) != {'planId', 'confirm'} or value.get('confirm') is not True or not isinstance(value.get('planId'), str):
                        raise ValueError('이 세션의 planId와 confirm:true가 필요합니다.')
                    return self.send_json(200, session.storage_reconcile_cleanup(value['planId']))
                shared_cache = re.fullmatch(r'/api/storage/(shared-preview|shared-cleanup)', parsed.path)
                if shared_cache:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8')); action=shared_cache[1]
                    if not isinstance(value, dict): raise ValueError('JSON 객체가 필요합니다')
                    if action == 'shared-preview':
                        if value: raise ValueError('공용 캐시 미리보기에는 입력값을 전달할 수 없습니다.')
                        return self.send_json(200, session.shared_cache_preview())
                    if set(value) != {'planId', 'confirm'} or value.get('confirm') is not True or not isinstance(value.get('planId'), str):
                        raise ValueError('이 세션의 planId와 confirm:true가 필요합니다.')
                    return self.send_json(200, session.shared_cache_cleanup(value['planId']))
                sweep = re.fullmatch(r'/api/storage/(sweep-preview|sweep-cleanup)', parsed.path)
                if sweep:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8'))
                    if sweep[1] == 'sweep-preview':
                        return self.send_json(200, session.sweep_preview(value))
                    if not isinstance(value, dict) or set(value) != {'planId', 'confirm'} or value.get('confirm') is not True or not isinstance(value.get('planId'), str):
                        raise ValueError('이 세션의 planId와 confirm:true가 필요합니다.')
                    return self.send_json(200, session.sweep_cleanup(value['planId']))
                maintenance = re.fullmatch(r'/api/storage/(maintenance-preview|maintenance-cleanup)', parsed.path)
                if maintenance:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8')); action=maintenance[1]
                    if not isinstance(value, dict): raise ValueError('JSON 객체가 필요합니다')
                    if action == 'maintenance-preview':
                        return self.send_json(200, session.maintenance_preview(value))
                    if set(value) != {'planId', 'confirm'} or value.get('confirm') is not True or not isinstance(value.get('planId'), str):
                        raise ValueError('이 세션의 planId와 confirm:true가 필요합니다.')
                    return self.send_json(200, session.maintenance_cleanup(value['planId']))
                restructure = re.fullmatch(r'/api/storage/(restructure-preview|restructure-cleanup)', parsed.path)
                if restructure:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8')); action=restructure[1]
                    if not isinstance(value, dict): raise ValueError('JSON 객체가 필요합니다')
                    if action == 'restructure-preview':
                        if value: raise ValueError('Output 구조 전환 미리보기에는 입력값을 전달할 수 없습니다.')
                        return self.send_json(200, session.restructure_preview())
                    if set(value) != {'planId', 'confirm'} or value.get('confirm') is not True or not isinstance(value.get('planId'), str):
                        raise ValueError('이 세션의 planId와 confirm:true가 필요합니다.')
                    return self.send_json(200, session.restructure_cleanup(value['planId']))
                file_remove = re.fullmatch(r'/api/storage/(file-remove-preview|file-remove)', parsed.path)
                if file_remove:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8')); action=file_remove[1]
                    if not isinstance(value, dict): raise ValueError('JSON 객체가 필요합니다')
                    if action == 'file-remove-preview':
                        return self.send_json(200, session.storage_file_remove_preview(value))
                    if set(value) != {'planId', 'confirm'} or value.get('confirm') is not True or not isinstance(value.get('planId'), str):
                        raise ValueError('이 세션의 planId와 confirm:true가 필요합니다.')
                    return self.send_json(200, session.storage_file_remove(value['planId']))
                project_finish = re.fullmatch(r'/api/storage/(project-finish-preview|project-finish)', parsed.path)
                if project_finish:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8')); action=project_finish[1]
                    if not isinstance(value, dict): raise ValueError('JSON 객체가 필요합니다')
                    if action == 'project-finish-preview':
                        return self.send_json(200, session.storage_project_finish_preview(value))
                    if set(value) != {'planId', 'confirm'} or value.get('confirm') is not True or not isinstance(value.get('planId'), str):
                        raise ValueError('이 세션의 planId와 confirm:true가 필요합니다.')
                    return self.send_json(200, session.storage_project_finish(value['planId']))
                storage = re.fullmatch(r'/api/storage/(track|policy|pin|preview|cleanup)', parsed.path)
                legacy = re.fullmatch(r'/api/storage/(adopt-preview|adopt)', parsed.path)
                if legacy:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8')); action=legacy[1]
                    if not isinstance(value, dict): raise ValueError('JSON 객체가 필요합니다')
                    if action == 'adopt-preview':
                        session.storage_project(value.get('projectId'))
                        result=session.storage.dispatch(action, value); session.storage_legacy_plans.add(result['planId']); return self.send_json(200,result)
                    if set(value)!={'planId','confirm'} or value.get('planId') not in session.storage_legacy_plans or value.get('confirm') is not True: raise ValueError('이 세션의 legacy 계획과 confirm:true가 필요합니다')
                    session.storage_legacy_plans.remove(value['planId']); return self.send_json(200,session.storage.dispatch(action,value))
                if storage:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON); value=json_load(raw.decode('utf-8')); action=storage[1]
                    if not isinstance(value, dict) or 'project' in value: raise ValueError('등록된 projectId만 사용할 수 있습니다')
                    if action == 'cleanup':
                        if set(value) != {'planId', 'confirm'} or value.get('confirm') is not True: raise ValueError('이 세션의 planId와 confirm:true가 필요합니다')
                        return self.send_json(200, session.storage_cleanup(value['planId']))
                    if action == 'preview':
                        if 'projectId' in value: session.storage_project(value['projectId'])
                        return self.send_json(200, session.storage_preview(value))
                    session.storage_project(value.get('projectId'))
                    return self.send_json(200, session.storage.dispatch(action, value))
                if parsed.path in {'/api/selection','/api/feedback'}:
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':return self.deny(415,'application/json 요청이 필요합니다')
                    raw,_=self.body(MAX_JSON);value=json_load(raw.decode('utf-8'))
                    if parsed.path.endswith('selection'):
                        result=session.save_selection(value)
                        self.send_json(201,result)
                        if not session.review:
                            threading.Timer(.05,session.done.set).start()
                        return
                    return self.send_json(201,session.save_feedback(value))
                if parsed.path == '/api/complete':
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower() not in {'', 'application/json'}:
                        return self.deny(415, '빈 요청 또는 application/json 요청이 필요합니다')
                    result = session.complete_review()
                    self.send_json(200, result)
                    threading.Timer(.05, session.done.set).start()
                    return
                return self.deny(404,'지원하지 않는 경로입니다')
            except (UnicodeDecodeError,json.JSONDecodeError,ValueError,OSError) as error:return self.deny(422,str(error))
    return Handler


def serve(project, music=None, host=None, open_browser=False, timeout=900, review=False, session_file=None):
    if not 1 <= timeout <= 86_400: raise ValueError('--timeout: 1..86400초가 필요합니다')
    session=Session(project,music,host,review)
    session.register_library_storage_projects()
    for project_id in session.storage_projects:
        try: session.storage.maybe_cleanup(project_id)
        except (OSError, ValueError) as error: print(json.dumps({'event':'studio-storage-warning','message':str(error)},ensure_ascii=False),file=sys.stderr,flush=True)
    if any(item.get('id') != 'music' and item.get('kind') in {'video','music','lyrics','captions'} for item in session._registered() if isinstance(item,dict)):
        try:session.library.register(session.project)
        except (OSError,ValueError) as error:print(json.dumps({'event':'studio-library-warning','message':str(error)},ensure_ascii=False),file=sys.stderr,flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(session));server.daemon_threads=True;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}/?token={session.token}'
    print(json.dumps({'event':'studio-ready','url':url,'project':str(session.project),'expiresSeconds':timeout,'review':review,'localExecutorOnly':True},ensure_ascii=False),file=sys.stderr,flush=True)
    registration = Path(session_file).resolve() if session_file else studio_session_file()
    if registration:
        registration.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(registration, {'schemaVersion':1,'url':url,'project':str(session.project),'pid':os.getpid(),'expiresAt':int(time.time())+timeout})
    if open_browser:
        try:
            if not open_page(url):print(json.dumps({"event":"studio-open-failed","message":"제작실 페이지를 열지 못했습니다"},ensure_ascii=False),file=sys.stderr,flush=True)
        except (OSError,subprocess.TimeoutExpired,ValueError):print(json.dumps({"event":"studio-open-failed","message":"제작실 페이지를 열지 못했습니다"},ensure_ascii=False),file=sys.stderr,flush=True)
    try:
        if not session.done.wait(timeout):
            action = '검수 마치기' if review else '선택 저장'
            raise TimeoutError(f'{action} 시간이 만료되었습니다. 이미 저장한 피드백은 유지됩니다')
        result={'status':'completed','project':str(session.project),'selection':str(session.project/SELECTION_FILE),'request':str(session.project/REQUEST_FILE),'review':review}
        showreel=session.project/SHOWREEL_REQUEST_FILE
        if showreel.is_file() and session.selection.get('mode') in {'showreel-cd','showreel-motion'} and session.selection.get('styleId') is not None: result['showreelRequest']=str(showreel)
        return result
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
        if registration and load_json(registration, {}).get('url') == url:
            registration.unlink(missing_ok=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('init');p.add_argument('--out',required=True);p.add_argument('--music');p.add_argument('--mode',choices=MODES,default='showreel-motion');p.add_argument('--host',choices=HOSTS,default='codex')
    p=sub.add_parser('serve');p.add_argument('--project',required=True);p.add_argument('--music');p.add_argument('--host',choices=HOSTS);p.add_argument('--mode',choices=MODES);p.add_argument('--open',action='store_true');p.add_argument('--review',action='store_true');p.add_argument('--session-file');p.add_argument('--timeout',type=int,default=900)
    p=sub.add_parser('library-register');p.add_argument('--project',required=True)
    p=sub.add_parser('publish');p.add_argument('--project',required=True);p.add_argument('--manifest',required=True);p.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.command=='init': result=init_project(args.out,args.music,args.mode,args.host)
        elif args.command=='publish': result=publish(args.project,args.manifest,args.dry_run)
        elif args.command=='library-register':result=WorkLibrary().register(args.project)
        else:
            if args.mode: raise ValueError('--mode은 init에만 사용할 수 있습니다. 선택은 제작실에서 저장합니다')
            result=serve(args.project,args.music,args.host,args.open,args.timeout,args.review,args.session_file)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except (OSError,ValueError,FileExistsError,TimeoutError) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr);return 2
    return 0

if __name__=='__main__': raise SystemExit(main())
