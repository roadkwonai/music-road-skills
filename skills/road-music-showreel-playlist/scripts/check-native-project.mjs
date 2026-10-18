import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const [projectArg, qaArg] = process.argv.slice(2);
assert(projectArg && qaArg, '사용법: node check-native-project.mjs PROJECT QA_DIR');
const project = path.resolve(projectArg);
const out = path.resolve(qaArg);
const reel = path.join(project, 'reel');
const skill = path.resolve(import.meta.dirname, '..');
const showreel = process.env.SHOWREEL_HOME || path.join(os.homedir(), '.local/share/roadmusic-video-tools/showreel');
const require = createRequire(path.join(showreel, 'scripts', 'package.json'));
const { chromium } = require('playwright-core');
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.wav': 'audio/wav', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.json': 'application/json' };
const finite = value => typeof value === 'number' && Number.isFinite(value);
const sha = value => crypto.createHash('sha256').update(value).digest('hex');

function fingerprint() {
  const roadMusicPython = path.join(os.homedir(), '.local/share/roadmusic-ltx23/src/.venv/bin/python');
  const python = process.env.SHOWREEL_PYTHON || (fs.existsSync(roadMusicPython) ? roadMusicPython : 'python3');
  const raw = execFileSync(python, [path.join(skill, 'scripts', 'native_project.py'), 'fingerprint', '--project', project], { encoding: 'utf8' });
  const parsed = JSON.parse(raw.trim());
  assert(parsed && parsed.files && typeof parsed.files === 'object', 'fingerprint가 files 맵을 반환해야 합니다.');
  return parsed.files;
}

function preparedCheck() {
  const roadMusicPython = path.join(os.homedir(), '.local/share/roadmusic-ltx23/src/.venv/bin/python');
  const python = process.env.SHOWREEL_PYTHON || (fs.existsSync(roadMusicPython) ? roadMusicPython : 'python3');
  const raw = execFileSync(python, [path.join(skill, 'scripts', 'native_project.py'), 'check', '--project', project], { encoding: 'utf8' });
  const parsed = JSON.parse(raw.trim());
  assert(!parsed.error && Array.isArray(parsed.scenes), `native prepared contract가 실패했습니다: ${parsed.error || 'scene report 없음'}`);
  return parsed;
}

function staticFile(name) {
  const file = path.join(reel, name);
  assert(fs.existsSync(file), `필수 파일이 없습니다: reel/${name}`);
  return fs.readFileSync(file, 'utf8');
}

function readGlobal(name) {
  const source = staticFile(name === 'FILM_INPUT' ? 'film-input.js' : 'film-plan.js');
  const marker = new RegExp(`^\\s*window\\.${name}\\s*=\\s*`, 'm');
  const match = source.match(marker);
  assert(match, `${name} 전역 형식이 아닙니다.`);
  return JSON.parse(source.slice(match.index + match[0].length).trim().replace(/;$/, ''));
}

function writeReport(report) {
  const canonical = path.join(project, 'qa', 'native-runtime.json');
  fs.mkdirSync(path.dirname(canonical), { recursive: true });
  fs.writeFileSync(canonical, JSON.stringify(report, null, 2));
}

for (const file of ['index.html', 'film-input.js', 'film-plan.js', 'film-runtime.js', 'scenes.js', 'engine.js', 'fx.js', 'timeline.js']) staticFile(file);
assert(/timeline\.js[\s\S]*engine\.js[\s\S]*fx\.js[\s\S]*film-input\.js[\s\S]*film-plan\.js[\s\S]*film-runtime\.js[\s\S]*scenes\.js/.test(staticFile('index.html')), 'native script 로드 순서가 틀렸습니다.');
const prepared = preparedCheck();
const files = fingerprint();
const sourceInput = readGlobal('FILM_INPUT');
const server = http.createServer((request, response) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname); } catch { response.writeHead(400); response.end(); return; }
  const file = path.resolve(project, `.${pathname}`);
  if (!file.startsWith(`${project}${path.sep}`) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { 'Content-Type': mime[path.extname(file).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-store' });
  fs.createReadStream(file).pipe(response);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port;
const report = { pass: false, files, project, checks: [], frames: [], network: [], sceneBindings: prepared.scenes };
let browser;
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--force-color-profile=srgb', '--hide-scrollbars', '--disable-lcd-text', '--mute-audio'] });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  await context.addInitScript(() => {
    const invalid = [];
    window.__filmCanvasInvalid = invalid;
    const methods = ['arc', 'arcTo', 'clearRect', 'ellipse', 'fillRect', 'lineTo', 'moveTo', 'rect', 'rotate', 'scale', 'setTransform', 'strokeRect', 'transform', 'translate'];
    for (const method of methods) {
      const original = CanvasRenderingContext2D.prototype[method];
      if (!original) continue;
      CanvasRenderingContext2D.prototype[method] = function (...args) {
        if (args.some(value => typeof value === 'number' && !Number.isFinite(value))) invalid.push({ method, args });
        return original.apply(this, args);
      };
    }
  });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.hostname === '127.0.0.1' && Number(url.port) === port) route.continue();
    else { report.network.push({ blocked: url.toString() }); route.abort(); }
  });
  const page = await context.newPage();
  const errors = [];
  let rejectPageError;
  const pageError = new Promise((_, reject) => { rejectPageError = reject; });
  page.on('pageerror', error => { errors.push(String(error)); rejectPageError(error); });
  await Promise.race([page.goto(`http://127.0.0.1:${port}/reel/index.html?check=1`, { waitUntil: 'load' }), pageError]);
  await Promise.race([page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 }), pageError]);
  assert.deepEqual(errors, [], `브라우저 오류: ${errors.join('\n')}`);
  assert.equal(report.network.length, 0, '외부 네트워크 요청이 있었습니다.');
  const model = await page.evaluate(() => ({ input: window.FILM_INPUT, plan: window.FILM_PLAN, meta: window.__meta, images: Object.fromEntries(Object.entries(window.FILM_IMAGES || {}).map(([id, image]) => [id, { width: image.naturalWidth, height: image.naturalHeight, complete: image.complete }])) }));
  assert.deepEqual(model.input.captions, sourceInput.captions, 'runtime이 가사 원문·words·검수 상태를 바꿨습니다.');
  assert(model.plan && Array.isArray(model.plan.scenes) && model.plan.scenes.length, '빈 native 장면은 검수할 수 없습니다.');
  assert(model.meta && Array.isArray(model.meta.scenes) && model.meta.scenes.length, 'REEL.scene 등록이 없습니다.');
  assert.equal(model.meta.duration, model.input.duration);
  assert.equal(model.meta.fps, model.input.fps);
  assert.equal(model.meta.width, model.input.width);
  assert.equal(model.meta.height, model.input.height);
  assert.equal(model.meta.width, 1920);
  assert.equal(model.meta.height, 1080);
  const fonts = await page.evaluate(() => ({ check: document.fonts.check('400 32px Paperlogy', '가나다라마바사'), loaded: window.__meta.fonts }));
  assert(fonts.check && fonts.loaded.some(font => font.includes('Paperlogy')), '제작 폰트가 실제로 로드되지 않았습니다.');
  const expectedScenes = model.plan.scenes.map(scene => [scene.id, scene.startSeconds, scene.endSeconds]);
  assert.equal(new Set(expectedScenes.map(scene => scene[0])).size, expectedScenes.length, 'PLAN 장면 id가 중복됩니다.');
  for (const [id, start, end] of expectedScenes) {
    assert(finite(start) && finite(end) && end > start, `PLAN 장면 범위가 유효하지 않습니다: ${id}`);
    const actual = model.meta.scenes.find(scene => scene[0] === id);
    assert(actual, `PLAN 장면이 REEL.scene에 없습니다: ${id}`);
    const tolerance = .5 / model.meta.fps + 1e-7;
    assert(Math.abs(actual[1] - start) <= tolerance && Math.abs(actual[2] - end) <= tolerance, `장면 경계가 PLAN과 다릅니다: ${id}`);
  }
  for (const scene of model.plan.scenes) for (const key of ['trackId', 'sourceStartSeconds', 'sourceEndSeconds', 'originStartSeconds', 'originEndSeconds']) {
    assert(Object.hasOwn(scene, key), `PLAN 장면의 ${key}가 없습니다: ${scene.id}`);
    if (key !== 'trackId') assert(finite(scene[key]), `PLAN 장면의 ${key}가 유한하지 않습니다: ${scene.id}`);
  }
  assert.equal(model.meta.scenes.length, expectedScenes.length, '저자 장면 외 등록이 있습니다.');
  report.registeredScenes = model.meta.scenes.map(([id, startSeconds, endSeconds]) => ({ id, startSeconds, endSeconds }));
  for (const [id, image] of Object.entries(model.images)) assert(image.complete && image.width > 0 && image.height > 0, `미디어 decode 실패: ${id}`);
  report.checks.push({ check: 'resolved scenes and all required image decodes', scenes: expectedScenes.length, assets: Object.keys(model.images).length });

  const screenshot = async (time, name) => {
    await page.evaluate(value => window.__seek(value), time);
    const state = await page.evaluate(() => window.__filmUiState());
    const png = await page.screenshot({ type: 'png' });
    const geometry = await page.evaluate(() => [...document.querySelectorAll('#stage,.scene,.film-caption,.film-spectrum,.film-now,.film-queue,.film-channel,.film-thumbnail')].map(node => ({ className: node.className, hidden: node.hidden, rect: node.getBoundingClientRect().toJSON(), transform: getComputedStyle(node).transform })));
    const file = path.join(out, `${name}.png`);
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(file, png);
    report.frames.push({ time, file, sha256: sha(png), state });
    return { png, state, geometry };
  };
  const smallAntiAliasDiff = async (first, second) => {
    if (first.png.equals(second.png)) return { exact: true, changedPixels: 0, maxChannelDelta: 0 };
    assert.deepEqual(second.geometry, first.geometry, '역순 seek에서 화면 기하가 달라졌습니다.');
    const result = await page.evaluate(async ([a, b]) => {
      const read = async encoded => { const image = new Image(); image.src = `data:image/png;base64,${encoded}`; await image.decode(); const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height; const context = canvas.getContext('2d'); context.drawImage(image, 0, 0); return context.getImageData(0, 0, canvas.width, canvas.height).data; };
      const [left, right] = await Promise.all([read(a), read(b)]); let changedPixels = 0, maxChannelDelta = 0;
      for (let index = 0; index < left.length; index += 4) { let pixelDelta = 0; for (let channel = 0; channel < 4; channel++) pixelDelta = Math.max(pixelDelta, Math.abs(left[index + channel] - right[index + channel])); if (pixelDelta) { changedPixels++; maxChannelDelta = Math.max(maxChannelDelta, pixelDelta); } }
      return { changedPixels, maxChannelDelta };
    }, [first.png.toString('base64'), second.png.toString('base64')]);
    assert(result.changedPixels <= 32 && result.maxChannelDelta <= 1, `역순 seek 픽셀 차이: ${JSON.stringify(result)}`);
    return { exact: false, ...result };
  };
  const duration = model.input.duration;
  const tracks = model.input.playlist?.tracks || [];
  const cues = model.input.captions?.cues || [];
  const interesting = new Set([0, Math.max(0, duration - 1 / model.meta.fps)]);
  for (const scene of model.plan.scenes) interesting.add((scene.startSeconds + scene.endSeconds) / 2);
  for (const track of tracks) if (finite(track.startSeconds)) interesting.add(Math.max(0, track.startSeconds));
  for (const cue of cues) { interesting.add(cue.startSeconds + .001); interesting.add(Math.max(cue.startSeconds, cue.endSeconds - .001)); }
  const samples = [...interesting].filter(time => finite(time) && time >= 0 && time < duration).sort((a, b) => a - b);
  const hashes = new Map();
  for (const [index, time] of samples.entries()) {
    const shot = await screenshot(time, `frame-${index}`);
    hashes.set(time, shot);
    const numbers = await page.evaluate(() => ({ dimensions: [...document.querySelectorAll('canvas')].map(canvas => [canvas.width, canvas.height]).every(([width, height]) => Number.isFinite(width) && Number.isFinite(height) && width >= 0 && height >= 0), invalid: window.__filmCanvasInvalid }));
    assert(numbers.dimensions && !numbers.invalid.length, `Canvas 숫자가 유한하지 않습니다: ${time}`);
  }
  for (const time of [...samples].reverse()) {
    await page.evaluate(value => window.__seek(value), time);
    const reverse = await screenshot(time, `reverse-${time.toFixed(4)}`);
    const comparison = await smallAntiAliasDiff(hashes.get(time), reverse);
    if (!comparison.exact) report.checks.push({ check: 'known Chrome anti-alias variance', time, ...comparison });
  }
  report.checks.push({ check: 'representative frames, finite canvases and reverse seeks', samples: samples.length, antiAliasPixelTolerance: { pixels: 32, rgb: 1 } });

  const expectedCueAt = time => cues.find(cue => time >= cue.startSeconds && time < cue.endSeconds) || null;
  for (const cue of cues) {
    assert(typeof cue.text === 'string' && cue.text.length, `가사 원문이 없습니다: ${cue.id}`);
    for (const time of [Math.max(0, cue.startSeconds - .0001), cue.startSeconds + .0001, Math.max(cue.startSeconds + .0001, cue.endSeconds - .0001), cue.endSeconds]) {
      if (time >= duration) continue;
      await page.evaluate(value => window.__seek(value), time);
      const state = await page.evaluate(() => window.__filmUiState());
      const expected = expectedCueAt(time);
      assert.equal(state.cueId, expected?.id || null, `가사 cue 시작/끝 gate 오류: ${cue.id}`);
      assert.equal(state.text, expected?.text || '', `가사 원문이 바뀌었습니다: ${cue.id}`);
      if (!expected) continue;
      assert(state.captionBounds.length > 0 && state.captionBounds.length <= 2, `가사 범위가 없습니다: ${cue.id}`);
      for (const bounds of state.captionBounds) assert(bounds.l >= 60 && bounds.r <= 1860 && bounds.t >= 40 && bounds.b <= 1040, `가사 안전 영역을 벗어났습니다: ${cue.id}`);
      assert(state.captionFontSize >= 42 && state.captionFontSize <= 64, `가사 글꼴 크기가 계약 밖입니다: ${cue.id}`);
    }
  }
  if (cues.length) {
    const layoutCalls = await page.evaluate(time => {
      const caption = document.querySelector('.film-caption');
      const original = caption.getClientRects.bind(caption);
      let calls = 0;
      caption.getClientRects = () => { calls++; return original(); };
      window.__seek(time); window.__seek(time); window.__seek(time);
      delete caption.getClientRects;
      return calls;
    }, cues[0].startSeconds + .001);
    assert.equal(layoutCalls, 0, '같은 cue seek에서 자막 레이아웃을 반복 측정했습니다.');
    report.checks.push({ check: 'repeated same-cue seeks reuse caption layout', layoutCalls });
  }
  const renderPage = await context.newPage();
  await Promise.race([renderPage.goto(`http://127.0.0.1:${port}/reel/index.html?render=1`, { waitUntil: 'load' }), pageError]);
  await Promise.race([renderPage.waitForFunction(() => window.__ready === true, null, { timeout: 60000 }), pageError]);
  const frame = model.meta.fps;
  const shutter = .5;
  const subTimes = target => Array.from({ length: 4 }, (_, index) => target + (((index + .5) / 4 - .5) * shutter) / frame);
  for (const cue of cues) for (const boundary of [cue.startSeconds, cue.endSeconds]) {
    const target = Math.ceil(boundary * frame - 1e-9) / frame;
    if (target < 0 || target >= duration) continue;
    const expected = expectedCueAt(target);
    for (const sample of subTimes(target)) {
      await renderPage.evaluate(value => window.__seek(value), sample);
      const state = await renderPage.evaluate(() => window.__filmUiState());
      assert.equal(state.cueId, expected?.id || null, `sub4 target-frame cue gate 오류: ${cue.id}`);
      assert.equal(state.text, expected?.text || '', `sub4 target-frame 원문 혼합: ${cue.id}`);
    }
  }
  await renderPage.close();
  report.checks.push({ check: 'sub4 shutter .5 target-frame caption gates', cues: cues.length, samplesPerBoundary: 4 });
  for (const track of tracks) {
    if (!finite(track.startSeconds) || track.startSeconds >= duration) continue;
    await page.evaluate(value => window.__seek(value), track.startSeconds);
    assert.equal((await page.evaluate(() => window.__filmUiState())).trackId, track.id, `곡 경계 trackId 오류: ${track.id}`);
  }
  const lastTrack = tracks.at(-1);
  if (lastTrack && finite(lastTrack.endSeconds) && lastTrack.endSeconds < duration) {
    await page.evaluate(value => window.__seek(value), (lastTrack.endSeconds + duration) / 2);
    assert.equal((await page.evaluate(() => window.__filmUiState())).trackId, lastTrack.id, '마지막 한 프레임 패딩에서 곡 상태가 사라졌습니다.');
  }
  const spectrum = model.input.spectrum;
  const spectrumProbeIndex = spectrum?.frames?.findIndex((frame, index) => (spectrum.t0 || 0) + index * spectrum.dt < duration && frame.some(value => value > 0)) ?? -1;
  const spectrumProbeTime = spectrumProbeIndex < 0 ? 0 : Math.min(duration - 1 / model.meta.fps, (spectrum.t0 || 0) + (spectrumProbeIndex + .25) * spectrum.dt);
  await page.evaluate(value => window.__seek(value), spectrumProbeTime);
  const displayState = await page.evaluate(() => {
    const read = selector => { const node = document.querySelector(selector); return { hidden: node.hidden, text: node.textContent, rect: node.getBoundingClientRect().toJSON(), style: getComputedStyle(node) }; };
    const spectrum = document.querySelector('.film-spectrum');
    const pixels = spectrum.getContext('2d').getImageData(0, 0, spectrum.width, spectrum.height).data;
    return { state: window.__filmUiState(), spectrum: { ...read('.film-spectrum'), painted: [...pixels].some(value => value !== 0) }, queue: read('.film-queue'), now: read('.film-now'), channel: read('.film-channel') };
  });
  assert.equal(displayState.spectrum.hidden, model.input.display.showSpectrum !== true, 'spectrum 표시 상태가 다릅니다.');
  assert.equal(displayState.queue.hidden, model.input.display.showQueue !== true, 'queue 표시 상태가 다릅니다.');
  assert.equal(displayState.now.hidden, model.input.display.showNowPlaying !== true, '현재 곡 표시 상태가 다릅니다.');
  assert.equal(displayState.channel.hidden, !(typeof model.input.display.channelName === 'string' && model.input.display.channelName && model.input.display.channelName !== 'SKIP'), '채널 표시 상태가 다릅니다.');
  if (model.input.display.showSpectrum === true) assert.equal(displayState.spectrum.painted, spectrumProbeIndex >= 0, '실제 FFT의 무음/가청 frame과 canvas pixels가 다릅니다.');
  for (const metadata of [displayState.now, displayState.queue, displayState.channel]) assert(Number.parseFloat(metadata.style.fontSize) >= 32 && metadata.rect.right <= 1920 && metadata.rect.bottom <= 1080, '표시 메타데이터가 읽기 안전 영역을 벗어났습니다.');
  report.checks.push({ check: 'independent display DOM, FFT pixels and metadata bounds', spectrumProbeTime, spectrumProbeIndex, display: model.input.display });
  report.checks.push({ check: 'cue source text, gates, bounds and track boundaries', cues: cues.length, tracks: tracks.length });
  const opening = model.plan.opening;
  if (opening?.thumbnailId) {
    const firstTrack = tracks.find(track => track.startSeconds <= 0 && track.endSeconds > 0);
    const cut = Number(firstTrack?.source?.cutStartSeconds || 0) > 0;
    await page.evaluate(() => window.__seek(0));
    assert.equal((await page.evaluate(() => window.__filmUiState())).thumbnailVisible, !cut, 'thumbnail cutStart 억제 오류');
    if (!cut) {
      const card = await screenshot(Math.min(.1, opening.seconds / 2), 'thumbnail-card');
      const owner = await page.evaluate(() => { const image = document.querySelector('.film-thumbnail'); return { fixedRaster: image.tagName === 'CANVAS' && image.width === FILM_INPUT.width && image.height === FILM_INPUT.height, top: image === image.parentElement.lastElementChild, zIndex: getComputedStyle(image).zIndex, hidden: image.hidden }; });
      assert(owner.fixedRaster, 'thumbnail은 출력 크기로 한 번 고정한 canvas여야 합니다.');
      assert(owner.top && Number(owner.zIndex) >= 10 && !owner.hidden, 'thumbnail이 마지막 paint layer가 아닙니다.');
      for (const time of [opening.seconds - .00625, opening.seconds + .00625]) { await page.evaluate(value => window.__seek(value), time); assert.equal((await page.evaluate(() => window.__filmUiState())).thumbnailVisible, false, '다음 target frame에 thumbnail이 남았습니다.'); }
      const after = await screenshot(opening.seconds + .00625, 'thumbnail-after');
      assert.notDeepEqual(card.png, after.png, 'thumbnail 종료 뒤에도 카드 픽셀이 남았습니다.');
    }
    report.checks.push({ check: 'thumbnail [0, seconds) and cutStart proof', suppressedForCut: cut });
  }
  report.pass = true;
  writeReport(report);
  console.log(JSON.stringify(report));
} catch (error) {
  report.error = String(error.stack || error);
  writeReport(report);
  throw error;
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
