import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { choiceDetails, canBakeDirecting, needsTimingReview, rankProfiles, preserveRecommendationState, restoreRecommendationState, restoreStudioDraft, studioDraft, tabForKey, validateAudioFile } from './studio.mjs';

const nativeChoices = { STYLES: { noir: { desc: '엔진에서 제공한 설명' } } };
assert.equal(choiceDetails('styleSelect', 'noir', '누아르', nativeChoices)[1], nativeChoices.STYLES.noir.desc);
for (const key of ['lyricpv', 'kinetic', 'wa', 'horror', 'pop', 'ballad']) {
  const [name, description] = choiceDetails('themeSelect', key, '日本語', nativeChoices);
  assert.ok(/[가-힣]/.test(name) && !/[ぁ-んァ-ン一-龯]/.test(name));
  assert.ok(description.length > 0);
}
assert.equal(choiceDetails('themeSelect', 'future', '새 테마', nativeChoices)[0], '새 테마');

const profiles = [{ id: 'ballad', name: '페이퍼 발라드', genres: ['발라드'], style: 'paper' }, { id: 'acid', name: '애시드 펄스', genres: ['EDM'], style: 'acid' }];
assert.equal(rankProfiles(profiles, { profile: 'acid' })[0].id, 'acid');
assert.equal(rankProfiles(profiles, {}, '발라드')[0].id, 'ballad');
const catalog = JSON.parse(await readFile(new URL('../directions.json', import.meta.url))).profiles;
const gentle = rankProfiles(catalog, {}, '', { bpm: 80, energy: [.4, .4, .41, .39] });
const driving = rankProfiles(catalog, {}, '', { bpm: 165, energy: [.1, 1, .1, 1] });
assert.notDeepEqual(gentle.map(p => p.id), driving.map(p => p.id));
assert.equal(new Set(gentle.map(p => p.style)).size, 3);
assert.ok(gentle[0].fx.motion < driving[0].fx.motion);
assert.equal(rankProfiles(catalog, { profile: 'paper-ballad' }, '', { bpm: 165, energy: [.1, 1] })[0].id, 'paper-ballad');
const before = { lyrics: '원문', timing: { lineTimes: { 0: 1.2 } }, fx: { motion: .4, glitch: .2 }, enabled: { decor: { ring: false } }, locks: { tech: { decor: true }, params: { motion: true } }, overrides: { 0: { lock: true, lockedCuts: [{ utext: '원문' }] }, 1: { cutTime: { start: 2 } }, 2: { cutTech: { 0: { decor: 'ring' } } } } };
const saved = preserveRecommendationState(before);
const regenerated = { fx: { motion: .9 }, enabled: { decor: { ring: true } }, overrides: {}, lyrics: '바뀐 가사', timing: {} };
restoreRecommendationState(regenerated, saved);
assert.deepEqual(regenerated.overrides, before.overrides);
assert.equal(regenerated.fx.motion, .4);
assert.equal(regenerated.enabled.decor.ring, false);
assert.equal(regenerated.lyrics, '원문');
assert.deepEqual(regenerated.timing, before.timing);
assert.equal(canBakeDirecting({ schemaVersion: 1 }, { sha256: 'abc' }, { sha256: 'abc' }), true);
assert.equal(canBakeDirecting({ schemaVersion: 1 }, { sha256: 'abc' }, { sha256: 'def' }), false);
assert.equal(needsTimingReview({ sha256: 'same' }, { sha256: 'other' }), true);
assert.equal(needsTimingReview({ sha256: 'same' }, { sha256: 'same' }), false);
const audio = { sha256: 'a'.repeat(64) };
const draft = studioDraft({ lyrics: '원문', fx: { motion: .4 } }, { source: { sha256: audio.sha256 } }, { profile: 'paper-ballad' }, 'paper-ballad', true, audio);
assert.deepEqual(restoreStudioDraft(draft, audio), {
  project: { lyrics: '원문', fx: { motion: .4 } }, sourceExtra: { source: { sha256: audio.sha256 } },
  direction: { profile: 'paper-ballad' }, selectedProfile: 'paper-ballad', timingReviewNeeded: true,
});
assert.equal(restoreStudioDraft(draft, { sha256: 'b'.repeat(64) }), null);
assert.equal(studioDraft({ lyrics: 'x'.repeat(1024 * 1024) }, {}, null, null, false, null), null);
let decoderClosed = false;
const audioBytes = new ArrayBuffer(8);
assert.equal(await validateAudioFile({ arrayBuffer: async () => audioBytes }, () => ({
  decodeAudioData: async bytes => { assert.equal(bytes, audioBytes); return { duration: 2.4 }; },
  close: async () => { decoderClosed = true; },
})), 2.4);
assert.equal(decoderClosed, true);
await assert.rejects(validateAudioFile({ arrayBuffer: async () => new ArrayBuffer(4) }, () => ({
  decodeAudioData: async () => { throw new Error('damaged'); },
  close: () => {},
})), /디코드할 수 없습니다/);
assert.equal(tabForKey('quick', 'ArrowRight'), 'editor');
assert.equal(tabForKey('quick', 'ArrowLeft'), 'help');
assert.equal(tabForKey('editor', 'Home'), 'quick');
assert.equal(tabForKey('editor', 'End'), 'help');
assert.equal(tabForKey('editor', 'Enter'), null);
const page = await readFile(new URL('./index.html', import.meta.url), 'utf8');
assert.match(page, /role="tablist"/);
for (const name of ['quick', 'editor', 'help']) {
  assert.match(page, new RegExp(`id="tab-${name}"[^>]*role="tab"[^>]*aria-controls="${name}"`));
  assert.match(page, new RegExp(`id="${name}"[^>]*role="tabpanel"[^>]*aria-labelledby="tab-${name}"`));
}
console.log('studio pure logic: ok');
