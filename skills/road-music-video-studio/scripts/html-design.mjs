import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const runFile = promisify(execFile);

export const assetRoot = fileURLToPath(new URL('../assets/design/', import.meta.url));
const iconNames = new Set(['adjustments-horizontal','arrow-down-tray','arrow-path','book-open','check-circle','chevron-down','chevron-right','clipboard-document','clipboard-document-check','document-duplicate','document-text','exclamation-triangle','film','folder-open','heart','information-circle','list-bullet','musical-note','photo','play','question-mark-circle','squares-2x2','x-mark']);
export function icon(name, cssClass = 'rm-icon') {
  if (!iconNames.has(name) || !/^[A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)*$/.test(cssClass)) throw new Error('등록된 아이콘 이름과 CSS 클래스가 필요합니다');
  return `<svg class="${cssClass}" aria-hidden="true" focusable="false"><use href="#rm-icon-${name}"></use></svg>`;
}
export async function injectIconLibrary(page) {
  if (page.includes('id="rm-icon-library"')) return page;
  const sprite = await readFile(join(assetRoot, 'heroicons.svg'), 'utf8');
  if (!/<svg\b[^>]*\bid="rm-icon-library"/i.test(sprite)) throw new Error('Heroicons 스프라이트가 올바르지 않습니다');
  return page.replace(/(<body\b[^>]*>)/i, `$1${sprite}`);
}
export async function cssText(fontBase = 'fonts/', token = null) {
  const fonts = await readFile(join(assetRoot, 'fonts.css'), 'utf8');
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  return fonts.replace(/url\("fonts\/([^"/]+)"\)/g, (_, file) => `url("${fontBase}${file}${query}")`) + '\n' + await readFile(join(assetRoot, 'design.css'), 'utf8');
}
export function validStudioURL(value) {
  if (typeof value !== 'string' || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/(?:(?:catalog|results|review|storage|dashboard|status|reference|recipes|ccm)\/|works\/(?:[0-9a-f]{64}\/)?|guide\/(?:[a-z0-9-]+\/)?)?\?token=[A-Za-z0-9_-]{16,128}(?:&(?:view=(?:list|large)|engine=(?:ACE|YuE)|(?:search|purpose|category|style|tag)=[A-Za-z0-9_%+.~-]*))*(?:#[^\s]*)?$/.test(value)) return false;
  try { const parsed = new URL(value); return Number(parsed.port) > 0 && Number(parsed.port) < 65536; } catch { return false; }
}
async function liveStudioURL() {
  const env = process.env, home = homedir();
  const root = env.ROADMUSIC_DATA_DIR || (process.platform === 'darwin' ? join(home, 'Library/Application Support/Road Music') : process.platform === 'win32' ? join(env.APPDATA || join(home, 'AppData/Roaming'), 'Road Music') : join(env.XDG_CONFIG_HOME || join(home, '.config'), 'Road Music'));
  try {
    const raw = await readFile(join(root, 'video-studio-session.json'));
    if (raw.length > 65536) return null;
    const state = JSON.parse(raw);
    return state.schemaVersion === 1 && Number.isFinite(state.expiresAt) && state.expiresAt > Date.now() / 1000 && validStudioURL(state.url) ? state.url : null;
  } catch { return null; }
}
export async function addNavigation(page, { current = 'review', sections = [], homeURL = null } = {}) {
  const home = homeURL === false ? null : (validStudioURL(homeURL) ? homeURL : await liveStudioURL()), escape = value => String(value).replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char]));
  const menu = JSON.parse(await readFile(join(assetRoot, 'navigation.json'), 'utf8'));
  const links = [];
  if (home) {
    for (const [key, label, pathname, hash] of menu) {
      const url = new URL(home); url.pathname = pathname; url.hash = hash;
      links.push([key, label, url.href]);
    }
  }
  links.push(...sections.filter(([, href]) => /^#[A-Za-z][A-Za-z0-9_-]*$/.test(href)).map(([label, href]) => [href.slice(1), label, href]));
  if (!links.length) links.push(['top', '페이지 처음으로', '#']);
  const navIcons = Object.fromEntries(menu.map(([key,,,,name]) => [key,name]));
  const nav = '<nav class="rm-nav" data-road-music-nav aria-label="Road Music 페이지 이동">' + links.map(([key,label,href]) => `<a href="${escape(href)}"${key === current ? ' aria-current="page"' : ''}>${icon(navIcons[key] || 'chevron-right')}<span>${escape(label)}</span></a>`).join('') + '</nav>';
  page = page.replace(/<nav\b(?=[^>]*\bdata-road-music-nav\b)[^>]*>.*?<\/nav>\s*/gis, '');
  const main = page.match(/<main\b[^>]*>/i);
  const target = main?.[0].match(/\bid=["']([^"']+)["']/i)?.[1] || 'main-content';
  if (main && !/\bid=/i.test(main[0])) page = page.replace(/<main\b[^>]*>/i, tag => tag.slice(0, -1) + ' id="main-content">');
  else if (!main) page = page.replace(/(<body\b[^>]*>)([\s\S]*?)(<\/body>)/i, '$1<main id="main-content">$2</main>$3');
  const skip = page.match(/<a\b(?=[^>]*\bclass=["'][^"']*\bskip-link\b)[^>]*>.*?<\/a>/is);
  if (skip) page = page.slice(0, skip.index + skip[0].length) + nav + page.slice(skip.index + skip[0].length);
  else page = /<body\b[^>]*>/i.test(page) ? page.replace(/(<body\b[^>]*>)/i, `$1<a class="skip-link" href="#${escape(target)}">본문으로 건너뛰기</a>${nav}`) : page.replace('<main', `${nav}<main`);
  if (current !== 'guide') {
    const topic = current === 'catalog' ? 'styles' : current;
    let href = `road-music-design/guides/${topic}.html`;
    if (home && ['studio','results','review','styles','jizura','works','storage','status','reference'].includes(topic)) { const url = new URL(home); url.pathname = `/guide/${topic}/`; url.hash = ''; href = url.href; }
    const tools = `<div class="rm-guide-tools" data-rm-guide-tools><a href="${escape(href)}">${icon('book-open')}<span>이 화면 사용법</span></a></div>`;
    const existing = /<div\b(?=[^>]*\bdata-rm-guide-tools\b)[^>]*>.*?<\/div>/is;
    if (existing.test(page)) page = page.replace(existing, () => tools);
    else if (!page.includes('data-rm-guide-tools')) page = page.replace(/(<main\b[^>]*>)/i, `$1${tools}`);
  }
  return injectIconLibrary(page);
}
export async function applyDesign(page, target, { ui = true } = {}) {
  const assets = resolve(dirname(target), 'road-music-design');
  await mkdir(assets, { recursive: true });
  await cp(assetRoot, assets, { recursive: true });
  await writeFile(join(assets, 'styles.css'), await cssText());
  if (ui) await runFile(process.env.SHOWREEL_PYTHON || 'python3', [fileURLToPath(new URL('./guide_content.py', import.meta.url)), '--out', assets], { timeout: 10_000 });
  page = page.replace(/<link\b(?=[^>]*\bdata-road-music-design\b)[^>]*>\s*/gi, '');
  if (ui && !/<html\b[^>]*\sdata-road-music-ui(?:\s|=|>)/i.test(page)) page = page.replace(/<html(?=[\s>])/, '<html data-road-music-ui');
  if (ui) page = await addNavigation(page);
  const link = '<link rel="stylesheet" data-road-music-design href="road-music-design/styles.css">';
  if (page.includes('</head>')) return page.replace('</head>', `${link}</head>`);
  if (page.includes('</style>')) return page.replace('</style>', `</style>${link}`);
  return page.replace('<body', `${link}<body`);
}
