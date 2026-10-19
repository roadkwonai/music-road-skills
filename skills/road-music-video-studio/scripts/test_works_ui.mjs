import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const shared = readFileSync(new URL('../assets/production-ui.js', import.meta.url), 'utf8');
const script = readFileSync(new URL('../assets/works.js', import.meta.url), 'utf8');
const worksHtml = readFileSync(new URL('../assets/works.html', import.meta.url), 'utf8');
const detailHtml = readFileSync(new URL('../assets/work-detail.html', import.meta.url), 'utf8');
const groupId = 'a'.repeat(64);

function harness(page = 'list') {
  const nodes = new Map();
  const forms = [];
  const documentListeners = new Map();
  const node = selector => {
    if (!nodes.has(selector)) {
      const attributes = new Map(), listeners = new Map();
      nodes.set(selector, {
        disabled: false, hidden: false, value: '', textContent: '', innerHTML: '', dataset: {}, options: [], style: {}, open: false, focusCount: 0, children: [],
        classList: { add() {}, remove() {}, toggle() {} },
        setAttribute(name, value) { attributes.set(name, String(value)); }, getAttribute(name) { return attributes.get(name) ?? null; }, removeAttribute(name) { attributes.delete(name); },
        closest() { return null; }, querySelector() { return null; }, addEventListener(name, handler) { listeners.set(name, handler); }, append(...values) { this.children.push(...values); }, replaceChildren(...values) { this.children = values; },
        showModal() { this.open = true; }, close() { this.open = false; listeners.get('close')?.(); }, emit(name, event = { target: this }) { listeners.get(name)?.(event); }, focus() { this.focusCount += 1; }, select() {},
      });
    }
    return nodes.get(selector);
  };
  node('main').dataset.page = page;
  const storage = new Map();
  const document = {
    querySelector(selector) { return node(selector); }, createElement(tag) { return node(`#created-${tag}-${nodes.size}`); },
    querySelectorAll(selector) { return selector === '.work-record-form' ? forms : []; },
    addEventListener(name, handler) { documentListeners.set(name, handler); },
  };
  const context = vm.createContext({
    window: { __STUDIO_BOOTSTRAP__: { token: 'works_token_12345678', groupId }, addEventListener() {} }, document,
    navigator: { clipboard: { async writeText() {} } }, sessionStorage: { getItem(key) { return storage.get(key) ?? null; }, setItem(key, value) { storage.set(key, String(value)); } },
    location: { hash: "" }, fetch: () => new Promise(() => {}), AbortSignal, URL, Intl, JSON, String, Number, Boolean, Object, Array, RegExp, Date, Map,
    encodeURIComponent, setTimeout, clearTimeout,
  });
  vm.runInContext(shared, context);
  vm.runInContext(script, context);
  return { context, node, forms, storage, documentListeners };
}

function group(overrides = {}) {
  return {
    groupId, title: '나를 믿어', styles: ['애시드'], dates: ['2026-10-19'], updatedAt: '2026-10-18T16:30:00Z',
    videoCount: 1, styleCount: 1, unclassifiedStyleCount: 0, fileCount: 4, available: true,
    source: { name: '나를 믿어.mp3', available: true, url: '/source', downloadUrl: '/source&download=1' },
    previewVideo: { name: '최종.mp4', available: true, url: '/video' }, detailUrl: '/works/' + groupId + '/?token=works_token_12345678', zipUrl: '/works/' + groupId + '/download.zip?token=works_token_12345678',
    ...overrides,
  };
}

assert.match(script, /timeZone:'Asia\/Seoul'/);
assert.match(script, /workDraftKey/);
assert.match(script, /workPage==='detail'/);
for (const html of [worksHtml, detailHtml]) {
  assert.ok(html.indexOf('/production-ui.js') < html.indexOf('/works.js'), 'load shared formatting before its consumers');
  assert.match(html, /id="openWorkHelp"/);
  assert.match(html, /<dialog id="workHelpDialog"/);
  assert.match(html, /id="closeWorkHelp"/);
}
assert.match(worksHtml, /rm-callout--note/);
assert.match(detailHtml, /rm-callout--important/);
assert.match(detailHtml, /rm-callout--warning/);
assert.match(detailHtml, /id="workArtifacts"/);
assert.match(detailHtml, /id="productionZip"/);
assert.match(detailHtml, /href="#work-versions"/);
assert.match(detailHtml, /id="work-versions"/);
assert.match(detailHtml, /id="versionProject"/);
assert.match(detailHtml, /id="versionFrom"/);
assert.match(detailHtml, /id="versionTo"/);
assert.match(detailHtml, /id="versionDiff"/);
assert.match(script, /function renderWorkVersions/);
assert.match(script, /\/versions\?projectId=/);
assert.match(script, /\/version-diff\?fromId=/);
assert.match(script, /같은 프로젝트의 버전만 비교할 수 있습니다/);
assert.match(script, /textContent/);
const versionRenderer = script.slice(script.indexOf('function renderWorkVersions'), script.indexOf('function openWorkHelp'));
assert.doesNotMatch(versionRenderer, /innerHTML/);
assert.match(versionRenderer, /textContent/);
assert.match(script, /syncChecks/);
assert.match(script, /forVideoSha256/);
assert.match(script, /styleId/);
assert.match(script, /productionZipUrl/);
assert.match(script, /productionAvailable/);
assert.match(script, /feedbackHistory/);
assert.match(script, /artifactSummary/);
assert.match(script, /function loadWorkEvents\(append=false\)/);
assert.match(script, /이전 변경 이력 더 보기/);
assert.match(script, /workEventsCursor/);
assert.match(script, /song-published/);
assert.match(script, /policy:'보존 정책 변경'/);

const list = harness();
list.node('#workSearch').value = '애시드';
list.node('#workDay').value = '2026-10-19';
vm.runInContext('workGroups=globalThis.groups;renderWorkList()', Object.assign(list.context, { groups: [group({ title: '<img src=x>' }), group({ title: '다른 곡', styles: ['발라드'], dates: ['2026-10-18'] })] }));
assert.match(list.node('#workGroups').innerHTML, /&lt;img src=x&gt;/);
assert.doesNotMatch(list.node('#workGroups').innerHTML, /다른 곡/);
assert.match(list.node('#worksStatus').textContent, /음악 그룹 1개/);
assert.equal(vm.runInContext("workDay('2026-10-18T16:30:00Z')", list.context), '2026-10-19');
console.log('works VM: Korean-time day filtering and escaped titles preserved');

list.context.fetch = async () => { throw new TypeError('browser network details'); };
vm.runInContext('workBusy=false', list.context);
await list.node('#refreshWorks').onclick();
assert.match(list.node('#worksStatus').textContent, /제작실에 연결할 수 없습니다/);
assert.doesNotMatch(list.node('#worksStatus').textContent, /browser network details/);
assert.equal(list.node('#refreshWorks').disabled, false);
console.log('works VM: failed refresh keeps a Korean recovery message and restores the control');

const favorites = harness();
let favoriteUrl = '';
favorites.context.location = { search: '?favorites=1' };
favorites.context.fetch = async url => ({ ok: true, async json() { favoriteUrl = String(url); return { groups: [] }; } });
vm.runInContext('workBusy=false', favorites.context);
await favorites.node('#refreshWorks').onclick();
assert.match(favoriteUrl, /\/api\/works\?favoritesOnly=true/);
console.log('works VM: favorite-only view requests the server-filtered music groups');

vm.runInContext('workGroups=globalThis.modalGroups', Object.assign(list.context, { modalGroups: [group()] }));
const beforeHelp = vm.runInContext('JSON.stringify(workGroups)', list.context);
list.node('#openWorkHelp').onclick({ currentTarget: list.node('#openWorkHelp') });
assert.equal(list.node('#workHelpDialog').open, true);
assert.equal(vm.runInContext('JSON.stringify(workGroups)', list.context), beforeHelp, 'opening help must preserve the current music groups');
list.node('#closeWorkHelp').onclick();
assert.equal(list.node('#workHelpDialog').open, false);
assert.equal(list.node('#openWorkHelp').focusCount, 1, 'closing help returns focus to the trigger');
list.node('#openWorkHelp').onclick({ currentTarget: list.node('#openWorkHelp') });
list.node('#workHelpDialog').emit('click');
assert.equal(list.node('#workHelpDialog').open, false, 'backdrop click closes the native dialog');
console.log('works VM: help dialog opens only on request and preserves list context');
let focusBoundary='', prevented=0;
const focusItems=['first','last'].map(name=>({getClientRects:()=>[{}],focus(){focusBoundary=name}}));
list.context.tabEvent={key:'Tab',shiftKey:false,currentTarget:{querySelectorAll:()=>focusItems},preventDefault(){prevented++}};
list.context.document.activeElement=focusItems[1];
vm.runInContext('containWorkHelpFocus(tabEvent)',list.context);
assert.equal(focusBoundary,'first');
list.context.tabEvent.shiftKey=true;list.context.document.activeElement=focusItems[0];
vm.runInContext('containWorkHelpFocus(tabEvent)',list.context);
assert.equal(focusBoundary,'last');
assert.equal(prevented,2);

const detail = harness('detail');
const syncRow = values => ({
  querySelector(selector) {
    const name = selector.match(/^\[name="(.+)"\]$/)?.[1];
    return name ? { value: values[name] ?? '' } : null;
  },
});
const form = (id, note, status, savedNote = '', savedStatus = 'draft', syncChecks = [], savedSyncChecks = []) => {
  const textarea = { value: note };
  const select = { value: status };
  return {
    dataset: { project: id, savedNote, savedStatus, savedSyncChecks: JSON.stringify(savedSyncChecks) },
    querySelector(selector) { return selector === 'textarea' ? textarea : selector === 'select' ? select : null; },
    querySelectorAll(selector) { return selector === '[data-sync-check]' ? syncChecks.map(syncRow) : []; },
  };
};
detail.forms.push(form('project-a', 'A만 보관', 'needs-revision'), form('project-b', 'B만 보관', 'approved'));
assert.equal(vm.runInContext('rememberWorkDrafts()', detail.context), true);
assert.notEqual(detail.storage.get(vm.runInContext("workDraftKey('project-a')", detail.context)), detail.storage.get(vm.runInContext("workDraftKey('project-b')", detail.context)));
assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(restoredWorkDraft({id:'project-a',feedback:{note:'server',status:'draft'}}))", detail.context)), { note: 'A만 보관', status: 'needs-revision', syncChecks: [] });
assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(restoredWorkDraft({id:'project-b',feedback:{note:'server',status:'draft'}}))", detail.context)), { note: 'B만 보관', status: 'approved', syncChecks: [] });
assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(cleanSyncChecks([{line:3,start:12.5,end:15,status:'confirmed',evidence:'원음 대조'}]))", detail.context)), [{ line: 3, start: 12.5, end: 15, status: 'confirmed', evidence: '원음 대조', videoSha256: '', captionSha256: '', lyricsSha256: '', reviewedAt: '' }]);
assert.match(vm.runInContext("syncCheckRow({reviewedAt:'2026-10-19T12:00:00+09:00'})", detail.context), /name="reviewedAt" type="hidden" value="2026-10-19T12:00:00\+09:00"/);
assert.throws(() => vm.runInContext("validateSyncChecks([{line:1,start:9,end:9,status:'confirmed',evidence:''}])", detail.context), /시작·끝 초/);
vm.runInContext("detailGroup={files:[]}", detail.context);
assert.match(vm.runInContext("syncOptions('video','b'.repeat(64))", detail.context), /이전 기록 SHA b{12}/);
const syncOnly = form('project-sync', '', 'draft', '', 'draft', [{ line: '4', start: '12.2', end: '14.8', syncStatus: 'estimated', evidence: '반복 후렴', reviewedAt: '2026-10-19T12:00:00+09:00' }], []);
detail.forms.splice(0, detail.forms.length, syncOnly);
detail.context.sessionStorage.setItem = () => { throw new Error('quota'); };
assert.equal(vm.runInContext('rememberWorkDrafts()', detail.context), false, 'sync-only change must block navigation when local draft storage fails');
let blocked = false;
detail.documentListeners.get('click')({
  target: { closest(selector) { return selector === 'a' ? { hasAttribute() { return false; }, getAttribute() { return '/works/'; } } : null; } },
  preventDefault() { blocked = true; },
});
assert.equal(blocked, true, 'before-navigation protection must retain a sync-only draft');
console.log('works VM: per-project review drafts, reviewed timestamps, and sync-only navigation protection remain isolated');

const numericRow = form('time-roundtrip', '', 'draft', '', 'draft', [{line:'1',start:'0',end:'1',syncStatus:'estimated',evidence:'예시 근거',reviewedAt:'1760842800'}], []);
detail.context.numericRow=numericRow;
assert.equal(vm.runInContext('syncChecksFromForm(numericRow)[0].reviewedAt', detail.context),1760842800);
assert.equal(vm.runInContext('cleanSyncChecks([{reviewedAt:0}])[0].reviewedAt',detail.context),0);

assert.equal(vm.runInContext("syncCounts([{status:'confirmed'},{status:'estimated'}])",detail.context),'확정 1행 · 추정 1행');

const eventCalls = [];
let eventPage = 0;
detail.context.fetch = async url => ({ ok: true, async json() { eventCalls.push(String(url)); eventPage += 1; return eventPage === 1 ? { events: [{ id: 2, action: 'song-published', createdAt: '2026-10-19T00:00:00Z' }], nextCursor: 2 } : { events: [{ id: 1, action: 'policy', createdAt: '2026-10-18T00:00:00Z' }], nextCursor: null }; } });
await vm.runInContext('loadWorkEvents()', detail.context);
assert.equal(vm.runInContext('workEvents.length', detail.context), 1);
assert.equal(vm.runInContext('workEventsCursor', detail.context), 2);
await vm.runInContext('loadWorkEvents(true)', detail.context);
assert.equal(vm.runInContext('workEvents.length', detail.context), 2);
assert.equal(vm.runInContext('workEventsCursor', detail.context), null);
assert.match(eventCalls[1], /cursor=2/);
console.log('works VM: explicit event pagination appends only the requested earlier page');

const historyTarget = { tagName: 'DETAILS', open: false, parentElement: null, scrollCount: 0, scrollIntoView() { this.scrollCount++; } };
detail.context.document.getElementById = id => id === 'work-versions' ? historyTarget : id === 'work-records' ? { contains: target => target === historyTarget } : null;
detail.context.location.hash = '#work-versions';
vm.runInContext('revealWorkHistory()', detail.context);
assert.equal(historyTarget.open, true);
assert.equal(historyTarget.scrollCount, 1);
detail.context.location.hash = '#%malformed';
vm.runInContext('revealWorkHistory()', detail.context);
assert.equal(historyTarget.scrollCount, 1);
console.log('works VM: folded version deep links open without breaking malformed hashes');
