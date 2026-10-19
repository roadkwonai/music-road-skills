import re
import json
import http.client
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from guide_content import GUIDE_SLUGS, filter_model_sections, guide_for_engine, guide_media_file, markdown_source, materialize_guides_assets, render_guide, render_markdown
from studio import Session, init_project, make_handler


class GuideContentTests(unittest.TestCase):
    def test_procedure_and_reference_cards_keep_native_lists_and_escape_content(self):
        rendered = render_markdown('1. **원음** 확인\n2. <script>실행 금지</script>\n\n- **원가사**: 승인된 <원문>\n- **자막**: [검수](review.md)에서 확인\n\n- 일반 설명\n- 다른 설명')
        self.assertIn('<ol class="guide-steps">', rendered)
        self.assertIn('<ul class="guide-reference-list" role="list">', rendered)
        self.assertIn('<strong class="guide-term-name">원가사</strong>', rendered)
        self.assertIn('<span class="guide-term-description">승인된 &lt;원문&gt;</span>', rendered)
        self.assertIn('/guide/review/', rendered)
        self.assertIn('<ul><li>일반 설명</li><li>다른 설명</li></ul>', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertEqual(rendered.count('<li>'), 6)

    def test_mixed_and_single_lists_do_not_become_reference_cards(self):
        for source in ('- **명칭**: 설명\n- 일반 설명', '- **명칭**: 한 항목', '1. 한 단계'):
            self.assertNotIn('guide-reference-list', render_markdown(source))
            self.assertNotIn('guide-steps', render_markdown(source))

    def test_semantic_notices_are_labelled_escaped_and_separate_from_code(self):
        rendered = render_markdown('> [!WARNING]\n> **원음** 확인 <script>bad</script>\n\n## 다음\n\n```text\n> [!CAUTION]\n```')
        self.assertIn('class="rm-callout rm-callout--warning"', rendered)
        self.assertIn('aria-label="주의"', rendered)
        self.assertIn('rm-icon-exclamation-triangle', rendered)
        self.assertIn('<strong>원음</strong>', rendered)
        self.assertNotIn('<script>bad', rendered)
        self.assertEqual(rendered.count('<aside'), 1)
        self.assertIn('id="다음"', rendered)

    def test_all_diagrams_have_semantic_structures_and_official_icons(self):
        from guide_diagrams import render_diagram
        expected = {'production-flow.svg': 'rm-diagram-flow', 'work-map.svg': 'rm-diagram-map',
                    'sync-review.svg': 'rm-diagram-branches', 'style-energy.svg': 'rm-diagram-energy',
                    'display-choices.svg': 'rm-diagram-options', 'lyrics-vs-captions.svg': 'rm-diagram-text-files',
                    'delivery-map.svg': 'rm-diagram-map'}
        for name, marker in expected.items():
            self.assertIn(marker, render_diagram(name))
        self.assertIn('#rm-icon-musical-note', render_diagram('production-flow.svg'))
        with self.assertRaises(ValueError):
            render_diagram('unknown.svg')
    def test_examples_have_individual_copy_and_ignore_code_headings(self):
        source = '## 실제 제목\n\n```prompt\n## 프롬프트 내부 제목\n원가사 <유지> & "확인"\n```\n\n## 실제 제목\n\n```bash\nprintf safe\n```'
        rendered = render_markdown(source)
        self.assertEqual(rendered.count('data-copy-example='), 2)
        self.assertIn('id="guide-example-1"', rendered)
        self.assertIn('id="guide-example-2"', rendered)
        self.assertIn('프롬프트 복사', rendered)
        self.assertIn('명령 복사', rendered)
        self.assertIn('원가사 &lt;유지&gt; &amp; "확인"', rendered)
        self.assertIn('id="실제-제목-2"', rendered)
        self.assertNotIn('id="프롬프트-내부-제목"', rendered)

    def test_only_bundled_images_render_with_captions_and_zoom(self):
        page = render_markdown('![제작 흐름](media/production-flow.svg)', token='test-token')
        self.assertIn('<figure', page)
        self.assertIn('/guide-media/production-flow.svg?token=test-token', page)
        self.assertIn('alt="제작 흐름"', page)
        self.assertIn('<figcaption>', page)
        self.assertIn('SVG 도식 원본 보기', page)
        self.assertIn('class="rm-diagram-flow"', page)
        self.assertEqual(page.count('class="rm-diagram-index"'), 5)
        for source in ('![외부](https://example.com/tracker.png)', '![경로](media/../../secret.png)', '![실행](data:image/svg+xml,bad)', '![누락](media/missing.png)'):
            self.assertNotIn('<img', render_markdown(source))
        for name in ('../secret.png', 'missing.png', 'production-flow.svg/extra', '%2e%2e%2fsecret.png'):
            with self.assertRaises(ValueError):
                guide_media_file(name)

    def test_knowledge_tables_and_safe_anchors_preserve_code_examples(self):
        source = '<a id="purpose"></a>\n\n| 용도 | 요청 |\n| --- | --- |\n| 기도 | `<script>` |\n\n```text\n| 이 줄은 프롬프트 |\n```'
        page = render_markdown(source)
        self.assertIn('<th scope="col">용도</th>', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('id="purpose"', page)
        self.assertIn('| 이 줄은 프롬프트 |', page)
        self.assertEqual(page.count('<table>'), 1)
        self.assertNotIn('<script>', page)

    def test_ccm_and_recipe_navigation_preserves_live_auth_and_portable_guides(self):
        page = render_markdown('[CCM](/ccm/) [조합](/recipes/) [명령](/reference/)', token='session-test')
        self.assertIn('/ccm/?token=session-test', page)
        self.assertIn('/recipes/?token=session-test', page)
        self.assertIn('/reference/?token=session-test', page)
        portable = render_markdown('[CCM](/ccm/) [조합](/recipes/)', static=True)
        self.assertIn('ccm.html', portable)
        self.assertIn('reference.html', portable)

    def test_all_guides_have_images_and_usable_examples(self):
        for slug in GUIDE_SLUGS:
            source = markdown_source(slug)
            visible_source = markdown_source(slug, engine='YuE')
            if slug not in {'ccm-library', 'ccm-advanced', 'yue-advanced'}:
                self.assertNotRegex(source, r'(?m)^\|', f'{slug}: 가이드는 지원되는 목록 문법으로 작성합니다')
            pictures = re.findall(r'!\[[^\]]+\]\(media/([^\s)]+)\)', source)
            self.assertTrue(pictures, slug)
            for name in pictures:
                self.assertTrue(guide_media_file(name).is_file(), (slug, name))
            examples = re.findall(r'```([a-zA-Z0-9_-]*)\n(.*?)\n```', visible_source, re.S)
            self.assertTrue(examples, slug)
            page = render_guide(slug, token='test-token')
            self.assertEqual(page.count('data-copy-example='), len(examples), slug)
            code = re.findall(r'<code id="guide-example-\d+">(.*?)</code>', page, re.S)
            import html
            self.assertEqual([html.unescape(value) for value in code], [value for _, value in examples], slug)
            for language, value in examples:
                if language == 'json':
                    json.loads(value)

    def test_model_filter_keeps_common_and_only_the_selected_heading_scope(self):
        source = '''# 공통 제목

## 공통 시작
공통 본문

## ACE 모델 설정
ACE 본문

### ACE 예시
ACE 전용 예시

### 공통 소제목
공통으로 다시 보입니다.

## YuE 모델 설정
YuE 본문

### YuE 예시
YuE 전용 예시

## 공통 마침
공통 마침
'''
        self.assertNotIn('ACE 본문', filter_model_sections(source, 'YuE'))
        self.assertIn('YuE 전용 예시', filter_model_sections(source, 'YuE'))
        self.assertNotIn('YuE 본문', filter_model_sections(source, 'ACE'))
        self.assertIn('ACE 전용 예시', filter_model_sections(source, 'ACE'))
        self.assertIn('공통으로 다시 보입니다.', filter_model_sections(source, 'ACE'))
        self.assertIn('공통 마침', filter_model_sections(source, 'YuE'))
        self.assertTrue(filter_model_sections(source.replace('# 공통 제목', '# ACE·YuE CCM 가이드'), 'YuE').startswith('# YuE CCM 가이드'))
        with self.assertRaises(ValueError):
            filter_model_sections(source, 'other')

    def test_model_specific_page_separates_toc_copy_download_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'guides'; root.mkdir()
            source = '''# 테스트 가이드

## 공통 절
공통 설명 [다음](results.md)

## ACE 모델 절
```prompt
ACE 전용 프롬프트
```

## YuE 모델 절
```prompt
YuE 전용 프롬프트
```
'''
            for slug in GUIDE_SLUGS:
                (root / f'{slug}.md').write_text(source, encoding='utf-8')
            yue = render_guide('start', token='t' * 32, guide_root=root)
            ace = render_guide('start', token='t' * 32, guide_root=root, engine='ACE')
            self.assertIn('YuE 전용 프롬프트', yue)
            self.assertNotIn('ACE 전용 프롬프트', yue)
            self.assertIn('/guide/start.md?token=', yue)
            self.assertIn('&amp;engine=YuE', yue)
            self.assertIn('/guide/results/?token=', yue)
            self.assertIn('&amp;engine=YuE', yue)
            self.assertIn('aria-current="page">YuE', yue)
            self.assertIn('ACE 전용 프롬프트', ace)
            self.assertNotIn('YuE 전용 프롬프트', ace)
            self.assertIn('&amp;engine=ACE', ace)
            self.assertIn('aria-current="page">ACE', ace)
            self.assertIn('download="start-ace.md"', ace)
            copied = re.search(r'<script id="guide-markdown" type="application/json">(.*?)</script>', ace, re.S)[1]
            self.assertNotIn('YuE 전용 프롬프트', json.loads(copied))

    def test_engine_only_guides_fall_back_to_ccm_for_ace(self):
        self.assertEqual(guide_for_engine('yue-advanced', 'ACE'), 'ccm')
        self.assertEqual(guide_for_engine('yue-advanced', 'YuE'), 'yue-advanced')

    def source_root(self):
        folder = tempfile.TemporaryDirectory()
        root = Path(folder.name) / 'guides'
        root.mkdir()
        source = '# 시작하기\n\n**안전한 안내**와 `명령`입니다.\n\n- 첫 항목\n- 둘째 항목\n\n[다음](results.md#download)\n\n[차단](javascript:alert(1))\n\n```sh\necho safe\n```\n'
        for slug in GUIDE_SLUGS:
            (root / f'{slug}.md').write_text(source.replace('시작하기', slug), encoding='utf-8')
        return folder, root

    def test_mobile_document_toc_precedes_body(self):
        page = render_guide('works', token='a'*32)
        self.assertIn('class="guide-mobile-toc"', page)
        self.assertLess(page.index('class="guide-mobile-toc"'), page.index('<h2'))
        self.assertNotIn('class="guide-mobile-toc" open', page)
        self.assertEqual(page.count('<h1>'), 1)

    def test_allowlisted_source_and_safe_rendering(self):
        folder, root = self.source_root()
        self.addCleanup(folder.cleanup)
        source = markdown_source('start', root)
        rendered = render_markdown(source, token='token')
        self.assertIn('<strong>안전한 안내</strong>', rendered)
        self.assertIn('<code>명령</code>', rendered)
        self.assertIn('/guide/results/?token=token#download', rendered)
        self.assertNotIn('javascript:', rendered)
        self.assertIn('&lt;', render_markdown('# x\n\n<script>x</script>'))
        with self.assertRaises(ValueError):
            markdown_source('../secret', root)

    def test_page_embeds_copy_source_without_html_execution(self):
        folder, root = self.source_root()
        self.addCleanup(folder.cleanup)
        page = render_guide('start', token='a' * 32, return_url='http://127.0.0.1:4343/?token=' + 'a' * 32, guide_root=root)
        self.assertIn('<title>Road Music 사용 가이드</title>', page)
        self.assertIn('id="guide-markdown" type="application/json"', page)
        self.assertIn('JSON.parse(document.getElementById(\'guide-markdown\').textContent)', page)
        self.assertIn('navigator.clipboard.writeText', page)
        self.assertIn('제작실로 돌아가기', page)
        self.assertIn('/guide/start.md?token=', page)
        self.assertIn('/guide/results/?token=', page)
        self.assertNotIn('<script>x</script>', page)
        hostile = render_guide('start', token='a' * 32, return_url='https://example.com/', guide_root=root)
        self.assertNotIn('제작실로 돌아가기', hostile)

    def test_materialize_writes_portable_html_and_markdown(self):
        folder, root = self.source_root()
        self.addCleanup(folder.cleanup)
        target = Path(folder.name) / 'out'
        guides = materialize_guides_assets(target, root)
        self.assertEqual((guides / 'start.md').read_text(encoding='utf-8'), markdown_source('start', root, 'YuE'))
        self.assertEqual((guides / 'start-ace.md').read_text(encoding='utf-8'), markdown_source('start', root, 'ACE'))
        page = (guides / 'start.html').read_text(encoding='utf-8')
        self.assertIn('href="../styles.css"', page)
        self.assertIn('results.html#download', page)
        ace = (guides / 'start-ace.html').read_text(encoding='utf-8')
        self.assertIn('results-ace.html#download', ace)
        self.assertIn('href="start.html"', ace)
        self.assertTrue((guides / 'yue-advanced.html').is_file())
        self.assertFalse((guides / 'yue-advanced-ace.html').exists())
        self.assertEqual(len(list(guides.glob('*.html'))), len(GUIDE_SLUGS) * 2 - 1)

    def test_portable_images_and_copy_fallback_are_self_contained(self):
        with tempfile.TemporaryDirectory() as folder:
            guides = materialize_guides_assets(folder)
            page = (guides / 'start.html').read_text(encoding='utf-8')
            self.assertIn('src="media/production-flow.svg"', page)
            self.assertTrue((guides / 'media/production-flow.svg').is_file())
            self.assertEqual((guides / 'media/production-flow.svg').read_bytes(), guide_media_file('production-flow.svg').read_bytes())
            self.assertIn('data-copy-example', page)
            self.assertIn('textarea', page)
            self.assertNotIn('/guide-media/', page)

    def test_portable_model_switch_keeps_only_the_selected_examples(self):
        with tempfile.TemporaryDirectory() as folder:
            guides = materialize_guides_assets(folder)
            yue = (guides / 'ccm-library.html').read_text(encoding='utf-8')
            ace = (guides / 'ccm-library-ace.html').read_text(encoding='utf-8')
            self.assertIn('YuE 모델 기본 요청 1', yue)
            self.assertNotIn('ACE 모델 기본 요청 1', yue)
            self.assertIn('ACE 모델 기본 요청 1', ace)
            self.assertNotIn('YuE 모델 기본 요청 1', ace)
            self.assertIn('href="ccm-library-ace.html"', yue)
            self.assertIn('href="ccm-library.html"', ace)
            self.assertTrue((guides / 'yue-advanced.html').is_file())
            self.assertFalse((guides / 'yue-advanced-ace.html').exists())


class GuideRouteTests(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        environment = patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': str(Path(state.name) / 'state')})
        environment.start()
        self.addCleanup(environment.stop)

    def test_routes_keep_token_auth_and_return_markdown(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'desk'
            init_project(project)
            session = Session(project, review=True)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(session))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown); self.addCleanup(server.server_close); self.addCleanup(thread.join, 2)

            def get(path):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port)
                client.request('GET', path)
                response = client.getresponse()
                result = response.status, dict(response.getheaders()), response.read()
                client.close()
                return result

            self.assertEqual(get('/guide/')[0], 403)
            self.assertEqual(get('/guide-media/production-flow.svg')[0], 403)
            status, headers, body = get(f'/guide-media/production-flow.svg?token={session.token}')
            self.assertEqual(status, 200)
            self.assertEqual(headers['Content-Type'], 'image/svg+xml')
            self.assertIn(b'<svg', body)
            self.assertEqual(get(f'/guide-media/unknown.svg?token={session.token}')[0], 404)
            self.assertEqual(get(f'/guide/not-a-guide/?token={session.token}')[0], 404)
            status, headers, body = get(f'/guide/start/?token={session.token}')
            self.assertEqual(status, 200)
            self.assertIn("default-src 'self'", headers['Content-Security-Policy'])
            self.assertIn(b'guide-markdown', body)
            self.assertEqual(body.count(b'<h1>'), 1)
            style = re.search(rb'<link rel="stylesheet" href="([^"]+)"', body)[1].decode()
            self.assertEqual(get(style)[0], 200)
            embedded = re.search(rb'<script id="guide-markdown" type="application/json">(.*?)</script>', body, re.S)[1]
            self.assertEqual(json.loads(embedded), markdown_source('start'))
            self.assertIn(f'/guide/results/?token={session.token}'.encode(), body)
            status, headers, body = get(f'/guide/start.md?token={session.token}')
            self.assertEqual(status, 200)
            self.assertEqual(headers['Content-Type'], 'text/markdown; charset=utf-8')
            self.assertEqual(body, markdown_source('start').encode())
            status, _, body = get(f'/guide/ccm-advanced/?token={session.token}')
            self.assertEqual(status, 200)
            self.assertIn('YuE MLX 회중 워십'.encode(), body)
            self.assertNotIn('ACE 회중 워십'.encode(), body)
            self.assertIn(b'engine=YuE', body)
            status, _, body = get(f'/guide/ccm-advanced/?token={session.token}&engine=ACE')
            self.assertEqual(status, 200)
            self.assertIn('ACE 회중 워십'.encode(), body)
            self.assertNotIn('YuE MLX 회중 워십'.encode(), body)
            self.assertIn(b'engine=ACE', body)
            status, _, body = get(f'/guide/ccm-advanced.md?token={session.token}&engine=ACE')
            self.assertEqual(status, 200)
            self.assertIn('ACE 회중 워십'.encode(), body)
            self.assertNotIn('YuE MLX 회중 워십'.encode(), body)
            self.assertEqual(get(f'/guide/ccm/?token={session.token}&engine=other')[0], 422)
            status, _, body = get(f'/guide/yue-advanced/?token={session.token}&engine=ACE')
            self.assertEqual(status, 200)
            self.assertIn('ACE의 CCM 제작'.encode(), body)
            for path, marker in (('/results/', b'Road Music \xec\x99\x84\xec\x84\xb1 \xea\xb2\xb0\xea\xb3\xbc'), ('/review/', b'Road Music \xea\xb2\xb0\xea\xb3\xbc \xea\xb2\x80\xec\x88\x98')):
                status, _, body = get(f'{path}?token={session.token}')
                self.assertEqual(status, 200)
                self.assertIn(marker, body)
                self.assertIn(b'data-road-music-nav', body)
                self.assertNotIn(b'__DESIGN_TOKEN__', body)
                self.assertNotIn(b'__GUIDE_MARKDOWN__', body)
                embedded = re.search(rb'<script id="page-guide-source" type="application/json">(.*?)</script>', body, re.S)[1]
                self.assertEqual(json.loads(embedded), markdown_source(path.strip('/')))
                self.assertIn(session.token.encode(), body)


if __name__ == '__main__':
    unittest.main()
