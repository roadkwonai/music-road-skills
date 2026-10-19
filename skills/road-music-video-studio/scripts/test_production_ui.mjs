import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const script = readFileSync(new URL('../assets/production-ui.js', import.meta.url), 'utf8');
const context = vm.createContext({ window: {}, Intl, Number, String, Date, Math, setTimeout });
vm.runInContext(script, context);

assert.equal(vm.runInContext('window.RoadMusicProductionUI.domainLabel("music")', context), '음악 제작');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.taskLabel("verification")', context), '검증');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.statusLabel("succeeded")', context), '완료');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.formatMs(null)', context), '측정값 없음');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.formatMs(0)', context), '0 ms');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.formatMs(0.01)', context), '<0.1 ms');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.formatMs(0,{unitGap:"",minutes:false})', context), '0ms');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.formatMs(0.01,{unitGap:"",minutes:false})', context), '<0.1ms');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.formatBytes(undefined)', context), '용량 미기록');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.formatBytes(0)', context), '0 KiB');
assert.equal(vm.runInContext('window.RoadMusicProductionUI.timeLabel("")', context), '시각 미기록');

function copyNode(tag) {
  return {
    tag, children: [], dataset: {}, attributes: {}, textContent: '', value: '', parentElement: null,
    append(...children) { for (const child of children) { child.parentElement = this; this.children.push(child); } },
    remove() { this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1); },
    querySelector(selector) { return this.children.find(child => selector.includes('fallback') ? child.dataset.productionCopyFallback : child.dataset.productionCopyStatus) || null; },
    setAttribute(name, value) { this.attributes[name] = value; }, focus() { this.focused = true; }, select() { this.selected = true; },
    addEventListener(type, listener) { this[type] = listener; },
  };
}
let rejectCopy = true;
const copyContext = vm.createContext({
  window: {}, Intl, Number, String, Date, Math, setTimeout: callback => { callback(); return 0; },
  navigator: { clipboard: { async writeText() { if (rejectCopy) throw Error('denied'); } } },
  document: { createElement: copyNode },
});
vm.runInContext(script, copyContext);
const copyHost = copyNode('article');
copyContext.copyHost = copyHost;
const copyButton = vm.runInContext('window.RoadMusicProductionUI.copyButton("원문",{fallbackHost:copyHost})', copyContext);
copyHost.append(copyButton);
await copyButton.click();
await copyButton.click();
assert.equal(copyHost.children.filter(node => node.dataset.productionCopyFallback).length, 1);
assert.equal(copyHost.children.find(node => node.dataset.productionCopyFallback).value, '원문');
assert.equal(copyHost.children.find(node => node.dataset.productionCopyFallback).attributes['aria-label'], '프롬프트 원문');
assert.equal(copyHost.children.find(node => node.dataset.productionCopyStatus).attributes.role, 'status');
assert.equal(copyHost.children.find(node => node.dataset.productionCopyStatus).textContent, '자동 복사를 허용하지 않았습니다. 프롬프트 원문을 선택해 직접 복사해 주세요.');
rejectCopy = false;
await copyButton.click();
assert.equal(copyHost.children.some(node => node.dataset.productionCopyFallback), false);
assert.equal(copyButton.textContent, '프롬프트 복사');
assert.equal(copyHost.children.find(node => node.dataset.productionCopyStatus).textContent, '프롬프트를 복사했습니다.');

console.log('production UI: shared prompt labels and zero/null/short measurement formatting are stable');

assert.equal(vm.runInContext('window.RoadMusicProductionUI.taskLabel("image-generation")', context), '이미지 생성');

const chartContext = vm.createContext({window:{},Intl,Number,String,Date,Math,setTimeout,document:{createElement:copyNode,createElementNS:(_ns,tag)=>copyNode(tag)}});
vm.runInContext(script,chartContext);
const chart = vm.runInContext('window.RoadMusicProductionUI.timeBreakdown([{domain:"music",taskType:"generation",elapsedMs:1000},{domain:"motion",taskType:"render",elapsedMs:3000},{domain:"motion",taskType:"review",elapsedMs:null,missingElapsedCount:1}])',chartContext);
const textOf = node => node.textContent + node.children.map(textOf).join(' ');
assert.match(textOf(chart),/25%/);
assert.match(textOf(chart),/75%/);
assert.match(textOf(chart),/측정값 없음/);
assert.equal(chart.children[0].attributes.role,'img');
assert.equal(chart.children[0].children.filter(n=>n.tag==='path').length,2);
const emptyChart=vm.runInContext('window.RoadMusicProductionUI.timeBreakdown([{domain:"music",taskType:"generation",elapsedMs:null}])',chartContext);
assert.doesNotMatch(textOf(emptyChart),/NaN|100%/);
assert.match(textOf(emptyChart),/측정/);

assert.equal(chart.children[0].children.filter(n=>n.tag==='text').length,2);
assert.match(textOf(chart.children[0]),/음악 생성.*25%/s);
