import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const sourcePath = new URL('../assets/presets/groove-dial/template/records.js', import.meta.url);
const source = await readFile(sourcePath, 'utf8');
assert.doesNotMatch(source, /로드 뮤직|여성 솔로|SIDE [A-Z]/, '특정 곡·가수·제작 메타를 템플릿에 넣지 않는다');
assert.match(source, /arc\(512, 512, 125, 0, TAU\)/, '작은 CD 라벨 반지름을 유지한다');
assert.match(source, /copy\.title, 512, 442, '800 22px Paperlogy', palette\.ink, 190/, '제목은 허브 위 작은 라벨 안에 둔다');
assert.match(source, /copy\.channel, 512, 584, '700 16px Paperlogy', palette\.accent, 190/, '채널은 허브 아래 작은 라벨 안에 둔다');
const label = { radius: 125, hub: 54, titleY: 442, titleHalfHeight: 11, titleWidth: 190, channelY: 584, channelHalfHeight: 8, channelWidth: 190 };
const chord = offset => 2 * Math.sqrt(label.radius ** 2 - offset ** 2);
assert(label.titleY + label.titleHalfHeight < 512 - label.hub, '제목이 금속 허브와 겹치지 않는다');
assert(label.channelY - label.channelHalfHeight > 512 + label.hub, '채널이 금속 허브와 겹치지 않는다');
assert(chord(Math.abs(label.titleY - label.titleHalfHeight - 512)) >= label.titleWidth, '제목 폭이 원형 라벨 안에 맞는다');
assert(chord(Math.abs(label.channelY + label.channelHalfHeight - 512)) >= label.channelWidth, '채널 폭이 원형 라벨 안에 맞는다');
const printed = [];
const gradient = { addColorStop() {} };
const context = () => ({
  save() {}, restore() {}, beginPath() {}, closePath() {}, arc() {}, clip() {}, fill() {}, stroke() {},
  fillRect() {}, strokeRect() {}, rect() {}, moveTo() {}, lineTo() {}, translate() {}, rotate() {}, drawImage() {},
  createRadialGradient: () => gradient, createLinearGradient: () => gradient, measureText: value => ({ width: String(value).length * 24 }),
  fillText(value) { printed.push(String(value)); },
});
const document = { createElement: () => ({ width: 0, height: 0, getContext: context }) };
const PLAYLIST_CONFIG = { preset: { variant: 'archive', palette: { accent: '#c76a4b', ink: '#344846', light: '#f5f5ef' } } };
const sandbox = { console, document, window: { PLAYLIST_CONFIG }, PLAYLIST_CONFIG };
vm.runInNewContext(source, sandbox, { filename: 'records.js' });
const image = { naturalWidth: 1200, naturalHeight: 900, width: 1200, height: 900 };
const copy = { title: '첫째 곡', channel: '', quotes: ['첫 줄', '둘째 줄', '셋째 줄'] };
const layers = sandbox.window.RecordLayers.create({ photos: [image, image, image], case: { ...image, naturalHeight: 1200 }, paper: image }, copy);
const target = context();
layers.drawDisc(target, { x: 960, y: 460, r: 350, angle: 25, index: 0, opacity: 1 });
layers.drawCard(target, 1, { x: 1410, y: 410, width: 525, angle: 0, opacity: 1 });
layers.drawTitleStamp(target, { x: 318, y: 182, width: 630, angle: -3, opacity: 1 });
assert.equal(JSON.stringify(layers.editorial), JSON.stringify(copy));
for (const value of ['첫째 곡', '첫 줄', '둘째 줄', '셋째 줄']) assert.ok(printed.includes(value), `${value} 인쇄 누락`);
assert.ok(!printed.includes(''), '빈 채널은 인쇄하지 않는다');
console.log('groove editorial canvas cache: ok');
