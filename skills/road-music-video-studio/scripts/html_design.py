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

ASSET_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'design'
FONT_FILES = frozenset(path.name for path in (ASSET_ROOT / 'fonts').glob('Paperlogy-*.ttf'))
EGO_TASK_SPACE = 'Road Music 제작실'
EGO_PAGE_TITLES = ('Road Music 영상 제작실', 'Road Music 스타일 카탈로그', 'JIZURA 음악 스튜디오', 'JIZURA 가사 가독성 검수', 'Road Music Showreel CD', 'Road Music 쇼릴 MV', 'Showreel 음악 모션그래픽', 'Showreel 플레이리스트 프리셋', 'Showreel 스타일 선택')


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
        return bool(re.fullmatch(r'http://127\.0\.0\.1:[1-9][0-9]{0,4}/(?:catalog/)?\?token=[A-Za-z0-9_-]{16,128}', value)) and 0 < urlparse(value).port < 65536
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
        local = r'/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/(?:catalog\/)?\?token=[A-Za-z0-9_-]{16,128}$/'
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
    links = []
    if home:
        parsed = urlparse(home)
        for key, label, path, fragment in json.loads((ASSET_ROOT / 'navigation.json').read_text()):
            links.append((key, label, urlunparse(parsed._replace(path=path, fragment=fragment))))
    links.extend((href.removeprefix('#'), label, href) for label, href in sections if isinstance(href, str) and re.fullmatch(r'#[A-Za-z][A-Za-z0-9_-]*', href))
    if not links:
        links = [('top', '페이지 처음으로', '#')]
    items = ''.join(f'<a href="{html.escape(href, quote=True)}"' + (' aria-current="page"' if key == current else '') + f'>{html.escape(label)}</a>' for key, label, href in links)
    return '<nav class="rm-nav" data-road-music-nav aria-label="Road Music 페이지 이동">' + items + '</nav>'


def add_navigation(page, current='studio', sections=(), home_url=None):
    page = re.sub(r'<nav\b(?=[^>]*\bdata-road-music-nav\b)[^>]*>.*?</nav>\s*', '', page, flags=re.I | re.S)
    nav = navigation_html(current, sections, home_url)
    if re.search(r'<body\b[^>]*>', page, flags=re.I):
        return re.sub(r'(<body\b[^>]*>)', lambda m: m[1] + nav, page, count=1, flags=re.I)
    return page.replace('<main', nav + '<main', 1)


def apply_design(page, target, ui=True, navigation_home=None):
    target = Path(target)
    assets = target.parent / 'road-music-design'
    shutil.copytree(ASSET_ROOT, assets, dirs_exist_ok=True)
    (assets / 'styles.css').write_text(css_text(), encoding='utf-8')
    page = re.sub(r'<link\b(?=[^>]*\bdata-road-music-design\b)[^>]*>\s*', '', page, flags=re.I)
    if ui and 'data-road-music-ui' not in page:
        page = re.sub(r'<html(?=[\s>])', '<html data-road-music-ui', page, count=1)
    if ui:
        page = add_navigation(page, current='catalog' if target.name == 'catalog.html' else 'review', home_url=navigation_home)
    link = '<link rel="stylesheet" data-road-music-design href="road-music-design/styles.css">'
    if '</head>' in page:
        return page.replace('</head>', link + '</head>', 1)
    if '</style>' in page:
        return page.replace('</style>', '</style>' + link, 1)
    return page.replace('<body', link + '<body', 1)
