import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { choiceDetails, canBakeDirecting, needsTimingReview, rankProfiles, preserveRecommendationState, restoreRecommendationState } from './studio.mjs';

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
console.log('studio pure logic: ok');
