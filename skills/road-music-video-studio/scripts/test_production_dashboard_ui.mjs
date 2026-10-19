import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../assets/dashboard.html', import.meta.url), 'utf8');
const script = readFileSync(new URL('../assets/dashboard.js', import.meta.url), 'utf8');
const shared = readFileSync(new URL('../assets/production-ui.js', import.meta.url), 'utf8');
const detail = readFileSync(new URL('../assets/work-detail.html', import.meta.url), 'utf8');

for (const id of ['dashboardSummary', 'dashboardTrend', 'dashboardTaskChart', 'dashboardTaskMetrics', 'dashboardSlowTasks', 'dashboardComponents', 'dashboardProjects', 'dashboardProjectSentinel', 'dashboardPromptDialog', 'dashboardPromptSentinel', 'dashboardMoreProjects', 'dashboardMorePrompts', 'dashboardMoreTasks', 'dashboardMoreFiles']) {
  assert.match(html, new RegExp(`id="${id}"`));
}
assert.doesNotMatch(html, /음악 그룹 ID|SQLITE 제작 원장/);
assert.match(html, /평균의 1\.5배/);
assert.match(script, /IntersectionObserver/);
assert.match(script, /productionProjectCursor/);
assert.match(script, /productionPromptCursor/);
assert.match(script, /productionTaskCursor/);
assert.match(script, /productionFileCursor/);
assert.match(script, /target\.length>120/);
assert.match(script, /children\.length>120/);
assert.match(script, /renderComponents/);
assert.match(script, /checkStatus/);
assert.match(script, /taskSummary/);
assert.match(script, /filter\(prompt=>!prompt\.main\)/);
assert.match(script, /스킬 묶음 업데이트/);
assert.match(script, /관리 스킬 전체 묶음/);
assert.match(script, /createElementNS/);
assert.match(shared, /navigator\.clipboard\.writeText/);
assert.match(html, /production-ui\.js\?token=/);
assert.doesNotMatch(script, /innerHTML/);
assert.match(detail, /id="dashboardLink"/);
assert.match(detail, /\/dashboard\/\?groupId=/);

const nodes = new Map();
const node = selector => {
  if (!nodes.has(selector)) nodes.set(selector, {
    dataset: {}, value: '', hidden: false, disabled: false, textContent: '', className: '', open: false, children: [],
    classList: { toggle() {} }, addEventListener() {}, append(...values) { this.children.push(...values); }, replaceChildren(...values) { this.children = values; },
    setAttribute() {}, removeAttribute() {}, showModal() { this.open = true; }, close() { this.open = false; }, querySelector() { return node('#dialog-body'); },
  });
  return nodes.get(selector);
};
const context = vm.createContext({
  window: { __STUDIO_BOOTSTRAP__: { token: 'test-token' } },
  document: { querySelector: node, createElement: tag => node(`#${tag}-${nodes.size}`), createElementNS: (_namespace, tag) => node(`#svg-${tag}-${nodes.size}`) },
  navigator: { clipboard: { async writeText() {} } }, fetch: () => new Promise(() => {}), AbortSignal, URLSearchParams, Intl, Number, String, Object, Array, Map, Set, Date, Math, JSON, encodeURIComponent, setTimeout, clearTimeout,
});
vm.runInContext(shared, context);
vm.runInContext(script, context);
assert.equal(vm.runInContext('productionMs(null)', context), '측정값 없음');
assert.equal(vm.runInContext('productionMs(30)', context), '30 ms');
assert.equal(vm.runInContext('productionMs(0.01)', context), '<0.1 ms');
assert.equal(vm.runInContext('productionBytes(undefined)', context), '용량 미기록');
assert.equal(vm.runInContext('productionTimeLabel("")', context), '시각 미기록');
assert.equal(vm.runInContext('metricNumber(null)', context), '측정값 없음');
assert.equal(vm.runInContext('slowMetric("realtimeFactor", null)', context), '측정값 없음');
assert.equal(vm.runInContext('slowBasisLabel("msPerFrame")', context), '프레임당 처리 시간');
assert.equal(vm.runInContext('JSON.stringify(projectFilter({projectId:"p",groupId:"g",domain:"mixed"}))', context), '{"projectId":"p","groupId":"g"}');
assert.equal(vm.runInContext('JSON.stringify(projectFilter({projectId:"p",groupId:"g",domain:"music"}))', context), '{"projectId":"p","groupId":"g","domain":"music"}');
assert.equal(vm.runInContext('recentTrend([{day:"2026-10-19"},{day:"2026-10-18"},{day:"2026-10-17"}]).map(row=>row.day).join(",")', context), '2026-10-17,2026-10-18,2026-10-19');
console.log('production dashboard UI: pagination, copy, safe SVG, component status, and linked group analysis are present');

vm.runInContext('renderTaskChart([{domain:"music",taskType:"generation",engine:"ace",avgElapsedMs:2000,count:2},{domain:"motion",taskType:"render",avgElapsedMs:null,count:1}])',context);
assert.equal(nodes.get('#dashboardTaskChart').children.length,2);
assert.match(nodes.get('#dashboardTaskChart').children[1].children[0].textContent,/2초 · 표본 2개/);

assert.equal(vm.runInContext('metricNumber(0.000738,"초")',context),'0.000738초');

vm.runInContext('renderComponents([{name:"소스 스킬",installedVersion:"0.1.1",checkStatus:"source-observed"}])',context);
assert.match(nodes.get('#dashboardComponents').children[0].children[1].textContent,/소스 버전 0.1.1/);
assert.match(nodes.get('#dashboardComponents').children[0].children[2].textContent,/설치 완료 기록이 아닌/);

vm.runInContext('renderComponents([{name:"초기화 전 스킬",installedVersion:"0.1.1",latestVersion:"0.1.0",checkStatus:"release-reset-required"}])',context);
const resetCard=nodes.get('#dashboardComponents').children[0];
assert.match(resetCard.children[2].textContent,/공개 Release보다 높습니다/);
assert.equal(resetCard.children[3].children[1].disabled,true);
assert.match(resetCard.children[3].children[1].title,/자동 교체를 막았습니다/);

vm.runInContext('renderComponents([{name:"배포 없음",installedVersion:"0.1.0",checkStatus:"no-release"}])',context);
assert.match(nodes.get('#dashboardComponents').children[0].children[2].textContent,/공개된 정식 배포가 없어/);

vm.runInContext('renderComponents([{name:"미설치 스킬",latestVersion:"0.1.0",checkStatus:"not-installed"}])',context);
assert.match(nodes.get('#dashboardComponents').children[0].children[1].textContent,/설치 상태 미설치/);
assert.match(nodes.get('#dashboardComponents').children[0].children[2].textContent,/install로 먼저 설치/);

const summaryCard=vm.runInContext('taskCard({taskType:"review",aiSummary:"확인한 AI 응답",resultSummary:"최종 파일 1개"})',context);
assert.ok(summaryCard.children.some(node=>node.textContent==='AI 응답: 확인한 AI 응답'));
assert.ok(summaryCard.children.some(node=>node.textContent==='결과: 최종 파일 1개'));

vm.runInContext('renderUpdateJob({action:"update",status:"running",phase:"installing",progress:null})',context);
assert.equal(nodes.get('#dashboardUpdateJob').hidden,false);
assert.ok(nodes.get('#dashboardUpdateJob').children.some(node=>node.textContent==='설치 중'));
vm.runInContext('renderUpdateJob({action:"update",status:"restart-required",progress:null})',context);
assert.equal(nodes.get('#dashboardUpdateJob').children[0].textContent,'재시작·설치 확인 필요');

const stored = new Map();
context.sessionStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value),removeItem:key=>stored.delete(key)};
context.setTimeout=()=>0;
context.fetch=async()=>{throw Error('temporary network failure')};
vm.runInContext('productionUpdateJobId="'+'c'.repeat(48)+'";rememberUpdateJob(productionUpdateJobId)',context);
await vm.runInContext('pollComponentUpdate(productionUpdateJobId)',context);
assert.equal(stored.get('road-music-update:test-token'),'c'.repeat(48));
assert.equal(nodes.get('#dashboardUpdateJob').children[0].textContent,'업데이트 상태 확인 필요');
let submitted=0;
context.fetch=async url=>{
  if(url.includes('/api/updates/update')){submitted++;throw new TypeError('lost POST response')}
  const job={jobId:'d'.repeat(48),componentId:'music-road-skills',action:'update',createdAt:Date.now(),status:'running',phase:'installing',progress:null};
  return {ok:true,json:async()=>url.includes('/jobs/')?job:{lastJobs:[job]}};
};
vm.runInContext('productionUpdateJobId=null;rememberUpdateJob(null)',context);
await vm.runInContext('startComponentUpdate("update",{componentId:"music-road-skills"})',context);
assert.equal(submitted,1);
assert.equal(stored.get('road-music-update:test-token'),'d'.repeat(48));
assert.equal(stored.has('road-music-update-attempt:test-token'),false);

vm.runInContext('productionProjects=[{projectId:"p1",title:"음악 A",domain:"music",performance:{totalElapsedMs:1000,avgElapsedMs:1000,missingElapsedCount:0,music:{totalElapsedMs:1000},motion:{totalElapsedMs:null}}},{projectId:"p2",title:"영상 B",domain:"motion",performance:{totalElapsedMs:3000,avgElapsedMs:3000,missingElapsedCount:1,music:{totalElapsedMs:null},motion:{totalElapsedMs:3000}}}];renderProjects()',context);
assert.equal(nodes.get('#dashboardProjects').children[0].children.length,7);
const rowText=n=>n.textContent+n.children.map(rowText).join(' ');
assert.match(rowText(nodes.get('#dashboardProjects').children[0]),/음악 A.*1초.*측정값 없음/s);
assert.match(rowText(nodes.get('#dashboardProjects').children[1]),/미측정 1건/);
nodes.get('#dashboardCompareSort').value='total';
vm.runInContext('renderProjects()',context);
assert.match(rowText(nodes.get('#dashboardProjects').children[0]),/영상 B/);
assert.ok(html.indexOf('id="dashboardProjectsTitle"')<html.indexOf('id="dashboardSummaryTitle"'));
