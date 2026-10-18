import hashlib
import http.client
import json
import os
import time
from unittest.mock import patch
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from html_design import ASSET_ROOT, FONT_FILES, apply_design, css_text, add_navigation, live_studio_url, valid_studio_url, open_page
from studio import Session, init_project, make_handler


class HTMLDesignTests(unittest.TestCase):
    def test_user_font_bytes_and_weights(self):
        source = json.loads((ASSET_ROOT / 'source.json').read_text())
        self.assertEqual(len(FONT_FILES), 9)
        for item in source['files']:
            self.assertEqual(hashlib.sha256((ASSET_ROOT / 'fonts' / item['file']).read_bytes()).hexdigest(), item['sha256'])
        for weight in range(100, 1000, 100):
            self.assertIn(f'font-weight:{weight};', css_text())

    def test_standalone_html_carries_usable_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'review.html'
            page = apply_design('<html lang="ko"><head><style>h1{margin:0}</style></head><body>검수</body></html>', output)
            self.assertIn('data-road-music-ui', page)
            self.assertIn('road-music-design/styles.css', page)
            self.assertTrue((output.parent / 'road-music-design/fonts/Paperlogy-4Regular.ttf').is_file())
            self.assertIn('url("fonts/Paperlogy-4Regular.ttf")', (output.parent / 'road-music-design/styles.css').read_text())

    def test_css_font_urls_escape_session_token(self):
        css = css_text('/design/fonts/', 'a"b')
        self.assertIn('Paperlogy-4Regular.ttf?token=a%22b', css)
        self.assertNotIn('token=a"b', css)

    def test_materialized_template_replaces_source_design_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'index.html'
            template = '<html><head><link data-road-music-design rel="stylesheet" href="../../source/fonts.css"><link data-road-music-design rel="stylesheet" href="../../source/design.css"></head><body>영상</body></html>'
            page = apply_design(template, target, ui=False)
            self.assertNotIn('../../source/', page)
            self.assertEqual(page.count('data-road-music-design'), 1)
            self.assertEqual(apply_design(page, target, ui=False), page)

    def test_ego_page_open_reuses_current_space_without_reloading_same_url(self):
        url='http://127.0.0.1:12345/?token='+'x'*32
        with patch.dict(os.environ,{'ROADMUSIC_EGO_TASK_SPACE':'18'}), patch('html_design.subprocess.run') as run:
            run.return_value.returncode=0
            self.assertTrue(open_page(url))
            args=run.call_args.args[0]
            self.assertEqual(args[:3],['ego-browser','nodejs','-e'])
            self.assertIn('taskSpace(18)',args[3])
            self.assertIn('page.url()!==url',args[3])
            self.assertNotIn('newPage',args[3])
            self.assertNotIn('claimTaskSpace',args[3])
            self.assertEqual(run.call_args.kwargs['timeout'],20)
        with patch.dict(os.environ, {}, clear=True), patch('html_design.subprocess.run') as run:
            run.return_value.returncode=0
            self.assertTrue(open_page(url))
            self.assertIn('const name="Road Music 제작실"',run.call_args.args[0][3])
            self.assertIn('await taskSpace(name)',run.call_args.args[0][3])
            self.assertIn('const reuse=true',run.call_args.args[0][3])
            self.assertIn('existing.createdBy!=="agent"',run.call_args.args[0][3])
            self.assertIn('item.createdBy==="agent"',run.call_args.args[0][3])
            self.assertIn('Showreel 플레이리스트 프리셋',run.call_args.args[0][3])
            self.assertIn('Showreel 스타일 선택',run.call_args.args[0][3])
            self.assertIn('JIZURA 가사 가독성 검수',run.call_args.args[0][3])
            self.assertIn('file:\\/\\/.*\\/review\\.html',run.call_args.args[0][3])
            self.assertIn('if(!reuse)throw new Error',run.call_args.args[0][3])
        with patch.dict(os.environ, {'ROADMUSIC_EGO_REUSE_ROAD_MUSIC_PAGE':'0'}, clear=True), patch('html_design.subprocess.run') as run:
            run.return_value.returncode=0
            self.assertTrue(open_page(url))
            self.assertIn('const reuse=false',run.call_args.args[0][3])
            self.assertIn('claimTaskSpace(existing.id)',run.call_args.args[0][3])
            self.assertIn('pickRoadMusicTab=async task',run.call_args.args[0][3])
            self.assertIn('task.adopt(tab.page,{as:"p1"})',run.call_args.args[0][3])
        with patch.dict(os.environ, {'ROADMUSIC_STUDIO_BROWSER':'system'}, clear=True), patch('html_design.webbrowser.open', return_value=True) as system:
            self.assertTrue(open_page(url))
            system.assert_called_once_with(url)
        with self.assertRaises(ValueError):open_page('https://example.com/')

    def test_navigation_uses_only_live_loopback_session_and_is_idempotent(self):
        url = 'http://127.0.0.1:41234/?token=' + 'test_token_' * 3
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': folder}):
            record = Path(folder) / 'video-studio-session.json'
            record.write_text(json.dumps({'schemaVersion': 1, 'url': url, 'expiresAt': time.time()+60}))
            self.assertEqual(live_studio_url(), url)
            page = add_navigation('<html><body><main>문서</main></body></html>', current='catalog')
            self.assertIn('/catalog/?token=', page)
            self.assertIn('#deliverables', page)
            self.assertIn('aria-current="page">스타일 둘러보기', page)
            self.assertEqual(add_navigation(page, current='catalog'), page)
            record.write_text(json.dumps({'schemaVersion': 1, 'url': url, 'expiresAt': time.time()-1}))
            self.assertIsNone(live_studio_url())
        self.assertTrue(valid_studio_url('http://127.0.0.1:41234/catalog/?token=' + 'a'*32))
        for bad in ('https://example.com/', 'http://127.0.0.1:99999/?token='+'a'*32, 'http://user@127.0.0.1:1000/?token='+'a'*32):
            self.assertFalse(valid_studio_url(bad))

    def test_video_materialization_has_no_navigation_overlay(self):
        with tempfile.TemporaryDirectory() as folder:
            page=apply_design('<html><body><main>장면</main></body></html>',Path(folder)/'video.html',ui=False)
            self.assertNotIn('data-road-music-nav',page)

    def test_server_font_auth_and_content(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'desk'
            init_project(project, mode='jizura')
            session = Session(project, review=True)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(session))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def get(path):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port)
                client.request('GET', path)
                response = client.getresponse()
                status, headers, data = response.status, dict(response.getheaders()), response.read()
                client.close()
                return status, headers, data
            try:
                self.assertEqual(get('/design.css')[0], 403)
                token = '?token=' + session.token
                status, headers, data = get('/design.css' + token)
                self.assertEqual(status, 200)
                self.assertIn(b'/design/fonts/Paperlogy-4Regular.ttf?token=', data)
                status, headers, data = get('/design/fonts/Paperlogy-4Regular.ttf' + token)
                self.assertEqual(status, 200)
                self.assertEqual(data, (ASSET_ROOT / 'fonts/Paperlogy-4Regular.ttf').read_bytes())
                self.assertEqual(get('/design/fonts/not-a-font.ttf' + token)[0], 404)
                status, headers, data = get('/' + token)
                self.assertIn("font-src 'self'", headers['Content-Security-Policy'])
                self.assertNotIn(b'__DESIGN_TOKEN__', data)
                self.assertIn(b'data-road-music-nav',data)
                status, headers, data=get('/catalog/'+token)
                self.assertEqual(status,200)
                self.assertIn(b'/media/preview-',data)
                self.assertIn(('/?token='+session.token+'#deliverables').encode(),data)
                self.assertNotIn(b'src="presets/',data)
                self.assertEqual(get('/catalog/')[0],403)
                state=json.loads(get('/api/state'+token)[2])
                self.assertEqual(state['application'],'road-music-video-studio')
                self.assertEqual(state['project'],str(project.resolve()))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
