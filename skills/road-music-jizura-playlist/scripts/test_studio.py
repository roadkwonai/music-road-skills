#!/usr/bin/env python3
"""HTTP contract checks for the loopback-only JIZURA Studio server."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


SCRIPT = Path(__file__).with_name('studio.py')


class StudioServer:
    def __init__(self, root, audio=None, project=None):
        runtime = root / 'jizura' / 'ko'
        runtime.mkdir(parents=True)
        (runtime / 'index.html').write_text('<!doctype html><title>engine</title>', encoding='utf-8')
        command = [sys.executable, str(SCRIPT), '--out', str(root / 'output'), '--jizura-root', str(runtime.parent)]
        if audio:
            command += ['--audio', str(audio)]
        if project:
            command += ['--project', str(project)]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = self.process.stdout.readline().strip()
        if not line:
            raise AssertionError(self.process.stderr.read())
        self.ready = json.loads(line)

    @property
    def url(self):
        return self.ready['url']

    @property
    def token(self):
        return self.url.split('token=', 1)[1]

    def request(self, path, method='GET', body=None, content_type=None, origin=True, token=True, headers=None):
        query = f'?token={self.token}' if token else ''
        request = Request(self.url.split('/?', 1)[0] + path + query, data=body, method=method)
        if content_type:
            request.add_header('Content-Type', content_type)
        if origin:
            request.add_header('Origin', self.url.split('/?', 1)[0])
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.read(), dict(response.headers)
        except HTTPError as error:
            with error:
                return error.code, error.read(), dict(error.headers)

    def stop(self):
        if self.process.poll() is None:
            self.request('/api/stop', method='POST', body=b'', content_type='application/json')
            self.process.wait(timeout=5)
        self.process.stdout.close()
        self.process.stderr.close()


class StudioTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.wav'
        self.source.write_bytes(b'first-audio')
        self.server = StudioServer(self.root, self.source)

    def tearDown(self):
        self.server.stop()
        self.temp.cleanup()

    def json_request(self, path, value, **kwargs):
        status, body, _headers = self.server.request(path, method='POST', body=json.dumps(value).encode(),
                                                     content_type='application/json', **kwargs)
        return status, json.loads(body)

    def test_token_origin_and_config(self):
        status, body, _headers = self.server.request('/api/config')
        config = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(config['schemaVersion'], 1)
        self.assertEqual(config['audio']['name'], 'source.wav')
        self.assertEqual(config['runtime']['version'], '0.10.1')
        status, page, _headers = self.server.request('/')
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), page)
        self.assertNotIn(b'__TOKEN__', page)
        self.assertEqual(self.server.request('/api/config', token=False)[0], 403)
        self.assertEqual(self.server.request('/api/config', headers={'Host': 'localhost:1'})[0], 421)
        self.assertEqual(self.server.request('/../secret', token=True)[0], 404)
        self.assertEqual(self.server.request('/engine/index.html')[0], 200)
        self.assertEqual(self.server.request('/api/stop', method='POST', body=b'', content_type='application/json', origin=False)[0], 403)

    def test_import_save_revisions_and_source_hash(self):
        bad_status, _body, _headers = self.server.request(
            '/api/import-audio', method='POST', body=b'x', content_type='application/octet-stream',
            headers={'X-File-Name': quote('../escape.wav')})
        self.assertEqual(bad_status, 422)
        status, body, _headers = self.server.request(
            '/api/import-audio', method='POST', body=b'imported-audio', content_type='application/octet-stream',
            headers={'X-File-Name': quote('new song.wav')})
        imported = json.loads(body)['audio']
        self.assertEqual(status, 201)
        self.assertTrue(Path(imported['path']).is_file())
        self.assertTrue(Path(imported['path']).is_relative_to((self.root / 'output' / 'inputs').resolve()))
        project = {
            'lyrics': '[00:00.000]원문', 'aspect': '16:9', 'res': 1080, 'fps': 30, 'quality': 'high',
            'style': 'noir', 'customNativeSetting': {'kept': True},
            'overrides': {'0': {'lock': True, 'lockedCuts': [{'unknownNativeField': {'kept': True}}]}},
            'source': {'sha256': imported['sha256'], 'path': '/untrusted/path'},
        }
        status, saved = self.json_request('/api/save', {'project': project, 'direction': {'profile': 'noir-groove'},
                                                        'plan': {'cuts': []}, 'studio': {'tab': 'quick'}})
        self.assertEqual(status, 201)
        self.assertEqual(saved['revision'], 'revision-001')
        native = json.loads(Path(saved['project']).read_text())
        self.assertEqual(native['source']['path'], imported['path'])
        self.assertEqual(native['appVersion'], '0.10.1')
        self.assertTrue(native['overrides']['0']['lockedCuts'][0]['unknownNativeField']['kept'])
        status, config_body, _headers = self.server.request('/api/config')
        self.assertEqual(status, 200)
        refreshed = json.loads(config_body)
        self.assertEqual(refreshed['project']['style'], 'noir')
        self.assertTrue(refreshed['project']['customNativeSetting']['kept'])
        self.assertEqual(refreshed['direction']['profile'], 'noir-groove')
        status, saved2 = self.json_request('/api/save', {'project': project})
        self.assertEqual(status, 201)
        self.assertEqual(saved2['revision'], 'revision-002')
        status, _body, _headers = self.server.request('/api/save', method='POST', body=b'{"project":NaN}', content_type='application/json')
        self.assertEqual(status, 422)
        project['source']['sha256'] = '0' * 64
        status, rejected = self.json_request('/api/save', {'project': project})
        self.assertEqual(status, 422)
        self.assertIn('해시', rejected['error'])
        status, body, _headers = self.server.request('/api/status')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['saves'], 2)

    def test_no_overwrite_output(self):
        self.server.stop()
        command = [sys.executable, str(SCRIPT), '--out', str(self.root / 'output'),
                   '--jizura-root', str(self.root / 'jizura')]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('새 폴더', result.stderr)

    def test_font_import_reopen_and_manifest_round_trip(self):
        initial = json.loads(self.server.request('/api/config')[1])
        source = {'sha256': initial['audio']['sha256']}
        bad_status, _body, _headers = self.server.request(
            '/api/import-font', method='POST', body=b'not-a-font', content_type='application/octet-stream',
            headers={'X-Font-Key': 'user_title', 'X-File-Name': quote('title.ttf')})
        self.assertEqual(bad_status, 422)
        self.assertEqual(self.server.request('/api/font/user_title')[0], 404)
        status, body, _headers = self.server.request(
            '/api/import-font', method='POST', body=b'\x00\x01\x00\x00small-test-font', content_type='application/octet-stream',
            headers={'X-Font-Key': 'user_title', 'X-File-Name': quote('title.ttf')})
        self.assertEqual(status, 201)
        font = json.loads(body)['font']
        before = Path(font['path']).read_bytes()
        bad_status, _body, _headers = self.server.request(
            '/api/import-font', method='POST', body=b'wrong', content_type='application/octet-stream',
            headers={'X-Font-Key': 'user_title', 'X-File-Name': quote('title.ttf')})
        self.assertEqual(bad_status, 422)
        self.assertEqual(self.server.request('/api/font/user_title')[0], 200)
        self.assertEqual(Path(font['path']).read_bytes(), before)
        project = {'lyrics': '텍스트', 'source': source, 'userFonts': [{'key': 'user_title', 'label': 'Title', 'family': 'Title', 'weight': 400}],
                   'fontAssets': [{'key': 'user_title', 'name': 'title.ttf', 'path': '/not/read', 'sha256': '0' * 64}]}
        status, saved = self.json_request('/api/save', {'project': project})
        self.assertEqual(status, 201)
        written = json.loads(Path(saved['project']).read_text())
        self.assertEqual(written['fontAssets'], [{key: font[key] for key in ('key', 'name', 'path', 'sha256')}])
        self.server.stop()
        reopened = StudioServer(self.root / 'reopened', project=Path(saved['project']))
        self.server = reopened
        config = json.loads(reopened.request('/api/config')[1])
        self.assertEqual(len(config['fonts']), 1)
        self.assertEqual(config['fonts'][0]['key'], 'user_title')
        self.assertEqual(reopened.request('/api/font/user_title')[0], 200)
        self.server.stop()
        warned_project = self.root / 'warning-project.json'
        invalid = dict(written)
        invalid['fontAssets'] = [{**written['fontAssets'][0], 'sha256': '0' * 64}]
        warned_project.write_text(json.dumps(invalid), encoding='utf-8')
        self.server = StudioServer(self.root / 'warning', project=warned_project)
        warning_config = json.loads(self.server.request('/api/config')[1])
        self.assertEqual(warning_config['fonts'], [])
        self.assertTrue(warning_config['fontWarnings'])

    def test_invalid_project_does_not_claim_output_path(self):
        self.server.stop()
        invalid = self.root / 'invalid.json'
        invalid.write_text('{', encoding='utf-8')
        output = self.root / 'invalid-output'
        command = [sys.executable, str(SCRIPT), '--out', str(output), '--project', str(invalid),
                   '--jizura-root', str(self.root / 'jizura')]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
