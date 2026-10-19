#!/usr/bin/env node
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';

const root = await mkdtemp(join(tmpdir(), 'jizura-render-test-'));
const audio = join(root, 'tone.wav'), project = join(root, 'project.jizura.json'), directedProject = join(root, 'directing.jizura.json'), partialProject = join(root, 'partial.jizura.json'), badProject = join(root, 'bad.jizura.json'), inspected = join(root, 'inspect'), directed = join(root, 'directed'), unassigned = join(root, 'unassigned'), reloaded = join(root, 'reloaded'), rendered = join(root, 'render');
function wav() {
  const rate = 48000, seconds = 4, data = Buffer.alloc(rate * seconds * 2), header = Buffer.alloc(44);
  header.write('RIFF'); header.writeUInt32LE(36 + data.length, 4); header.write('WAVE', 8); header.write('fmt ', 12); header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22); header.writeUInt32LE(rate, 24); header.writeUInt32LE(rate * 2, 28); header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34); header.write('data', 36); header.writeUInt32LE(data.length, 40);
  for (let i = 0; i < rate * seconds; i++) data.writeInt16LE(Math.round(Math.sin(i / rate * Math.PI * 440 * 2) * 8000), i * 2);
  return Buffer.concat([header, data]);
}
function run(...args) { return new Promise((resolve, reject) => { const p = spawn(process.execPath, [fileURLToPath(new URL('./render-jizura.mjs', import.meta.url)), ...args], { env: { ...process.env, ROADMUSIC_DATA_DIR: join(root, 'profile') }, stdio: ['ignore', 'pipe', 'pipe'] }); const out = [], err = []; p.stdout.on('data', d => out.push(d)); p.stderr.on('data', d => err.push(d)); p.once('exit', code => code ? reject(new Error(Buffer.concat([...out, ...err]).toString())) : resolve(JSON.parse(Buffer.concat(out).toString()))); }); }
try {
  const wavData = wav(); await writeFile(audio, wavData);
  await writeFile(project, JSON.stringify({ version: 1, title: '', source: { sha256: createHash('sha256').update(wavData).digest('hex'), duration: 4 }, targetDuration: 4, lyrics: '[00:00.00][간주 4]', style: 'noir', mood: 'calm', aspect: '16:9', res: 360, fps: 24, includeAudio: true, timing: { bpm: 120, snap: true, tail: 0, useAudioLength: false } }));
  assert.equal((await run('--self-check')).ok, true);
  assert.equal((await run('--inspect', '--project', project, '--audio', audio, '--out', inspected, '--timeout-seconds', '90')).ok, true);
  const analysis = JSON.parse(await readFile(join(inspected, 'analysis.json')));
  assert.ok(analysis.audio.duration > 3.9 && analysis.audio.duration < 4.1);
  const fontPath = process.env.JIZURA_TEST_FONT || fileURLToPath(new URL('../../road-music-showreel-playlist/assets/template/fonts/PretendardVariable.woff2', import.meta.url));
  const fontData = await readFile(fontPath);
  const fontProject = join(root, 'font.jizura.json');
  await writeFile(fontProject, JSON.stringify({ version: 1, lyrics: '[00:00.00]FONT TEST\n[00:04.00][간주 0.01]',
    style: 'noir', lang: 'en', res: 360, fps: 24, userFonts: [{ key: 'user_StudioTest', family: 'StudioTest', label: 'Studio Test', weight: 400 }],
    fonts: { display: 'user_StudioTest', serif: 'user_StudioTest', body: 'user_StudioTest' },
    fontAssets: [{ key: 'user_StudioTest', path: fontPath, sha256: createHash('sha256').update(fontData).digest('hex') }],
    timing: { offset: 0, tail: 0, snap: false, useAudioLength: false } }));
  await run('--inspect', '--project', fontProject, '--audio', audio, '--out', join(root, 'font-inspect'), '--timeout-seconds', '90');
  const fontAnalysis = JSON.parse(await readFile(join(root, 'font-inspect/analysis.json')));
  assert.deepEqual(fontAnalysis.restoredFontAssets, ['user_StudioTest']);
  assert.deepEqual(fontAnalysis.missingUserFonts, []);
  await writeFile(badProject, JSON.stringify({ style: 'missing-style', lyrics: 'x' }));
  await assert.rejects(() => run('--inspect', '--project', badProject, '--audio', audio, '--out', join(root, 'bad-out'), '--timeout-seconds', '90'), /없는 스타일/);
  const hash = createHash('sha256').update(wavData).digest('hex');
  await writeFile(partialProject, JSON.stringify({ version: 1, source: { sha256: hash, duration: 4 }, lyrics: '[00:00.00]안녕\n[00:02.00]안녕\n[00:04.00][간주 0.01]', style: 'noir', fps: 24, timing: { bpm: 120, snap: false }, directing: { schemaVersion: 1, sourceSha256: hash, accents: [{ time: .25, type: 'shake', amp: 1, dur: 1 / 24 }, { time: 4, type: 'flash', amp: 1, dur: 1 / 24 }] } }));
  await assert.rejects(() => run('--inspect', '--project', partialProject, '--audio', audio, '--out', unassigned, '--timeout-seconds', '90'), /active lyric cut/);
  const unassignedReport = JSON.parse(await readFile(join(unassigned, 'directing-report.json')));
  assert.deepEqual({ ok: unassignedReport.ok, matched: unassignedReport.matched, unassigned: unassignedReport.unassigned.length }, { ok: false, matched: 1, unassigned: 1 });
  await writeFile(directedProject, JSON.stringify({ version: 1, title: '', source: { sha256: hash, duration: 4, path: audio }, targetDuration: 4, lyrics: '[00:00.00]안녕\n[00:02.00]안녕\n[00:04.00][간주 0.01]', cueMap: [{ line: 0, sourceLine: 1, text: '안녕', start: 0, end: 2, timingStatus: 'forced-dtw-unreviewed' }, { line: 1, sourceLine: 2, text: '안녕', start: 2, end: 4, timingStatus: 'user-approved-estimated-placement' }], style: 'noir', mood: 'calm', aspect: '16:9', res: 360, fps: 24, includeAudio: true, timing: { bpm: 120, snap: false, tail: 0, useAudioLength: false }, overrides: { '0': { cuts: 1 }, '1': { cuts: 1 } }, directing: { schemaVersion: 1, sourceSha256: hash, accents: [{ time: 0, type: 'chroma', amp: .2, dur: 1 / 24 }, { time: 0, type: 'chroma', amp: .7, dur: .1 }, { time: .25, type: 'shake', amp: 1, dur: 1 / 24 }, { time: 2.25, type: 'flash', amp: .8, dur: 1 / 24 }], schemes: [{ start: 0, end: 4, index: 0 }], motifs: [{ lines: [0, 1] }] } }));
  const directedResult = await run('--inspect', '--project', directedProject, '--audio', audio, '--out', directed, '--timeout-seconds', '90');
  assert.equal(directedResult.ok, true);
  const readability = JSON.parse(await readFile(join(directed, 'readability.json')));
  assert.equal(readability.status, 'needs-visual-review');
  assert.deepEqual(readability.rows.map(row => row.timing.status), ['aligned-draft', 'estimated']);
  const directingReport = JSON.parse(await readFile(join(directed, 'directing-report.json')));
  assert.equal(directingReport.matched, 4); assert.equal(directingReport.unassigned.length, 0);
  assert.deepEqual(directingReport.actualAppliedEvents.find(event => event.type === 'chroma'), { time: 0, type: 'chroma', amp: .7, dur: .1, line: 0, dt: 0 });
  const baked = JSON.parse(await readFile(join(directed, 'directed.jizura.json')));
  assert.equal(baked.directing, undefined); assert.equal(baked.directingProvenance.schemaVersion, 1); assert.equal(baked.timing.snap, false);
  assert.equal(baked.source.sha256, hash);
  const reloadResult = await run('--inspect', '--project', join(directed, 'directed.jizura.json'), '--audio', audio, '--out', reloaded, '--timeout-seconds', '90');
  assert.equal(reloadResult.ok, true);
  const directedPlan = JSON.parse(await readFile(join(directed, 'plan.json'))), reloadedPlan = JSON.parse(await readFile(join(reloaded, 'plan.json')));
  const cuts = plan => plan.cuts.filter(c => c.line === 0 || c.line === 1).map(c => ({ line: c.line, layout: c.layout, params: c.params, decor: c.decor, bg: c.bg, cam: c.cam, trans: c.trans, scheme: c.scheme, events: plan.events.filter(e => e.t >= c.start && e.t < c.end).map(e => ({ t: +e.t.toFixed(4), type: e.type, amp: e.amp, dur: e.dur })) }));
  assert.deepEqual(cuts(reloadedPlan), cuts(directedPlan));
  const done = await run('--render', '--project', project, '--audio', audio, '--out', rendered, '--timeout-seconds', '300');
  assert.equal(done.ok, true); assert.ok(done.frames > 0); assert.equal(done.productionWarning, undefined);
  assert.deepEqual(JSON.parse(await readFile(join(rendered, 'result.json'))).actualExportSpan, { t0: 0, dur: 4 });
  const lyricRender = await run('--render', '--project', join(directed, 'directed.jizura.json'), '--audio', audio, '--out', join(root, 'lyric-render'), '--timeout-seconds', '300');
  assert.equal(lyricRender.ok, true);
  const lyricReview = JSON.parse(await readFile(join(root, 'lyric-render/readability-final/review.json')));
  assert.equal(lyricReview.visualReview, 'pending');
  assert.equal(lyricReview.listeningReviewed, false);
  assert.ok(lyricReview.frames.length >= 6);
  assert.ok(lyricReview.frames.every(frame => /^[0-9a-f]{64}$/.test(frame.sha256)));
  const silentProject = join(root, 'silent.jizura.json');
  await writeFile(silentProject, JSON.stringify({ version: 1, lyrics: '[00:00.00][간주 2]\n[00:02.00][간주 2]',
    style: 'noir', aspect: '9:16', res: 360, fps: 30, includeAudio: false,
    exportRange: { from: 1, to: 1 }, timing: { offset: 0, tail: 0, snap: false, useAudioLength: false } }));
  const silent = await run('--render', '--project', silentProject, '--audio', audio, '--out', join(root, 'silent'), '--timeout-seconds', '300');
  const silentResult = JSON.parse(await readFile(join(root, 'silent/result.json')));
  assert.equal(silent.ok, true); assert.equal(silentResult.audioExpected, false);
  assert.equal(silentResult.audio, undefined); assert.equal(silentResult.actualExportSpan.t0, 1.75);
  assert.ok(silentResult.video.height > silentResult.video.width);
  console.log(JSON.stringify({ ok: true, root, output: done.output }));
} finally { if (!process.env.JIZURA_KEEP_TEST_OUTPUT) await rm(root, { recursive: true, force: true }); }
