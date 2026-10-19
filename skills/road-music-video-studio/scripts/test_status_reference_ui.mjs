import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const statusScript = readFileSync(new URL('../assets/status.js', import.meta.url), 'utf8');
const referenceScript = readFileSync(new URL('../assets/reference.js', import.meta.url), 'utf8');
const referenceHtml = readFileSync(new URL('../assets/reference.html', import.meta.url), 'utf8');

function harness(script, data, clipboard = async () => {}, fetchImpl) {
  const nodes = new Map(), timeouts = [];
  const node = selector => {
    if (!nodes.has(selector)) {
      const listeners = new Map();
      const attributes = new Map(), classes = new Set();
      nodes.set(selector, {
        disabled: false, hidden: true, value: '', textContent: '', innerHTML: '', dataset: {}, focusCount: 0, selectCount: 0,
        addEventListener(name, handler) { listeners.set(name, handler); }, listeners,
        classList: { add(value) { classes.add(value); }, remove(value) { classes.delete(value); }, contains(value) { return classes.has(value); } },
        setAttribute(name, value) { attributes.set(name, String(value)); }, getAttribute(name) { return attributes.get(name) ?? null; }, focus() { this.focusCount += 1; }, select() { this.selectCount += 1; }, matches(value) { return value === '.reference-copy'; },
      });
    }
    return nodes.get(selector);
  };
  const context = vm.createContext({
    window: { __STUDIO_BOOTSTRAP__: { token: 'status_token_12345678' } }, document: { querySelector: node },
    navigator: { clipboard: { writeText: clipboard } }, fetch: fetchImpl || (async () => ({ ok: true, async json() { return data; } })),
    AbortSignal: { timeout(value) { timeouts.push(value); return {}; } }, URL, Intl, Date, JSON, String, Object, Array, Set, RegExp, Number, Boolean,
    encodeURIComponent, setTimeout, clearTimeout,
  });
  vm.runInContext(script, context);
  return { node, timeouts };
}

const status = harness(statusScript, {
  checkedAt: '2026-10-19T00:00:00Z', cli: { state: 'available', root: '/kit', version: { cliVersion: '0.1.0', appVersion: '0.1.0' }, schema: { commandCount: 135, groups: ['song', 'video'] } },
  service: { state: 'connected' }, runtime: { state: 'available', checks: { 'engines:list': { state: 'available', data: { engines: [{ id: 'ace', state: 'ready' }, { id: 'yue-mlx', state: 'missing' }] } }, 'queue:list': { state: 'available', data: { queue: [{ id: 'job-1', state: 'waiting' }] } } } }, skills: [],
  storage: { state: 'available', data: { capabilities: { workspaceScan: { enabled: true }, git: { enabled: false, reason: 'Git 저장소 없음 <test>' }, artifacts: { enabled: false } } } },
});
await new Promise(resolve => setTimeout(resolve, 0));
assert.deepEqual(status.timeouts, [40000]);
assert.match(status.node('#cliStatus').innerHTML, /CLI 버전/);
assert.match(status.node('#cliStatus').innerHTML, /공개 명령 수/);
assert.match(status.node('#runtimeStatus').innerHTML, /ID: ace/);
assert.match(status.node('#runtimeStatus').innerHTML, /상태: ready/);
assert.doesNotMatch(status.node('#runtimeStatus').innerHTML, /\[object Object\]/);
assert.match(status.node('#storageCapabilityStatus').innerHTML, /작업 폴더 용량/);
assert.match(status.node('#storageCapabilityStatus').innerHTML, /활성화/);
assert.match(status.node('#storageCapabilityStatus').innerHTML, /비활성화/);
assert.match(status.node('#storageCapabilityStatus').innerHTML, /Git 저장소 없음 &lt;test&gt;/);
assert.match(status.node('#storageCapabilityStatus').innerHTML, /현재 설치에서는 사용할 수 없는 검사/);
console.log('status VM: nested runtime data uses Korean key labels without object-string leakage');

const verboseStatus = harness(statusScript, {
  checkedAt: '2026-10-19T00:00:00Z', cli: { state: 'available' }, service: { state: 'connected' }, skills: [], storage: { state: 'unavailable' },
  runtime: { state: 'available', checks: { 'setup:check': { state: 'available', data: Object.fromEntries(Array.from({ length: 9 }, (_, index) => [`command${index}`, { raw: 'x'.repeat(180) }])) } } },
});
await new Promise(resolve => setTimeout(resolve, 0));
const verboseMarkup = verboseStatus.node('#runtimeStatus').innerHTML;
assert.match(verboseMarkup, /전체 응답 보기/);
assert.match(verboseMarkup, /추가 항목/);
assert.match(verboseMarkup, /command8/);
const collapsedStatus = verboseMarkup.split('<details')[0];
assert.doesNotMatch(collapsedStatus, /command8|x{180}/);
assert.ok(collapsedStatus.length < 1800);
assert.match(verboseMarkup, /x{180}/);
console.log('status VM: long command data stays summarized until the explicit full-response details view');

const failedStatus = harness(statusScript, {}, async () => {}, async () => { await Promise.resolve(); throw Error('상태 서버에 연결할 수 없습니다.'); });
await new Promise(resolve => setTimeout(resolve, 0));
for (const selector of ['#cliStatus', '#runtimeStatus', '#storageCapabilityStatus', '#skillStatus']) assert.equal(failedStatus.node(selector).getAttribute('aria-busy'), 'false', `${selector}: 실패 뒤에도 로딩 상태를 끝낸다`);
assert.equal(failedStatus.node('#refreshStatus').disabled, false, '실패 뒤에는 다시 시도할 수 있다');
assert.equal(failedStatus.node('#statusMessage').classList.contains('message-error'), true);
assert.match(failedStatus.node('#statusMessage').textContent, /상태 서버에 연결할 수 없습니다/);
console.log('status VM: asynchronous request failure clears busy state and restores refresh');

for (const [name, expected] of [['TypeError', '제작실에 연결할 수 없습니다'], ['TimeoutError', '시간이 초과'], ['SyntaxError', '응답을 읽지 못했습니다']]) {
  const broken = harness(statusScript, {}, async () => {}, async () => { const error = Error('browser failure'); error.name = name; throw error; });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(broken.node('#statusMessage').textContent.includes(expected));
  assert.equal(broken.node('#refreshStatus').disabled, false);
}

const reference = harness(referenceScript, {
  commands: [{ command: 'song:generate', group: 'song', classification: 'change', description: '곡 생성 작업을 시작합니다', required: [], fields: [{ name: 'style', required: false, type: 'string' }], example: 'node cli/road-music.js schema --json {"command":"song:generate"}', help: { useWhen: '승인 뒤 생성', avoidWhen: '승인 전 생성 금지', expected: 'jobId를 반환', example: 'node cli/road-music.js song:generate --json {"instrumental":true}', guide: 'guide/reference/#빠른-활용-순서' } }],
  guides: [{ id: 'instrument-keyboards', category: '악기', tags: ['건반', '발라드'], title: '피아노·첼로 중심', summary: '공개 악기명', useWhen: '잔잔한 보컬곡', avoidWhen: '드럼 중심 곡', expected: '방향을 요청', prompt: '피아노와 첼로로 준비해줘.', fields: ['parts.instruments'], source: 'docs/music-options.md' }],
}, async () => { throw new Error('denied'); });
await new Promise(resolve => setTimeout(resolve, 0));
assert.deepEqual(reference.timeouts, [40000]);
assert.match(reference.node('#referenceGuideList').innerHTML, /피아노·첼로 중심/);
assert.match(reference.node('#referenceGuideList').innerHTML, /사용 전 주의할 점/);
assert.match(reference.node('#referenceCategory').innerHTML, /악기/);
assert.match(reference.node('#referenceTag').innerHTML, /건반/);
assert.match(reference.node('#referenceList').innerHTML, /그룹: song/);
assert.match(reference.node('#referenceList').innerHTML, /이럴 때 사용/);
assert.match(reference.node('#referenceList').innerHTML, /<details/);
assert.match(reference.node('#referenceList').innerHTML, /\/guide\/reference\/\?token=status_token_12345678#빠른-활용-순서/);
reference.node('#referenceTag').value = '건반';
reference.node('#referenceTag').listeners.get('change')();
assert.match(reference.node('#referenceGuideList').innerHTML, /피아노·첼로 중심/);
reference.node('#referenceTag').value = '없는 태그';
reference.node('#referenceTag').listeners.get('change')();
assert.match(reference.node('#referenceGuideList').innerHTML, /조건에 맞는 활용 참고가 없습니다/);
const copy = reference.node('#referenceList').listeners.get('click');
copy({ target: { matches: value => value === '.reference-copy', dataset: { example: 'song:generate' } } });
await new Promise(resolve => setTimeout(resolve, 0));
assert.equal(reference.node('#referenceCopyFallback').hidden, false);
assert.equal(reference.node('#referenceCopyFallback').value, 'node cli/road-music.js song:generate --json {"instrumental":true}');
assert.equal(reference.node('#referenceCopyFallback').focusCount, 1);
assert.equal(reference.node('#referenceCopyFallback').selectCount, 1);
assert.match(reference.node('#referenceCopyStatus').textContent, /직접 복사/);
assert.match(referenceHtml, /id="referenceCopyFallback"/);
assert.match(referenceHtml, /id="referenceCategory"/);
assert.match(referenceHtml, /id="referenceTag"/);
console.log('reference VM: category/tag guides and denied clipboard fallback render without executing a command');
