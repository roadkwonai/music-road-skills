"""Apply the shared DESIGN.md tokens and bundled Paperlogy to generated HTML."""
import html
import json
import os
import sys
import subprocess
import webbrowser
import time
from pathlib import Path
import re
import shutil
from urllib.parse import quote, urlparse, urlunparse
from ui_icons import icon, inject_icon_library

ASSET_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'design'
FONT_FILES = frozenset(path.name for path in (ASSET_ROOT / 'fonts').glob('Paperlogy-*.ttf'))
EGO_TASK_SPACE = 'Road Music 제작실'
EGO_PAGE_TITLES = ('Road Music 영상 제작실', 'Road Music 스타일 카탈로그', 'JIZURA 음악 스튜디오', 'JIZURA 가사 가독성 검수', 'Road Music Showreel CD', 'Road Music 쇼릴 MV', 'Showreel 음악 모션그래픽', 'Showreel 플레이리스트 프리셋', 'Showreel 스타일 선택', 'Road Music 완성 결과', 'Road Music 결과 검수', 'Road Music 사용 가이드', 'Road Music 내 작업물', 'Road Music 음악 그룹', 'Road Music 저장공간 관리', 'Road Music 제작 분석', 'Road Music 환경 상태', 'Road Music 공개 명령 레퍼런스', 'Road Music CCM 전문 제작 가이드', 'Road Music 공개 명령 상세 활용 가이드')


def copy_local_asset(source, target):
    """Copy an editable local asset while preserving its metadata."""
    source, target = Path(source), Path(target)
    path_copy = getattr(Path, 'copy', None)
    if path_copy is not None:
        return source.copy(target, preserve_metadata=True)
    return shutil.copy2(source, target)


def css_text(font_base='fonts/', token=None):
    fonts = (ASSET_ROOT / 'fonts.css').read_text(encoding='utf-8')
    query = '?token=' + quote(token, safe='') if token else ''
    fonts = re.sub(r'url\("fonts/([^"/]+)"\)', lambda match: 'url("' + font_base + match[1] + query + '")', fonts)
    return fonts + '\n' + (ASSET_ROOT / 'design.css').read_text(encoding='utf-8')


def studio_session_file():
    if os.environ.get('ROADMUSIC_DATA_DIR'):
        root = Path(os.environ['ROADMUSIC_DATA_DIR'])
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support/Road Music'
    elif sys.platform == 'win32':
        root = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / 'Road Music'
    else:
        root = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'Road Music'
    return root / 'video-studio-session.json'


def valid_studio_url(value):
    if not isinstance(value, str):
        return False
    try:
        return bool(re.fullmatch(r'http://127\.0\.0\.1:[1-9][0-9]{0,4}/(?:(?:catalog|results|review|storage|dashboard|status|reference|recipes|ccm)/|works/(?:[0-9a-f]{64}/)?|guide/(?:[a-z0-9-]+/)?)?\?token=[A-Za-z0-9_-]{16,128}(?:&(?:view=(?:list|large)|engine=(?:ACE|YuE)|(?:search|purpose|category|style|tag)=[A-Za-z0-9_%+.~-]*))*(?:#[^\s]*)?', value)) and 0 < urlparse(value).port < 65536
    except ValueError:
        return False


def open_page(url):
    if not valid_studio_url(url):
        raise ValueError('제작실은 등록된 로컬 주소로만 엽니다')
    if os.environ.get('ROADMUSIC_STUDIO_BROWSER') == 'system':
        return webbrowser.open(url)
    value = os.environ.get('ROADMUSIC_EGO_TASK_SPACE', '')
    if value.isdigit() and 0 < int(value) <= 9007199254740991:
        script = f'const task=await taskSpace({int(value)});const page=task.page("p1");const url={json.dumps(url)};if(await page.url()!==url)await page.goto(url);'
    else:
        name = json.dumps(EGO_TASK_SPACE, ensure_ascii=False)
        reuse = json.dumps(os.environ.get('ROADMUSIC_EGO_REUSE_ROAD_MUSIC_PAGE') != '0')
        titles = json.dumps(EGO_PAGE_TITLES, ensure_ascii=False)
        local = r'/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/(?:(?:catalog|results|review|storage|dashboard|status|reference|recipes|ccm)\/|works\/(?:[0-9a-f]{64}\/)?|guide\/(?:[a-z0-9-]+\/)?)?\?token=[A-Za-z0-9_-]{16,128}(?:&(?:view=(?:list|large)|engine=(?:ACE|YuE)|(?:search|purpose|category|style|tag)=[A-Za-z0-9_%+.~-]*))*(?:#[^\s]*)?$/'
        script = f'const name={name};const url={json.dumps(url)};const reuse={reuse};const titles={titles};const isRoadMusicURL=(current,title)=>{local}.test(current)||(title==="JIZURA 가사 가독성 검수"&&/^file:\\/\\/.*\\/review\\.html(?:[?#].*)?$/.test(current));const isRoadMusicPage=async page=>isRoadMusicURL(await page.url(),await page.title());const pickRoadMusicTab=async task=>{{const matches=[];for(const item of await task.tabs())if(isRoadMusicURL(item.url,item.title))matches.push(item);const active=matches.filter(item=>item.active);return active.length===1?active[0]:matches.length===1?matches[0]:null}};const entries=await listTaskSpaces();const exact=entries.filter(item=>item.name===name);if(exact.length>1)throw new Error("Road Music 제작실 작업 공간이 여러 개입니다");const fallback=exact.length?[]:entries.filter(item=>item.createdBy==="agent"&&typeof item.name==="string"&&item.name.startsWith("Road Music")&&Array.isArray(item.recentTabTitles)&&item.recentTabTitles.some(title=>titles.includes(title)));if(fallback.length>1)throw new Error("재사용할 Road Music 제작실 작업 공간이 여러 개입니다");const existing=exact[0]||fallback[0];const verifyCurrent=Boolean(fallback[0]);if(existing?.ownership==="user"&&existing.createdBy!=="agent")throw new Error("사용자가 만든 작업 공간은 재사용하지 않습니다");let task;let claimed=false;if(existing?.ownership==="user"){{if(!reuse)throw new Error("완료된 Road Music 제작실 페이지 재사용이 허용되지 않았습니다");task=await claimTaskSpace(existing.id);claimed=true}}else task=existing?await taskSpace(existing.id):await taskSpace(name);const hasP1=(await task.tabs()).some(item=>item.label==="p1");let page;if(claimed||(existing&&!hasP1)){{const tab=await pickRoadMusicTab(task);if(!tab)throw new Error("재사용할 Road Music 제작실 페이지가 로컬 제작실이 아닙니다");page=await task.adopt(tab.page,{{as:"p1"}})}}else page=task.page("p1");if(verifyCurrent&&!await isRoadMusicPage(page))throw new Error("재사용할 Road Music 제작실 페이지가 로컬 제작실이 아닙니다");if(await page.url()!==url)await page.goto(url);'
    result = subprocess.run(['ego-browser', 'nodejs', '-e', script], capture_output=True, timeout=20, check=False)
    return result.returncode == 0


def live_studio_url():
    try:
        raw = studio_session_file().read_bytes()
        if len(raw) > 65536:
            return None
        state = json.loads(raw)
        if state.get('schemaVersion') == 1 and isinstance(state.get('expiresAt'), (int, float)) and state['expiresAt'] > time.time() and valid_studio_url(state.get('url')):
            return state['url']
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def navigation_html(current='studio', sections=(), home_url=None):
    home = None if home_url is False else (home_url if valid_studio_url(home_url) else live_studio_url())
    menu = json.loads((ASSET_ROOT / 'navigation.json').read_text())
    links = []
    if home:
        parsed = urlparse(home)
        for key, label, path, fragment, _icon in menu:
            links.append((key, label, urlunparse(parsed._replace(path=path, fragment=fragment))))
    links.extend((href.removeprefix('#'), label, href) for label, href in sections if isinstance(href, str) and re.fullmatch(r'#[A-Za-z][A-Za-z0-9_-]*', href))
    if not links:
        links = [('top', '페이지 처음으로', '#')]
    icons = {row[0]: row[4] for row in menu}
    items = ''.join(f'<a href="{html.escape(href, quote=True)}"' + (' aria-current="page"' if key == current else '') + f'>{icon(icons.get(key, "chevron-right"))}<span>{html.escape(label)}</span></a>' for key, label, href in links)
    return '<nav class="rm-nav" data-road-music-nav aria-label="Road Music 페이지 이동">' + items + '</nav>'


def add_navigation(page, current='studio', sections=(), home_url=None, guide_url=None, guide_topic=None):
    page = re.sub(r'<nav\b(?=[^>]*\bdata-road-music-nav\b)[^>]*>.*?</nav>\s*', '', page, flags=re.I | re.S)
    nav = navigation_html(current, sections, home_url)
    main = re.search(r'<main\b[^>]*>', page, flags=re.I)
    if main:
        target = re.search(r'\bid=["\']([^"\']+)["\']', main[0], flags=re.I)
        target = target[1] if target else 'main-content'
        if not re.search(r'\bid=', main[0], flags=re.I):
            page = page[:main.start()] + main[0][:-1] + ' id="main-content">' + page[main.end():]
    else:
        target = 'main-content'
        page = re.sub(r'(<body\b[^>]*>)(.*?)(</body>)', lambda m: m[1] + '<main id="main-content">' + m[2] + '</main>' + m[3], page, count=1, flags=re.I | re.S)
    skip = re.search(r'<a\b(?=[^>]*\bclass=["\'][^"\']*\bskip-link\b)[^>]*>.*?</a>', page, flags=re.I | re.S)
    if skip:
        page = page[:skip.end()] + nav + page[skip.end():]
    elif re.search(r'<body\b[^>]*>', page, flags=re.I):
        skip = '<a class="skip-link" href="#' + html.escape(target, quote=True) + '">본문으로 건너뛰기</a>'
        page = re.sub(r'(<body\b[^>]*>)', lambda m: m[1] + skip + nav, page, count=1, flags=re.I)
    else:
        page = page.replace('<main', nav + '<main', 1)
    topics = {'studio':'studio', 'results':'results', 'review':'review', 'catalog':'styles', 'chooser':'styles', 'jizura':'jizura', 'works':'works', 'dashboard':'production', 'storage':'storage', 'status':'status', 'reference':'reference'}
    topic = guide_topic or topics.get(current)
    if topic:
        base = guide_url if valid_studio_url(guide_url) else (None if home_url is False else (home_url if valid_studio_url(home_url) else live_studio_url()))
        if base:
            parsed = urlparse(base)
            href = urlunparse(parsed._replace(path=f'/guide/{topic}/', fragment=''))
        else:
            href = f'road-music-design/guides/{topic}.html'
        tools = '<div class="rm-guide-tools" data-rm-guide-tools><a href="' + html.escape(href, quote=True) + '">' + icon('book-open') + '<span>이 화면 사용법</span></a></div>'
        existing_tools = r'<div\b(?=[^>]*\bdata-rm-guide-tools\b)[^>]*>.*?</div>'
        if re.search(existing_tools, page, flags=re.I | re.S):
            page = re.sub(existing_tools, lambda _: tools, page, count=1, flags=re.I | re.S)
        elif 'data-rm-guide-tools' not in page:
            page = re.sub(r'(<main\b[^>]*>)', lambda m: m[1] + tools, page, count=1, flags=re.I)
    return inject_icon_library(page)


def apply_design(page, target, ui=True, navigation_home=None):
    target = Path(target)
    assets = target.parent / 'road-music-design'
    shutil.copytree(ASSET_ROOT, assets, dirs_exist_ok=True, copy_function=copy_local_asset)
    (assets / 'styles.css').write_text(css_text(), encoding='utf-8')
    if ui:
        from guide_content import materialize_guides_assets
        materialize_guides_assets(assets)
    page = re.sub(r'<link\b(?=[^>]*\bdata-road-music-design\b)[^>]*>\s*', '', page, flags=re.I)
    if ui and not re.search(r'<html\b[^>]*\sdata-road-music-ui(?:\s|=|>)', page, re.I):
        page = re.sub(r'<html(?=[\s>])', '<html data-road-music-ui', page, count=1)
    if ui:
        page = add_navigation(page, current='catalog' if target.name == 'catalog.html' else 'review', home_url=navigation_home)
    link = '<link rel="stylesheet" data-road-music-design href="road-music-design/styles.css">'
    if '</head>' in page:
        return page.replace('</head>', link + '</head>', 1)
    if '</style>' in page:
        return page.replace('</style>', '</style>' + link, 1)
    return page.replace('<body', link + '<body', 1)
