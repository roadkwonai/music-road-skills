"""Safe, dependency-free rendering for the Road Music HTML guides."""
from __future__ import annotations

import html
import json
import argparse
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse, quote
from guide_diagrams import render_diagram
from ui_icons import icon, inject_icon_library


GUIDE_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'guides'
GUIDE_SLUGS = ('start', 'workflow', 'topics', 'studio', 'works', 'production', 'storage', 'storage-tracking', 'status', 'reference', 'ccm', 'ccm-library', 'ccm-advanced', 'yue-advanced', 'results', 'review', 'styles', 'jizura', 'cli', 'troubleshooting')
GUIDE_ITEMS = (
    ('start', '시작하기'),
    ('workflow', '작업 흐름'),
    ('topics', '작업별 안내'),
    ('studio', '영상 제작실'),
    ('works', '내 작업물'),
    ('production', '제작 분석'),
    ('storage', '저장공간 관리'),
    ('storage-tracking', '소유권·SQLite'),
    ('status', '상태'),
    ('reference', '명령·등록 계획'),
    ('ccm', 'CCM 전문 제작'),
    ('ccm-library', 'CCM 스타일·가사·입력 예시'),
    ('ccm-advanced', 'ACE·YuE CCM 고급 활용'),
    ('yue-advanced', 'YuE 고급 활용'),
    ('results', '완성 결과'),
    ('review', '결과 검수'),
    ('styles', '스타일'),
    ('jizura', 'JIZURA'),
    ('cli', 'CLI'),
    ('troubleshooting', '문제 해결'),
)
_HEADINGS = re.compile(r'^(#{1,3})\s+(.+?)\s*$')
_GUIDE_ENGINES = ('YuE', 'ACE')
_ENGINE_WORD = {engine: re.compile(r'(?<![A-Za-z0-9])' + engine + r'(?![A-Za-z0-9])', re.I) for engine in _GUIDE_ENGINES}
_ENGINE_PAIR = re.compile(r'ACE\s*(?:·|/|&|와|및)\s*YuE|YuE\s*(?:·|/|&|와|및)\s*ACE', re.I)
_ENGINE_ONLY_GUIDES = {'yue-advanced': 'YuE'}
_BULLET = re.compile(r'^[-*]\s+(.+?)\s*$')
_ORDERED = re.compile(r'^\d+[.)]\s+(.+?)\s*$')
_LINK = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
_IMAGE = re.compile(r'^!\[([^\]]+)\]\(media/([a-z0-9-]+\.(?:svg|webp|png))\)$')
_CALLOUT = re.compile(r'^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$')
_CALLOUTS = {
    'NOTE': ('안내', 'information-circle'), 'TIP': ('활용 팁', 'check-circle'),
    'IMPORTANT': ('중요', 'clipboard-document-check'), 'WARNING': ('주의', 'exclamation-triangle'),
    'CAUTION': ('경고', 'exclamation-triangle'),
}
GUIDE_MEDIA_ROOT = GUIDE_ROOT / 'media'
GUIDE_MEDIA = {
    'studio-screen.webp': (1280, 900), 'works-screen.webp': (1280, 900),
    'detail-screen.webp': (1280, 900), 'storyboard-screen.webp': (1440, 600),
    'style-sample.webp': (1280, 720), 'production-flow.svg': (600, 706),
    'work-map.svg': (600, 608), 'sync-review.svg': (600, 654),
    'style-energy.svg': (600, 684),
    'display-choices.svg': (600, 420), 'lyrics-vs-captions.svg': (600, 570),
    'delivery-map.svg': (600, 620),
    'music-mascot.webp': (512, 512), 'style-concepts.webp': (2172, 724),
    'detail-lyrics.webp': (737, 1565),
    'detail-videos.webp': (737, 1035),
    'display-step.webp': (1280, 900),
    'help-dialog.webp': (760, 678),
    'mode-step.webp': (1280, 900),
    'music-mascot-listening.webp': (512, 512),
    'music-mascot-review.webp': (512, 512),
    'music-step.webp': (1280, 900),
    'review-records.webp': (737, 844),
    'save-step.webp': (1280, 900),
}


def guide_media_file(name):
    if name not in GUIDE_MEDIA:
        raise ValueError('등록된 가이드 이미지가 아닙니다')
    path = GUIDE_MEDIA_ROOT / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('가이드 이미지를 찾지 못했습니다')
    return path


def _slug(value):
    if value not in GUIDE_SLUGS:
        raise ValueError('등록된 가이드가 아닙니다')
    return value


def _path(slug, guide_root=GUIDE_ROOT):
    slug = _slug(slug)
    root = Path(guide_root).resolve()
    path = (root / f'{slug}.md').resolve()
    if root not in path.parents or path.suffix != '.md':
        raise ValueError('등록된 가이드가 아닙니다')
    return path


def _engine(value):
    if value not in _GUIDE_ENGINES:
        raise ValueError('가이드 모델은 YuE 또는 ACE여야 합니다')
    return value


def guide_for_engine(slug, engine=None):
    """Return a guide available to the selected engine without exposing an engine-only page."""
    slug = _slug(slug)
    if engine is None:
        return slug
    engine = _engine(engine)
    return 'ccm' if _ENGINE_ONLY_GUIDES.get(slug) not in {None, engine} else slug


def _heading_engine(title):
    matched = [engine for engine, pattern in _ENGINE_WORD.items() if pattern.search(title)]
    return matched[0] if len(matched) == 1 else None


def filter_model_sections(source, engine):
    """Keep common Markdown plus the selected model's explicit H2/H3 sections."""
    engine = _engine(engine)
    kept, scopes = [], []
    in_code = False
    for line in source.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if line.startswith('```'):
            in_code = not in_code
        heading = None if in_code else _HEADINGS.match(line)
        if heading:
            level, marked = len(heading.group(1)), _heading_engine(heading.group(2))
            while scopes and scopes[-1][0] >= level:
                scopes.pop()
            if marked:
                scopes.append((level, marked))
        active = scopes[-1][1] if scopes else None
        if active in {None, engine}:
            kept.append(line)
    filtered = '\n'.join(kept)
    return re.sub(r'(?m)^(#\s+)(?:' + _ENGINE_PAIR.pattern + r')(?=\s|$)', lambda match: match[1] + engine, filtered, count=1)


def markdown_source(slug, guide_root=GUIDE_ROOT, engine=None):
    """Read only an allow-listed UTF-8 guide; never accept a file path from HTTP."""
    path = _path(slug, guide_root)
    try:
        source = path.read_text(encoding='utf-8')
        return source if engine is None else filter_model_sections(source, engine)
    except OSError as error:
        raise ValueError('가이드 원문을 찾지 못했습니다') from error


def _heading_id(value):
    normalized = re.sub(r'[^0-9A-Za-z가-힣_-]+', '-', value.strip().lower())
    return normalized.strip('-') or 'section'


def _document_headings(source):
    """Return the visible H2/H3 structure for the document-local table of contents."""
    headings = []
    used = set()
    in_code = False
    for line in source.splitlines():
        if line.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = _HEADINGS.match(line)
        if not match or len(match.group(1)) == 1:
            continue
        title = match.group(2)
        base = _heading_id(title)
        identifier = base
        number = 2
        while identifier in used:
            identifier = f'{base}-{number}'
            number += 1
        used.add(identifier)
        headings.append((identifier, title, len(match.group(1))))
    return headings


def _guide_path(slug, static=False, token=None, engine=None):
    engine = _engine(engine) if engine is not None else None
    if static:
        return f'{slug}{"-ace" if engine == "ACE" else ""}.html'
    query = f'?token={token}' if token else ''
    if engine:
        query += ('&' if query else '?') + 'engine=' + engine
    return f'/guide/{slug}/{query}'


def _safe_url(url, static=False, token=None, engine=None):
    parsed = urlparse(url)
    if parsed.scheme.lower() in {'javascript', 'data', 'vbscript'}:
        return None
    if parsed.scheme and parsed.scheme.lower() not in {'http', 'https', 'mailto'}:
        return None
    if parsed.scheme in {'http', 'https'} and not parsed.netloc:
        return None
    if url in {'/ccm/', '/recipes/', '/reference/'}:
        guide = 'ccm' if url == '/ccm/' else 'reference'
        if static:
            return _guide_path(guide, static=True, engine=engine)
        query = ('?token=' + quote(token, safe='')) if token else ''
        if engine:
            query += ('&' if query else '?') + 'engine=' + _engine(engine)
        return url + query
    if parsed.scheme or url.startswith(('/', '#')):
        return url
    match = re.fullmatch(r'([a-z][a-z0-9-]*)\.md(#[A-Za-z0-9가-힣_-]+)?', url)
    if match and match.group(1) in GUIDE_SLUGS:
        fragment = match.group(2) or ''
        return _guide_path(guide_for_engine(match.group(1), engine), static, token, engine) + fragment
    return None


def _inline(value, static=False, token=None, engine=None):
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r'`([^`]+)`', lambda match: '<code>' + html.escape(html.unescape(match.group(1)), quote=False) + '</code>', escaped)
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)

    def link(match):
        label, raw = html.unescape(match.group(1)), html.unescape(match.group(2))
        url = _safe_url(raw, static, token, engine)
        if not url:
            return html.escape(label, quote=False)
        external = ' rel="noreferrer"' if urlparse(url).scheme in {'http', 'https'} else ''
        return f'<a href="{html.escape(url, quote=True)}"{external}>{html.escape(label, quote=False)}</a>'

    return _LINK.sub(link, escaped)


def render_markdown(source, static=False, token=None, engine=None):
    """Render the small documentation subset used by the bundled guides."""
    if engine is not None:
        engine = _engine(engine)
    blocks, paragraph, list_items, list_tag, code = [], [], [], None, []
    code_language, example_number = '', 0
    callout_type, callout_lines = None, []
    table_rows = []

    def flush_table():
        nonlocal table_rows
        if not table_rows:
            return
        rows = [[cell.strip() for cell in re.split(r'(?<!\\)\|', line.strip().strip('|'))] for line in table_rows]
        if len(rows) > 1 and all(re.fullmatch(r':?-{3,}:?', cell) for cell in rows[1]):
            header = ''.join('<th scope="col">' + _inline(cell, static, token, engine) + '</th>' for cell in rows[0])
            body = ''.join('<tr>' + ''.join('<td>' + _inline(cell, static, token, engine) + '</td>' for cell in row) + '</tr>' for row in rows[2:])
            blocks.append('<div class="guide-table-wrap" role="region" aria-label="활용 가이드 비교표, 좌우로 이동해 확인" tabindex="0"><table><thead><tr>' + header + '</tr></thead><tbody>' + body + '</tbody></table></div>')
        else:
            blocks.append('<p>' + '<br>'.join(_inline(line, static, token, engine) for line in table_rows) + '</p>')
        table_rows = []

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            blocks.append('<p>' + '<br>'.join(_inline(line, static, token, engine) for line in paragraph) + '</p>')
            paragraph = []

    def flush_list():
        nonlocal list_items, list_tag
        if list_items:
            terms = [re.fullmatch(r'\*\*([^*]+)\*\*\s*[:：]\s*(.+)', item) for item in list_items]
            if list_tag == 'ul' and len(terms) > 1 and all(terms):
                items = ''.join('<li><strong class="guide-term-name">' + _inline(term[1], static, token, engine)
                                + '</strong><span class="guide-term-description">' + _inline(term[2], static, token, engine)
                                + '</span></li>' for term in terms)
                blocks.append('<ul class="guide-reference-list" role="list">' + items + '</ul>')
            else:
                css = ' class="guide-steps"' if list_tag == 'ol' and len(list_items) > 1 else ''
                blocks.append(f'<{list_tag}{css}>' + ''.join(f'<li>{_inline(item, static, token, engine)}</li>' for item in list_items) + f'</{list_tag}>')
            list_items, list_tag = [], None

    def flush_code():
        nonlocal code, example_number
        if code:
            example_number += 1
            label = {'prompt': '프롬프트', 'bash': '명령', 'sh': '명령', 'json': 'JSON 예시'}.get(code_language, '텍스트 예시')
            identifier = f'guide-example-{example_number}'
            blocks.append(f'<div class="guide-example"><div class="guide-example-toolbar"><span>{label}</span>'
                          f'<button type="button" data-copy-example="{identifier}" aria-label="예시 {example_number} {label} 복사">{icon("clipboard-document")}{label} 복사</button></div>'
                          f'<pre tabindex="0" aria-label="예시 {example_number} {label}"><code id="{identifier}">' + html.escape('\n'.join(code), quote=False) + '</code></pre>'
                          '<p class="guide-copy-status" role="status"></p>'
                          '<textarea class="copy-fallback" aria-label="직접 복사할 예시" readonly hidden></textarea></div>')
            code = []

    def flush_callout():
        nonlocal callout_type, callout_lines
        if callout_type:
            label, symbol = _CALLOUTS[callout_type]
            body = '<br>'.join(_inline(line, static, token, engine) for line in callout_lines)
            blocks.append(f'<aside class="rm-callout rm-callout--{callout_type.lower()}" role="note" aria-label="{label}"><div class="rm-callout-heading">{icon(symbol)}<strong>{label}</strong></div><p>{body}</p></aside>')
            callout_type, callout_lines = None, []

    in_code = False
    heading_ids = iter(identifier for identifier, _, _ in _document_headings(source))
    for line in source.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if not in_code and line.strip().startswith('|') and line.strip().endswith('|'):
            flush_paragraph(); flush_list()
            table_rows.append(line)
            continue
        flush_table()
        if callout_type:
            if line.startswith('>'):
                callout_lines.append(line[1:].lstrip())
                continue
            flush_callout()
        note = _CALLOUT.fullmatch(line) if not in_code else None
        if note:
            flush_paragraph(); flush_list()
            callout_type = note[1]
            continue
        if line.startswith('```'):
            if in_code:
                flush_code()
            else:
                flush_paragraph(); flush_list()
                code_language = line[3:].strip().lower()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        anchor = re.fullmatch(r'<a id="([A-Za-z0-9_-]+)"></a>', line.strip())
        if anchor:
            flush_paragraph(); flush_list()
            blocks.append('<span id="' + anchor[1] + '" class="guide-anchor"></span>')
            continue
        heading = _HEADINGS.match(line)
        picture = _IMAGE.fullmatch(line.strip())
        bullet, ordered = _BULLET.match(line), _ORDERED.match(line)
        if picture and picture[2] in GUIDE_MEDIA:
            flush_paragraph(); flush_list()
            name = picture[2]
            width, height = GUIDE_MEDIA[name]
            src = f'media/{name}' if static else f'/guide-media/{name}' + ('?token=' + quote(token, safe='') if token else '')
            src, caption = html.escape(src, quote=True), html.escape(picture[1], quote=True)
            diagram = name.endswith('.svg')
            preview = render_diagram(name) if diagram else f'<img src="{src}" alt="{caption}" width="{width}" height="{height}" loading="lazy" decoding="async">'
            expand_label = 'SVG 도식 원본 보기' if diagram else '원본 크기로 펼치기'
            blocks.append(f'<figure class="guide-figure">{preview}'
                          f'<figcaption>{caption}</figcaption><details class="guide-image-zoom"><summary>{expand_label}</summary>'
                          f'<div class="guide-image-pan" tabindex="0" role="region" aria-label="{caption} 확대 이미지"><img src="{src}" alt="{caption}" width="{width}" height="{height}" loading="lazy"></div></details></figure>')
        elif heading:
            flush_paragraph(); flush_list()
            level, title = len(heading.group(1)), heading.group(2)
            identifier = _heading_id(title) if level == 1 else next(heading_ids)
            blocks.append(f'<h{level} id="{html.escape(identifier, quote=True)}">{_inline(title, static, token, engine)}</h{level}>')
        elif bullet or ordered:
            flush_paragraph()
            tag, item = ('ul', bullet.group(1)) if bullet else ('ol', ordered.group(1))
            if list_tag and list_tag != tag:
                flush_list()
            list_tag = tag; list_items.append(item)
        elif not line.strip():
            flush_paragraph(); flush_list()
        else:
            flush_list(); paragraph.append(line.strip())
    if in_code:
        flush_code()
    flush_callout(); flush_table()
    flush_paragraph(); flush_list()
    return '\n'.join(blocks)


def _return_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port and not parsed.username and not parsed.password:
        return value
    return None


def render_guide(slug, token=None, return_url=None, guide_root=GUIDE_ROOT, static=False, stylesheet='/design.css', engine='YuE'):
    engine = _engine(engine)
    slug = guide_for_engine(slug, engine)
    source = markdown_source(slug, guide_root, engine)
    body_source = re.sub(r'\A#\s+[^\n]+\n(?:\n)?', '', source, count=1)
    article = render_markdown(body_source, static=static, token=token, engine=engine)
    title_match = re.search(r'^#\s+(.+?)\s*$', source, re.M)
    title = title_match.group(1) if title_match else 'Road Music 가이드'
    copied = json.dumps(source, ensure_ascii=False).replace('<', '\\u003c')
    back = _return_url(return_url)
    back_link = f'<a class="button secondary" href="{html.escape(back, quote=True)}">제작실로 돌아가기</a>' if back else ''
    markdown_href = (f'/guide/{slug}.md?token={quote(token, safe="")}&engine={engine}' if token and not static
                     else f'{slug}{"-ace" if engine == "ACE" else ""}.md')
    markdown_name = f'{slug}{"-ace" if engine == "ACE" else ""}.md'
    if token and not static:
        stylesheet += ('&' if '?' in stylesheet else '?') + 'token=' + quote(token, safe='')
    style_href = html.escape(stylesheet, quote=True)
    nav = '<nav class="guide-sidebar" aria-label="가이드 목차"><details id="guide-topics" open><summary>가이드 목차</summary><ul>' + ''.join(
        f'<li><a href="{html.escape(_guide_path(name, static, token, engine), quote=True)}"' + (' aria-current="page"' if name == slug else '') + f'>{label}</a></li>'
        for name, label in GUIDE_ITEMS if _ENGINE_ONLY_GUIDES.get(name) in {None, engine}
    ) + '</ul></details></nav>'
    headings = _document_headings(body_source)
    on_page = '' if not headings else '<nav class="guide-on-page" aria-label="이 문서에서"><details id="guide-on-page" open><summary>이 문서에서</summary><ul>' + ''.join(
        f'<li><a href="#{html.escape(identifier, quote=True)}" data-depth="{depth}">{_inline(heading, static, token, engine)}</a></li>'
        for identifier, heading, depth in headings
    ) + '</ul></details></nav>'
    mobile_toc = '' if not headings else '<details class="guide-mobile-toc"><summary>이 문서 목차</summary><nav aria-label="이 문서 목차"><ul>' + ''.join(
        f'<li><a href="#{html.escape(identifier, quote=True)}" data-depth="{depth}">{_inline(heading, static, token, engine)}</a></li>'
        for identifier, heading, depth in headings
    ) + '</ul></nav></details>'
    mascot_name = ('music-mascot-listening.webp' if slug in {'studio', 'jizura'} else 'music-mascot-review.webp' if slug in {'works', 'results', 'review', 'troubleshooting'} else 'music-mascot.webp')
    mascot_src = f'media/{mascot_name}' if static else f'/guide-media/{mascot_name}' + ('?token=' + quote(token, safe='') if token else '')
    script = """<script>
const compact=matchMedia('(max-width:760px)').matches;
document.getElementById('guide-topics').open=!compact;
const local=document.getElementById('guide-on-page');if(local)local.open=!compact;
const source=JSON.parse(document.getElementById('guide-markdown').textContent);
async function copyText(value,button,status,box){
  button.disabled=true;status.textContent='';
  try{
    await navigator.clipboard.writeText(value);
    box.hidden=true;box.value='';status.textContent='복사했습니다.';
  }catch{
    box.hidden=false;box.value=value;box.focus();box.select();
    status.textContent='자동 복사가 차단되어 내용을 선택했습니다. ⌘C 또는 Ctrl+C로 복사하세요.';
  }finally{button.disabled=false}
}
document.getElementById('copy-markdown').addEventListener('click',event=>copyText(source,event.currentTarget,document.getElementById('copy-status'),document.getElementById('copy-fallback')));
for(const button of document.querySelectorAll('[data-copy-example]')){
  button.addEventListener('click',()=>{
    const example=button.closest('.guide-example');
    copyText(document.getElementById(button.dataset.copyExample).textContent,button,example.querySelector('[role="status"]'),example.querySelector('textarea'));
  });
}
const links=[...document.querySelectorAll('.guide-on-page a,.guide-mobile-toc a')];
const headings=[...new Set(links.map(link=>document.getElementById(link.getAttribute('href').slice(1))).filter(Boolean))];
const update=()=>{
  if(!headings.length)return;
  const line=innerHeight*.3;let active=headings[0];
  for(const heading of headings){if(heading.getBoundingClientRect().top>line)break;active=heading}
  for(const link of links){
    if(link.getAttribute('href')==='#'+active.id)link.setAttribute('aria-current','location');
    else link.removeAttribute('aria-current');
  }
};
addEventListener('scroll',update,{passive:true});addEventListener('resize',update);update();
</script>"""
    engine_switch = '<nav class="guide-engine-selector" aria-label="가이드 모델 선택"><span>표시 모델</span>' + ''.join(
        f'<a class="button guide-engine" href="{html.escape(_guide_path(guide_for_engine(slug, value), static, token, value), quote=True)}"'
        + (' aria-current="page"' if value == engine else '') + f'>{value}</a>'
        for value in _GUIDE_ENGINES
    ) + '<p class="hint">모델 전용 설명·예시·목차·복사 원문을 분리해 보여 줍니다.</p></nav>'
    page = f'''<!doctype html><html lang="ko" data-road-music-ui><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f5f5f5"><title>Road Music 사용 가이드</title><link rel="stylesheet" href="{style_href}"></head><body><a class="skip-link" href="#main-content">본문으로 건너뛰기</a><main id="main-content" class="guide-layout">{nav}<article class="guide-article"><header class="page-heading"><div><div class="guide-title"><img class="guide-mascot" src="{mascot_src}" width="512" height="512" alt=""><h1>{_inline(title, static, token, engine)}</h1></div><p>이 페이지의 기능과 다음 단계를 확인한 뒤 제작실에서 작업하세요.</p></div><div class="page-actions">{back_link}<a class="button secondary" href="{html.escape(markdown_href, quote=True)}" download="{markdown_name}">{icon("arrow-down-tray")}원문 다운로드</a><button id="copy-markdown" type="button">{icon("clipboard-document")}마크다운 복사</button></div></header>{engine_switch}<p id="copy-status" class="hint" role="status"></p><textarea id="copy-fallback" class="copy-fallback" aria-label="복사할 마크다운 원문" readonly hidden></textarea>{mobile_toc}{article}</article>{on_page}</main><script id="guide-markdown" type="application/json">{copied}</script>{script}</body></html>'''
    return inject_icon_library(page)


def materialize_guides_assets(directory, guide_root=GUIDE_ROOT):
    """Create portable guide HTML/Markdown files for generated offline bundles."""
    target = Path(directory) / 'guides'
    target.mkdir(parents=True, exist_ok=True)
    media = target / 'media'
    media.mkdir(exist_ok=True)
    for name in sorted(GUIDE_MEDIA):
        shutil.copyfile(guide_media_file(name), media / name)
    for slug in GUIDE_SLUGS:
        for engine, suffix in (('YuE', ''), ('ACE', '-ace')):
            resolved = guide_for_engine(slug, engine)
            if resolved != slug:
                continue
            source = markdown_source(slug, guide_root, engine)
            (target / f'{slug}{suffix}.md').write_text(source, encoding='utf-8')
            page = render_guide(slug, guide_root=guide_root, static=True, stylesheet='../styles.css', engine=engine)
            (target / f'{slug}{suffix}.html').write_text(page, encoding='utf-8')
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description='Materialize the bundled Road Music Markdown guides.')
    parser.add_argument('--out', required=True, help='absolute design asset directory')
    args = parser.parse_args(argv)
    output = Path(args.out)
    if not output.is_absolute():
        parser.error('--out에는 절대 경로가 필요합니다')
    target = materialize_guides_assets(output.resolve())
    print(json.dumps({'status': 'materialized', 'directory': str(target), 'count': len(GUIDE_SLUGS)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
