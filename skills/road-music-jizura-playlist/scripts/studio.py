#!/usr/bin/env python3
"""Serve the local JIZURA music studio on a token-protected loopback URL."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JIZURA_ROOT = Path.home() / '.local/share/roadmusic-video-tools/jizura'
VERSION = '0.10.1'
SOURCE_URL = 'https://github.com/852wa/JIZURA'
MAX_JSON_BODY = 16 * 1024 * 1024
MAX_AUDIO_BODY = 512 * 1024 * 1024
MAX_FONT_BODY = 32 * 1024 * 1024
MAX_TEXT = 1024 * 1024
MAX_METADATA = 64 * 1024
ASPECTS = {'16:9', '9:16', '4:3', '3:4', '1:1', '4:5', '21:9'}
RESOLUTIONS = {720, 1080, 1440, 2160}
FPS = {24, 30, 60}
QUALITIES = {'standard', 'high', 'max'}
FONT_KEY = re.compile(r'user_[A-Za-z0-9_-]{1,80}\Z')
FONT_HEADERS = {
    '.ttf': b'\x00\x01\x00\x00', '.otf': b'OTTO', '.woff': b'wOFF',
    '.woff2': b'wOF2', '.ttc': b'ttcf',
}
FONT_MIME_TYPES = {
    '.ttf': 'font/ttf', '.otf': 'font/otf', '.woff': 'font/woff',
    '.woff2': 'font/woff2', '.ttc': 'font/collection',
}


def _json_loads(raw):
    def reject_constant(value):
        raise ValueError(f'JSON 숫자 {value}은 허용되지 않습니다')
    return json.loads(raw, parse_constant=reject_constant)


def _check_json(value, depth=0, counter=None):
    """Keep a native project opaque while rejecting unsafe JSON resource shapes."""
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > 150_000 or depth > 64:
        raise ValueError('JSON 구조가 너무 큽니다')
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('유한한 숫자만 저장할 수 있습니다')
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT:
            raise ValueError('문자열이 너무 깁니다')
        return
    if isinstance(value, list):
        for item in value:
            _check_json(item, depth + 1, counter)
        return
    if isinstance(value, dict):
        if len(value) > 4_000:
            raise ValueError('객체 키가 너무 많습니다')
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 512:
                raise ValueError('JSON 키가 올바르지 않습니다')
            _check_json(item, depth + 1, counter)
        return
    raise ValueError('지원하지 않는 JSON 값입니다')


def _read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_JSON_BODY:
        raise ValueError(f'{path}: JSON 파일이 너무 큽니다')
    value = _json_loads(raw.decode('utf-8-sig'))
    _check_json(value)
    return value


def _sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _atomic_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     prefix='.' + path.name + '.', delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        temporary = Path(stream.name)
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _absolute_file(value, name):
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f'{name}: 절대 경로가 필요합니다')
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f'{name}: 파일이 필요합니다')
    return path


def _audio_info(path, url=None):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('음원 파일이 필요합니다')
    return {
        'name': path.name,
        'path': str(path),
        'sha256': _sha256(path),
        'url': url,
        'size': path.stat().st_size,
    }


def _valid_file_name(encoded):
    if not isinstance(encoded, str) or not encoded or len(encoded) > 1024:
        raise ValueError('X-File-Name이 필요합니다')
    name = unquote(encoded)
    if (not name or len(name) > 180 or name in {'.', '..'} or '\x00' in name or
            '/' in name or '\\' in name or Path(name).name != name):
        raise ValueError('안전한 파일명만 가져올 수 있습니다')
    return name


def _valid_font_name(encoded, key):
    name = f'{key}.ttf' if encoded is None else _valid_file_name(encoded)
    if Path(name).suffix.lower() not in FONT_HEADERS:
        raise ValueError('TTF/OTF/WOFF/WOFF2/TTC 글꼴 파일만 사용할 수 있습니다')
    return name


def _font_descriptor(path, key, name=None, expected_sha256=None):
    if not isinstance(key, str) or not FONT_KEY.fullmatch(key):
        raise ValueError('X-Font-Key은 user_ 접두사의 안전한 키여야 합니다')
    original = Path(path)
    if original.is_symlink():
        raise ValueError('심볼릭 링크 글꼴은 사용할 수 없습니다')
    path = original.resolve(strict=True)
    if not path.is_file():
        raise ValueError('글꼴 파일이 필요합니다')
    suffix = path.suffix.lower()
    if suffix not in FONT_HEADERS or path.stat().st_size < 4 or path.stat().st_size > MAX_FONT_BODY:
        raise ValueError('글꼴 파일 형식 또는 크기가 올바르지 않습니다')
    with path.open('rb') as stream:
        if stream.read(4) != FONT_HEADERS[suffix]:
            raise ValueError('글꼴 확장자와 실제 헤더가 일치하지 않습니다')
    name = _valid_font_name(name, key) if name is not None else path.name
    if Path(name).suffix.lower() != suffix:
        raise ValueError('글꼴 이름과 파일 확장자가 일치하지 않습니다')
    digest = _sha256(path)
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256) or digest != expected_sha256.lower():
            raise ValueError('글꼴 파일 해시가 일치하지 않습니다')
    return {'key': key, 'name': name, 'path': str(path), 'sha256': digest, 'size': path.stat().st_size}


class StudioSession:
    def __init__(self, out, audio=None, project=None, direction=None, analysis=None, jizura_root=None):
        output = Path(out)
        if not output.is_absolute():
            raise ValueError('--out: 새 절대 출력 경로가 필요합니다')
        self.output = output.resolve()
        if self.output.exists():
            raise FileExistsError(f'--out은 새 폴더여야 합니다: {self.output}')
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.saves = 0
        self.last_project = None
        self.audio = _audio_info(_absolute_file(audio, '--audio')) if audio else None
        self.project = _read_json(_absolute_file(project, '--project')) if project else None
        self.direction = _read_json(_absolute_file(direction, '--direction')) if direction else None
        self.analysis = _read_json(_absolute_file(analysis, '--analysis')) if analysis else None
        self.analysis_status = None
        if self.project is not None and not isinstance(self.project, dict):
            raise ValueError('--project: JSON 객체가 필요합니다')
        for name in ('direction', 'analysis'):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), dict):
                raise ValueError(f'--{name}: JSON 객체가 필요합니다')
        root = Path(jizura_root) if jizura_root else DEFAULT_JIZURA_ROOT
        if not root.is_absolute():
            raise ValueError('--jizura-root: 절대 경로가 필요합니다')
        self.jizura_root = root.resolve(strict=True)
        self.engine = self.jizura_root / 'ko' / 'index.html'
        if not self.engine.is_file():
            raise ValueError('JIZURA 한국어 런타임(ko/index.html)을 찾을 수 없습니다')
        directions = _read_json(SKILL_ROOT / 'assets' / 'directions.json')
        self.profiles = directions.get('profiles')
        if not isinstance(self.profiles, list):
            raise ValueError('directions.json의 profiles가 올바르지 않습니다')
        # Validate all caller-supplied inputs before claiming the requested new output path.
        self.output.mkdir(parents=True, exist_ok=False)
        self.inputs = self.output / 'inputs'
        try:
            self.inputs.mkdir()
        except Exception:
            self.output.rmdir()
            raise
        self.fonts = {}
        self.font_warnings = []
        self._restore_project_fonts()
        self._exclude_stale_analysis()

    def audio_payload(self, port):
        if self.audio is None:
            return None
        return {**self.audio, 'url': f'/api/audio?token={quote(self.token, safe="")}'}

    def config(self, port):
        return {
            'schemaVersion': 1,
            'runtime': {'version': VERSION, 'sourceUrl': SOURCE_URL, 'root': str(self.jizura_root)},
            'profiles': self.profiles,
            'project': self.project,
            'direction': self.direction,
            'analysis': self.analysis,
            'analysisStatus': self.analysis_status,
            'audio': self.audio_payload(port),
            'fonts': [self.font_payload(font) for font in self.fonts.values()],
            'fontWarnings': self.font_warnings,
            'output': str(self.output),
        }

    def _exclude_stale_analysis(self):
        if self.audio is None or not isinstance(self.analysis, dict):
            return
        source = self.analysis.get('audio')
        recorded = source.get('sha256') if isinstance(source, dict) else None
        if isinstance(recorded, str) and recorded.lower() != self.audio['sha256']:
            self.analysis = None
            self.analysis_status = {'status': 'unreviewed', 'reason': 'source-sha256-mismatch'}

    def font_payload(self, font):
        return {**font, 'url': f'/api/font/{quote(font["key"], safe="")}?token={quote(self.token, safe="")}' }

    @staticmethod
    def _project_font_keys(project):
        fonts = project.get('userFonts', []) if isinstance(project, dict) else []
        if not isinstance(fonts, list):
            return []
        return [font['key'] for font in fonts if isinstance(font, dict) and isinstance(font.get('key'), str) and FONT_KEY.fullmatch(font['key'])]

    def _copy_font(self, source, key, name, expected_sha256=None):
        source_info = _font_descriptor(source, key, name, expected_sha256)
        target = self.inputs / f'{uuid.uuid4().hex}-{source_info["name"]}'
        try:
            with Path(source_info['path']).open('rb') as read, target.open('xb') as write:
                while block := read.read(64 * 1024):
                    write.write(block)
            return _font_descriptor(target, key, source_info['name'], source_info['sha256'])
        except Exception:
            if target.exists():
                target.unlink()
            raise

    def _restore_project_fonts(self):
        if not isinstance(self.project, dict):
            return
        declared = self.project.get('fontAssets', [])
        if declared is None:
            declared = []
        if not isinstance(declared, list):
            self.font_warnings.append('fontAssets 형식이 올바르지 않아 글꼴 파일을 복원하지 않았습니다')
            self.project['fontAssets'] = []
            return
        restored = []
        for index, asset in enumerate(declared):
            try:
                if not isinstance(asset, dict) or set(asset) - {'key', 'name', 'path', 'sha256'} or set(asset) != {'key', 'name', 'path', 'sha256'}:
                    raise ValueError('key/name/path/sha256이 필요합니다')
                source = _absolute_file(asset['path'], f'fontAssets[{index}].path')
                copied = self._copy_font(source, asset['key'], asset['name'], asset['sha256'])
                if copied['key'] in self.fonts:
                    raise ValueError('글꼴 키가 중복됩니다')
                self.fonts[copied['key']] = copied
                restored.append({key: copied[key] for key in ('key', 'name', 'path', 'sha256')})
            except (OSError, ValueError) as error:
                self.font_warnings.append(f'fontAssets[{index}] 복원 실패: {error}')
        self.project['fontAssets'] = restored
        for key in self._project_font_keys(self.project):
            if key not in self.fonts:
                self.font_warnings.append(f'{key}: 검증된 글꼴 파일이 없어 기본 글꼴로 엽니다')

    def import_font(self, key, encoded_name, stream, length):
        if not isinstance(key, str) or not FONT_KEY.fullmatch(key):
            raise ValueError('X-Font-Key은 user_ 접두사의 안전한 키여야 합니다')
        name = _valid_font_name(encoded_name, key)
        if length < 4 or length > MAX_FONT_BODY:
            raise ValueError('글꼴 크기는 4바이트~32MiB여야 합니다')
        target = self.inputs / f'{uuid.uuid4().hex}-{name}'
        digest = hashlib.sha256()
        remaining, header = length, b''
        try:
            with target.open('xb') as destination:
                while remaining:
                    block = stream.read(min(64 * 1024, remaining))
                    if not block:
                        raise ValueError('글꼴 본문이 중간에 끝났습니다')
                    if len(header) < 4:
                        header += block[:4 - len(header)]
                    destination.write(block)
                    digest.update(block)
                    remaining -= len(block)
            suffix = Path(name).suffix.lower()
            if header != FONT_HEADERS[suffix]:
                raise ValueError('글꼴 확장자와 실제 헤더가 일치하지 않습니다')
            info = _font_descriptor(target, key, name, digest.hexdigest())
        except Exception:
            if target.exists():
                target.unlink()
            raise
        with self.lock:
            self.fonts[key] = info
        return info

    def import_audio(self, encoded_name, stream, length):
        name = _valid_file_name(encoded_name)
        if length < 1 or length > MAX_AUDIO_BODY:
            raise ValueError('음원 크기는 1바이트~512MiB여야 합니다')
        target = self.inputs / f'{uuid.uuid4().hex}-{name}'
        digest = hashlib.sha256()
        remaining = length
        try:
            with target.open('xb') as destination:
                while remaining:
                    block = stream.read(min(64 * 1024, remaining))
                    if not block:
                        raise ValueError('음원 본문이 중간에 끝났습니다')
                    destination.write(block)
                    digest.update(block)
                    remaining -= len(block)
            info = {'name': name, 'path': str(target.resolve()), 'sha256': digest.hexdigest(),
                    'url': None, 'size': length}
        except Exception:
            if target.exists():
                target.unlink()
            raise
        with self.lock:
            self.audio = info
            self._exclude_stale_analysis()
        return info

    @staticmethod
    def _native_project(project, audio, fonts):
        if not isinstance(project, dict) or isinstance(project, list):
            raise ValueError('project는 native JIZURA JSON 객체여야 합니다')
        _check_json(project)
        value = json.loads(json.dumps(project, ensure_ascii=False, allow_nan=False))
        if 'version' in value and value['version'] != 1:
            raise ValueError('project.version은 1이어야 합니다')
        if 'timingOrder' in value and value['timingOrder'] != 2:
            raise ValueError('project.timingOrder는 2여야 합니다')
        if 'aspect' in value and value['aspect'] not in ASPECTS:
            raise ValueError('project.aspect이 JIZURA 지원 화면비가 아닙니다')
        if 'res' in value and (isinstance(value['res'], bool) or value['res'] not in RESOLUTIONS):
            raise ValueError('project.res가 JIZURA 지원 해상도가 아닙니다')
        if 'fps' in value and (isinstance(value['fps'], bool) or value['fps'] not in FPS):
            raise ValueError('project.fps가 JIZURA 지원 값이 아닙니다')
        if 'quality' in value and value['quality'] not in QUALITIES:
            raise ValueError('project.quality가 JIZURA 지원 값이 아닙니다')
        if 'lyrics' in value and (not isinstance(value['lyrics'], str) or len(value['lyrics']) > MAX_TEXT):
            raise ValueError('project.lyrics는 제한 안의 문자열이어야 합니다')
        for field in ('title', 'artist'):
            if field in value and (not isinstance(value[field], str) or len(value[field]) > 4096):
                raise ValueError(f'project.{field}가 너무 깁니다')
        if 'metadata' in value:
            if not isinstance(value['metadata'], dict) or len(json.dumps(value['metadata'], ensure_ascii=False, allow_nan=False).encode()) > MAX_METADATA:
                raise ValueError('project.metadata가 너무 큽니다')
        for field in ('fx', 'overrides', 'fonts', 'colors', 'timing'):
            if field in value and not isinstance(value[field], dict):
                raise ValueError(f'project.{field}는 객체여야 합니다')
        font_assets = []
        for key in dict.fromkeys(StudioSession._project_font_keys(value)):
            font = fonts.get(key)
            if font is not None:
                font_assets.append({field: font[field] for field in ('key', 'name', 'path', 'sha256')})
        value['fontAssets'] = font_assets
        if audio is None:
            if value.get('source') not in (None, {}):
                raise ValueError('현재 음원 없이 project.source를 저장할 수 없습니다')
            value.pop('source', None)
        else:
            source = value.get('source')
            if not isinstance(source, dict) or not isinstance(source.get('sha256'), str):
                raise ValueError('현재 음원에는 project.source.sha256이 필요합니다')
            if source['sha256'].lower() != audio['sha256']:
                raise ValueError('project.source.sha256과 현재 음원 해시가 다릅니다')
            source['sha256'] = audio['sha256']
            source['path'] = audio['path']
            value['source'] = source
        value['version'] = 1
        value['timingOrder'] = 2
        value['appVersion'] = VERSION
        return value

    def save(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'project', 'direction', 'plan', 'studio'}:
            raise ValueError('저장 요청은 project/direction/plan/studio만 포함합니다')
        if 'project' not in payload:
            raise ValueError('project가 필요합니다')
        for field in ('direction', 'plan', 'studio'):
            if field in payload and payload[field] is not None and not isinstance(payload[field], dict):
                raise ValueError(f'{field}는 객체 또는 null이어야 합니다')
        _check_json(payload)
        with self.lock:
            project = self._native_project(payload['project'], self.audio, self.fonts)
            number = 1
            while True:
                revision = self.output / f'revision-{number:03d}'
                try:
                    revision.mkdir()
                    break
                except FileExistsError:
                    number += 1
            _atomic_json(revision / 'project.jizura.json', project)
            for field, name in (('direction', 'direction.json'), ('plan', 'plan.json'), ('studio', 'studio.json')):
                if payload.get(field) is not None:
                    _atomic_json(revision / name, payload[field])
            self.project = project
            self.direction = payload.get('direction')
            self.saves += 1
            self.last_project = str((revision / 'project.jizura.json').resolve())
        return {'ok': True, 'revision': revision.name, 'project': self.last_project, 'output': str(revision.resolve())}


def handler_for(session):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'JizuraStudio/1.0'

        def log_message(self, _format, *_args):
            return

        def _origin(self):
            return f'http://127.0.0.1:{self.server.server_port}'

        def _host_ok(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def _token_ok(self, parsed):
            values = parse_qs(parsed.query, keep_blank_values=True)
            return set(values) == {'token'} and values['token'] == [session.token]

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, value):
            self._send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'),
                       'application/json; charset=utf-8')

        def _error(self, status, message):
            self._json(status, {'ok': False, 'error': str(message)})

        def _static(self, path, content_type, csp=None, inject_token=False):
            if not path.is_file() or path.is_symlink():
                return self._error(404, '찾을 수 없는 자산입니다')
            body = path.read_bytes()
            if inject_token:
                body = body.replace(b'__TOKEN__', session.token.encode('ascii'))
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            if csp:
                self.send_header('Content-Security-Policy', csp)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _audio(self):
            with session.lock:
                audio = dict(session.audio) if session.audio else None
            if audio is None:
                return self._error(404, '연결된 음원이 없습니다')
            path = Path(audio['path'])
            if not path.is_file() or path.stat().st_size != audio['size'] or _sha256(path) != audio['sha256']:
                return self._error(409, '연결된 음원이 변경되었습니다')
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(audio['size']))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
                with path.open('rb') as stream:
                    while block := stream.read(64 * 1024):
                        self.wfile.write(block)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _font(self, key):
            if not FONT_KEY.fullmatch(key):
                return self._error(404, '찾을 수 없는 글꼴입니다')
            with session.lock:
                font = dict(session.fonts[key]) if key in session.fonts else None
            if font is None:
                return self._error(404, '찾을 수 없는 글꼴입니다')
            try:
                checked = _font_descriptor(font['path'], font['key'], font['name'], font['sha256'])
            except (OSError, ValueError):
                return self._error(409, '연결된 글꼴 파일이 변경되었습니다')
            try:
                self.send_response(200)
                self.send_header('Content-Type', FONT_MIME_TYPES[Path(checked['name']).suffix.lower()])
                self.send_header('Content-Length', str(checked['size']))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
                with Path(checked['path']).open('rb') as stream:
                    while block := stream.read(64 * 1024):
                        self.wfile.write(block)
            except (BrokenPipeError, ConnectionResetError):
                return

        def do_GET(self):
            parsed = urlparse(self.path)
            if not self._host_ok():
                return self._error(421, '허용되지 않은 Host입니다')
            if not self._token_ok(parsed):
                return self._error(403, '세션 토큰이 올바르지 않습니다')
            assets = SKILL_ROOT / 'assets' / 'studio'
            routes = {
                '/': (assets / 'index.html', 'text/html; charset=utf-8',
                      "default-src 'self'; connect-src 'self'; media-src 'self'; frame-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'", True),
                '/studio.mjs': (assets / 'studio.mjs', 'text/javascript; charset=utf-8', None),
                '/studio.css': (assets / 'studio.css', 'text/css; charset=utf-8', None),
                '/directing.mjs': (SKILL_ROOT / 'scripts' / 'directing.mjs', 'text/javascript; charset=utf-8', None),
                '/engine/index.html': (session.engine, 'text/html; charset=utf-8',
                                        "default-src 'self' 'unsafe-inline' blob:; connect-src 'self'; media-src 'self' blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; base-uri 'none'; frame-ancestors 'self'"),
            }
            if parsed.path == '/api/config':
                return self._json(200, session.config(self.server.server_port))
            if parsed.path == '/api/status':
                with session.lock:
                    return self._json(200, {'ok': True, 'saves': session.saves, 'lastProject': session.last_project})
            if parsed.path == '/api/audio':
                return self._audio()
            font_match = re.fullmatch(r'/api/font/([^/]+)', parsed.path)
            if font_match:
                return self._font(unquote(font_match.group(1)))
            if parsed.path in routes:
                return self._static(*routes[parsed.path])
            return self._error(404, '지원하지 않는 경로입니다')

        def _content_length(self, limit):
            try:
                length = int(self.headers.get('Content-Length', ''))
            except ValueError:
                raise ValueError('Content-Length가 필요합니다')
            if length < 1 or length > limit:
                raise ValueError('요청 본문 크기가 올바르지 않습니다')
            return length

        def _body(self, limit):
            length = self._content_length(limit)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('요청 본문이 중간에 끝났습니다')
            return raw, length

        def do_POST(self):
            parsed = urlparse(self.path)
            if (not self._host_ok() or self.headers.get('Origin') != self._origin() or
                    not self._token_ok(parsed)):
                return self._error(403, '허용되지 않은 요청입니다')
            if parsed.path == '/api/import-audio':
                if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/octet-stream':
                    return self._error(415, 'application/octet-stream 요청이 필요합니다')
                try:
                    length = self._content_length(MAX_AUDIO_BODY)
                    info = session.import_audio(self.headers.get('X-File-Name'), self.rfile, length)
                except ValueError as error:
                    return self._error(422, error)
                return self._json(201, {'ok': True, 'audio': {**info, 'url': f'/api/audio?token={quote(session.token, safe="")}'} })
            if parsed.path == '/api/import-font':
                if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/octet-stream':
                    return self._error(415, 'application/octet-stream 요청이 필요합니다')
                try:
                    length = self._content_length(MAX_FONT_BODY)
                    info = session.import_font(self.headers.get('X-Font-Key'), self.headers.get('X-File-Name'), self.rfile, length)
                except ValueError as error:
                    return self._error(422, error)
                return self._json(201, {'ok': True, 'font': session.font_payload(info)})
            if parsed.path == '/api/save':
                if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                    return self._error(415, 'application/json 요청이 필요합니다')
                try:
                    raw, _length = self._body(MAX_JSON_BODY)
                    payload = _json_loads(raw.decode('utf-8'))
                    result = session.save(payload)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                    return self._error(422, error)
                return self._json(201, result)
            if parsed.path == '/api/stop':
                if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() not in {'', 'application/json'}:
                    return self._error(415, '빈 요청 또는 application/json 요청이 필요합니다')
                self._json(200, {'ok': True, 'stopping': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self._error(404, '지원하지 않는 경로입니다')

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--audio')
    parser.add_argument('--project')
    parser.add_argument('--direction')
    parser.add_argument('--analysis')
    parser.add_argument('--jizura-root')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('--port: 0..65535')
    try:
        session = StudioSession(args.out, args.audio, args.project, args.direction, args.analysis, args.jizura_root)
    except (OSError, ValueError, FileExistsError) as error:
        parser.error(str(error))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(session))
    server.daemon_threads = True
    ready = {'ok': True, 'url': f'http://127.0.0.1:{server.server_port}/?token={session.token}',
             'output': str(session.output), 'pid': os.getpid(), 'version': VERSION}
    print(json.dumps(ready, ensure_ascii=False, allow_nan=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
