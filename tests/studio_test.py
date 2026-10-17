#!/usr/bin/env python3
import http.client
from html.parser import HTMLParser
import io
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unicodedata
import unittest
from urllib.parse import quote

SCRIPT = Path(__file__).resolve().parents[1] / 'skills' / 'road-music-video-studio' / 'scripts' / 'studio.py'
SPEC = importlib.util.spec_from_file_location('video_studio', SCRIPT)
studio = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(studio)


class StudioServerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.song = root / 'song.mp3'
        self.song.write_bytes(b'not-a-real-mp3-but-an-isolated-media-fixture')
        self.project = root / 'project'
        studio.init_project(str(self.project), str(self.song), 'showreel-motion', 'antigravity')
        self.session = studio.Session(str(self.project))
        self.server = studio.ThreadingHTTPServer(('127.0.0.1', 0), studio.make_handler(self.session))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.token = self.session.token

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        headers = headers or {}
        headers.setdefault('Host', f'127.0.0.1:{self.port}')
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response, raw

    def post_json(self, route, value, origin=True):
        raw = json.dumps(value).encode()
        headers = {'Content-Type': 'application/json', 'Content-Length': str(len(raw)), 'X-Studio-Token': self.token}
        if origin:
            headers['Origin'] = f'http://127.0.0.1:{self.port}'
        return self.request('POST', f'{route}?token={self.token}', raw, headers)

    def selection(self):
        return {'host': 'antigravity', 'mode': 'showreel-motion', 'styleId': self.session.cards[0]['id'],
                'display': {'showSpectrum': True, 'showQueue': None, 'showNowPlaying': False, 'channelName': '로드뮤직'}}

    def test_media_range_selection_and_feedback_persist(self):
        self.assertFalse(self.session.state()['hasSavedSelection'])
        response, raw = self.request('GET', f'/media/music?token={self.token}', headers={'Range': 'bytes=0-3'})
        self.assertEqual(response.status, 206)
        self.assertEqual(raw, b'not-')
        response, raw = self.post_json('/api/selection', self.selection())
        self.assertEqual(response.status, 201, raw)
        self.assertTrue(self.session.done.wait(.2))
        self.assertTrue(self.session.state()['hasSavedSelection'])
        saved = json.loads((self.project / 'selection.json').read_text())
        self.assertEqual(saved['host'], 'antigravity')
        self.assertTrue(saved['display']['showSpectrum'])
        self.assertIsNone(saved['display']['showQueue'])
        showreel = json.loads((self.project / 'showreel-request.json').read_text())
        self.assertEqual(set(showreel), {'schemaVersion', 'styleId', 'display', 'music'})
        self.assertFalse(showreel['display']['showQueue'])
        response, raw = self.post_json('/api/feedback', {'status': 'needs-revision', 'note': '인트로를 조금 짧게'})
        self.assertEqual(response.status, 201, raw)
        self.assertEqual(json.loads((self.project / 'feedback.json').read_text())['status'], 'needs-revision')

    def test_host_origin_and_media_path_bounds(self):
        response, _ = self.request('GET', f'/?token={self.token}', headers={'Host': 'localhost:1'})
        self.assertEqual(response.status, 421)
        response, _ = self.request('GET', f'/media/../../etc/passwd?token={self.token}')
        self.assertEqual(response.status, 404)
        response, _ = self.post_json('/api/selection', self.selection(), origin=False)
        self.assertEqual(response.status, 403)

    def test_served_html_inline_scripts_parse(self):
        response, raw = self.request('GET', f'/?token={self.token}')
        self.assertEqual(response.status, 200)
        scripts = re.findall(r'<script>(.*?)</script>', raw.decode('utf-8'), re.DOTALL)
        self.assertEqual(len(scripts), 2)
        for script in scripts:
            checked = subprocess.run(['node', '--check', '-'], input=script, text=True, capture_output=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_explicit_skip_survives_draft_mode_change(self):
        template = (SCRIPT.parent.parent / 'assets' / 'studio.html').read_text()
        source = re.findall(r'<script>(.*?)</script>', template, re.DOTALL)[-1]
        script = 'const source=' + json.dumps(source) + ';\n' + r'''
const vm = require('node:vm');
const elements = new Map(), selected = new Map();
const get = selector => {
  if (!selector.startsWith('#')) return selected.get(selector) || null;
  if (!elements.has(selector)) elements.set(selector, {value:'', checked:false, dataset:{}, classList:{toggle(){},add(){},remove(){}}});
  return elements.get(selector);
};
const context = vm.createContext({window:{__STUDIO_BOOTSTRAP__:{token:'test'}}, document:{querySelector:get,querySelectorAll:()=>[],addEventListener(){}}, fetch:()=>new Promise(()=>{}),structuredClone});
let musicHTML='', musicWrites=0;
Object.defineProperty(get('#music'),'innerHTML',{get:()=>musicHTML,set:value=>{musicHTML=value;musicWrites++}});
vm.runInContext(source, context);
vm.runInContext("state={host:'codex',mode:'showreel-cd',hasSavedSelection:false,selection:{styleId:null,display:{showSpectrum:null,showQueue:null,showNowPlaying:null,channelName:null}},feedback:{},modes:[],styles:[],samples:{},media:{music:{name:'song.mp3',url:'/media/music',sha256:'first'},review:{}}};draft=startDraft(state);render()",context);
const initial = get('#display').innerHTML;
for (const key of ['showSpectrum','showQueue','showNowPlaying']) selected.set(`input[name=${key}]:checked`, {value:'skip'});
get('#channelSkip').checked=true;
vm.runInContext("capture();draft.mode='showreel-mv';render()",context);
const changed=get('#display').innerHTML, musicWritesAfterMode=musicWrites;
vm.runInContext("state.media.music.sha256='replacement';render()",context);
console.log(JSON.stringify({initial,changed,musicWritesAfterMode,musicWritesAfterSourceChange:musicWrites}));
'''
        checked = subprocess.run(['node', '-e', script], text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        rendered = json.loads(checked.stdout)

        class Inputs(HTMLParser):
            def __init__(self, markup):
                super().__init__()
                self.checked = []
                self.feed(markup)

            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == 'input' and 'checked' in values:
                    self.checked.append(values)

        self.assertEqual(Inputs(rendered['initial']).checked, [])
        controls = Inputs(rendered['changed']).checked
        self.assertEqual({item.get('name') for item in controls if item.get('type') == 'radio'},
                         {'showSpectrum', 'showQueue', 'showNowPlaying'})
        self.assertTrue(all(item.get('value') == 'skip' for item in controls if item.get('type') == 'radio'))
        self.assertTrue(any(item.get('id') == 'channelSkip' for item in controls))
        self.assertEqual(rendered['musicWritesAfterMode'], 1)
        self.assertEqual(rendered['musicWritesAfterSourceChange'], 2)

    def test_music_identity_changes_even_when_replacement_filename_is_identical(self):
        initial = self.session.state()['media']['music']
        self.assertEqual(initial['sha256'], studio.sha256(self.song))
        replacement = Path(self.temp.name) / 'replacement.mp3'
        replacement.write_bytes(b'new-song-with-the-same-display-name')
        self.session.set_music(replacement, external=True, name=self.song.name)
        changed = self.session.state()['media']['music']
        self.assertEqual(changed['name'], initial['name'])
        self.assertEqual(changed['url'], initial['url'])
        self.assertNotEqual(changed['sha256'], initial['sha256'])

    def test_template_escapes_special_filename_characters_in_attributes(self):
        template = (SCRIPT.parent.parent / 'assets' / 'studio.html').read_text()
        function = re.search(r'function esc\(s\)\{[^\n]+\}', template)
        self.assertIsNotNone(function)
        special = '" onload="bad&<tag>\''
        expected = '&quot; onload=&quot;bad&amp;&lt;tag&gt;&#39;'
        script = f'{function.group(0)}\nif (esc({json.dumps(special)}) !== {json.dumps(expected)}) process.exit(1);'
        checked = subprocess.run(['node', '-e', script], text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn('최근 제작 샘플', template)
        self.assertIn('프리셋 구조 참고', template)

    def test_publish_refreshes_existing_session_and_marks_source(self):
        video = Path(self.temp.name) / 'final.mp4'
        video.write_bytes(b'video-fixture')
        manifest = Path(self.temp.name) / 'publish.json'
        manifest.write_text(json.dumps({'title': '새 검수 제목', 'sourceMusicSha256': studio.sha256(self.song), 'video': str(video)}))
        result = studio.publish(str(self.project), str(manifest))
        self.assertEqual(result['status'], 'published')
        state = self.session.state()
        self.assertEqual(state['projectName'], '새 검수 제목')
        self.assertEqual(state['media']['review']['videos'][0]['name'], 'final.mp4')
        self.assertEqual(state['media']['review']['videos'][0]['sourceStatus'], 'current')
        replacement = Path(self.temp.name) / 'replacement.mp3'
        replacement.write_bytes(b'another-song')
        self.session.set_music(replacement, external=True)
        self.assertEqual(self.session.state()['media']['review']['videos'][0]['sourceStatus'], 'different-source')

    def test_all_supported_hosts_round_trip(self):
        for host in ('codex', 'antigravity', 'antigravity-cli'):
            self.assertEqual(studio.Session(str(self.project), host=host).state()['host'], host)
            self.assertEqual(json.loads((self.project / 'selection.json').read_text())['host'], host)

    def test_skip_retains_saved_display_values_when_switching_modes(self):
        previous = self.selection()
        previous['display'] = {'showSpectrum': True, 'showQueue': False, 'showNowPlaying': True, 'channelName': '내 채널'}
        self.session.save_selection(previous)
        changed = {'host': 'antigravity-cli', 'mode': 'showreel-mv', 'styleId': None,
                   'display': {key: None for key in previous['display']}}
        self.session.save_selection(changed)
        reopened = studio.Session(str(self.project)).state()
        self.assertEqual(reopened['mode'], 'showreel-mv')
        self.assertEqual(reopened['selection']['display'], previous['display'])
        self.assertEqual(reopened['imagePolicy'], {'provider': 'antigravity-native', 'allowPaidModels': False})

    def test_mv_and_jizura_cannot_be_coerced_to_cd_preset(self):
        value = self.selection()
        value['mode'] = 'showreel-mv'
        with self.assertRaisesRegex(ValueError, 'CD 프리셋'):
            studio.validate_selection(value, self.session.selection)

    def test_cd_cards_exclude_motion_only_preset_and_backend_rejects_it(self):
        styles = self.session.state()['styles']
        self.assertEqual(len(styles), 7)
        self.assertEqual(len([item for item in styles if item['category'] in {'cd', 'rhythm-cd'}]), 6)
        value = self.selection()
        value['mode'] = 'showreel-cd'
        value['styleId'] = 'rhythm-canvas'
        with self.assertRaisesRegex(ValueError, 'CD 프리셋'):
            self.session.save_selection(value)

    def test_registered_example_media_is_served_and_unregistered_sample_is_denied(self):
        examples_root = Path(self.temp.name) / 'examples-root'
        examples_root.mkdir()
        video, poster = examples_root / 'sample.mp4', examples_root / 'sample.jpg'
        video.write_bytes(b'example-video')
        poster.write_bytes(b'example-poster')
        manifest = Path(self.temp.name) / 'examples.json'
        manifest.write_text(json.dumps([{
            'mode': 'showreel-mv', 'title': 'MV 예시', 'summary': '예시 설명', 'tags': ['리듬'],
            'video': 'sample.mp4', 'poster': 'sample.jpg', 'audioNote': '다른 곡 예시', 'provenance': '검증된 로컬 결과',
        }]))
        self.session.samples = {item['mode']: item for item in studio.example_cards(manifest, examples_root)}
        response, raw = self.request('GET', f'/media/sample-showreel-mv?token={self.token}', headers={'Range': 'bytes=0-6'})
        self.assertEqual((response.status, raw), (206, b'example'))
        response, _ = self.request('GET', f'/media/sample-jizura?token={self.token}')
        self.assertEqual(response.status, 404)

    def test_release_examples_register_all_four_modes(self):
        examples = studio.example_cards()
        self.assertEqual({item['mode'] for item in examples}, set(studio.MODES))
        self.assertEqual(len(examples), 4)

    def test_empty_init_can_accept_browser_upload(self):
        empty = Path(self.temp.name) / 'empty-project'
        result = studio.init_project(str(empty), None, 'showreel-motion', 'codex')
        self.assertIsNone(result['music'])
        self.assertEqual(json.loads((empty / 'studio-project.json').read_text())['media'], [])
        blank = studio.Session(str(empty))
        uploaded = blank.upload_music('chosen.mp3', io.BytesIO(b'uploaded-audio'), len(b'uploaded-audio'))
        self.assertEqual(uploaded['name'], 'chosen.mp3')
        self.assertEqual(blank.state()['media']['music']['name'], 'chosen.mp3')
        self.assertEqual(json.loads((empty / 'studio-project.json').read_text())['imagePolicy'], {'provider': 'image_gen', 'allowPaidModels': False})

    def test_urlencoded_korean_nfd_filename_upload_is_decoded_before_length_check(self):
        filename = unicodedata.normalize('NFD', '아직 나의 봄.mp3')
        body = b'korean-nfd-upload'
        headers = {
            'Content-Type': 'application/octet-stream', 'Content-Length': str(len(body)),
            'Origin': f'http://127.0.0.1:{self.port}', 'X-Studio-Token': self.token,
            'X-File-Name': quote(filename, safe=''),
        }
        response, raw = self.request('POST', f'/api/music?token={self.token}', body, headers)
        self.assertEqual(response.status, 201, raw)
        self.assertEqual(json.loads(raw)['name'], filename)
        registered = self.session.state()['media']['music']['name']
        self.assertEqual(registered, filename)

    def test_review_session_finishes_only_on_complete_endpoint(self):
        review = studio.Session(str(self.project), review=True)
        server = studio.ThreadingHTTPServer(('127.0.0.1', 0), studio.make_handler(review))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port, token = server.server_port, review.token
            raw = json.dumps(self.selection()).encode()
            headers = {'Host': f'127.0.0.1:{port}', 'Origin': f'http://127.0.0.1:{port}', 'X-Studio-Token': token,
                       'Content-Type': 'application/json', 'Content-Length': str(len(raw))}
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
            connection.request('POST', f'/api/selection?token={token}', raw, headers)
            self.assertEqual(connection.getresponse().status, 201)
            connection.close()
            self.assertFalse(review.done.wait(.1))
            headers['Content-Length'] = '2'
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
            connection.request('POST', f'/api/complete?token={token}', b'{}', headers)
            self.assertEqual(connection.getresponse().status, 200)
            connection.close()
            self.assertTrue(review.done.wait(.2))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == '__main__':
    unittest.main()
