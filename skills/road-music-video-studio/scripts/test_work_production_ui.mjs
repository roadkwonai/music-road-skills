import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const list = readFileSync(new URL('../assets/works.html', import.meta.url), 'utf8');
const detail = readFileSync(new URL('../assets/work-detail.html', import.meta.url), 'utf8');
const script = readFileSync(new URL('../assets/work-production.js', import.meta.url), 'utf8');
const shared = readFileSync(new URL('../assets/production-ui.js', import.meta.url), 'utf8');
const works = readFileSync(new URL('../assets/works.js', import.meta.url), 'utf8');
const design = readFileSync(new URL('../assets/design/design.css', import.meta.url), 'utf8');

assert.match(list, /\/work-production\.js\?token=/);
assert.match(detail, /\/work-production\.js\?token=/);
assert.match(script, /\/api\/production\/\$\{kind\}/);
for (const endpoint of ['prompts', 'tasks', 'files']) assert.match(script, new RegExp(`'${endpoint}'`));
assert.match(script, /groupId=\$\{encodeURIComponent\(groupId\)\}/);
assert.match(script, /workProductionMainPrompts/);
assert.match(script, /workProductionPromptCursor/);
assert.match(script, /workProductionRequests\[kind\]/);
assert.match(script, /workProductionUI\.copyButton/);
assert.match(script, /workFavoriteButton/);
assert.match(script, /\/favorite/);
assert.match(script, /favorites/);
assert.match(script, /rm-icon-heart/);
assert.match(script, /aria-label',value\?'좋아요 취소':'좋아요 추가'/);
assert.match(script, /fill',value\?'currentColor':'none'/);
assert.match(script, /aria-busy/);
assert.match(design, /\.work-favorite \.rm-icon \{ fill: none; stroke: currentColor;/);
assert.match(design, /\.work-favorite\[aria-pressed=true\] \.rm-icon \{ color: var\(--rm-negative\); fill: currentColor;/);
assert.match(script, /workProductionCap/);
assert.match(script, /children\.length>120/);
assert.match(script, /workProductionElapsed/);
assert.match(list, /production-ui\.js\?token=/);
assert.match(detail, /production-ui\.js\?token=/);
assert.match(script, /filter\(item=>kind!=='prompts'\|\|!item\.main\)/);
assert.doesNotMatch(script, /workFavoriteDecorate\(\).*workProductionStatus/);
assert.match(script, /workFavoriteRefreshPending/);
assert.match(script, /완료 후 선택한 좋아요 필터를 적용합니다/);
assert.match(script, /AI 응답:/);
assert.match(script, /결과:/);
assert.match(script, /textContent/);
assert.doesNotMatch(script, /innerHTML/);
assert.match(works, /favoritesOnly=true/);

const main = { dataset: { page: 'none' } };
let favoriteRetry;
const favoriteContext = vm.createContext({
  window: { __STUDIO_BOOTSTRAP__: { token: 'test-token' } }, location: { origin: 'http://127.0.0.1:1', search: '' },
  document: { querySelector(selector) { return selector === '#main-content' ? main : null; }, createElement() { return { children: [], append(...nodes) { this.children.push(...nodes); }, addEventListener() {} }; }, createElementNS() {} },
  fetch: async () => ({ ok: true, async json() { return { favorite: true, likedAt: '2026-10-19T12:00:00Z' }; } }),
  AbortSignal, Intl, Number, String, Object, Array, Map, Set, Date, Math, JSON, encodeURIComponent, setTimeout: callback => { favoriteRetry = callback; return 0; }, clearTimeout,
});
vm.runInContext(shared, favoriteContext);
vm.runInContext(script, favoriteContext);
vm.runInContext('workGroups=[{groupId:"a",favorite:false,likedAt:null}]', favoriteContext);
await vm.runInContext('workFavoriteSet("a",true)', favoriteContext);
assert.equal(vm.runInContext('JSON.stringify(workGroups[0])', favoriteContext), '{"groupId":"a","favorite":true,"likedAt":"2026-10-19T12:00:00Z"}');

function favoriteNode(tag) {
  const attributes = new Map(), listeners = new Map(), classes = new Set();
  return {
    tagName: tag.toUpperCase(), children: [], disabled: false, className: '',
    classList: { add(...names) { names.forEach(name => classes.add(name)); }, contains(name) { return classes.has(name); } },
    setAttribute(name, value) { attributes.set(name, String(value)); }, getAttribute(name) { return attributes.get(name) ?? null; }, removeAttribute(name) { attributes.delete(name); },
    append(...nodes) { this.children.push(...nodes); }, replaceChildren(...nodes) { this.children = nodes; },
    addEventListener(name, handler) { listeners.set(name, handler); }, emit(name) { return listeners.get(name)?.({ currentTarget: this }); },
  };
}
favoriteContext.document.createElement = favoriteNode;
favoriteContext.document.createElementNS = (_, tag) => favoriteNode(tag);
favoriteContext.document.createTextNode = text => ({ nodeType: 3, textContent: String(text) });
vm.runInContext('workFavoriteMap.set("heart",{favorite:false,likedAt:null})', favoriteContext);
const heart = vm.runInContext('workFavoriteButton("heart")', favoriteContext);
const icon = heart.children[0];
assert.equal(heart.className, 'secondary work-favorite');
assert.equal(heart.getAttribute('aria-pressed'), 'false');
assert.equal(heart.getAttribute('aria-label'), '좋아요 추가');
assert.equal(icon.getAttribute('fill'), 'none');
assert.equal(icon.getAttribute('stroke'), 'currentColor');
assert.equal(icon.getAttribute('stroke-width'), '1.75');
assert.equal(heart.children[1].textContent, '좋아요');
let favoritePosts = 0, resolveFavorite;
favoriteContext.fetch = async () => {
  favoritePosts += 1;
  return new Promise(resolve => { resolveFavorite = () => resolve({ ok: true, async json() { return { favorite: true, likedAt: '2026-10-19T12:00:00Z' }; } }); });
};
const firstFavorite = heart.emit('click');
heart.emit('click');
assert.equal(favoritePosts, 1, '좋아요 저장 중에는 중복 요청을 보내지 않습니다.');
assert.equal(heart.disabled, true);
assert.equal(heart.getAttribute('aria-busy'), 'true');
resolveFavorite();
await firstFavorite;
assert.equal(heart.disabled, false);
assert.equal(heart.getAttribute('aria-busy'), null);
assert.equal(heart.getAttribute('aria-pressed'), 'true');
assert.equal(heart.getAttribute('aria-label'), '좋아요 취소');
assert.equal(heart.children[0].getAttribute('fill'), 'currentColor');
assert.equal(heart.children[0].getAttribute('stroke'), 'currentColor');
favoriteContext.fetch = async () => ({ ok: false, async json() { return { error: '저장 실패' }; } });
await heart.emit('click');
assert.equal(heart.getAttribute('aria-pressed'), 'true', '저장 실패 시 기존 좋아요 상태를 유지합니다.');
assert.equal(heart.children[0].getAttribute('fill'), 'currentColor');
const rerenderedHeart = vm.runInContext('workFavoriteButton("heart")', favoriteContext);
assert.equal(rerenderedHeart.getAttribute('aria-pressed'), 'true', '목록을 다시 그려도 SQLite 응답 상태를 사용합니다.');
assert.equal(rerenderedHeart.children[0].getAttribute('fill'), 'currentColor');
console.log('work production UI: favorite hearts distinguish outlined and filled states, retain state on failure, and block duplicate saves');

vm.runInContext('workBusy=true;workFavoriteRefresh()', favoriteContext);
assert.equal(vm.runInContext('workFavoriteRefreshPending', favoriteContext), true);
assert.equal(typeof favoriteRetry, 'function');
console.log('work production UI: group-scoped records, copy, pagination, and favorite controls are wired');

assert.equal(vm.runInContext('workProductionElapsed(0)',favoriteContext),'0ms');
const card=vm.runInContext('workProductionPromptCard({intent:"create",prompt:"원문",taskSummary:{latest:{taskType:"verification",status:"succeeded",summary:"파일 1개",aiSummary:"검수 응답"}}})',favoriteContext);
assert.equal(card.children[0].textContent,'제작 요청');
assert.equal(card.children[3].textContent,'검증 · 완료 · 파일 1개');
assert.equal(card.children[4].textContent,'AI 응답: 검수 응답');

const titledCard=vm.runInContext('workProductionPromptCard({intent:"create",projectTitle:"이미지 준비",prompt:"복사할 원문"})',favoriteContext);
assert.match(titledCard.children[1].textContent,/프로젝트: 이미지 준비/);
assert.equal(titledCard.children[2].textContent,'복사할 원문');
