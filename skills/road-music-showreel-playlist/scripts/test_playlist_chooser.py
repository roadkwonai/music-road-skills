#!/usr/bin/env python3
"""HTTP and selection-contract checks for the local preset chooser."""
from __future__ import annotations

import http.client
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import cd_presets as cd
from playlist_chooser import MAX_BODY, ChooserSession, handler_for, load_selection, open_chooser_page


class ChooserServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='playlist-chooser-')
        self.root = Path(self.temp.name)
        self.music = self.root / 'song.mp3'
        self.music.write_bytes(b'not-decoded-by-chooser')
        self.output = self.root / 'selection'
        self.session = ChooserSession(self.output, self.music)
        from http.server import ThreadingHTTPServer
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.session))
        self.server_errors = []
        self.server.handle_error = lambda request, client_address: self.server_errors.append((request, client_address))
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.origin = f'http://127.0.0.1:{self.port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        merged = {'Host': f'127.0.0.1:{self.port}'}
        merged.update(headers or {})
        connection.request(method, path, body=body, headers=merged)
        response = connection.getresponse()
        payload = response.read()
        result = response.status, dict(response.getheaders()), payload
        connection.close()
        return result

    def valid_choice(self):
        return {'schemaVersion': 1, 'styleId': 'groove-dial', 'display': {
            'showSpectrum': True, 'showQueue': False, 'showNowPlaying': False, 'channelName': 'PLAYLIST LAB',
        }}

    def post(self, value, **headers):
        body = json.dumps(value, ensure_ascii=False).encode()
        return self.request('POST', '/api/submit', body, {
            'Content-Type': 'application/json', 'Content-Length': str(len(body)),
            'Origin': self.origin, 'X-Playlist-Token': self.session.token, **headers,
        })

    def test_http_success_requires_complete_choice_and_preserves_music(self):
        page, _, body = self.request('GET', f'/?token={self.session.token}')
        self.assertEqual(page, 200)
        self.assertIn(b'groove-dial', body)
        self.assertIn(b'data-road-music-ui', body)
        self.assertIn(b'Paperlogy', body)
        self.assertIn(b'data-road-music-nav', body)
        self.assertIn('스타일 선택'.encode(), body)
        self.assertIn(b'href="#display-settings"', body)
        self.assertIn('aria-label="그루브 다이얼 스타일 미리보기"'.encode(), body)
        self.assertEqual(self.request('GET', f'/design/fonts/Paperlogy-4Regular.ttf?token={self.session.token}')[0], 200)
        partial = self.valid_choice()
        del partial['display']['showNowPlaying']
        self.assertEqual(self.post(partial)[0], 422)
        self.assertFalse(self.output.exists())
        status, _, body = self.post(self.valid_choice())
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)['status'], 'completed')
        request = json.loads((self.output / 'request.json').read_text(encoding='utf-8'))
        self.assertEqual(request['styleId'], 'groove-dial')
        self.assertEqual(request['music'], str(self.music.resolve()))
        self.assertEqual(request['display']['channelName'], 'PLAYLIST LAB')
        self.assertEqual(json.loads((self.output / 'display-options.json').read_text(encoding='utf-8')), request['display'])
        self.assertEqual(self.post(self.valid_choice())[0], 409)

    def test_rejects_cross_origin_token_path_and_oversized_requests(self):
        valid = self.valid_choice()
        body = json.dumps(valid).encode()
        self.assertEqual(self.request('GET', f'/?token={self.session.token}', headers={'Host': 'attacker.invalid'})[0], 421)
        self.assertEqual(self.request('POST', '/api/submit', body, {
            'Content-Type': 'application/json', 'Content-Length': str(len(body)), 'Origin': 'http://attacker.invalid',
            'X-Playlist-Token': self.session.token,
        })[0], 403)
        self.assertEqual(self.post(valid, **{'X-Playlist-Token': 'wrong'})[0], 403)
        self.assertEqual(self.request('POST', '/api/submit', body, {
            'Content-Type': 'text/plain', 'Content-Length': str(len(body)), 'Origin': self.origin,
            'X-Playlist-Token': self.session.token,
        })[0], 415)
        self.assertEqual(self.request('GET', f'/asset/../../scripts/cd_presets.py?token={self.session.token}')[0], 404)
        self.assertEqual(self.request('GET', f'/design/fonts/not-a-font.ttf?token={self.session.token}')[0], 404)
        self.assertEqual(self.request('POST', '/api/submit', b'', {
            'Content-Type': 'application/json', 'Content-Length': str(MAX_BODY + 1), 'Origin': self.origin,
            'X-Playlist-Token': self.session.token,
        })[0], 413)
        self.assertFalse(self.output.exists())

    def test_preview_range_is_limited_to_registered_media(self):
        status, headers, body = self.request('GET', f'/asset/groove-dial/preview?token={self.session.token}', headers={'Range': 'bytes=100-199'})
        self.assertEqual(status, 206)
        self.assertEqual(headers['Content-Range'].split()[0], 'bytes')
        self.assertEqual(len(body), 100)
        self.assertEqual(self.request('GET', f'/asset/groove-dial/preview?token=wrong')[0], 404)

    def test_cancelled_preview_stream_does_not_block_following_selection(self):
        connection = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        request = (f'GET /asset/groove-dial/preview?token={self.session.token} HTTP/1.1\r\n'
                   f'Host: 127.0.0.1:{self.port}\r\nRange: bytes=0-9999999\r\nConnection: close\r\n\r\n')
        connection.sendall(request.encode('ascii'))
        self.assertIn(b'206', connection.recv(1024))
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        connection.close()
        time.sleep(.2)
        self.assertEqual(self.post(self.valid_choice())[0], 201)
        time.sleep(.2)
        self.assertEqual(self.server_errors, [])

    def test_existing_destination_is_never_reused(self):
        existing = self.root / 'existing'
        existing.mkdir()
        sentinel = existing / 'keep.txt'
        sentinel.write_text('keep', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            ChooserSession(existing, self.music)
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep')

    def test_browser_open_uses_shared_helper_and_keeps_selection_session_alive_on_failure(self):
        events = []
        url = f'{self.origin}/?token={self.session.token}'
        with patch('playlist_chooser.open_page', return_value=True) as opener:
            self.assertTrue(open_chooser_page(url, events.append))
        opener.assert_called_once_with(url)
        self.assertEqual(events, [])
        with patch('playlist_chooser.open_page', side_effect=RuntimeError('ego unavailable')):
            self.assertFalse(open_chooser_page(url, events.append))
        self.assertEqual(events[-1], {'event': 'chooser-open-failed', 'url': url, 'error': 'ego unavailable'})
        self.assertFalse(self.session.done.is_set())

    def test_plan_reads_selection_and_rejects_conflicting_explicit_style(self):
        choice = self.valid_choice()
        self.session.save(choice)
        loaded = load_selection(self.output / 'request.json')
        self.assertEqual(loaded['value']['styleId'], 'groove-dial')
        args = type('Args', (), {'genre': '록 발라드', 'brief': '', 'artist': '', 'instrumental': False,
            'style': None, 'look': None, 'vocal': None, 'act': 'auto', 'display': None,
            'selection': str(self.output / 'request.json'), 'out': None, 'host': None})()
        plan = cd.plan_command(args)
        self.assertEqual(plan['basePresetId'], 'groove-dial')
        self.assertEqual(plan['imageGeneration']['host'], 'codex')
        args.style = '네온'
        with self.assertRaisesRegex(ValueError, 'selection'):
            cd.plan_command(args)

    def test_selection_loader_accepts_only_supported_optional_hosts(self):
        request = self.root / 'selection.json'
        for host in ('codex', 'claude', 'antigravity', 'antigravity-cli'):
            choice = self.valid_choice()
            choice['host'] = host
            request.write_text(json.dumps(choice), encoding='utf-8')
            self.assertEqual(load_selection(request)['value']['host'], host)
        choice['host'] = 'imaginary'
        request.write_text(json.dumps(choice), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'host'):
            load_selection(request)

    def test_create_rejects_a_different_music_than_the_selection(self):
        self.session.save(self.valid_choice())
        other = self.root / 'other.mp3'
        other.write_bytes(b'other')
        args = type('Args', (), {'plan': None, 'selection': str(self.output / 'request.json'),
            'style': None, 'playlist': None, 'music': str(other)})()
        with self.assertRaisesRegex(ValueError, '--music'):
            cd.create(args)


if __name__ == '__main__':
    unittest.main()
