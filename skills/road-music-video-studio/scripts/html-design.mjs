import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

export const assetRoot = fileURLToPath(new URL('../assets/design/', import.meta.url));
export async function cssText(fontBase = 'fonts/', token = null) {
  const fonts = await readFile(join(assetRoot, 'fonts.css'), 'utf8');
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  return fonts.replace(/url\("fonts\/([^"/]+)"\)/g, (_, file) => `url("${fontBase}${file}${query}")`) + '\n' + await readFile(join(assetRoot, 'design.css'), 'utf8');
}
export function validStudioURL(value) {
  if (typeof value !== 'string' || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/\?token=[A-Za-z0-9_-]{16,128}$/.test(value)) return false;
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
  const links = [];
  if (home) {
    for (const [key, label, pathname, hash] of JSON.parse(await readFile(join(assetRoot, 'navigation.json'), 'utf8'))) {
      const url = new URL(home); url.pathname = pathname; url.hash = hash;
      links.push([key, label, url.href]);
    }
  }
  links.push(...sections.filter(([, href]) => /^#[A-Za-z][A-Za-z0-9_-]*$/.test(href)).map(([label, href]) => [href.slice(1), label, href]));
  if (!links.length) links.push(['top', '페이지 처음으로', '#']);
  const nav = '<nav class="rm-nav" data-road-music-nav aria-label="Road Music 페이지 이동">' + links.map(([key,label,href]) => `<a href="${escape(href)}"${key === current ? ' aria-current="page"' : ''}>${escape(label)}</a>`).join('') + '</nav>';
  page = page.replace(/<nav\b(?=[^>]*\bdata-road-music-nav\b)[^>]*>.*?<\/nav>\s*/gis, '');
  return /<body\b[^>]*>/i.test(page) ? page.replace(/(<body\b[^>]*>)/i, `$1${nav}`) : page.replace('<main', `${nav}<main`);
}
export async function applyDesign(page, target, { ui = true } = {}) {
  const assets = join(dirname(target), 'road-music-design');
  await mkdir(assets, { recursive: true });
  await cp(assetRoot, assets, { recursive: true });
  await writeFile(join(assets, 'styles.css'), await cssText());
  page = page.replace(/<link\b(?=[^>]*\bdata-road-music-design\b)[^>]*>\s*/gi, '');
  if (ui && !page.includes('data-road-music-ui')) page = page.replace(/<html(?=[\s>])/, '<html data-road-music-ui');
  if (ui) page = await addNavigation(page);
  const link = '<link rel="stylesheet" data-road-music-design href="road-music-design/styles.css">';
  if (page.includes('</head>')) return page.replace('</head>', `${link}</head>`);
  if (page.includes('</style>')) return page.replace('</style>', `</style>${link}`);
  return page.replace('<body', `${link}<body`);
}
