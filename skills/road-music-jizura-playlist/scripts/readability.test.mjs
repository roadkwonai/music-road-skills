#!/usr/bin/env node
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { auditPlan, escapeHTML } from './readability.mjs';

const hash = 'a'.repeat(64);
const project = {
  source: { sha256: hash, duration: 8 }, fps: 30,
  cueMap: [
    { line: 0, sourceLine: 1, text: '가나다라마바사', start: 0, end: 1, timingStatus: 'original-text-forced-dtw-estimated-unreviewed' },
    { line: 1, sourceLine: 2, text: '하나 둘 셋', start: 1, end: 2, timingStatus: 'user-approved-estimated-placement' },
    { line: 2, sourceLine: 3, text: 'CONFIRMED', start: 2, end: 3, timingStatus: 'asr', timingReview: { status: 'confirmed', sourceSha256: hash, textSha256: '102cf1442cf6e329f9df12a5d987fa046b68b1c5e09c3b839f0d6f27b187238c', start: 2, end: 3, method: 'manual-listening', reviewer: 'tester', evidence: 'listened' } },
    { line: 3, sourceLine: 4, text: 'LONG, ENGLISH, PHRASE, HERE', start: 3, end: 3.8, timingStatus: 'asr' }
  ]
};
const plan = { fps: 30, lines: [{ visEnd: 1 }, { visEnd: 2 }, { visEnd: 3 }, { visEnd: 3.65 }], cuts: [
  { line: 0, utext: '가나다라마바사', start: 0, end: 1, layout: 'center', cam: 'knReadPan', treatP: { scale: 1.3 }, outDur: .2 },
  { line: 1, utext: '하나둘셋', start: 1, end: 2, layout: 'center', exit: 'echoFrames' },
  { line: 2, utext: 'CONFIRMED', start: 2, end: 3, layout: 'center' },
  { line: 3, utext: 'LONG, ENGLISH, PHRASE, HERE', start: 3.04, end: 3.65, layout: 'splitScreen' }
], events: [{ t: 1.04, type: 'echoFrames' }, { t: 1.25, type: 'shake' }, { t: 1.75, type: 'slice' }] };
const before = JSON.stringify({ project, plan });
const report = auditPlan(project, plan);
assert.equal(report.status, 'needs-visual-review'); assert.equal(report.rows.length, 4);
assert.equal(report.rows[0].timing.status, 'aligned-draft'); assert.equal(report.rows[1].timing.status, 'estimated'); assert.equal(report.rows[2].timing.status, 'confirmed');
assert.ok(report.rows[0].riskFlags.includes('large-scale-pan')); assert.ok(report.rows[0].riskFlags.includes('early-exit-or-ghost'));
assert.ok(report.rows[1].riskFlags.includes('short-line-entry-effect')); assert.ok(report.rows[3].riskFlags.includes('latin-wrap-or-comma-split')); assert.ok(report.rows[3].riskFlags.includes('text-or-display-clock-mismatch'));
assert.ok(report.rows[1].sampleTimes.some(sample => sample.reason.includes('효과 echoFrames'))); assert.ok(report.rows[1].sampleTimes.every(sample => sample.time >= 1 && sample.time <= 8));
assert.ok(report.rows[1].sampleTimes.some(sample => sample.reason === '잔상 겹침 확인' && sample.time > 2));
assert.equal(JSON.stringify({ project, plan }), before); assert.equal(escapeHTML('<x&"\'>'), '&lt;x&amp;&quot;&#39;&gt;');
const stale = structuredClone(project); stale.cueMap[2].timingReview.textSha256 = 'b'.repeat(64); assert.equal(auditPlan(stale, plan).rows[2].timing.status, 'aligned-draft');
const changedTime = structuredClone(project); changedTime.cueMap[2].timingReview.end = 2.9; assert.equal(auditPlan(changedTime, plan).rows[2].timing.status, 'aligned-draft');
const changedText = structuredClone(project); changedText.cueMap[2].text = 'MUTATED'; assert.equal(auditPlan(changedText, plan).rows[2].timing.status, 'aligned-draft');
const draftReview = structuredClone(project); draftReview.cueMap[2].timingReview.status = 'draft'; assert.equal(auditPlan(draftReview, plan).rows[2].timing.status, 'aligned-draft');
const plainEstimated = structuredClone(project); plainEstimated.cueMap[3].timingStatus = 'estimated'; assert.equal(auditPlan(plainEstimated, plan).rows[3].timing.status, 'estimated');
for (const status of ['estimated-forced-dtw-low-confidence', 'estimated-free-asr-assisted', 'estimated-source-text-mismatch']) {
  const cueStatus = structuredClone(project); cueStatus.cueMap[3].timingStatus = status;
  assert.equal(auditPlan(cueStatus, plan).rows[3].timing.status, 'estimated', status);
}
for (const status of ['aligned-draft', 'auto-aligned-draft']) {
  const cueStatus = structuredClone(project); cueStatus.cueMap[3].timingStatus = status;
  assert.equal(auditPlan(cueStatus, plan).rows[3].timing.status, 'aligned-draft', status);
}
const tinyRetime = structuredClone(project); tinyRetime.cueMap[2].start += .00001; assert.notEqual(auditPlan(tinyRetime, plan).rows[2].timing.status, 'confirmed');
const earlyFade = structuredClone(plan); earlyFade.lines[0].visEnd = .5;
assert.ok(auditPlan(project, earlyFade).rows[0].riskFlags.includes('text-or-display-clock-mismatch'));
assert.ok(auditPlan(project, earlyFade).rows[0].sampleTimes.some(sample => sample.time > .5));
const divided = structuredClone(plan); divided.cuts.splice(0, 1,
  { line: 0, text: '가나다', start: 0, end: .5 }, { line: 0, text: '라마바사', start: .5, end: 1 });
assert.ok(!auditPlan(project, divided).rows[0].riskFlags.includes('text-or-display-clock-mismatch'));
assert.ok(!auditPlan(project, divided, { start: .3, end: .7 }).rows[0].riskFlags.includes('text-or-display-clock-mismatch'));
divided.cuts[1].start = .6; assert.ok(auditPlan(project, divided).rows[0].riskFlags.includes('text-or-display-clock-mismatch'));
const joined = structuredClone(plan); Object.assign(joined.cuts[1], { trans: 'inkBlob', transDur: .5 });
const joinAudit = auditPlan(project, joined).rows[1];
assert.ok(joinAudit.riskFlags.includes('previous-text-transition'));
assert.ok(joinAudit.sampleTimes.some(sample => sample.time === 1.25 && sample.reason.includes('textTransition')));
joined.cuts[0].utext = ''; joined.cuts[0].layout = 'interlude';
assert.ok(!auditPlan(project, joined).rows[1].riskFlags.includes('previous-text-transition'));
const edgeScope = auditPlan(project, plan, { start: 0, end: 1.05 }).rows[0]; assert.ok(edgeScope.sampleTimes.some(sample => sample.reason === '잔상 겹침 확인' && sample.time > 1 && sample.time < 1.05)); assert.ok(edgeScope.sampleTimes.every(sample => sample.time < 1.05));
const root = await mkdtemp(join(tmpdir(), 'jizura-readability-'));
const projectPath = join(root, 'project.json'), planPath = join(root, 'plan.json'), out = join(root, 'report.json'), video = join(root, 'tiny.mp4'), source = join(root, 'source.mp3'), reviewOut = join(root, 'review');
const run = (...args) => new Promise((resolve, reject) => { const child = spawn(process.execPath, [fileURLToPath(new URL('./readability.mjs', import.meta.url)), ...args], { stdio: ['ignore', 'pipe', 'pipe'] }); const out = [], err = []; child.stdout.on('data', d => out.push(d)); child.stderr.on('data', d => err.push(d)); child.once('exit', code => code ? reject(new Error(Buffer.concat([...out, ...err]).toString())) : resolve(JSON.parse(Buffer.concat(out).toString()))); });
try {
  await Promise.all([writeFile(projectPath, JSON.stringify(project)), writeFile(planPath, JSON.stringify(plan))]);
  assert.equal((await run('--project', projectPath, '--plan', planPath, '--out', out)).mode, 'plan-only');
  assert.equal(JSON.parse(await readFile(out)).status, 'needs-visual-review');
  await assert.rejects(() => run('--project', projectPath, '--plan', planPath, '--out', out), /새 경로/);
  try { await new Promise((resolve, reject) => { const child = spawn('ffmpeg', ['-nostdin', '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30:duration=4', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-shortest', '-y', video]); child.once('error', reject); child.once('exit', code => code ? reject(new Error('ffmpeg tiny video 실패')) : resolve()); }); }
  catch (error) { if (error.code === 'ENOENT') { console.log(JSON.stringify({ ok: true, skipped: 'ffmpeg unavailable' })); process.exit(0); } throw error; }
  const sourceData = Buffer.from('original source'), sourceSha = createHash('sha256').update(sourceData).digest('hex'), cliProject = structuredClone(project); cliProject.source = { ...cliProject.source, path: source, sha256: sourceSha }; cliProject.cueMap[2].timingReview.sourceSha256 = sourceSha; await writeFile(source, sourceData); await writeFile(projectPath, JSON.stringify(cliProject));
  const manifestRoot = join(root, 'manifest'), first = join(manifestRoot, 'first'), second = join(manifestRoot, 'second'), manifestProject = { source: { path: source, sha256: sourceSha, duration: 2 }, lyrics: 'one', cueMap: [{ line: 0, sourceLine: 1, text: '한 줄', start: 0, end: 1, displayHoldUntil: 1, timingStatus: 'estimated' }], timing: {}, overrides: {} }, manifestPlan = { fps: 30, lines: [{ visEnd: 1 }], cuts: [{ line: 0, text: '한 줄', start: 0, end: 1 }], events: [] };
  await Promise.all([mkdir(join(first, 'render'), { recursive: true }), mkdir(join(second, 'render'), { recursive: true })]);
  await Promise.all([writeFile(join(first, 'project.json'), JSON.stringify(manifestProject)), writeFile(join(second, 'project.json'), JSON.stringify(manifestProject)), writeFile(join(first, 'render', 'plan.json'), JSON.stringify(manifestPlan)), writeFile(join(second, 'render', 'plan.json'), JSON.stringify(manifestPlan)), writeFile(join(first, 'render', 'result.json'), JSON.stringify({ ok: true, actualExportSpan: { t0: 0, dur: 1 } })), writeFile(join(second, 'render', 'result.json'), JSON.stringify({ ok: true, actualExportSpan: { t0: 1, dur: 1 } }))]);
  const manifestPath = join(manifestRoot, 'composition.json'), manifestOut = join(manifestRoot, 'audit.json'); await writeFile(manifestPath, JSON.stringify({ audio: source, sourceSha256: sourceSha, start: 0, end: 2, segments: [{ start: 0, end: 1, project: join(first, 'project.json'), render: join(first, 'render', 'result.json') }, { start: 1, end: 2, project: join(second, 'project.json'), render: join(second, 'render', 'result.json') }] }));
  const manifestAudit = await run('--manifest', manifestPath, '--out', manifestOut); assert.equal(manifestAudit.rows, 1); assert.ok(JSON.parse(await readFile(manifestOut)).rows[0].sampleTimes.some(sample => sample.reason === '잔상 겹침 확인' && sample.time > 1));
  const smoke = await run('--project', projectPath, '--plan', planPath, '--video', video, '--source-start', '0', '--out', reviewOut);
  assert.equal(smoke.mode, 'video-review'); const review = JSON.parse(await readFile(join(reviewOut, 'review.json'))); assert.equal(review.visualReview, 'pending'); assert.equal(review.visualReady, false); assert.equal(review.deliveryReady, false); assert.equal(review.listeningReviewed, false); assert.ok(review.frames.length > 0); assert.equal(review.timingSummary.confirmed, 1);
  const reviewHtml = await readFile(join(reviewOut, 'review.html'), 'utf8'), reviewCss = await readFile(join(reviewOut, 'road-music-design', 'styles.css'), 'utf8');
  assert.match(reviewHtml, /data-road-music-ui/); assert.match(reviewHtml, /road-music-design\/styles\.css/); assert.match(reviewCss, /Paperlogy/);
  const chosen = review.frames.find(frame => frame.frame > 0), expected = join(root, 'expected.jpg');
  await new Promise((resolve, reject) => { const child = spawn('ffmpeg', ['-v', 'error', '-i', video, '-vf', `select=eq(n\\,${chosen.frame})`, '-frames:v', '1', '-q:v', '3', expected]); child.once('error', reject); child.once('exit', code => code ? reject(new Error('frame reference failed')) : resolve()); });
  assert.deepEqual(await readFile(join(reviewOut, chosen.file)), await readFile(expected));
  assert.equal(chosen.sourceTime, chosen.frame / review.fps);
  const offsetOut = join(root, 'offset-review'); await run('--project', projectPath, '--plan', planPath, '--video', video, '--source-start', '1', '--video-start', '1', '--out', offsetOut);
  const offset = JSON.parse(await readFile(join(offsetOut, 'review.json'))); assert.equal(offset.videoStart, 1); assert.ok(offset.frames.every(frame => frame.requestedSourceTime >= 1 && frame.requestedSourceTime <= 4 && frame.frame >= 0 && frame.localTime <= 4));
  const offsetFrame = offset.frames[0]; assert.equal(offsetFrame.frame, Math.round((offsetFrame.requestedSourceTime - 1 + 1) * offset.fps)); assert.equal(offsetFrame.sourceTime, 1 + offsetFrame.frame / offset.fps - 1);
  const offsetExpected = join(root, 'offset-expected.jpg'); await new Promise((resolve, reject) => { const child = spawn('ffmpeg', ['-v', 'error', '-i', video, '-vf', `select=eq(n\\,${offsetFrame.frame})`, '-frames:v', '1', '-q:v', '3', offsetExpected]); child.once('error', reject); child.once('exit', code => code ? reject(new Error('offset frame reference failed')) : resolve()); }); assert.deepEqual(await readFile(join(offsetOut, offsetFrame.file)), await readFile(offsetExpected));
  const template = JSON.parse(await readFile(join(reviewOut, 'decision-template.json'))), missing = { ...template, frames: [] }, missingPath = join(root, 'missing.json'), missingVerdict = join(root, 'missing-verdict.json');
  const decide = (reviewPath, decisionPath, verdictPath) => run('--review', reviewPath, '--decision', decisionPath, '--project', projectPath, '--plan', planPath, '--source-start', '0', '--out', verdictPath);
  await writeFile(missingPath, JSON.stringify(missing)); const incomplete = await decide(join(reviewOut, 'review.json'), missingPath, missingVerdict); assert.equal(incomplete.visualReady, false);
  const passing = { ...template, reviewer: 'reviewer', status: 'pass', frames: template.frames.map(frame => ({ ...frame, status: 'pass' })) }, passingPath = join(root, 'pass.json'), passVerdict = join(root, 'pass-verdict.json');
  await writeFile(passingPath, JSON.stringify(passing)); assert.equal((await decide(join(reviewOut, 'review.json'), passingPath, passVerdict)).visualReady, true);
  const trimmedReview = { ...review, frames: [review.frames[0]] }, trimmedReviewPath = join(reviewOut, 'trimmed-review.json'); await writeFile(trimmedReviewPath, JSON.stringify(trimmedReview)); await assert.rejects(() => decide(trimmedReviewPath, passingPath, join(root, 'trimmed-verdict.json')), /표본 전체/);
  const sourceLessProject = structuredClone(cliProject), sourceLessProjectPath = join(root, 'source-less-project.json'); delete sourceLessProject.source.path; await writeFile(sourceLessProjectPath, JSON.stringify(sourceLessProject)); const sourceLess = await run('--review', join(reviewOut, 'review.json'), '--decision', passingPath, '--project', sourceLessProjectPath, '--plan', planPath, '--source-start', '0', '--out', join(root, 'source-less-verdict.json')); assert.strictEqual(sourceLess.visualReady, false);
  const emptyReview = { ...review, frames: [] }, emptyReviewPath = join(root, 'empty-review.json'), emptyDecision = { videoSHA256: review.videoSHA256, sourceSha256: review.sourceSha256, reviewer: 'reviewer', status: 'pass', frames: [] }, emptyDecisionPath = join(root, 'empty-decision.json'); await writeFile(emptyReviewPath, JSON.stringify(emptyReview)); await writeFile(emptyDecisionPath, JSON.stringify(emptyDecision)); await assert.rejects(() => decide(emptyReviewPath, emptyDecisionPath, join(root, 'empty-verdict.json')), /표본 전체/);
  const relativeVideoReview = { ...review, video: 'tiny.mp4' }, relativeVideoReviewPath = join(root, 'relative-video-review.json'); await writeFile(relativeVideoReviewPath, JSON.stringify(relativeVideoReview)); await assert.rejects(() => decide(relativeVideoReviewPath, passingPath, join(root, 'relative-video-verdict.json')), /review.json 형식/);
  const badFileReview = { ...review, frames: review.frames.map((frame, index) => index ? frame : { ...frame, file: '../outside.jpg' }) }, badFileReviewPath = join(reviewOut, 'bad-file-review.json'); await writeFile(badFileReviewPath, JSON.stringify(badFileReview)); await assert.rejects(() => decide(badFileReviewPath, passingPath, join(root, 'bad-file-verdict.json')), /review frame 시계|review frame 형식/);
  const staleVideo = { ...passing, videoSHA256: 'b'.repeat(64) }, staleVideoPath = join(root, 'stale-video.json'); await writeFile(staleVideoPath, JSON.stringify(staleVideo)); await assert.rejects(() => decide(join(reviewOut, 'review.json'), staleVideoPath, join(root, 'stale-video-verdict.json')), /원음\/영상 해시/);
  const staleFrame = { ...passing, frames: passing.frames.map((frame, index) => index ? frame : { ...frame, sha256: 'c'.repeat(64) }) }, staleFramePath = join(root, 'stale-frame.json'); await writeFile(staleFramePath, JSON.stringify(staleFrame)); await assert.rejects(() => decide(join(reviewOut, 'review.json'), staleFramePath, join(root, 'stale-frame-verdict.json')), /frame 해시/);
  const staleReview = { ...review, videoSHA256: 'd'.repeat(64) }, staleReviewPath = join(root, 'stale-review.json'), matchingStaleVideo = { ...passing, videoSHA256: staleReview.videoSHA256 }, matchingStaleVideoPath = join(root, 'matching-stale-video.json'); await writeFile(staleReviewPath, JSON.stringify(staleReview)); await writeFile(matchingStaleVideoPath, JSON.stringify(matchingStaleVideo)); await assert.rejects(() => decide(staleReviewPath, matchingStaleVideoPath, join(root, 'actual-stale-video-verdict.json')), /영상 파일이 바뀌었습니다/);
  const staleFile = review.frames[0].file, staleFrameReview = { ...review, frames: review.frames.map(frame => frame.file === staleFile ? { ...frame, sha256: 'e'.repeat(64) } : frame) }, staleFrameReviewPath = join(reviewOut, 'stale-frame-review.json'), matchingStaleFrame = { ...passing, frames: passing.frames.map(frame => frame.file === staleFile ? { ...frame, sha256: 'e'.repeat(64) } : frame) }, matchingStaleFramePath = join(root, 'matching-stale-frame.json'); await writeFile(staleFrameReviewPath, JSON.stringify(staleFrameReview)); await writeFile(matchingStaleFramePath, JSON.stringify(matchingStaleFrame)); await assert.rejects(() => decide(staleFrameReviewPath, matchingStaleFramePath, join(root, 'actual-stale-frame-verdict.json')), /frame 파일이 바뀌었습니다/);
  await writeFile(source, 'changed source'); await assert.rejects(() => decide(join(reviewOut, 'review.json'), passingPath, join(root, 'changed-source-verdict.json')), /원음 파일이 바뀌었습니다/);
  console.log(JSON.stringify({ ok: true, root }));
} finally { if (!process.env.JIZURA_KEEP_TEST_OUTPUT) await rm(root, { recursive: true, force: true }); }
