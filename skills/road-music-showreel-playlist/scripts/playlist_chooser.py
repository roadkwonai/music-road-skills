#!/usr/bin/env python3
"""Loopback-only preset picker for a local ChatGPT/Codex executor."""
from __future__ import annotations

import html
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from cd_presets import registry
from playlist_tools import DISPLAY_KEYS, normalize_display


ROOT = Path(__file__).resolve().parents[1]
DESIGN_SCRIPTS = ROOT.parent / 'road-music-video-studio' / 'scripts'
if str(DESIGN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DESIGN_SCRIPTS))
from html_design import ASSET_ROOT, FONT_FILES, add_navigation, css_text, open_page
from guide_content import guide_media_file, markdown_source, render_guide


MAX_BODY = 4096
SCHEMA_VERSION = 1


def _atomic_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix='.' + path.name + '.', delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        temporary = Path(stream.name)
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class ChooserSession:
    """One in-memory selection session. No token is persisted with the result."""

    def __init__(self, output, music=None):
        self.output = Path(output).resolve()
        self.music = Path(music).resolve(strict=True) if music else None
        if self.music and not self.music.is_file():
            raise ValueError('--music: 파일 필요')
        if self.output.exists():
            raise FileExistsError(f'새 세션 폴더가 이미 존재합니다: {self.output}')
        self.token = secrets.token_urlsafe(32)
        self.presets = {spec['id']: (spec, directory) for spec, directory in registry()}
        self.done = threading.Event()
        self.choice = None
        self.lock = threading.Lock()

    def selection(self, value):
        if not isinstance(value, dict) or set(value) != {'schemaVersion', 'styleId', 'display'}:
            raise ValueError('선택은 schemaVersion/styleId/display만 포함해야 합니다')
        if value['schemaVersion'] != SCHEMA_VERSION or not isinstance(value['styleId'], str) or value['styleId'] not in self.presets:
            raise ValueError('지원하지 않는 schemaVersion 또는 styleId입니다')
        display = value['display']
        if not isinstance(display, dict) or set(display) != DISPLAY_KEYS:
            raise ValueError('display는 스펙트럼/대기목록/현재곡/채널명을 모두 선택해야 합니다')
        choice = {
            'schemaVersion': SCHEMA_VERSION,
            'styleId': value['styleId'],
            'display': normalize_display(display),
        }
        if self.music:
            choice['music'] = str(self.music)
        return choice

    def save(self, value):
        choice = self.selection(value)
        with self.lock:
            if self.done.is_set():
                raise RuntimeError('이 선택 세션은 이미 완료되었습니다')
            try:
                self.output.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                raise FileExistsError(f'새 세션 폴더가 이미 존재합니다: {self.output}')
            try:
                _atomic_json(self.output / 'request.json', choice)
                _atomic_json(self.output / 'display-options.json', choice['display'])
            except Exception:
                # A failed first write must not expose a partially completed selection.
                for path in (self.output / 'request.json', self.output / 'display-options.json'):
                    if path.exists():
                        path.unlink()
                self.output.rmdir()
                raise
            self.choice = choice
            self.done.set()
        return choice


def _html_page(session, guide_base=None):
    esc = html.escape
    token = quote(session.token, safe='')
    design_css = css_text('/design/fonts/', session.token)
    cards = []
    for style_id, (spec, directory) in session.presets.items():
        preview = spec.get('preview', {})
        video = directory / preview.get('video', '')
        poster = directory / preview.get('poster', '')
        media = ''
        if preview.get('status') == 'ready' and video.is_file() and poster.is_file():
            media = (f'<video controls preload="metadata" playsinline aria-label="{esc(spec["name"])} 스타일 미리보기" poster="/asset/{quote(style_id)}/poster?token={token}">'
                     f'<source src="/asset/{quote(style_id)}/preview?token={token}" type="video/mp4"></video>')
        else:
            media = '<div class="missing">미리보기 준비 중</div>'
        cards.append(f'<article><label class="card">{media}<input type="radio" name="style" aria-label="{esc(spec["name"])} 선택" data-style-name="{esc(spec["name"])}" value="{esc(style_id)}"><span><b>{esc(spec["name"])}</b><small>{esc(spec["description"])}</small></span></label></article>')
    music_label = esc(session.music.name) if session.music else '음악 파일은 다음 제작 단계에서 연결합니다'
    page = f'''<!doctype html><html lang="ko" data-road-music-ui><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Showreel 스타일 선택</title><style>
*{{box-sizing:border-box}}main{{max-width:1320px;margin:auto;padding:36px 24px}}.music,.missing,small{{color:var(--rm-muted)}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}article,.options{{border:1px solid var(--rm-border);overflow:hidden}}.card{{display:block;cursor:pointer}}video,.missing{{display:block;width:100%;aspect-ratio:16/9;background:#101112}}.missing{{display:grid;place-items:center}}.card span{{display:block;padding:14px 16px}}small{{display:block;margin-top:4px}}article:has(input:checked){{outline:3px solid var(--rm-primary);outline-offset:2px}}.option{{padding:18px;margin:18px 0}}fieldset{{border:0;padding:0;margin:0 0 16px}}legend{{font-weight:700;margin-bottom:7px}}.pick{{display:inline-flex;align-items:center;gap:6px;margin-right:12px}}#channel{{width:min(100%,480px)}}button{{padding:12px 20px;border:0;font-weight:700;cursor:pointer}}#status{{min-height:24px}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}main{{padding:20px 14px}}}}
</style><style>{design_css}</style></head><body><main><p class="music">{music_label}</p><h1>스타일과 화면 표시를 고르세요.</h1><p>아래 영상은 스타일 샘플입니다. 선택 후 지금 음악으로 새로 제작합니다. 표시 항목은 각각 SKIP할 수 있습니다.</p><form id="form"><section class="grid">{''.join(cards)}</section><section class="options option">
<fieldset id="display-settings" data-flag="showSpectrum"><legend>선형 스펙트럼</legend><p class="hint">음량 변화에 반응하는 그래프의 표시 여부입니다.</p><label class="pick"><input type="radio" name="showSpectrum" value="true">표시</label><label class="pick"><input type="radio" name="showSpectrum" value="false">표시 안 함</label><label class="pick"><input type="radio" name="showSpectrum" value="SKIP">SKIP</label></fieldset>
<fieldset data-flag="showQueue"><legend>재생 대기 곡 목록</legend><p class="hint">여러 곡 중 뒤에 이어질 곡 목록을 보여 줍니다.</p><label class="pick"><input type="radio" name="showQueue" value="true">표시</label><label class="pick"><input type="radio" name="showQueue" value="false">표시 안 함</label><label class="pick"><input type="radio" name="showQueue" value="SKIP">SKIP</label></fieldset>
<fieldset data-flag="showNowPlaying"><legend>현재 재생 곡 이름</legend><p class="hint">영상에서 현재 곡 제목을 표시합니다.</p><label class="pick"><input type="radio" name="showNowPlaying" value="true">표시</label><label class="pick"><input type="radio" name="showNowPlaying" value="false">표시 안 함</label><label class="pick"><input type="radio" name="showNowPlaying" value="SKIP">SKIP</label></fieldset>
<fieldset><legend>운영 채널명</legend><p class="hint" id="channel-help">표시할 채널명을 입력하거나 SKIP으로 생략합니다.</p><input id="channel" name="channelName" type="text" aria-label="운영 채널명" aria-describedby="channel-help" title="표시할 채널명입니다. SKIP은 이 항목을 생략합니다" maxlength="120" autocomplete="off" placeholder="채널명 입력"><label class="pick"><input id="channelSkip" type="checkbox">SKIP</label></fieldset>
<button id="submit" type="submit" disabled>선택 저장</button><p id="status" role="status"></p></section></form></main><script>
document.addEventListener('play',event=>{{if(event.target.matches('audio,video'))document.querySelectorAll('audio,video').forEach(media=>{{if(media!==event.target)media.pause()}})}},true);
let completed=false;
const form=document.querySelector('#form'), submit=document.querySelector('#submit'), status=document.querySelector('#status'), channel=document.querySelector('#channel'), channelSkip=document.querySelector('#channelSkip');
function selected(name){{const v=form.querySelector(`input[name="${{name}}"]:checked`);return v&&v.value}}
function ready(){{if(completed){{submit.disabled=true;return;}}const flags=['showSpectrum','showQueue','showNowPlaying'].every(selected);submit.disabled=!(selected('style')&&flags&&(channelSkip.checked||channel.value.trim()));}}
form.addEventListener('input',ready); form.addEventListener('change',()=>{{channel.disabled=channelSkip.checked;ready();}});
form.addEventListener('submit',async e=>{{e.preventDefault();if(submit.disabled)return;const display={{}};for(const name of ['showSpectrum','showQueue','showNowPlaying']){{const v=selected(name);display[name]=v==='true';}}display.channelName=channelSkip.checked?'SKIP':channel.value.trim();submit.disabled=true;status.textContent='저장 중…';try{{const r=await fetch('/api/submit',{{method:'POST',headers:{{'Content-Type':'application/json','X-Playlist-Token':'{token}'}},body:JSON.stringify({{schemaVersion:1,styleId:selected('style'),display}})}});const data=await r.json();if(!r.ok)throw new Error(data.error||'저장 실패');completed=true;form.querySelectorAll('input,button').forEach(control=>{{control.disabled=true;}});form.querySelectorAll('video').forEach(media=>{{media.pause();media.controls=false;}});status.textContent='선택이 저장되었습니다: '+form.querySelector('input[name=style]:checked').dataset.styleName+' · 채널 '+(data.display.channelName||'SKIP')+'. 선택값이 CLI에 전달되었습니다.';}}catch(err){{status.textContent=err.message;ready();}}}});
</script></body></html>'''
    page = page.replace('<section class="grid">', '<section id="styles" class="grid">', 1)
    return add_navigation(page, current='chooser', guide_url=guide_base, sections=[('스타일 선택', '#styles'), ('표시 설정', '#display-settings')])


def handler_for(session):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'PlaylistChooser/1.0'

        def log_message(self, _format, *_args):
            return

        def _origin(self):
            return f'http://127.0.0.1:{self.server.server_port}'

        def _host_ok(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def _send_json(self, status, value):
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(encoded)

        def _deny(self, status, message):
            self._send_json(status, {'error': message})

        def _document(self, body, content_type='text/html; charset=utf-8'):
            data = body.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _token_ok(self, parsed):
            return parse_qs(parsed.query).get('token') == [session.token]

        def _send_media(self, candidate, content_type):
            size = candidate.stat().st_size
            requested = self.headers.get('Range')
            start, end, status = 0, size - 1, 200
            if requested:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested.strip())
                if not match:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.end_headers()
                    return
                left, right = match.groups()
                if not left and not right:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.end_headers()
                    return
                if left:
                    start = int(left)
                    end = min(int(right), size - 1) if right else size - 1
                else:
                    length = int(right)
                    start = max(0, size - length)
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.end_headers()
                    return
                status = 206
            length = end - start + 1
            try:
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(length))
                self.send_header('Accept-Ranges', 'bytes')
                if status == 206:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                with candidate.open('rb') as stream:
                    stream.seek(start)
                    remaining = length
                    while remaining:
                        block = stream.read(min(64 * 1024, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError):
                # Closing a preview player is a normal client-side media cancellation.
                return

        def _guide_media(self, name):
            path = guide_media_file(name)
            content_type = {
                '.svg': 'image/svg+xml',
                '.webp': 'image/webp',
            }.get(path.suffix.lower(), mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            return self._send_media(path, content_type)

        def do_GET(self):
            parsed = urlparse(self.path)
            if not self._host_ok():
                return self._deny(421, '허용되지 않은 Host입니다')
            if parsed.path == '/':
                if not self._token_ok(parsed):
                    return self._deny(403, '세션 토큰이 올바르지 않습니다')
                body = _html_page(session, self._origin()+'/?token='+session.token).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                return self.wfile.write(body)
            if parsed.path == '/design.css' and self._token_ok(parsed):
                return self._document(css_text('/design/fonts/', session.token), 'text/css; charset=utf-8')
            if parsed.path.startswith('/guide-media/'):
                if not self._token_ok(parsed):
                    return self._deny(403, '세션 토큰이 올바르지 않습니다')
                match = re.fullmatch(r'/guide-media/([^/]+)', parsed.path)
                if not match:
                    return self._deny(404, '등록된 가이드 이미지가 아닙니다')
                try:
                    return self._guide_media(match.group(1))
                except (OSError, ValueError):
                    return self._deny(404, '등록된 가이드 이미지가 아닙니다')
            if parsed.path.startswith('/guide/'):
                if not self._token_ok(parsed):
                    return self._deny(403, '세션 토큰이 올바르지 않습니다')
                match = re.fullmatch(r'/guide/(?:([a-z][a-z0-9-]*)(/|\.md))?', parsed.path)
                if not match:
                    return self._deny(404, '찾을 수 없는 가이드입니다')
                slug, ending = match.groups()
                try:
                    if ending == '.md':
                        return self._document(markdown_source(slug), 'text/markdown; charset=utf-8')
                    page = render_guide(slug or 'start', session.token, self._origin()+'/?token='+session.token).replace('>제작실로 돌아가기</a>', '>선택 화면으로 돌아가기</a>')
                    return self._document(add_navigation(page, current='guide'))
                except ValueError as error:
                    return self._deny(404, str(error))
            parts = parsed.path.split('/')
            if len(parts) == 4 and parts[1:3] == ['design', 'fonts'] and self._token_ok(parsed):
                name = parts[3]
                candidate = ASSET_ROOT / 'fonts' / name
                if name not in FONT_FILES or candidate.is_symlink() or not candidate.is_file():
                    return self._deny(404, '찾을 수 없는 디자인 폰트입니다')
                return self._send_media(candidate, 'font/ttf')
            if len(parts) == 4 and parts[1] == 'asset' and self._token_ok(parsed):
                style_id, kind = parts[2], parts[3]
                if style_id not in session.presets or kind not in {'preview', 'poster'}:
                    return self._deny(404, '찾을 수 없는 미리보기 자산입니다')
                spec, directory = session.presets[style_id]
                name = spec.get('preview', {}).get('video' if kind == 'preview' else 'poster', '')
                candidate = directory / name
                if not name or candidate.is_symlink() or not candidate.is_file() or candidate.parent != directory:
                    return self._deny(404, '찾을 수 없는 미리보기 자산입니다')
                return self._send_media(candidate, 'video/mp4' if kind == 'preview' else 'image/jpeg')
            return self._deny(404, '지원하지 않는 경로입니다')

        def do_POST(self):
            parsed = urlparse(self.path)
            if not self._host_ok() or self.headers.get('Origin') != self._origin() or self.headers.get('X-Playlist-Token') != session.token:
                return self._deny(403, '허용되지 않은 선택 요청입니다')
            if parsed.path != '/api/submit' or parsed.query:
                return self._deny(404, '지원하지 않는 경로입니다')
            if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                return self._deny(415, 'application/json 요청이 필요합니다')
            try:
                length = int(self.headers.get('Content-Length', ''))
            except ValueError:
                return self._deny(411, 'Content-Length가 필요합니다')
            if length < 1 or length > MAX_BODY:
                return self._deny(413, '요청 본문 크기가 올바르지 않습니다')
            try:
                value = json.loads(self.rfile.read(length).decode('utf-8'))
                choice = session.save(value)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                return self._deny(422, str(error))
            except (FileExistsError, RuntimeError) as error:
                return self._deny(409, str(error))
            return self._send_json(201, {'status': 'completed', 'styleId': choice['styleId'], 'display': choice['display']})

    return Handler


def open_chooser_page(url, progress=None):
    try:
        opened = open_page(url)
    except Exception as caught:
        opened, message = False, str(caught)
    else:
        message = None if opened else '기본 브라우저가 URL을 열지 않았습니다'
    if not opened and progress:
        progress({'event': 'chooser-open-failed', 'url': url, 'error': message})
    return bool(opened)


def choose(output, music=None, open_browser=False, timeout=900, progress=None):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 86_400:
        raise ValueError('--timeout: 1..86400초 필요')
    session = ChooserSession(output, music)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(session))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/?token={session.token}'
    event = {'event': 'chooser-ready', 'url': url, 'expiresSeconds': timeout, 'localExecutorOnly': True}
    if progress:
        progress(event)
    if open_browser:
        open_chooser_page(url, progress)
    try:
        if not session.done.wait(timeout):
            raise TimeoutError('스타일 선택 시간이 만료되었습니다. 선택값은 저장하지 않았습니다')
        return {
            'status': 'completed', 'out': str(session.output), 'request': str(session.output / 'request.json'),
            'displayOptions': str(session.output / 'display-options.json'), **session.choice,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def choose_command(args):
    return choose(args.out, args.music, args.open, args.timeout, lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True))


def load_selection(path):
    """Read a completed choice without accepting arbitrary project settings."""
    source = Path(path).resolve(strict=True)
    value = json.loads(source.read_text(encoding='utf-8-sig'))
    required = {'schemaVersion', 'styleId', 'display'}
    optional = {'music', 'host'}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        raise ValueError('선택 JSON은 schemaVersion/styleId/display와 선택 music/host만 포함해야 합니다')
    if value.get('schemaVersion') != SCHEMA_VERSION or not isinstance(value.get('styleId'), str):
        raise ValueError('선택 JSON의 schemaVersion/styleId가 올바르지 않습니다')
    if not isinstance(value.get('display'), dict) or set(value['display']) != DISPLAY_KEYS:
        raise ValueError('선택 JSON의 display는 네 표시 항목을 모두 포함해야 합니다')
    if 'music' in value and (not isinstance(value['music'], str) or not Path(value['music']).is_absolute()):
        raise ValueError('선택 JSON의 music은 절대 경로 문자열이어야 합니다')
    if 'host' in value and value['host'] not in {'codex', 'claude', 'antigravity', 'antigravity-cli'}:
        raise ValueError('선택 JSON의 host는 지원되는 작업 호스트여야 합니다')
    with source.open('rb') as stream:
        source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': source, 'sha256': source_hash, 'value': {
        **{'schemaVersion': SCHEMA_VERSION, 'styleId': value['styleId'], 'display': normalize_display(value.get('display'))},
        **({'music': value['music']} if 'music' in value else {}),
        **({'host': value['host']} if 'host' in value else {}),
    }}
