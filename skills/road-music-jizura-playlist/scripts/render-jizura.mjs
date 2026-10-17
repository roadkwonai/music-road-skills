#!/usr/bin/env node
// Render a saved JIZURA project through its own browser UI. No private JIZURA APIs are patched.
import { spawn } from 'node:child_process';
import { access, mkdir, mkdtemp, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { createHash } from 'node:crypto';
import { createServer } from 'node:net';
import { dirname, extname, isAbsolute, join } from 'node:path';
import { homedir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { browserBakeExpression } from './directing.mjs';

const DEFAULT_JIZURA = join(homedir(), '.local/share/roadmusic-video-tools/jizura');
const DEFAULT_CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const exists = path => access(path, constants.R_OK).then(() => true, () => false);
const fail = message => { throw new Error(message); };

function args(argv) {
  const out = { timeoutSeconds: 1800, chrome: DEFAULT_CHROME, jizuraRoot: DEFAULT_JIZURA };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--inspect' || a === '--render' || a === '--self-check') out[a.slice(2)] = true;
    else if (a === '--project') out.project = argv[++i];
    else if (a === '--audio') out.audio = argv[++i];
    else if (a === '--out') out.out = argv[++i];
    else if (a === '--jizura-root') out.jizuraRoot = argv[++i];
    else if (a === '--chrome') out.chrome = argv[++i];
    else if (a === '--timeout-seconds') out.timeoutSeconds = Number(argv[++i]);
    else fail(`알 수 없는 옵션: ${a}`);
  }
  if ([out.inspect, out.render, out['self-check']].filter(Boolean).length !== 1) fail('--self-check, --inspect, --render 중 하나를 지정하세요');
  if (!Number.isFinite(out.timeoutSeconds) || out.timeoutSeconds < 10 || out.timeoutSeconds > 3600) fail('--timeout-seconds는 10..3600이어야 합니다');
  if (!out['self-check']) for (const k of ['project', 'audio', 'out']) if (!out[k]) fail(`--${k}가 필요합니다`);
  return out;
}

async function sha256(path) {
  return createHash('sha256').update(await readFile(path)).digest('hex');
}

async function readFontAssets(project) {
  const assets = project.fontAssets || [];
  if (!Array.isArray(assets)) fail('fontAssets는 배열이어야 합니다');
  const keys = new Set((project.userFonts || []).map(font => font.key));
  const result = [];
  for (const asset of assets) {
    if (!asset || !/^user_[A-Za-z0-9_-]{1,80}$/.test(asset.key) || !keys.has(asset.key) ||
        typeof asset.path !== 'string' || !isAbsolute(asset.path) ||
        !['.ttf', '.otf', '.woff', '.woff2', '.ttc'].includes(extname(asset.path).toLowerCase()) ||
        !/^[0-9a-f]{64}$/i.test(asset.sha256 || '')) fail('fontAssets의 key/path/sha256이 올바르지 않습니다');
    const info = await stat(asset.path);
    if (!info.isFile() || info.size < 4 || info.size > 32 * 1024 * 1024) fail('폰트 파일 크기가 올바르지 않습니다');
    const data = await readFile(asset.path);
    if (!['00010000', '4f54544f', '774f4646', '774f4632', '74746366'].includes(data.subarray(0, 4).toString('hex')) ||
        createHash('sha256').update(data).digest('hex') !== asset.sha256.toLowerCase()) fail(`폰트 파일 형식/해시가 다릅니다: ${asset.key}`);
    result.push({ key: asset.key, base64: data.toString('base64') });
  }
  return result;
}

async function checkRuntime(o) {
  const needed = [o.chrome, join(o.jizuraRoot, 'VERSION'), join(o.jizuraRoot, 'ko', 'index.html')];
  for (const path of needed) if (!await exists(path)) fail(`필수 파일이 없습니다: ${path}`);
  const [version, html] = await Promise.all([readFile(join(o.jizuraRoot, 'VERSION'), 'utf8'), readFile(join(o.jizuraRoot, 'ko', 'index.html'), 'utf8')]);
  for (const symbol of ['J.exportMP4', 'J.plan =', 'J.lineSnapshot', 'J.ui = S', 'J.uiApi =', 'id="fileProject"', 'id="audioFile"', 'id="btnMP4"']) if (!html.includes(symbol)) fail(`JIZURA 공개 실행 경로를 찾지 못했습니다: ${symbol}`);
  return { jizuraRoot: o.jizuraRoot, version: version.trim(), chrome: o.chrome };
}

async function validateInput(o) {
  for (const [name, value] of Object.entries({ project: o.project, audio: o.audio, out: o.out })) if (!isAbsolute(value)) fail(`--${name}는 절대 경로여야 합니다`);
  if (await exists(o.out)) fail(`--out은 아직 없는 새 디렉터리여야 합니다: ${o.out}`);
  const [projectText, audioInfo] = await Promise.all([readFile(o.project, 'utf8'), stat(o.audio)]);
  if (!audioInfo.isFile() || audioInfo.size === 0) fail(`오디오 파일을 읽을 수 없습니다: ${o.audio}`);
  let project;
  try { project = JSON.parse(projectText); } catch { fail(`JIZURA 프로젝트 JSON이 아닙니다: ${o.project}`); }
  if (!project || typeof project !== 'object' || Array.isArray(project)) fail('프로젝트 최상위 값은 객체여야 합니다');
  if (project.source && typeof project.source.sha256 === 'string') {
    const actual = await sha256(o.audio);
    if (actual !== project.source.sha256.toLowerCase()) fail('project.source.sha256과 --audio 파일 해시가 다릅니다');
  }
  return project;
}

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const { port } = server.address();
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function waitFor(work, label, timeoutMs) {
  const until = Date.now() + timeoutMs;
  let last;
  while (Date.now() < until) {
    try { last = await work(); if (last) return last; } catch (error) { last = error.message; }
    await sleep(120);
  }
  fail(`${label} 시간 초과${last ? `: ${last}` : ''}`);
}

function cdp(url) {
  const ws = new WebSocket(url);
  const pending = new Map(); let next = 0;
  const ready = new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  ws.onmessage = ({ data }) => { const m = JSON.parse(data), p = pending.get(m.id); if (!p) return; pending.delete(m.id); m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result); };
  ws.onclose = () => { for (const p of pending.values()) p.reject(new Error('CDP 연결이 닫혔습니다')); pending.clear(); };
  return { ready, send(method, params = {}) { return ready.then(() => new Promise((resolve, reject) => { const id = ++next; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); })); }, close() { ws.close(); } };
}

async function evaluate(page, expression) {
  const result = await page.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) fail(result.exceptionDetails.exception?.description || result.exceptionDetails.text || '브라우저 평가 실패');
  return result.result.value;
}

async function inputFile(page, selector, path) {
  const root = (await page.send('DOM.getDocument', { depth: 1 })).root.nodeId;
  const nodeId = (await page.send('DOM.querySelector', { nodeId: root, selector })).nodeId;
  if (!nodeId) fail(`JIZURA 입력 요소가 없습니다: ${selector}`);
  await page.send('DOM.setFileInputFiles', { files: [path], nodeId });
}

async function ffprobe(path) {
  const proc = spawn('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', path], { stdio: ['ignore', 'pipe', 'pipe'] });
  const chunks = []; const errors = [];
  proc.stdout.on('data', d => chunks.push(d)); proc.stderr.on('data', d => errors.push(d));
  const code = await new Promise((resolve, reject) => { proc.once('exit', resolve); proc.once('error', reject); });
  if (code !== 0) fail(`ffprobe 실패: ${Buffer.concat(errors).toString().trim()}`);
  return JSON.parse(Buffer.concat(chunks).toString());
}

async function collect(page, project, audioPath) {
  const data = await evaluate(page, `(() => {
    const p = J.ui.plan, a = J.ui.audio;
    const styles = Object.fromEntries(J.STYLE_ORDER.map(id => [id, { name: J.STYLES[id].name, desc: J.STYLES[id].desc }]));
    const groups = Object.fromEntries(J.GROUP_KEYS.map(group => [group, J.order(group).map(id => ({ id, name: (J.registry(group)[id] || {}).name || '' }))]));
    const fonts = J.fontsOfPlan(p).map(k => ({ key: k, loaded: k === '@var' ? true : document.fonts.check(J.fontCSS(k === '@var' ? 'gothic_bold' : k, 64), 'Aa가나다') }));
    return { audio: { duration: a.duration, bpm: a.bpm, beats: a.beats, energy: Array.from(a.energy || []), energyRate: a.energyRate || 0, sampleRate: a.sampleRate }, plan: { duration: p.duration, beats: p.beats, energy: p.energy ? Array.from(p.energy) : null, energyRate: p.energyRate || 0, lines: p.lines, cuts: p.cuts, events: p.events, fps: p.fps }, registry: { styles, groups, fontCheck: fonts, missingUserFonts: J.missingUserFonts(J.fontsOfPlan(p)) } };
  })()`);
  const digest = await sha256(audioPath);
  if (project.source && Number.isFinite(project.source.duration) && Math.abs(project.source.duration - data.audio.duration) > 0.15) fail(`project.source.duration(${project.source.duration})과 실제 오디오 길이(${data.audio.duration})가 다릅니다`);
  if (data.audio.bpm < 70 || data.audio.bpm > 180) data.audio.bpmHeuristicWarning = 'JIZURA BPM 추정값은 70~180 BPM 범위를 벗어나므로 확정 값이 아닙니다.';
  return { analysis: { audio: { path: audioPath, sha256: digest, ...data.audio }, plan: { duration: data.plan.duration, beats: data.plan.beats }, fontCheck: data.registry.fontCheck, missingUserFonts: data.registry.missingUserFonts }, plan: data.plan, registry: data.registry };
}

async function saveSamples(page, out, project) {
  const duration = await evaluate(page, 'J.ui.plan.duration');
  const reviewTimes = Array.isArray(project.reviewTimes) && project.reviewTimes.length
    ? project.reviewTimes.filter(time => Number.isFinite(time) && time >= 0 && time <= duration)
    : [0, Math.min(1, duration / 2), Math.max(0, duration - 0.1)];
  for (const [i, time] of reviewTimes.entries()) {
    const png = await evaluate(page, `(async () => { J.uiApi.seek(${time}); await new Promise(requestAnimationFrame); return document.getElementById('view').toDataURL('image/png').split(',')[1]; })()`);
    await writeFile(join(out, `frame-${i + 1}.png`), Buffer.from(png, 'base64'));
  }
}

async function run(o) {
  const runtime = await checkRuntime(o);
  if (o['self-check']) return { ok: true, mode: 'self-check', ...runtime };
  const rawProject = await validateInput(o);
  const fontAssets = await readFontAssets(rawProject);
  await mkdir(dirname(o.out), { recursive: true });
  await mkdir(o.out);
  const port = await freePort();
  await mkdir(join(o.jizuraRoot, 'runtime'), { recursive: true });
  const profile = await mkdtemp(join(o.jizuraRoot, 'runtime', 'road-music-jizura-'));
  const chrome = spawn(o.chrome, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const chromeExit = new Promise(resolve => chrome.once('exit', resolve));
  let browser; let page;
  try {
    const version = await waitFor(async () => { const r = await fetch(`http://127.0.0.1:${port}/json/version`); return r.ok ? r.json() : null; }, 'Chrome DevTools 시작', 15000);
    browser = cdp(version.webSocketDebuggerUrl); await browser.ready;
    await browser.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: o.out, eventsEnabled: true });
    const pageUrl = pathToFileURL(join(o.jizuraRoot, 'ko', 'index.html')).href;
    const target = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(pageUrl)}`, { method: 'PUT' })).json();
    page = cdp(target.webSocketDebuggerUrl); await page.ready;
    await page.send('DOM.enable'); await page.send('Runtime.enable');
    await waitFor(() => evaluate(page, 'document.readyState === "complete" && !!window.J && !!J.uiApi'), 'JIZURA 시작', 20000);
    await inputFile(page, '#fileProject', o.project);
    await waitFor(() => evaluate(page, 'J.ui && J.ui.project && J.ui.project.lyrics === ' + JSON.stringify(String(rawProject.lyrics || ''))), 'JIZURA 프로젝트 불러오기', 15000);
    const valid = await evaluate(page, `(() => {
      const p = J.ui.project, raw = ${JSON.stringify(rawProject)}, bad = [];
      const check = (group, id, where) => { if (id && !(group === 'style' ? J.STYLES[id] : J.registry(group)[id])) bad.push(where + ':' + id); };
      check('style', raw.style, 'style');
      for (const g of J.GROUP_KEYS) for (const [id, enabled] of Object.entries((raw.enabled || {})[g] || {})) if (enabled !== false) check(g, id, 'enabled.' + g);
      for (const [line, ov] of Object.entries(raw.overrides || {})) {
        if (!ov || typeof ov !== 'object') continue;
        for (const [field, group] of Object.entries({ layout: 'layout', enter: 'enter', hold: 'hold', exit: 'exit', treat: 'treat', bg: 'bg', cam: 'cam', trans: 'trans' })) check(group, ov[field], 'overrides.' + line + '.' + field);
        for (const id of Array.isArray(ov.decor) ? ov.decor : []) check('decor', id, 'overrides.' + line + '.decor');
        for (const tech of Object.values(ov.cutTech || {})) if (tech && typeof tech === 'object') for (const group of ['layout', 'enter', 'hold', 'exit', 'treat', 'bg', 'cam', 'decor']) if (tech[group] !== 'none') check(group, tech[group], 'overrides.' + line + '.cutTech.' + group);
        for (const id of Object.values(ov.cutLayouts || {})) check('layout', id, 'overrides.' + line + '.cutLayouts');
      }
      return bad;
    })()`);
    if (valid.length) fail(`JIZURA에 없는 스타일/구성요소 ID: ${valid.join(', ')}`);
    await inputFile(page, '#audioFile', o.audio);
    await waitFor(() => evaluate(page, '!!(J.ui && J.ui.audio && Number.isFinite(J.ui.audio.duration) && J.ui.audio.duration > 0)'), 'JIZURA 오디오 분석', Math.min(o.timeoutSeconds * 1000, 180000));
    if (rawProject.timing && typeof rawProject.timing === 'object') await evaluate(page, `(() => { J.ui.project.timing = Object.assign({}, J.ui.project.timing || {}, ${JSON.stringify(rawProject.timing)}); J.uiApi.replan(); return true; })()`);
    for (const asset of fontAssets) {
      const saved = await evaluate(page, `(async () => { const binary = atob(${JSON.stringify(asset.base64)}); const bytes = Uint8Array.from(binary, c => c.charCodeAt(0)); return J.saveFontData(${JSON.stringify(asset.key)}, bytes.buffer); })()`);
      if (!saved) fail(`폰트 캐시를 복원하지 못했습니다: ${asset.key}`);
    }
    if (fontAssets.length) {
      const missing = await evaluate(page, '(async () => { const missing = await J.restoreUserFonts(J.ui.project.userFonts || []); J.uiApi.replan(); return missing; })()');
      if (missing.length) fail(`폰트 원본을 복원하지 못했습니다: ${missing.join(', ')}`);
    }
    const fontLoadCompleted = await evaluate(page, 'Promise.race([J.ensureFonts(J.ui.project.lyrics, J.fontsOfPlan(J.ui.plan)).then(() => true), new Promise(resolve => setTimeout(() => resolve(false), 20000))])');
    let directingReport = null;
    if (rawProject.directing) {
      const audioHash = await sha256(o.audio);
      directingReport = await evaluate(page, browserBakeExpression(rawProject.directing, audioHash, rawProject.source?.duration));
      await writeFile(join(o.out, 'directing-report.json'), JSON.stringify(directingReport, null, 2));
      if (!directingReport.ok) fail(`directing accents 중 ${directingReport.unassigned.length}개가 active lyric cut에 없습니다`);
      const directed = Object.assign({}, rawProject, await evaluate(page, 'JSON.parse(JSON.stringify(J.ui.project))'), { appVersion: runtime.version });
      delete directed.directing;
      await writeFile(join(o.out, 'directed.jizura.json'), JSON.stringify(directed, null, 2));
    }
    const records = await collect(page, rawProject, o.audio);
    records.analysis.fontLoadCompleted = fontLoadCompleted;
    records.analysis.restoredFontAssets = fontAssets.map(asset => asset.key);
    await Promise.all([writeFile(join(o.out, 'analysis.json'), JSON.stringify(records.analysis, null, 2)), writeFile(join(o.out, 'plan.json'), JSON.stringify(records.plan, null, 2)), writeFile(join(o.out, 'registry.json'), JSON.stringify(records.registry, null, 2))]);
    await saveSamples(page, o.out, rawProject);
    if (o.inspect) return { ok: true, mode: 'inspect', output: o.out, duration: records.analysis.audio.duration, bpm: records.analysis.audio.bpm, directing: directingReport };
    await waitFor(() => evaluate(page, '!document.getElementById("btnMP4").disabled'), 'JIZURA WebCodecs 준비', 30000);
    const exportSpan = await evaluate(page, '(() => { const range = J.uiApi.exportRange(); const t0 = range ? range.t0 : 0; const t1 = range ? range.t1 : J.ui.plan.duration; return { t0, dur: t1 - t0 }; })()');
    const started = Date.now();
    await evaluate(page, 'document.getElementById("btnMP4").click(); true');
    const rendered = await waitFor(async () => {
      const names = await readdir(o.out); const name = names.find(n => n.endsWith('.mp4'));
      if (!name || names.some(n => n.endsWith('.crdownload'))) return null;
      const path = join(o.out, name), info = await stat(path);
      return info.mtimeMs >= started && info.size > 0 ? { path, bytes: info.size } : null;
    }, 'JIZURA MP4 내보내기', o.timeoutSeconds * 1000);
    const probe = await ffprobe(rendered.path);
    const streams = probe.streams || [], video = streams.find(s => s.codec_type === 'video'), audio = streams.find(s => s.codec_type === 'audio');
    const expectedDuration = exportSpan.dur;
    const audioExpected = rawProject.includeAudio !== false;
    const result = { ok: !!(video && (!audioExpected || audio)), output: rendered.path, bytes: rendered.bytes, duration: Number(probe.format?.duration || 0), actualExportSpan: exportSpan, audioExpected, sourceDuration: Number(rawProject.source?.duration) || null, durationDelta: Number((Number(probe.format?.duration || 0) - expectedDuration).toFixed(6)), video: video && { codec: video.codec_name, width: video.width, height: video.height, frames: Number(video.nb_read_frames || video.nb_frames || 0) }, audio: audio && { codec: audio.codec_name, sampleRate: Number(audio.sample_rate || 0), channels: audio.channels }, sidecarWav: (await readdir(o.out)).filter(n => /\.wav$/i.test(n)) };
    await writeFile(join(o.out, 'result.json'), JSON.stringify(result, null, 2));
    if (!video) fail('내보낸 MP4에 영상 스트림이 없습니다');
    if (audioExpected && !audio) fail(`내보낸 MP4에 오디오 스트림이 없습니다. JIZURA의 native AAC 지원을 확인하거나 ${result.sidecarWav.length ? 'WAV sidecar를 별도 mux 하세요' : 'Chrome WebCodecs/AAC 지원을 확인하세요'}.`);
    return { ok: true, mode: 'render', output: rendered.path, duration: result.duration, frames: result.video.frames, audioCodec: result.audio?.codec || null };
  } finally {
    page?.close(); browser?.close(); chrome.kill('SIGTERM');
    await Promise.race([chromeExit, sleep(5000)]); await rm(profile, { recursive: true, force: true });
  }
}

try { console.log(JSON.stringify(await run(args(process.argv.slice(2))))); }
catch (error) { console.log(JSON.stringify({ ok: false, error: error.message })); process.exitCode = 1; }
