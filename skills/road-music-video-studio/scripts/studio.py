#!/usr/bin/env python3
"""Token-protected loopback desk for choosing and reviewing local music-video work."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT.parent
PLAYLIST_ROOT = SKILLS_ROOT / 'road-music-showreel-playlist'
PRESET_ROOT = PLAYLIST_ROOT / 'assets' / 'presets'
JIZURA_SCRIPT = SKILLS_ROOT / 'road-music-jizura-playlist' / 'scripts' / 'studio.py'
DEFAULT_JIZURA_ROOT = Path.home() / '.local/share/roadmusic-video-tools/jizura'
TEMPLATE = ROOT / 'assets' / 'studio.html'
EXAMPLES = ROOT / 'assets' / 'examples.json'
PROJECT_FILE = 'studio-project.json'
SELECTION_FILE = 'selection.json'
FEEDBACK_FILE = 'feedback.json'
REQUEST_FILE = 'production-request.json'
SHOWREEL_REQUEST_FILE = 'showreel-request.json'
MAX_JSON = 64 * 1024
MAX_UPLOAD = 512 * 1024 * 1024
MODES = {
    'showreel-cd': ('Road Music Showreel CD', '실제 CD 프리셋으로 플레이리스트 영상을 준비합니다.'),
    'showreel-mv': ('Road Music 쇼릴 MV', '스토리보드와 리듬 편집 방향을 저장합니다.'),
    'jizura': ('JIZURA 음악 스튜디오', '별도 JIZURA 편집기에 전달할 제작 방향을 저장합니다.'),
    'showreel-motion': ('Showreel 음악 모션그래픽', '이미지·타이포·리듬 모션 방향을 저장합니다.'),
}
HOSTS = {'codex', 'antigravity', 'antigravity-cli'}
MEDIA_EXTENSIONS = {
    'music': {'.aac', '.aif', '.aiff', '.flac', '.m4a', '.mp3', '.oga', '.ogg', '.opus', '.wav', '.webm'},
    'video': {'.m4v', '.mov', '.mp4', '.webm'},
    'storyboard': {'.avif', '.gif', '.jpeg', '.jpg', '.png', '.webp'},
    'captions': {'.ass', '.lrc', '.srt', '.vtt'},
}
SAFE_ID = re.compile(r'[a-z][a-z0-9-]{0,80}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


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


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def absolute_file(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label}: 절대 파일 경로가 필요합니다')
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f'{label}: 절대 파일 경로가 필요합니다')
    path = path.resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'{label}: 일반 파일이 필요합니다')
    return path


def allowed_media(path, kind):
    path = Path(path)
    if path.suffix.lower() not in MEDIA_EXTENSIONS[kind]:
        raise ValueError(f'{kind}: 지원하지 않는 파일 형식입니다')
    return path


def descriptor(path, kind, identifier='music'):
    path = allowed_media(Path(path), kind).resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValueError('일반 파일만 등록할 수 있습니다')
    return {'id': identifier, 'kind': kind, 'path': str(path), 'name': path.name,
            'size': path.stat().st_size, 'sha256': sha256(path)}


def empty_selection(mode='showreel-motion', host='codex'):
    return {'schemaVersion': 1, 'host': host, 'mode': mode, 'styleId': None,
            'display': {'showSpectrum': None, 'showQueue': None, 'showNowPlaying': None, 'channelName': None}}


def image_policy(host):
    if host not in HOSTS:
        raise ValueError('지원하지 않는 작업 호스트입니다')
    return {'provider': 'image_gen' if host == 'codex' else 'antigravity-native', 'allowPaidModels': False}


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
    if mode in {'showreel-cd', 'showreel-motion'} and style is None:
        raise ValueError('Showreel 제작에는 실제 스타일을 선택해야 합니다')
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

    def _refresh_project(self):
        value = load_json(self.project / PROJECT_FILE, None)
        if not isinstance(value, dict) or value.get('schemaVersion') != 1:
            raise ValueError(f'{PROJECT_FILE}: 지원하지 않는 프로젝트입니다')
        self.data = value

    def _registered(self):
        self._refresh_project()
        value = self.data.get('media', [])
        return value if isinstance(value, list) else []

    def _set_registered(self, media):
        self.data['media'] = media
        atomic_json(self.project / PROJECT_FILE, self.data)

    def set_music(self, path, external=False, name=None):
        item = descriptor(path, 'music', 'music')
        if name is not None:
            item['name'] = name
        item['source'] = 'external' if external else 'uploaded'
        with self.lock:
            media = [m for m in self._registered() if not (isinstance(m, dict) and m.get('id') == 'music')]
            media.append(item)
            self._set_registered(media)
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
                    value[item['id']] = {**item, 'path': path}
            except OSError:
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
        review = {'storyboard': [], 'videos': [], 'audios': [], 'captions': []}
        current_music = media.get('music')
        for item in media.values():
            if item['id'] == 'music':
                continue
            target = {'storyboard': 'storyboard', 'video': 'videos', 'music': 'audios', 'captions': 'captions'}.get(item.get('kind'))
            if target:
                source = item.get('sourceMusicSha256')
                source_status = ('current' if current_music and source == current_music['sha256'] else
                                 'different-source' if isinstance(source, str) else 'unverified-source')
                review[target].append({'name': item['name'], 'url': f'/media/{item["id"]}?token={quote(self.token, safe="")}', 'sourceStatus': source_status})
        music = current_music
        return {'projectName': self.data.get('name', self.project.name), 'reviewSession': self.review, 'hasSavedSelection': self.has_saved_selection, 'host': self.selection.get('host', self.data.get('host', 'codex')), 'imagePolicy': image_policy(self.selection.get('host', self.data.get('host', 'codex'))), 'mode': self.selection.get('mode', self.data.get('mode', 'showreel-motion')),
                'modeLabel': MODES.get(self.selection.get('mode'), MODES['showreel-motion'])[0],
                'modes': [{'id': key, 'name': name, 'description': desc} for key, (name, desc) in MODES.items()],
                'samples': samples, 'styles': cards, 'selection': self.selection, 'feedback': self.feedback,
                'media': {'music': ({'name': music['name'], 'sha256': music['sha256'], 'url': f'/media/music?token={quote(self.token, safe="")}'} if music else None), 'review': review},
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
                'styleId': selection['styleId'],
                'display': {
                    'showSpectrum': bool(selection['display']['showSpectrum']),
                    'showQueue': bool(selection['display']['showQueue']),
                    'showNowPlaying': bool(selection['display']['showNowPlaying']),
                    'channelName': selection['display']['channelName'] or '',
                },
                'music': str(music['path']),
            }
        with self.lock:
            self._refresh_project()
            self.data['host'] = selection['host']
            self.data['imagePolicy'] = image_policy(selection['host'])
            atomic_json(self.project / PROJECT_FILE, self.data)
            atomic_json(self.project / SELECTION_FILE, selection)
            request = {'schemaVersion': 1, 'status': 'saved', 'selection': selection, 'imagePolicy': image_policy(selection['host']), 'savedAt': int(time.time())}
            atomic_json(self.project / REQUEST_FILE, request)
            if showreel_request is not None:
                atomic_json(self.project / SHOWREEL_REQUEST_FILE, showreel_request)
            self.selection = selection
            self.has_saved_selection = True
        result = {'status': 'saved', 'request': str(self.project / REQUEST_FILE), 'selection': selection}
        if showreel_request is not None:
            result['showreelRequest'] = str(self.project / SHOWREEL_REQUEST_FILE)
        return result

    def save_feedback(self, value):
        if not isinstance(value, dict) or set(value) != {'status', 'note'}:
            raise ValueError('피드백에는 status와 note가 필요합니다')
        if value['status'] not in {'draft', 'needs-revision', 'approved'} or not isinstance(value['note'], str) or len(value['note']) > 12_000:
            raise ValueError('피드백 값이 올바르지 않습니다')
        result = {'schemaVersion': 1, 'status': value['status'], 'note': value['note'].strip(), 'savedAt': int(time.time())}
        with self.lock:
            atomic_json(self.project / FEEDBACK_FILE, result)
            self.feedback = result
        return result

    def complete_review(self):
        if not self.review:
            raise ValueError('검수 전용 세션에서만 검수를 마칠 수 있습니다')
        return {'status': 'completed', 'project': str(self.project), 'feedback': str(self.project / FEEDBACK_FILE)}


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
    target = target.resolve()
    if target.exists():
        raise FileExistsError('--out: 새 폴더여야 합니다')
    target.mkdir(parents=True)
    try:
        media = []
        if source:
            entry = descriptor(source, 'music', 'music')
            entry['source'] = 'external'
            media.append(entry)
        atomic_json(target / PROJECT_FILE, {'schemaVersion': 1, 'name': target.name, 'host': host, 'imagePolicy': image_policy(host), 'mode': mode, 'media': media})
        atomic_json(target / SELECTION_FILE, empty_selection(mode, host))
        atomic_json(target / FEEDBACK_FILE, {'schemaVersion': 1, 'status': 'draft', 'note': ''})
    except Exception:
        # Keep incomplete project visible for recovery rather than deleting user paths.
        raise
    return {'status': 'initialized', 'project': str(target), 'music': str(source) if source else None, 'mode': mode, 'host': host}


def publish(project, manifest):
    project = project_path(project)
    source = absolute_file(manifest, '--manifest')
    raw = source.read_bytes()
    if len(raw) > MAX_JSON:
        raise ValueError('--manifest: JSON이 너무 큽니다')
    value = json_load(raw.decode('utf-8-sig'))
    if not isinstance(value, dict) or set(value) - {'title', 'sourceMusicSha256', 'video', 'audio', 'captions', 'storyboard'}:
        raise ValueError('manifest는 title/sourceMusicSha256/video/audio/captions/storyboard만 포함합니다')
    title = value.get('title')
    if title is not None and (not isinstance(title, str) or not 1 <= len(title.strip()) <= 180 or any(ord(char) < 32 for char in title)):
        raise ValueError('title은 제어문자 없는 1~180자 문자열이어야 합니다')
    source_sha = value.get('sourceMusicSha256')
    if source_sha is not None and (not isinstance(source_sha, str) or not SHA256.fullmatch(source_sha.lower())):
        raise ValueError('sourceMusicSha256은 64자리 SHA-256이어야 합니다')
    session = Session(project)
    registered = [m for m in session._registered() if isinstance(m, dict) and m.get('id') == 'music']
    fields = (('video', 'video'), ('audio', 'music'), ('captions', 'captions'), ('storyboard', 'storyboard'))
    for key, kind in fields:
        paths = value.get(key, [])
        if paths is None:
            continue
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or len(paths) > 24:
            raise ValueError(f'{key}: 최대 24개 절대 경로 목록이 필요합니다')
        for index, item in enumerate(paths):
            path = absolute_file(item, key)
            entry = descriptor(path, kind, f'{kind}-{index}')
            entry['sourceMusicSha256'] = source_sha.lower() if source_sha else None
            registered.append(entry)
    if title:
        session.data['name'] = title.strip()
    session._set_registered(registered)
    return {'status': 'published', 'project': str(project), 'manifest': str(source), 'mediaCount': len(registered)}


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
        def media(self, path):
            size=path.stat().st_size; start,end,status=0,size-1,200; requested=self.headers.get('Range')
            if requested:
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested.strip())
                if not match: self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
                left,right=match.groups()
                if left: start=int(left);end=min(int(right),size-1) if right else size-1
                elif right: start=max(0,size-int(right))
                else: self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
                if start>=size or end<start: self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
                status=206
            length=end-start+1
            try:
                self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(length));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                with path.open('rb') as stream:
                    stream.seek(start); left=length
                    while left:
                        data=stream.read(min(64*1024,left))
                        if not data:break
                        self.wfile.write(data);left-=len(data)
            except (BrokenPipeError,ConnectionResetError): return
        def do_GET(self):
            parsed=urlparse(self.path)
            if not self.host_ok(): return self.deny(421,'허용되지 않은 Host입니다')
            if not self.token_ok(parsed): return self.deny(403,'세션 토큰이 올바르지 않습니다')
            if parsed.path=='/':
                page=TEMPLATE.read_text(encoding='utf-8').replace('__STUDIO_BOOTSTRAP__', 'window.__STUDIO_BOOTSTRAP__='+json.dumps({'token':session.token},ensure_ascii=False).replace('<','\\u003c')+';', 1).encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(page)));self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'self'; media-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'");self.send_header('X-Content-Type-Options','nosniff');self.end_headers();return self.wfile.write(page)
            if parsed.path=='/api/state': return self.send_json(200,session.state())
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
            return self.media(item['path'])
        def do_POST(self):
            parsed=urlparse(self.path)
            if not self.host_ok() or self.headers.get('Origin')!=self.origin() or self.headers.get('X-Studio-Token')!=session.token or not self.token_ok(parsed):return self.deny(403,'허용되지 않은 요청입니다')
            try:
                if parsed.path=='/api/music':
                    if self.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/octet-stream':return self.deny(415,'application/octet-stream 요청이 필요합니다')
                    try: length=int(self.headers.get('Content-Length',''))
                    except ValueError: raise ValueError('Content-Length가 필요합니다')
                    if not 1 <= length <= MAX_UPLOAD: raise ValueError('요청 본문 크기가 올바르지 않습니다')
                    return self.send_json(201,session.upload_music(self.headers.get('X-File-Name'),self.rfile,length))
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


def serve(project, music=None, host=None, open_browser=False, timeout=900, review=False):
    if not 1 <= timeout <= 86_400: raise ValueError('--timeout: 1..86400초가 필요합니다')
    session=Session(project,music,host,review);server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(session));server.daemon_threads=True;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}/?token={session.token}'
    print(json.dumps({'event':'studio-ready','url':url,'project':str(session.project),'expiresSeconds':timeout,'review':review,'localExecutorOnly':True},ensure_ascii=False),file=sys.stderr,flush=True)
    if open_browser:webbrowser.open(url)
    try:
        if not session.done.wait(timeout):
            action = '검수 마치기' if review else '선택 저장'
            raise TimeoutError(f'{action} 시간이 만료되었습니다. 이미 저장한 피드백은 유지됩니다')
        result={'status':'completed','project':str(session.project),'selection':str(session.project/SELECTION_FILE),'request':str(session.project/REQUEST_FILE),'review':review}
        showreel=session.project/SHOWREEL_REQUEST_FILE
        if showreel.is_file() and session.selection.get('mode') in {'showreel-cd','showreel-motion'}: result['showreelRequest']=str(showreel)
        return result
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('init');p.add_argument('--out',required=True);p.add_argument('--music');p.add_argument('--mode',choices=MODES,default='showreel-motion');p.add_argument('--host',choices=HOSTS,default='codex')
    p=sub.add_parser('serve');p.add_argument('--project',required=True);p.add_argument('--music');p.add_argument('--host',choices=HOSTS);p.add_argument('--mode',choices=MODES);p.add_argument('--open',action='store_true');p.add_argument('--review',action='store_true');p.add_argument('--timeout',type=int,default=900)
    p=sub.add_parser('publish');p.add_argument('--project',required=True);p.add_argument('--manifest',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='init': result=init_project(args.out,args.music,args.mode,args.host)
        elif args.command=='publish': result=publish(args.project,args.manifest)
        else:
            if args.mode: raise ValueError('--mode은 init에만 사용할 수 있습니다. 선택은 제작실에서 저장합니다')
            result=serve(args.project,args.music,args.host,args.open,args.timeout,args.review)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except (OSError,ValueError,FileExistsError,TimeoutError) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr);return 2
    return 0

if __name__=='__main__': raise SystemExit(main())
