import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../assets/review.html', import.meta.url), 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]).findLast(source => source.includes('const boot=window.__STUDIO_BOOTSTRAP__'));

function harness() {
  const nodes = new Map();
  const node = selector => {
    if (!nodes.has(selector)) {
      const attributes = new Map();
      nodes.set(selector, {
        disabled: false, hidden: false, value: '', textContent: '', innerHTML: '', dataset: {}, style: {},
        classList: { add() {}, remove() {}, toggle() {} },
        setAttribute(name, value) { attributes.set(name, String(value)); }, getAttribute(name) { return attributes.get(name) ?? null; },
        closest() { return null; }, querySelector() { return null; }, focus() {}, select() {},
      });
    }
    return nodes.get(selector);
  };
  const session = new Map();
  const document = { querySelector: node, querySelectorAll() { return []; }, getElementById(id) { return node('#' + id); }, addEventListener() {} };
  const context = vm.createContext({
    window: { __STUDIO_BOOTSTRAP__: { token: 'review_token_12345678' }, addEventListener() {} }, document,
    navigator: { clipboard: { async writeText() {} } }, sessionStorage: { getItem(key) { return session.get(key) ?? null; }, setItem(key, value) { session.set(key, String(value)); } },
    location: { href: 'http://127.0.0.1:40123/review/?token=review_token_12345678' }, history: { replaceState() {} },
    fetch: () => new Promise(() => {}), AbortSignal, URL, Intl, JSON, String, Number, Boolean, Object, Array, RegExp, encodeURIComponent, structuredClone,
  });
  vm.runInContext(script, context);
  return { context, node, session };
}

function state(feedback = { note: '', status: 'draft' }) {
  return { projectName: '검수 곡', reviewSession: true, feedback, media: { review: { videos: [], storyboard: [], lyrics: [], captions: [] } } };
}

assert.match(html, /id="refreshReview"/);
assert.match(html, /function feedbackNeedsSave/);
assert.match(html, /피드백을 저장하지 못해 검수를 마칠 수 없습니다/);

const successful = harness();
const requests = [];
successful.context.fetch = async (path, options = {}) => {
  requests.push({ path, options });
  return { ok: true, async json() { return {}; } };
};
vm.runInContext("state=globalThis.testState", successful.context, { filename: 'setup' });
successful.context.testState = state();
vm.runInContext('state=globalThis.testState', successful.context);
successful.node('#feedback').value = '00:32 자막 위치를 올려 주세요';
successful.node('#reviewStatus').value = 'needs-revision';
await successful.node('#completeReview').onclick();
assert.deepEqual(requests.map(request => request.path), ['/api/feedback?token=review_token_12345678', '/api/complete?token=review_token_12345678']);
assert.deepEqual(JSON.parse(requests[0].options.body), { note: '00:32 자막 위치를 올려 주세요', status: 'needs-revision' });
assert.equal(successful.node('#saveFeedback').disabled, false);
assert.equal(successful.node('#completeReview').disabled, false);
assert.match(successful.node('#completion').textContent, /검수를 마쳤습니다/);

const rejected = harness();
const rejectedRequests = [];
rejected.context.fetch = async (path, options = {}) => {
  rejectedRequests.push({ path, options });
  return { ok: false, async json() { return { error: '저장 실패' }; } };
};
rejected.context.testState = state();
vm.runInContext('state=globalThis.testState', rejected.context);
rejected.node('#feedback').value = '저장되지 않은 의견';
await rejected.node('#completeReview').onclick();
assert.deepEqual(rejectedRequests.map(request => request.path), ['/api/feedback?token=review_token_12345678']);
assert.match(rejected.node('#feedbackResult').textContent, /검수를 마칠 수 없습니다/);
assert.equal(rejected.node('#completeReview').disabled, false);

const refreshed = harness();
let release;
refreshed.context.fetch = () => new Promise(resolve => { release = resolve; });
refreshed.context.testState = state({ note: '저장된 의견', status: 'draft' });
vm.runInContext('state=globalThis.testState', refreshed.context);
refreshed.node('#feedback').value = '작성 중인 새 의견';
refreshed.node('#reviewStatus').value = 'approved';
const refresh = refreshed.node('#refreshReview').onclick();
assert.equal(refreshed.node('#feedback').disabled, true);
assert.equal(refreshed.node('#saveFeedback').disabled, true);
release({ ok: true, async json() { return state({ note: '서버의 이전 의견', status: 'draft' }); } });
await refresh;
assert.equal(refreshed.node('#feedback').value, '작성 중인 새 의견');
assert.equal(refreshed.node('#reviewStatus').value, 'approved');
assert.equal(refreshed.node('#refreshReview').disabled, false);
assert.match(refreshed.node('#refreshReviewResult').textContent, /작성 중인 피드백은 유지했습니다/);

console.log('review VM: feedback-before-complete, failure guard, shared lock, and draft-preserving refresh verified');
