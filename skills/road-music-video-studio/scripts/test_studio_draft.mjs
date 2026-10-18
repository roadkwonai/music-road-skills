import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../assets/studio.html', import.meta.url), 'utf8');
const nodes = new Map();
const node = selector => {
  if (!nodes.has(selector)) nodes.set(selector, { checked: false, value: selector.includes('[value=skip]') ? 'skip' : '', classList: { add() {}, remove() {}, toggle() {} } });
  return nodes.get(selector);
};
const context = vm.createContext({
  window: { __STUDIO_BOOTSTRAP__: { token: 'test' }, addEventListener() {} },
  sessionStorage: {value:null,getItem(){return this.value},setItem(key,value){this.value=value}},
  document: { querySelector(selector) {
    const match = selector.match(/^input\[name=(\w+)\]:checked$/);
    if (match) return [...nodes.entries()].find(([key, value]) => key.startsWith(`input[name=${match[1]}]`) && value.checked)?.[1] || null;
    return node(selector);
  }, addEventListener() {} },
  fetch: () => new Promise(() => {}),
  structuredClone,
  AbortSignal,
});
vm.runInContext([...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1], context);
vm.runInContext(`
  state={host:'codex',mode:'jizura',hasSavedSelection:false,selection:{styleId:null,display:{showSpectrum:null,showQueue:null,showNowPlaying:null,channelName:null}},feedback:{}};
  draft=startDraft(state);
`, context);
assert.equal(vm.runInContext('draft.answeredDisplay.showSpectrum', context), false);
node('#skipAll').onclick();
vm.runInContext("capture(); draft.mode='showreel-mv'", context);
for (const key of ['showSpectrum', 'showQueue', 'showNowPlaying', 'channelName']) {
  assert.equal(vm.runInContext(`draft.answeredDisplay.${key}`, context), true, `${key}: SKIP must survive a mode change before saving`);
  assert.equal(vm.runInContext(`draft.display.${key}`, context), null);
}
vm.runInContext('state.hasSavedSelection=true; draft=startDraft(state)', context);
assert.equal(vm.runInContext('draft.answeredDisplay.channelName', context), true);
console.log('studio draft: SKIP and saved answers preserved');

vm.runInContext(`
state.media={review:{audios:[{name:'완성 음악.mp3',url:'/media/music-0?token=test',downloadUrl:'/media/music-0?token=test&download=1',size:1048576,sourceStatus:'current'}],lyrics:[{name:'원가사.txt',url:'/media/lyrics-0?token=test',downloadUrl:'/media/lyrics-0?token=test&download=1',text:'원문 첫 줄\\n<script>원문</script>',sourceStatus:'current'}],videos:[{name:'완성 모션.mp4',url:'/media/video-0?token=test',sourceStatus:'current'}]}};
renderDeliverables();
`, context);
const completed = node('#finishedMedia').innerHTML;
assert.match(completed, /음악 다운로드/);
assert.match(completed, /가사 다운로드/);
assert.match(completed, /영상 다운로드/);
assert.match(completed, /원문 첫 줄\n&lt;script&gt;원문&lt;\/script&gt;/);
assert.match(completed, /download="원가사.txt"/);
assert.match(completed, /token=test&amp;download=1/);
assert.match(completed, /1\.0 MB/);
assert.equal(node('#resultSummary').textContent, '등록된 파일: 음원 1개 · 원가사 1개 · 영상 1개');
vm.runInContext('state.media={music:{name:"입력.mp3"},review:{}};renderDeliverables()', context);
assert.match(node('#finishedMedia').innerHTML, /아직 등록된 완성 음원이 없습니다/);
assert.doesNotMatch(node('#finishedMedia').innerHTML, /입력.mp3/);
console.log('deliverables: three media types, original lyrics escaped, input music not marked completed');

vm.runInContext("state.modes=[{id:'jizura'}];state.styles=[]",context);
node('#feedback').value='아직 저장하지 않은 의견';
node('#reviewStatus').value='draft';
vm.runInContext("draft=startDraft(state);rememberDraft();draft=restoreDraft(state)",context);
assert.equal(vm.runInContext('draft.feedback.note',context),'아직 저장하지 않은 의견');
assert.equal(vm.runInContext('draft.answeredDisplay.showQueue',context),true);
vm.runInContext("sessionStorage.value='{invalid';draft=restoreDraft(state)",context);
assert.equal(vm.runInContext('draft.host',context),'codex');
console.log('navigation draft: unsaved feedback and selections restored, invalid cache ignored');

context.fetch=async()=>{throw new Error('연결 끊김')};
await node('#refreshResults').onclick();
assert.match(node('#resultSummary').textContent,/새 결과를 확인하지 못했습니다.*연결 끊김/);
assert.equal(node('#refreshResults').disabled,false);
assert.notEqual(node('#feedbackResult').textContent,'연결 끊김');
console.log('refresh failure: error remains visible beside results, retry button restored');

const failedUpload={files:[{name:'invalid.txt'}],disabled:false};
await node('#musicFile').onchange({target:failedUpload});
assert.match(node('#musicResult').textContent,/연결 끊김/);
assert.equal(failedUpload.disabled,false);
console.log('upload failure: local status and retry input restored');

context.fetch=async()=>{throw new TypeError('Failed to fetch')};
await node('#refreshResults').onclick();
assert.match(node('#resultSummary').textContent,/제작실에 연결할 수 없습니다/);
assert.doesNotMatch(node('#resultSummary').textContent,/Failed to fetch/);
console.log('network failure: Korean recovery message instead of browser internals');
