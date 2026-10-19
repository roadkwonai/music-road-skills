#!/usr/bin/env node
// Candidate finder only: rendered frames still need visual review.
import { spawn } from 'node:child_process';
import { access, mkdir, readFile, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, isAbsolute, join } from 'node:path';
import { applyDesign } from '../../road-music-video-studio/scripts/html-design.mjs';

const fail = message => { throw new Error(message); };
const exists = path => access(path, constants.R_OK).then(() => true, () => false);
const finite = (value, name) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(`${name}: 유한한 숫자가 필요합니다`);
  return value;
};
const norm = value => String(value || '').replace(/\s+/g, '').replace(/[\u200b\ufeff]/g, '');
const textHash = value => createHash('sha256').update(String(value || ''), 'utf8').digest('hex');
const sha256 = async path => createHash('sha256').update(await readFile(path)).digest('hex');
const json = async path => JSON.parse(await readFile(path, 'utf8'));
const round = value => +value.toFixed(6);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const nonempty = value => typeof value === 'string' ? !!value.trim() : !!(value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length);
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;

function timingOf(cue, sourceSha256) {
  const originalStatus = typeof cue.timingStatus === 'string' ? cue.timingStatus : null;
  const review = cue.timingReview;
  const verified = review && typeof review === 'object' && review.status === 'confirmed' &&
    ['manual-listening', 'user-confirmed'].includes(review.method) && typeof review.reviewer === 'string' && review.reviewer.trim() &&
    nonempty(review.evidence) && /^[0-9a-f]{64}$/i.test(review.sourceSha256 || '') &&
    String(review.sourceSha256).toLowerCase() === String(sourceSha256 || '').toLowerCase() &&
    String(review.textSha256 || '').toLowerCase() === textHash(cue.text).toLowerCase() &&
    Number.isFinite(review.start) && Number.isFinite(review.end) &&
    review.start === cue.start && review.end === cue.end;
  if (verified) return { status: 'confirmed', originalStatus, evidence: review.evidence };
  const lower = String(originalStatus || '').toLowerCase();
  // This legacy label meant an unreviewed tool draft, not a failed alignment placement.
  if (lower === 'original-text-forced-dtw-estimated-unreviewed') return { status: 'aligned-draft', originalStatus, evidence: cue.timingEvidence ?? null };
  if (lower.includes('estimated')) return { status: 'estimated', originalStatus, evidence: cue.timingEvidence ?? null };
  if (['aligned-draft', 'auto-aligned-draft'].includes(lower) || /(forced|dtw|asr)/.test(lower)) return { status: 'aligned-draft', originalStatus, evidence: cue.timingEvidence ?? null };
  return { status: 'unreviewed', originalStatus, evidence: cue.timingEvidence ?? null };
}

function orderedUnique(samples) {
  const seen = new Map();
  for (const sample of samples) {
    const key = sample.time.toFixed(6);
    const prior = seen.get(key);
    if (prior) prior.reason = `${prior.reason}, ${sample.reason}`;
    else seen.set(key, sample);
  }
  return [...seen.values()].sort((a, b) => a.time - b.time);
}

function postTailSamples(end, fps, scopeEnd) {
  return [end + 1 / fps, end + .1].filter(time => time < scopeEnd - 1e-9).map(time => ({ time: round(time), reason: '잔상 겹침 확인' }));
}

function cueSamples(start, end, events, riskFlags, fps, scopeEnd = end) {
  const duration = Math.max(0, end - start);
  const last = Math.max(start, end - 1 / fps);
  const clampTime = time => round(Math.max(start, Math.min(last, time)));
  const edge = Math.min(.18, duration * .25);
  const tail = Math.min(.15, duration * .2);
  const samples = [
    { time: start + edge, reason: '입구' },
    { time: start + duration / 2, reason: '중간' },
    { time: end - tail, reason: '끝' }
  ].map(sample => ({ ...sample, time: clampTime(sample.time) }));
  const eventRisk = new Set(['echoFrames', 'chroma', 'slice', 'shake', 'zoomPunch', 'rotateSnap', 'radialChroma', 'flash', 'lightSweep', 'typewriter', 'stagger', 'textTransition']);
  for (const event of events) if (eventRisk.has(event.type)) {
    const t = Number(event.t);
    if (t >= start && t <= end) {
      const duration = Math.max(0, Number(event.dur) || 0);
      for (const [time, stage] of [[t, '시작'], [t + duration / 2, '중간'], [t + duration, '끝']]) samples.push({ time: clampTime(time), reason: `효과 ${event.type} ${stage}` });
    }
  }
  if (riskFlags.includes('early-exit-or-ghost')) samples.push({ time: round(Math.max(start, end - Math.min(.04, duration / 3))), reason: '잔상/소멸 확인' });
  samples.push(...postTailSamples(end, fps, scopeEnd));
  return orderedUnique(samples);
}

function cutsForLine(plan, nativeLine) {
  return (Array.isArray(plan.cuts) ? plan.cuts : []).filter(cut => cut && cut.line === nativeLine && norm(cut.utext ?? cut.text ?? cut.lineText));
}

function sourceLines(project) {
  if (!Array.isArray(project.cueMap)) fail('project.cueMap 배열이 필요합니다');
  return project.cueMap.map((cue, index) => {
    if (!cue || typeof cue !== 'object' || typeof cue.text !== 'string' || !Number.isInteger(cue.line) || !Number.isFinite(cue.start) || !Number.isFinite(cue.end) || cue.end <= cue.start) fail(`cueMap[${index}] 가사/행/시계가 올바르지 않습니다`);
    return cue;
  });
}

function intervalCoverage(cuts, start, end) {
  const intervals = cuts.map(cut => ({ start: Number(cut.start), end: Number(cut.end) })).filter(interval => Number.isFinite(interval.start) && Number.isFinite(interval.end) && interval.end > interval.start).sort((a, b) => a.start - b.start);
  if (!intervals.length || intervals[0].start > start + .035) return false;
  let covered = intervals[0].end;
  for (const interval of intervals.slice(1)) { if (interval.start > covered + .035) return false; covered = Math.max(covered, interval.end); }
  return covered >= end - .035;
}

/**
 * Finds timing/readability candidates without claiming a pixel or listening pass.
 * It never mutates project or plan.
 */
export function auditPlan(project, plan, { start = 0, end = project?.source?.duration } = {}) {
  if (!project || typeof project !== 'object' || !plan || typeof plan !== 'object') fail('project와 plan 객체가 필요합니다');
  const sourceSha256 = String(project.source?.sha256 || '').toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(sourceSha256)) fail('project.source.sha256 64자리가 필요합니다');
  finite(start, 'start'); finite(end, 'end'); if (end <= start) fail('검수 범위 start..end가 올바르지 않습니다');
  if (start < 0 || end > finite(project.source.duration, 'source.duration') + .001) fail('검수 범위가 원음 길이를 벗어납니다');
  const fps = Number(plan.fps) || Number(project.fps) || 30;
  const allEvents = Array.isArray(plan.events) ? plan.events : [];
  const cues = sourceLines(project);
  const rows = [];
  for (const cue of cues) {
    if (cue.start < 0 || cue.end > project.source.duration + .001) fail('cueMap 시각이 원음 길이를 벗어납니다');
    const nativeLine = Number.isInteger(cue.line) ? cue.line : null;
    const cuts = nativeLine == null ? [] : cutsForLine(plan, nativeLine);
    const line = nativeLine == null ? null : (Array.isArray(plan.lines) ? plan.lines[nativeLine] : null);
    const expectedDisplayEnd = cue.displayHoldUntil == null ? cue.end : finite(cue.displayHoldUntil, `cueMap sourceLine ${cue.sourceLine ?? nativeLine}.displayHoldUntil`);
    if (expectedDisplayEnd < cue.end) fail('displayHoldUntil은 원래 cue.end보다 빠를 수 없습니다');
    const visibleCuts = cuts.map(cut => ({ ...cut, end: Math.min(cut.end, Number.isFinite(line?.visEnd) ? line.visEnd : Infinity) }));
    const actualDisplayEnd = Math.max(0, ...visibleCuts.map(cut => Number(cut.end) || 0));
    if (expectedDisplayEnd <= start || cue.start >= end) continue;
    const flags = [];
    const renderedText = cuts.map(cut => cut.text ?? cut.utext ?? cut.lineText ?? '').join('');
    const expectedStart = Math.max(start, cue.start), expectedEnd = Math.min(end, expectedDisplayEnd);
    if (!cuts.length || norm(renderedText) !== norm(cue.text) || !intervalCoverage(visibleCuts, expectedStart, expectedEnd)) flags.push('text-or-display-clock-mismatch');
    const cut = cuts[0] || {};
    const previous = (plan.cuts || [])[(plan.cuts || []).indexOf(cut) - 1];
    const joinDuration = Number(cut.transDur) || Number(cut.morph?.dur) || 0;
    const textJoin = (cut.trans || cut.morph) && joinDuration > 0 && previous && previous.line !== nativeLine &&
      previous.layout !== 'interlude' && norm(previous.utext ?? previous.text ?? previous.lineText);
    if (textJoin) flags.push('previous-text-transition');
    const params = cut.params || {};
    const big = Math.max(Number(params.sx) || 1, Number(cut.treatP?.scale) || 1, Number(cut.treatP?.big) || 1);
    if (big > 1.25 && (cut.layout === 'center' || cut.cam === 'knReadPan')) flags.push('large-scale-pan');
    const latin = /[A-Za-z]/.test(cue.text);
    if (latin && ['center', 'splitScreen'].includes(cut.layout) && (cue.text.length > 20 || /[,，]/.test(cue.text))) flags.push('latin-wrap-or-comma-split');
    const duration = Math.max(0, actualDisplayEnd - cue.start);
    const entryEffects = allEvents.filter(event => event && Number.isFinite(event.t) && event.t >= cue.start && event.t <= cue.start + Math.min(.35, duration / 2));
    const shortEffects = entryEffects.some(event => ['echoFrames', 'chroma', 'slice', 'shake', 'typewriter', 'stagger'].includes(event.type));
    if (duration < 1.35 && (shortEffects || ['type', 'typewriter', 'stagger'].includes(cut.enter) || Number(cut.stagger) > 0)) flags.push('short-line-entry-effect');
    if ((Number(cut.outDur) || 0) > .15 || ['echoFrames', 'chroma', 'slice'].includes(cut.exit) || entryEffects.some(event => event.type === 'echoFrames')) flags.push('early-exit-or-ghost');
    rows.push({
      id: `line-${nativeLine ?? 'missing'}-${cue.sourceLine ?? 'source'}`,
      nativeLine,
      sourceLine: cue.sourceLine ?? null,
      text: cue.text,
      start: cue.start,
      end: cue.end,
      displayEnd: expectedDisplayEnd,
      timing: timingOf(cue, sourceSha256),
      riskFlags: flags,
      sampleTimes: cueSamples(expectedStart, expectedEnd, textJoin ? [...allEvents, { t: cut.start, dur: joinDuration, type: 'textTransition' }] : allEvents, flags, fps, end)
    });
  }
  return { schemaVersion: 1, sourceSha256, status: 'needs-visual-review', range: { start, end }, fps, rows };
}

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    const out = [], err = []; child.stdout.on('data', chunk => out.push(chunk)); child.stderr.on('data', chunk => err.push(chunk));
    child.once('error', reject); child.once('exit', code => code === 0 ? resolve(Buffer.concat(out).toString()) : reject(new Error(`${command} 실패: ${Buffer.concat(err).toString().trim()}`)));
  });
}

async function ffprobe(video) {
  return JSON.parse(await run('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', video]));
}

function parseRate(value) {
  const [a, b] = String(value || '').split('/').map(Number); return b ? a / b : a;
}

function frameFiles(samples, fps, sourceStart, videoStart, frameCount) {
  const frameOf = sample => Math.max(0, Math.min(frameCount - 1, Math.round((sample.time - sourceStart + videoStart) * fps)));
  const indices = [...new Set(samples.map(frameOf))].sort((a, b) => a - b);
  const files = new Map(indices.map((frame, index) => [frame, `frame-${String(index + 1).padStart(6, '0')}.jpg`]));
  return samples.map(sample => {
    const frame = frameOf(sample);
    return { ...sample, frame, requestedSourceTime: sample.sourceTime, sourceTime: sourceStart + frame / fps - videoStart, localTime: frame / fps, file: files.get(frame) };
  });
}

async function makeFrames(video, items, fps, out) {
  if (!items.length) return;
  const indices = [...new Set(items.map(item => item.frame))].sort((a, b) => a - b);
  // Balance the expression to avoid FFmpeg's parser depth limit on long songs.
  const sum = terms => terms.length === 1 ? terms[0] : `(${sum(terms.slice(0, terms.length >> 1))}+${sum(terms.slice(terms.length >> 1))})`;
  const select = sum(indices.map(frame => `eq(n,${frame})`));
  await run('ffmpeg', ['-nostdin', '-hide_banner', '-v', 'error', '-n', '-i', video,
    '-vf', `select='${select}'`, '-fps_mode', 'vfr', '-q:v', '3', join(out, 'frame-%06d.jpg')]);
}

async function reviewHTML(review, target) {
  const timingNames = { confirmed: '확정', 'aligned-draft': '자동 정렬 초안', estimated: '추정', unreviewed: '미검수' };
  const riskNames = { 'text-or-display-clock-mismatch': '원문·표시 시각 불일치', 'large-scale-pan': '확대·이동 중 잘림 주의', 'latin-wrap-or-comma-split': '영어 구절 줄바꿈 주의', 'short-line-entry-effect': '짧은 가사의 입구 효과 주의', 'early-exit-or-ghost': '잔상·끝 소멸 주의', 'previous-text-transition': '이전 가사가 남는 전환 주의' };
  const cards = review.frames.map(frame => `<article><img loading="lazy" src="${escapeHTML(frame.file)}" alt="${escapeHTML(frame.text)} @ ${frame.sourceTime.toFixed(3)}초"><p><b>${escapeHTML(frame.text)}</b><br>${frame.sourceLine == null ? '' : `${escapeHTML(frame.sourceLine)}행 · `}${frame.sourceTime.toFixed(3)}초 · ${escapeHTML(frame.reason)} · ${escapeHTML(timingNames[frame.timingStatus] || '미검수')}${frame.riskFlags.length ? `<br>후보: ${escapeHTML(frame.riskFlags.map(flag => riskNames[flag] || flag).join(', '))}` : ''}</p></article>`).join('');
  const page = `<!doctype html><html lang="ko" data-road-music-ui><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JIZURA 가사 가독성 검수</title><style>main{max-width:1440px;margin:auto;padding:32px 16px 64px}h1{margin:0 0 8px}.lead{max-width:800px;margin:0 0 24px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:16px}article{margin:0;overflow:hidden;border:1px solid var(--rm-border);border-radius:var(--rm-panel-radius);box-shadow:var(--rm-shadow)}img{display:block;width:100%;background:#000}article p{padding:12px;margin:0;font-size:14px;line-height:1.5}article b{font-weight:700}</style></head><body><main><h1>가사 가독성 검수 시트</h1><p class="lead">화면 검수 대기 · 자동 검사는 위험 후보만 표시합니다. 실제 프레임에서 잘림·줄바꿈·잔상을 확인하고, 가창 싱크는 원음 근거로 따로 확인합니다.</p><div class="grid">${cards}</div></main></body></html>`;
  return applyDesign(page, target, { ui: true });
}

async function auditManifest(path, scope = null) {
  const manifest = await json(path);
  if (!manifest || typeof manifest !== 'object' || !Array.isArray(manifest.segments) || !manifest.segments.length) fail('compose manifest의 segments가 필요합니다');
  const sourceSha256 = String(manifest.sourceSha256 || '').toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(sourceSha256)) fail('manifest sourceSha256 64자리가 필요합니다');
  if (typeof manifest.audio !== 'string' || !isAbsolute(manifest.audio) || !await exists(manifest.audio) || await sha256(manifest.audio) !== sourceSha256) fail('manifest audio와 sourceSha256이 일치하지 않습니다');
  const manifestStart = finite(manifest.start ?? 0, 'manifest.start');
  const manifestEnd = finite(manifest.end ?? manifest.segments.at(-1)?.end, 'manifest.end');
  if (manifestEnd <= manifestStart) fail('manifest start..end가 올바르지 않습니다');
  const result = [];
  let clock, cursor = manifestStart;
  for (const segment of manifest.segments) {
    if (!segment || typeof segment.project !== 'string' || typeof segment.render !== 'string' || !isAbsolute(segment.project) || !isAbsolute(segment.render)) fail('manifest segment project/render은 절대 경로여야 합니다');
    const [project, render] = await Promise.all([json(segment.project), json(segment.render)]);
    if (String(project.source?.sha256 || '').toLowerCase() !== sourceSha256 || render.ok !== true || !render.actualExportSpan) fail('manifest 구간 원음/렌더 상태가 일치하지 않습니다');
    const planPath = join(dirname(segment.render), 'plan.json'); if (!await exists(planPath)) fail(`구간 plan.json이 필요합니다: ${planPath}`);
    const plan = await json(planPath);
    if (!Array.isArray(project.cueMap)) fail('manifest 프로젝트 cueMap이 필요합니다');
    const protectedCues = project.cueMap.map(cue => {
      const { jizura, ...protectedFields } = cue || {};
      return protectedFields;
    });
    const cutTimes = Object.fromEntries(Object.entries(project.overrides || {}).filter(([, value]) => value && Object.hasOwn(value, 'cutTime')).map(([line, value]) => [line, value.cutTime]));
    const signature = JSON.stringify(stable({ lyrics: project.lyrics, cueMap: protectedCues, timing: project.timing, cutTime: project.cutTime ?? null, overridesCutTime: cutTimes }));
    if (clock != null && signature !== clock) fail('manifest 모든 구간의 가사/타이밍/cutTime 시계가 같아야 합니다');
    clock = signature;
    const rangeStart = finite(segment.start, 'segment.start'), rangeEnd = finite(segment.end, 'segment.end');
    const spanStart = finite(render.actualExportSpan.t0, 'render.actualExportSpan.t0'), spanDuration = finite(render.actualExportSpan.dur, 'render.actualExportSpan.dur');
    if (Math.abs(rangeStart - cursor) > 1e-6 || rangeEnd <= rangeStart || rangeEnd > manifestEnd + 1e-6 || spanStart > rangeStart + 1e-9 || spanStart + spanDuration < rangeEnd - 1e-9) fail('manifest 구간 범위/실제 렌더 시계가 이어지지 않습니다');
    cursor = rangeEnd;
    const partStart = scope ? Math.max(rangeStart, scope.start) : rangeStart;
    const partEnd = scope ? Math.min(rangeEnd, scope.end) : rangeEnd;
    if (partEnd > partStart) result.push(auditPlan(project, plan, { start: partStart, end: partEnd }));
  }
  if (Math.abs(cursor - manifestEnd) > 1e-6) fail('manifest 구간이 end까지 이어지지 않습니다');
  const rows = result.flatMap(item => item.rows);
  const unique = new Map();
  for (const row of rows) {
    const key = `${row.nativeLine}|${row.start}|${row.end}`, prior = unique.get(key);
    unique.set(key, prior ? { ...prior, riskFlags: [...new Set([...prior.riskFlags, ...row.riskFlags])], sampleTimes: orderedUnique([...prior.sampleTimes, ...row.sampleTimes]) } : row);
  }
  const range = scope ? { start: Math.max(manifestStart, scope.start), end: Math.min(manifestEnd, scope.end) } : { start: manifestStart, end: manifestEnd };
  for (const row of unique.values()) row.sampleTimes = orderedUnique([...row.sampleTimes, ...postTailSamples(row.displayEnd, result[0]?.fps || 30, range.end)]);
  return { schemaVersion: 1, sourceSha256, status: 'needs-visual-review', range, fps: result[0]?.fps || 30, rows: [...unique.values()] };
}

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (!['--project', '--plan', '--manifest', '--video', '--out', '--source-start', '--video-start', '--review', '--decision'].includes(key)) fail(`알 수 없는 옵션: ${key}`);
    out[key.slice(2).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = argv[++i];
  }
  if (!out.out || !isAbsolute(out.out)) fail('--out은 새 절대 경로여야 합니다');
  if (out.review || out.decision) {
    if (!out.review || !out.decision || out.video || (!!out.manifest === !!out.project)) fail('--review --decision과 --manifest 또는 --project --plan을 함께 지정하세요');
    if (!isAbsolute(out.review) || !isAbsolute(out.decision)) fail('--review와 --decision은 절대 경로여야 합니다');
  }
  if (!!out.manifest === !!out.project) fail('--manifest 또는 --project --plan 중 하나를 지정하세요');
  if (out.project && (!out.plan || !isAbsolute(out.project) || !isAbsolute(out.plan))) fail('--project와 --plan은 절대 경로여야 합니다');
  if (out.manifest && !isAbsolute(out.manifest)) fail('--manifest는 절대 경로여야 합니다');
  if (out.video && !isAbsolute(out.video)) fail('--video는 절대 경로여야 합니다');
  if (out.sourceStart != null && (!Number.isFinite(Number(out.sourceStart)) || Number(out.sourceStart) < 0)) fail('--source-start는 0 이상의 숫자여야 합니다');
  if (out.videoStart != null && (!Number.isFinite(Number(out.videoStart)) || Number(out.videoStart) < 0)) fail('--video-start는 0 이상의 숫자여야 합니다');
  return out;
}

function timingSummary(rows) {
  return Object.fromEntries(rows.reduce((counts, row) => {
    const status = row.timing?.status || 'unreviewed'; counts.set(status, (counts.get(status) || 0) + 1); return counts;
  }, new Map()));
}

async function verifyProjectSource(project) {
  const path = project?.source?.path, expected = String(project?.source?.sha256 || '').toLowerCase();
  if (typeof path !== 'string' || !isAbsolute(path) || !await exists(path)) return false;
  if (await sha256(path) !== expected) fail('project.source.path 원음 파일이 바뀌었습니다');
  return true;
}

async function auditVideo(opt, video) {
  const probe = await ffprobe(video), stream = (probe.streams || []).find(item => item.codec_type === 'video');
  if (!stream) fail('영상 스트림이 없습니다');
  const fps = parseRate(stream.avg_frame_rate || stream.r_frame_rate), duration = Number(stream.duration ?? probe.format?.duration);
  if (!Number.isFinite(fps) || fps <= 0 || !Number.isFinite(duration) || duration <= 0) fail('영상 FPS/길이를 확인할 수 없습니다');
  const frameCount = Number(stream.nb_frames) || Math.max(1, Math.round(duration * fps));
  const manifest = opt.manifest ? await json(opt.manifest) : null;
  const manifestStart = manifest ? finite(manifest.start ?? 0, 'manifest.start') : 0;
  const sourceStart = opt.sourceStart == null ? manifestStart : Number(opt.sourceStart), videoStart = Number(opt.videoStart || 0);
  if (videoStart >= duration) fail('--video-start는 실제 영상 길이보다 짧아야 합니다');
  const available = duration - videoStart, project = opt.project ? await json(opt.project) : null;
  const defaultEnd = project?.source?.duration ?? Infinity, manifestEnd = manifest ? finite(manifest.end ?? manifest.segments?.at(-1)?.end, 'manifest.end') : null;
  if (manifest && (sourceStart !== manifestStart || videoStart !== 0 || Math.abs(available - (manifestEnd - manifestStart)) > 1 / fps + .03)) fail('영상 길이/원음 시작이 manifest 전체 범위와 다릅니다');
  if (project && opt.sourceStart == null && available + .5 / fps < defaultEnd) fail('부분 영상에는 실제 --source-start를 명시하세요');
  const scope = { start: sourceStart, end: manifestEnd ?? Math.min(defaultEnd, sourceStart + available) };
  const report = opt.manifest ? await auditManifest(opt.manifest, scope) : auditPlan(project, await json(opt.plan), scope);
  if (report.range.end <= report.range.start) fail('영상과 원음 검수 범위가 겹치지 않습니다');
  if (opt.manifest && duration + .5 / fps < report.range.end - report.range.start) fail('영상 길이가 manifest 검수 범위를 반 프레임까지 덮지 않습니다');
  const samples = report.rows.flatMap(row => row.sampleTimes.map(sample => ({ ...sample, id: row.id, nativeLine: row.nativeLine, sourceLine: row.sourceLine, text: row.text, timingStatus: row.timing.status, riskFlags: row.riskFlags, sourceTime: sample.time })))
    .filter(sample => sample.sourceTime >= sourceStart - .0001 && sample.sourceTime <= sourceStart + available + .0001);
  return { report, fps, duration, frameCount, sourceStart, videoStart, frames: frameFiles(samples, fps, sourceStart, videoStart, frameCount), sourceVerified: manifest ? true : await verifyProjectSource(project) };
}

function sameNumber(left, right) { return Number.isFinite(left) && Number.isFinite(right) && Math.abs(left - right) < .000001; }

async function applyDecision(opt) {
  const [review, decision] = await Promise.all([json(opt.review), json(opt.decision)]);
  if (!review || review.schemaVersion !== 1 || typeof review.video !== 'string' || !isAbsolute(review.video) || !Array.isArray(review.frames) || !/^[0-9a-f]{64}$/i.test(review.sourceSha256 || '') || !/^[0-9a-f]{64}$/i.test(review.videoSHA256 || '')) fail('review.json 형식이 올바르지 않습니다');
  if (!decision || typeof decision !== 'object' || !Array.isArray(decision.frames) || !['pass', 'needs-revision'].includes(decision.status)) fail('visual-review.json 형식이 올바르지 않습니다');
  if (String(decision.sourceSha256 || '').toLowerCase() !== review.sourceSha256.toLowerCase() || String(decision.videoSHA256 || '').toLowerCase() !== review.videoSHA256.toLowerCase()) fail('decision 원음/영상 해시가 review와 다릅니다');
  const actualVideoSha = await sha256(review.video);
  if (actualVideoSha !== review.videoSHA256.toLowerCase()) fail('review 이후 영상 파일이 바뀌었습니다');
  const audit = await auditVideo(opt, review.video);
  if (review.sourceSha256.toLowerCase() !== audit.report.sourceSha256 || !sameNumber(review.fps, audit.fps) || !sameNumber(review.sourceStart, audit.sourceStart) || !sameNumber(review.videoStart ?? 0, audit.videoStart)) fail('review와 원본 프로젝트의 시계가 다릅니다');
  if (review.frames.length !== audit.frames.length) fail('review frame 목록이 원본 검수 표본 전체와 다릅니다');
  for (const [index, expectedFrame] of audit.frames.entries()) {
    const actualFrame = review.frames[index];
    if (!actualFrame || actualFrame.file !== expectedFrame.file || actualFrame.frame !== expectedFrame.frame || !sameNumber(actualFrame.requestedSourceTime, expectedFrame.requestedSourceTime) || !sameNumber(actualFrame.sourceTime, expectedFrame.sourceTime) || !sameNumber(actualFrame.localTime, expectedFrame.localTime)) fail('review frame 시계가 원본 검수 표본과 다릅니다');
  }
  const expected = new Map();
  for (const frame of review.frames) {
    if (!frame || typeof frame.file !== 'string' || !/^frame-\d{6}\.jpg$/.test(frame.file) || !/^[0-9a-f]{64}$/i.test(frame.sha256 || '')) fail('review frame 형식이 올바르지 않습니다');
    const prior = expected.get(frame.file);
    if (prior && prior !== frame.sha256.toLowerCase()) fail('같은 review frame 파일의 해시가 다릅니다');
    expected.set(frame.file, frame.sha256.toLowerCase());
  }
  const decisions = new Map();
  for (const frame of decision.frames) {
    if (!frame || typeof frame.file !== 'string' || !/^frame-\d{6}\.jpg$/.test(frame.file) || !/^[0-9a-f]{64}$/i.test(frame.sha256 || '') || !['pass', 'issue', 'pending'].includes(frame.status)) fail('decision frame 형식이 올바르지 않습니다');
    if (decisions.has(frame.file)) fail('decision frame 파일은 중복될 수 없습니다');
    decisions.set(frame.file, frame);
  }
  const checked = [];
  for (const [file, expectedSha] of expected) {
    const actual = await sha256(join(dirname(opt.review), file));
    if (actual !== expectedSha) fail(`review frame 파일이 바뀌었습니다: ${file}`);
    const decisionFrame = decisions.get(file);
    if (decisionFrame && decisionFrame.sha256.toLowerCase() !== expectedSha) fail(`decision frame 해시가 다릅니다: ${file}`);
    checked.push({ file, sha256: expectedSha, status: decisionFrame?.status || 'pending' });
  }
  for (const file of decisions.keys()) if (!expected.has(file)) fail(`decision에 없는 review frame이 있습니다: ${file}`);
  const covered = checked.length === expected.size && checked.every(frame => frame.status === 'pass');
  const visualReady = Boolean(audit.sourceVerified && expected.size > 0 && decision.status === 'pass' && typeof decision.reviewer === 'string' && decision.reviewer.trim() && covered);
  const verdict = {
    schemaVersion: 1, sourceSha256: review.sourceSha256, videoSHA256: review.videoSHA256,
    review: opt.review, decision: opt.decision, reviewer: decision.reviewer || '', status: decision.status,
    visualReview: visualReady ? 'pass' : 'needs-revision', visualReady, deliveryReady: false,
    listeningReviewed: false, sourceVerified: audit.sourceVerified, frames: checked
  };
  await mkdir(dirname(opt.out), { recursive: true }); await writeFile(opt.out, JSON.stringify(verdict, null, 2));
  return { ok: true, mode: 'decision', output: opt.out, visualReady, frames: checked.length, sourceVerified: audit.sourceVerified };
}

async function main(opt) {
  if (await exists(opt.out)) fail(`--out은 아직 없는 새 경로여야 합니다: ${opt.out}`);
  if (opt.review) return applyDecision(opt);
  if (!opt.video) {
    const report = opt.manifest ? await auditManifest(opt.manifest) : auditPlan(await json(opt.project), await json(opt.plan));
    await mkdir(dirname(opt.out), { recursive: true }); await writeFile(opt.out, JSON.stringify(report, null, 2));
    return { ok: true, mode: 'plan-only', output: opt.out, rows: report.rows.length, status: report.status };
  }
  const audit = await auditVideo(opt, opt.video), { report, fps, sourceStart, videoStart, frames, sourceVerified } = audit;
  await mkdir(opt.out, { recursive: false });
  await makeFrames(opt.video, frames, fps, opt.out);
  const files = await Promise.all(frames.map(async frame => ({ ...frame, sha256: await sha256(join(opt.out, frame.file)) })));
  const review = { schemaVersion: 1, sourceSha256: report.sourceSha256, video: opt.video, videoSHA256: await sha256(opt.video), fps, sourceStart, videoStart, visualReview: 'pending', visualReady: false, deliveryReady: false, listeningReviewed: false, sourceVerified, timingSummary: timingSummary(report.rows), frames: files };
  const template = { videoSHA256: review.videoSHA256, sourceSha256: review.sourceSha256, reviewer: '', status: 'needs-revision', frames: [...new Map(files.map(frame => [frame.file, { file: frame.file, sha256: frame.sha256, status: 'pending' }])).values()] };
  const reviewPage = join(opt.out, 'review.html');
  await Promise.all([writeFile(join(opt.out, 'review.json'), JSON.stringify(review, null, 2)), writeFile(join(opt.out, 'decision-template.json'), JSON.stringify(template, null, 2)), writeFile(join(opt.out, 'candidates.json'), JSON.stringify(report, null, 2)), reviewHTML(review, reviewPage).then(page => writeFile(reviewPage, page))]);
  return { ok: true, mode: 'video-review', output: opt.out, rows: report.rows.length, frames: files.length, status: report.status };
}

if (process.argv[1] && process.argv[1].endsWith('readability.mjs')) {
  try { console.log(JSON.stringify(await main(args(process.argv.slice(2))))); }
  catch (error) { console.log(JSON.stringify({ ok: false, error: error.message })); process.exitCode = 1; }
}

export { escapeHTML };
