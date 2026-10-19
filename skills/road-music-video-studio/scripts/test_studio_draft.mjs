import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { addNavigation } from './html-design.mjs';

const root = new URL('../assets/', import.meta.url);
const studioHtml = readFileSync(new URL('studio.html', root), 'utf8');
const resultsHtml = readFileSync(new URL('results.html', root), 'utf8');
const reviewHtml = readFileSync(new URL('review.html', root), 'utf8');
const css = readFileSync(new URL('design/design.css', root), 'utf8');

function inlineScript(html) {
  return [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]).findLast(script => script.includes('const boot=window.__STUDIO_BOOTSTRAP__'));
}

function harness(html) {
  const nodes = new Map();
  const selection = new Map();
  const node = selector => {
    if (!nodes.has(selector)) {
      const attributes = new Map(), listeners = new Map();
      nodes.set(selector, {
        checked: false, disabled: false, value: '', textContent: '', innerHTML: '', dataset: {}, files: [], hidden: false, open: false, focusCount: 0,
        classList: { add() {}, remove() {}, toggle() {} }, style: {},
        setAttribute(name, value) { attributes.set(name, String(value)); }, getAttribute(name) { return attributes.get(name) ?? null; },
        removeAttribute(name) { attributes.delete(name); },
        closest() { return null; }, querySelector() { return null; }, insertAdjacentHTML() {},
        addEventListener(name, handler) { listeners.set(name, handler); },
        showModal() { this.open = true; }, close() { this.open = false; listeners.get('close')?.(); }, focus() { this.focusCount += 1; }, select() {},
      });
      let markup = '';
      Object.defineProperty(nodes.get(selector), 'innerHTML', { get() { return markup; }, set(value) { markup = String(value); this.textContent = markup.replace(/<[^>]*>/g, ''); } });
    }
    return nodes.get(selector);
  };
  const document = {
    querySelector(selector) {
      const checked = selector.match(/^input\[name=([\w-]+)\](?:\[value=([^\]]+)\])?:checked$/);
      if (checked) return selection.get(checked[1]) ?? null;
      const byValue = selector.match(/^input\[name=([\w-]+)\]\[value=([^\]]+)\]$/);
      if (byValue) return node(`#${byValue[1]}-${byValue[2]}`);
      return node(selector);
    },
    querySelectorAll(selector) {
      if (selector === '.studio-flow a[data-flow-target]') return ['music-section', 'production-mode', 'display-section', 'save-section'].map(id => {
        const link = node('#flow-' + id); link.dataset.flowTarget = id; return link;
      });
      return [];
    }, addEventListener() {}, getElementById(id) { return node('#' + id); },
  };
  const session = new Map();
  const location = { href: 'http://127.0.0.1:40123/?token=test_token_12345678', hash: '', replace(value) { this.href = value; } };
  const context = vm.createContext({
    window: { __STUDIO_BOOTSTRAP__: { token: 'test_token_12345678' }, addEventListener() {} }, document, location,
    history: { replaceState(_state, _title, value) { location.href = String(value); } }, navigator: { clipboard: { async writeText() {} } },
    sessionStorage: { getItem(key) { return session.get(key) ?? null; }, setItem(key, value) { session.set(key, String(value)); } },
    fetch: () => new Promise(() => {}), AbortSignal, URL, Intl, JSON, String, Number, Boolean, Object, Array, RegExp,
    encodeURIComponent, structuredClone, setTimeout, clearTimeout,
  });
  vm.runInContext(inlineScript(html), context);
  return { context, node, selection, session, location };
}

assert.match(studioHtml, /<h1>영상 제작실<\/h1>/);
assert.doesNotMatch(studioHtml, /완성 파일 · 재생과 다운로드|id="finishedMedia"|id="feedback"|id="completeReview"/);
assert.match(resultsHtml, /<h1>완성 결과<\/h1>/);
assert.doesNotMatch(resultsHtml, /id="feedback"|\/api\/feedback/);
assert.match(reviewHtml, /<h1>스토리보드와 결과 검수<\/h1>/);
assert.doesNotMatch(reviewHtml, /\/downloads\/complete\.zip/);
assert.match(studioHtml, /class="studio-flow"/);
assert.match(studioHtml, /id="flowResultsLink"/);
assert.match(studioHtml, /<dialog id="decisionGuide"/);
assert.match(studioHtml, /Showreel CD/);
assert.match(studioHtml, /JIZURA 음악 스튜디오/);

const studio = harness(studioHtml);
const sparseDraft = JSON.parse(vm.runInContext('JSON.stringify(startDraft({host:"codex",mode:"showreel-motion",selection:{styleId:null},hasSavedSelection:false}))', studio.context));
assert.deepEqual(sparseDraft.display, {});
assert.deepEqual(Object.values(sparseDraft.answeredDisplay), [false, false, false, false]);

vm.runInContext('state={media:{music:{sha256:"a".repeat(64)},review:{videos:[]}}}', studio.context);
assert.equal(vm.runInContext('workResultsUrl()', studio.context), '/works/?token=test_token_12345678', 'unfinished music opens the library instead of a missing detail');
vm.runInContext('state.media.review.videos=[{name:"final.mp4"}]', studio.context);
assert.match(vm.runInContext('workResultsUrl()', studio.context), /\/works\/a{64}\//);
const playbackEvents = {};
const playbackAudio = {
  paused: true, ended: false, currentTime: 0, duration: NaN, muted: false, volume: 1, error: null,
  addEventListener(name, handler) { playbackEvents[name] = handler; },
  async play() { this.paused = false; playbackEvents.play?.(); },
  pause() { this.paused = true; playbackEvents.pause?.(); },
};
studio.context.playbackAudio = playbackAudio;
vm.runInContext('bindMusicPlayback(playbackAudio)', studio.context);
assert.match(studio.node('#musicPlaybackStatus').textContent, /재생 준비됨/);
for (const event of ['loadedmetadata', 'durationchange', 'canplay']) assert.equal(typeof playbackEvents[event], 'function', `${event} refreshes delayed duration metadata`);
playbackAudio.duration = 164.8; playbackEvents.durationchange();
assert.match(studio.node('#musicPlaybackStatus').textContent, /2:44/);
await studio.node('#musicPlay').onclick();
assert.equal(playbackAudio.paused, false, 'the explicit button starts playback from a user click');
playbackAudio.currentTime = 3; playbackEvents.timeupdate();
assert.match(studio.node('#musicPlaybackStatus').textContent, /재생 중 · 0:03/);
playbackAudio.muted = true; playbackAudio.volume = 0; playbackEvents.volumechange();
assert.equal(studio.node('#musicSound').disabled, false, 'silent audio exposes a recovery control');
await studio.node('#musicSound').onclick();
assert.equal(playbackAudio.muted, false); assert.equal(playbackAudio.volume, 1);
playbackAudio.error = { code: 3 }; playbackEvents.error();
assert.match(studio.node('#musicPlaybackStatus').textContent, /해석하지 못했습니다/, 'decode failures remain visible instead of looking silent');
const deniedAudio = { paused: true, ended: false, currentTime: 0, duration: 1, muted: false, volume: 1, error: null, addEventListener() {}, play() { return Promise.reject({ name: 'NotAllowedError' }); }, pause() {} };
studio.context.deniedAudio = deniedAudio;
vm.runInContext('bindMusicPlayback(deniedAudio)', studio.context);
await studio.node('#musicPlay').onclick();
assert.match(studio.node('#musicPlaybackStatus').textContent, /사용자 클릭/, 'autoplay permission failures give an actionable message');
assert.match(vm.runInContext('playbackError({code:4})', studio.context), /지원하지 않는/);
vm.runInContext('setFlowCurrent("display-section")', studio.context);
assert.equal(studio.node('#flow-display-section').getAttribute('aria-current'), 'step');
assert.equal(studio.node('#flow-music-section').getAttribute('aria-current'), null);
vm.runInContext(`state={projectName:'검수 곡',host:'codex',mode:'jizura',hasSavedSelection:false,modes:[{id:'jizura'},{id:'showreel-motion'}],samples:{},styles:[{id:'neon'}],media:{review:{}},selection:{styleId:null,display:{showSpectrum:null,showQueue:null,showNowPlaying:null,channelName:null}}};draft=startDraft(state);`, studio.context);
assert.equal(vm.runInContext('draft.answeredDisplay.showSpectrum', studio.context), false);
for (const key of ['showSpectrum', 'showQueue', 'showNowPlaying']) studio.selection.set(key, { value: 'skip', checked: true });
studio.node('#channelSkip').checked = true;
studio.node('#display-channelName').value = 'ignored';
studio.selection.set('host', { value: 'claude', checked: true });
studio.selection.set('style', { value: '__native__', checked: true });
vm.runInContext('capture();draft.mode="showreel-motion";', studio.context);
for (const key of ['showSpectrum', 'showQueue', 'showNowPlaying', 'channelName']) {
  assert.equal(vm.runInContext(`draft.answeredDisplay.${key}`, studio.context), true, `${key}: SKIP must survive a mode change`);
  assert.equal(vm.runInContext(`draft.display.${key}`, studio.context), null);
}
assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(selectionPayload(false))', studio.context)), {
  host: 'claude', mode: 'showreel-motion', styleId: null,
  display: { showSpectrum: null, showQueue: null, showNowPlaying: null, channelName: null },
});
assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(selectionPayload(true))', studio.context)), {
  host: 'claude', mode: 'showreel-motion', styleId: null,
  display: { showSpectrum: null, showQueue: null, showNowPlaying: null, channelName: null },
}, 'Showreel 저장은 JIZURA 요청 인자로 제작 방식을 바꾸지 않는다');
vm.runInContext('draft.mode="jizura";render()', studio.context);
assert.equal(studio.node('#saveSelection').hidden, true);
assert.equal(studio.node('#saveSelection').disabled, true);
assert.equal(studio.node('#jizuraRequest').hidden, false);
assert.equal(studio.node('#jizuraRequest').disabled, false);
assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(selectionPayload(true))', studio.context)), {
  host: 'claude', mode: 'jizura', styleId: null,
  display: { showSpectrum: null, showQueue: null, showNowPlaying: null, channelName: null }, request: 'jizura-editor',
});
vm.runInContext('draft.mode="showreel-motion";render()', studio.context);
assert.equal(studio.node('#saveSelection').hidden, false);
assert.equal(studio.node('#saveSelection').disabled, false);
assert.equal(studio.node('#jizuraRequest').hidden, true);
assert.equal(studio.node('#jizuraRequest').disabled, true);
studio.node('#studioListView').setAttribute('aria-pressed', 'true');
studio.node('#studioLargeView').setAttribute('aria-pressed', 'false');
vm.runInContext('setStudioView("large")', studio.context);
assert.equal(studio.node('main').dataset.view, 'large');
assert.equal(studio.node('#studioListView').disabled,false);
assert.equal(studio.node('#studioLargeView').disabled,false);
assert.match(studio.node('#studioLargeView').textContent,/선택/);
assert.match(studio.location.href, /[?&]view=large/);
assert.equal(studio.session.get('road-music-studio-view:test_token_12345678'), 'large');
const beforeDialog = vm.runInContext('JSON.stringify(draft)', studio.context);
vm.runInContext('openDecisionGuide({currentTarget:document.querySelector("#openDecisionGuide")})', studio.context);
assert.equal(studio.node('#decisionGuide').open, true);
assert.equal(vm.runInContext('JSON.stringify(draft)', studio.context), beforeDialog, 'opening the decision guide must not rewrite the draft');
vm.runInContext('closeDecisionGuide()', studio.context);
assert.equal(studio.node('#decisionGuide').open, false);
assert.equal(studio.node('#openDecisionGuide').focusCount, 1, 'native close event restores focus to the opener');
let focusedControl='', preventedTabs=0;
const focusControls=['first','last'].map(name=>({getClientRects:()=>[{}],focus(){focusedControl=name}}));
studio.context.focusEvent={key:'Tab',shiftKey:false,currentTarget:{querySelectorAll:()=>focusControls},preventDefault(){preventedTabs++}};
studio.context.document.activeElement=focusControls[1];
vm.runInContext('containDecisionFocus(focusEvent)',studio.context);
assert.equal(focusedControl,'first');
studio.context.focusEvent.shiftKey=true;studio.context.document.activeElement=focusControls[0];
vm.runInContext('containDecisionFocus(focusEvent)',studio.context);
assert.equal(focusedControl,'last');
studio.context.focusEvent.metaKey=true;
vm.runInContext('containDecisionFocus(focusEvent)',studio.context);
assert.equal(preventedTabs,2,'browser keyboard shortcuts remain available');
vm.runInContext('rememberDraft();draft=restoreDraft(state)', studio.context);
assert.equal(vm.runInContext('draft.host', studio.context), 'claude');
studio.session.set('road-music-studio-draft:test_token_12345678', '{bad');
vm.runInContext('draft=restoreDraft(state)', studio.context);
assert.equal(vm.runInContext('draft.host', studio.context), 'codex');
assert.equal(vm.runInContext('esc("<script>\\\"&")', studio.context), '&lt;script&gt;&quot;&amp;');
studio.node('#page-guide-source').textContent = JSON.stringify('# 제작실 안내');
studio.context.navigator.clipboard.writeText = async () => { throw new Error('denied'); };
await studio.node('#copyPageGuide').onclick();
assert.equal(studio.node('#pageCopyFallback').hidden, false);
assert.equal(studio.node('#pageCopyFallback').value, '# 제작실 안내');

vm.runInContext('draft.mode="showreel-motion";render()', studio.context);
let selectionCalls=0,resolveSelection;
studio.context.fetch=()=>{selectionCalls++;return new Promise(resolve=>{resolveSelection=()=>resolve({ok:true,async json(){return {}}})})};
const firstSave=studio.node('#saveSelection').onclick();
assert.equal(studio.node('#saveSelection').disabled,true);
assert.equal(studio.node('#jizuraRequest').disabled,true);
await studio.node('#jizuraRequest').onclick();
assert.equal(selectionCalls,1,'concurrent save buttons must share one request lock');
resolveSelection();await firstSave;
assert.equal(studio.node('#saveSelection').disabled,false);
assert.equal(studio.node('#jizuraRequest').disabled,true);
vm.runInContext('draft.mode="jizura"', studio.context);
assert.match(vm.runInContext('nextProductionMessage(false)', studio.context), /JIZURA 편집기/);
vm.runInContext('draft.mode="showreel-mv"', studio.context);
assert.match(vm.runInContext('nextProductionMessage(false)', studio.context), /Showreel MV 스킬/);
console.log('studio VM: draft capture, flow/modal preservation, native payload, view state, invalid cache, escaping, and Markdown fallback preserved');

const results = harness(resultsHtml);
vm.runInContext(`state={projectName:'검수 곡',media:{review:{audios:[{name:'완성 음악.mp3',url:'/media/music?token=test',downloadUrl:'/media/music?token=test&download=1',size:1048576,sourceStatus:'current'}],videos:[{name:'완성 영상.mp4',url:'/media/video?token=test',size:2048,sourceStatus:'current'}],lyrics:[{name:'원가사.txt',url:'/media/lyrics?token=test',downloadUrl:'/media/lyrics?token=test&download=1',text:'첫 줄\\n<script>원문</script>',size:20,sourceStatus:'current'}],captions:[{name:'자막.srt',url:'/media/srt?token=test',size:30,sourceStatus:'current'}]}}};render();`, results.context);
assert.match(results.node('#resultGroups').innerHTML, /완성 영상/);
assert.match(results.node('#resultGroups').innerHTML, /원가사/);
assert.match(results.node('#resultGroups').innerHTML, /자막\.srt/);
assert.match(results.node('#resultGroups').innerHTML, /&lt;script&gt;원문&lt;\/script&gt;/);
assert.match(results.node('#resultGroups').innerHTML, /download="원가사\.txt"/);
vm.runInContext('setView("large")', results.context);
assert.equal(results.node('main').dataset.view, 'large');
assert.match(results.location.href, /[?&]view=large/);
results.context.fetch = async () => { throw new TypeError('network internals'); };
await results.node('#refreshResults').onclick();
assert.match(results.node('#resultSummary').textContent, /제작실에 연결할 수 없습니다/);
assert.doesNotMatch(results.node('#resultSummary').textContent, /network internals/);
assert.equal(results.node('#refreshResults').disabled, false);
console.log('results VM: video, music, original lyrics, captions, list/large view, and retry recovery preserved');

const review = harness(reviewHtml);
let feedbackRequest;
review.context.fetch = async (path, options = {}) => {
  feedbackRequest = { path, options };
  return { ok: true, async json() { return {}; } };
};
vm.runInContext("state={feedback:{note:'',status:'draft'}}", review.context);
review.node('#feedback').value = '00:32 자막 위치를 올려 주세요';
review.node('#reviewStatus').value = 'needs-revision';
await review.node('#feedbackForm').onsubmit({ preventDefault() {} });
assert.equal(feedbackRequest.path, '/api/feedback?token=test_token_12345678');
assert.equal(feedbackRequest.options.headers['X-Studio-Token'], 'test_token_12345678');
assert.deepEqual(JSON.parse(feedbackRequest.options.body), { note: '00:32 자막 위치를 올려 주세요', status: 'needs-revision' });
assert.equal(review.node('#saveFeedback').disabled, false);
assert.equal(review.node('#feedbackResult').textContent, '피드백을 저장했습니다.');
assert.equal(review.session.get('road-music-review-draft:test_token_12345678'), JSON.stringify({ note: '00:32 자막 위치를 올려 주세요', status: 'needs-revision' }));
review.session.set('road-music-review-draft:test_token_12345678', JSON.stringify({ note: '새 탭 임시 의견', status: 'approved' }));
assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(restoreFeedback({note:"저장된 의견",status:"draft"}))', review.context)), { note: '새 탭 임시 의견', status: 'approved' });
review.session.set('road-music-review-draft:test_token_12345678', '{bad');
review.session.set('road-music-studio-draft:test_token_12345678', JSON.stringify({ feedback: { note: '이전 화면 의견', status: 'needs-revision' } }));
assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(restoreFeedback({note:"저장된 의견",status:"draft"}))', review.context)), { note: '이전 화면 의견', status: 'needs-revision' });
review.node('#page-guide-source').textContent = JSON.stringify('# 검수 안내');
review.context.navigator.clipboard.writeText = async () => { throw new Error('denied'); };
await review.node('#copyPageGuide').onclick();
assert.equal(review.node('#pageCopyFallback').value, '# 검수 안내');
console.log('review VM: feedback submission and Markdown fallback preserved');

for (const needle of ['.rm-help-wrap', '.rm-tooltip', '.rm-guide-tools', '.guide-layout', '.guide-sidebar', '.guide-article', '.copy-fallback', '.skip-link']) assert.match(css, new RegExp(needle.replace('.', '\\.')));
assert.match(css, /prefers-reduced-motion/);
assert.match(css, /:focus-visible/);
assert.doesNotMatch(css, /transition:\s*all/);
console.log('design CSS: guide, tooltip, focus, and reduced-motion contracts present');

for (const source of ['<body><a class="skip-link" href="#content">건너뛰기</a><main id="content">본문</main></body>', '<body><main>본문</main></body>', '<body>본문</body>']) {
  const page=await addNavigation(source,{homeURL:false});
  assert.ok(page.indexOf('class="skip-link"')<page.indexOf('data-road-music-nav'));
  assert.ok(page.includes(source.includes('id="content"')?'href="#content"':'href="#main-content"'));
  assert.equal(await addNavigation(page,{homeURL:false}),page);
}
console.log('shared Node navigation: skip-link is first and repeated injection is stable');
const portableGuide = '<html><body><main><div class="rm-guide-tools" data-rm-guide-tools><a href="road-music-design/guides/styles.html">도움말</a></div></main></body></html>';
const rebased = await addNavigation(portableGuide, { current: 'catalog', homeURL: 'http://127.0.0.1:40123/?token=test_token_12345678' });
assert.match(rebased, /http:\/\/127\.0\.0\.1:40123\/guide\/styles\/\?token=test_token_12345678/);
assert.doesNotMatch(rebased, /href="road-music-design\/guides\/styles.html"/);
assert.equal((rebased.match(/class="rm-guide-tools"/g)||[]).length,1);
