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
from ui_icons import ICON_NAMES, icon, inject_icon_library


class HTMLDesignTests(unittest.TestCase):
    def test_css_selector_does_not_replace_the_html_ui_attribute(self):
        import re
        import subprocess
        source = '<html lang="ko"><head><style>html[data-road-music-ui] button{color:black}</style></head><body><main>필터</main></body></html>'
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'catalog.html'
            page = apply_design(source, target, navigation_home=False)
            self.assertRegex(page, r'<html\b[^>]*\sdata-road-music-ui[\s>]')
            video = apply_design(source, target, ui=False)
            self.assertNotRegex(video, r'<html\b[^>]*\sdata-road-music-ui[\s>]')
            script = "import {applyDesign} from " + json.dumps((Path(__file__).parent / 'html-design.mjs').resolve().as_uri()) + "; console.log(await applyDesign(" + json.dumps(source) + "," + json.dumps(str(target)) + "));"
            result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertRegex(result.stdout, r'<html\b[^>]*\sdata-road-music-ui[\s>]')

    def test_shared_ui_contract_hides_inactive_controls_and_groups_records(self):
        from html.parser import HTMLParser
        class Menus(HTMLParser):
            def __init__(self): super().__init__(); self.nav = False; self.links = []
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == 'nav' and values.get('class') == 'work-subnav': self.nav = True
                if self.nav and tag == 'a': self.links.append(values['href'])
            def handle_endtag(self, tag):
                if tag == 'nav': self.nav = False
        page = (ASSET_ROOT.parent / 'work-detail.html').read_text()
        menus = Menus(); menus.feed(page)
        self.assertEqual(len(menus.links), 6)
        self.assertEqual(menus.links[-1], '#work-records')
        self.assertIn('id="workProductionHost"', page)
        for name in ('work-versions', 'work-changes', 'work-review'):
            self.assertIn('<details id="' + name + '"', page)
        css = css_text()
        self.assertIn('[hidden] { display: none !important; }', css)
        self.assertIn('.work-record-links', css)
        self.assertNotIn('--rm-text-muted', (ASSET_ROOT.parent / 'storage.html').read_text())
        self.assertNotIn('prefers-color-scheme:dark', (ASSET_ROOT.parent / 'storage.html').read_text())

    def test_python_and_node_navigation_share_labels_icons_and_order(self):
        import subprocess
        import re
        from html_design import navigation_html
        url = 'http://127.0.0.1:41234/?token=' + 'x' * 32
        source = "import { addNavigation, icon } from " + json.dumps((Path(__file__).parent / 'html-design.mjs').resolve().as_uri()) + "; console.log(await addNavigation('<html><body><main>본문</main></body></html>',{current:'works',homeURL:" + json.dumps(url) + "})); console.error(icon('heart'));"
        result = subprocess.run(['node', '--input-type=module', '-e', source], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = re.search(r'<nav.*?</nav>', result.stdout).group(0)
        self.assertEqual(actual, navigation_html(current='works', home_url=url))
        self.assertIn('rm-icon-heart', result.stderr)

    def test_existing_portable_guide_link_is_rebased_for_a_live_page(self):
        page = '<html><body><main><div class="rm-guide-tools" data-rm-guide-tools><a href="road-music-design/guides/styles.html">이 화면 사용법</a></div></main></body></html>'
        url = 'http://127.0.0.1:41234/?token=' + 'x' * 32
        actual = add_navigation(page, current='catalog', home_url=url)
        self.assertIn('http://127.0.0.1:41234/guide/styles/?token=', actual)
        self.assertNotIn('href="road-music-design/guides/styles.html"', actual)
        self.assertEqual(actual.count('class="rm-guide-tools"'), 1)
        self.assertEqual(add_navigation(actual, current='catalog', home_url=url), actual)
    def test_official_icon_subset_is_local_label_safe_and_idempotent(self):
        import xml.etree.ElementTree as ET
        sprite = ET.parse(ASSET_ROOT / 'heroicons.svg').getroot()
        names = {item.attrib['id'].removeprefix('rm-icon-') for item in sprite}
        self.assertEqual(names, ICON_NAMES)
        source = json.loads((ASSET_ROOT / 'heroicons-source.json').read_text())
        self.assertEqual(source['license'], 'MIT')
        self.assertTrue((ASSET_ROOT / source['licenseFile']).is_file())
        page = inject_icon_library('<html><body>본문</body></html>')
        self.assertEqual(inject_icon_library(page), page)
        self.assertEqual(page.count('id="rm-icon-library"'), 1)
        self.assertIn('aria-hidden="true"', icon('musical-note'))
        for name in ('script', '../private', 'film" onload="bad'):
            with self.assertRaises(ValueError):
                icon(name)
    def test_skip_link_precedes_navigation_and_targets_main(self):
        for source in ('<body><a class="skip-link" href="#content">건너뛰기</a><main id="content">본문</main></body>', '<body><main>본문</main></body>', '<body>본문</body>'):
            page = add_navigation(source, home_url=False)
            self.assertLess(page.index('class="skip-link"'), page.index('data-road-music-nav'))
            self.assertIn('href="#content"' if 'id="content"' in source else 'href="#main-content"', page)
            self.assertEqual(add_navigation(page, home_url=False), page)

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
            self.assertIn('/works/?token=', page)
            self.assertNotIn('/review/?token=', page)
            self.assertIn('/guide/?token=', page)
            self.assertNotIn('#deliverables', page)
            self.assertRegex(page, r'aria-current="page">.*?스타일.*?</a>')
            self.assertIn('id="rm-icon-library"', page)
            self.assertEqual(page.count('id="rm-icon-library"'), 1)
            self.assertEqual(add_navigation(page, current='catalog'), page)
            record.write_text(json.dumps({'schemaVersion': 1, 'url': url, 'expiresAt': time.time()-1}))
            self.assertIsNone(live_studio_url())
        self.assertTrue(valid_studio_url('http://127.0.0.1:41234/catalog/?token=' + 'a'*32))
        self.assertTrue(valid_studio_url('http://127.0.0.1:41234/works/'+'b'*64+'/?token='+'a'*32))
        for route in ('storage', 'dashboard', 'status', 'reference', 'recipes', 'ccm'):
            self.assertTrue(valid_studio_url(f'http://127.0.0.1:41234/{route}/?token=' + 'a'*32))
        self.assertTrue(valid_studio_url('http://127.0.0.1:41234/ccm/?token='+'a'*32+'&engine=YuE&tag=%EA%B8%B0%EB%8F%84'))
        self.assertFalse(valid_studio_url('http://127.0.0.1:41234/ccm/?token='+'a'*32+'&engine=OTHER'))
        for bad in ('https://example.com/', 'http://127.0.0.1:99999/?token='+'a'*32, 'http://user@127.0.0.1:1000/?token='+'a'*32):
            self.assertFalse(valid_studio_url(bad))

    def test_video_materialization_has_no_navigation_overlay(self):
        with tempfile.TemporaryDirectory() as folder:
            page=apply_design('<html><body><main>장면</main></body></html>',Path(folder)/'video.html',ui=False)
            self.assertNotIn('data-road-music-nav',page)
            self.assertNotIn('id="rm-icon-library"',page)

    def test_offline_ui_materialization_has_markdown_backed_guides(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'results.html'
            page = apply_design('<html><head></head><body><main>완성 결과</main></body></html>', target, ui=True)
            guides = target.parent / 'road-music-design' / 'guides'
            self.assertIn('data-road-music-nav', page)
            self.assertIn('이 화면 사용법', page)
            self.assertTrue((guides / 'start.md').is_file())
            self.assertTrue((guides / 'start.html').is_file())
            self.assertIn('id="guide-markdown" type="application/json"', (guides / 'start.html').read_text())
            self.assertIn('id="copy-markdown"', (guides / 'start.html').read_text())

    def test_server_font_auth_and_content(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': str(Path(folder) / 'state')}):
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
                self.assertIn(b'poster="/media/poster-',data)
                self.assertNotIn(b'poster="presets/',data)
                for card in session.cards:
                    code, poster_headers, poster = get('/media/poster-' + card['id'] + token)
                    self.assertEqual(code, 200)
                    self.assertIn('image/', poster_headers['Content-Type'])
                    self.assertEqual(poster, card['posterPath'].read_bytes())
                self.assertIn(('/works/?token='+session.token).encode(),data)
                self.assertNotIn(('/review/?token='+session.token).encode(),data)
                self.assertIn(('/guide/?token='+session.token).encode(),data)
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
