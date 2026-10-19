#!/usr/bin/env node
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { applyDesign } from '../../road-music-video-studio/scripts/html-design.mjs';

const skill = path.resolve(import.meta.dirname, '..');
const template = path.join(skill, 'assets/template');
const showreelHome = process.env.SHOWREEL_HOME || path.join(os.homedir(), '.local/share/roadmusic-video-tools/showreel');
const require = createRequire(path.join(showreelHome, 'scripts/package.json'));
const { chromium } = require('playwright-core');
const mime = { '.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png','.woff2':'font/woff2','.ttf':'font/ttf' };
const variants = ['archive', 'noir', 'neon', 'notebook', 'prism'];
const tracks = [
  { id: 'track-001', title: '길고도 아주 긴 첫 번째 곡 제목은 두 줄 안에서 안전하게 보입니다', startSeconds: 0, endSeconds: 12, durationSeconds: 12 },
  { id: 'track-002', title: '두 번째 곡', startSeconds: 12, endSeconds: 24, durationSeconds: 12 },
  { id: 'track-003', title: '세 번째 곡', startSeconds: 24, endSeconds: 36, durationSeconds: 12 },
  { id: 'track-004', title: '네 번째 곡', startSeconds: 36, endSeconds: 48, durationSeconds: 12 },
  { id: 'track-005', title: '다섯 번째 곡', startSeconds: 48, endSeconds: 60, durationSeconds: 12 },
  { id: 'track-006', title: '여섯 번째 곡', startSeconds: 60, endSeconds: 72, durationSeconds: 12 },
  { id: 'track-007', title: '일곱 번째 곡', startSeconds: 72, endSeconds: 84, durationSeconds: 12 }
];
const spectrum = { schemaVersion: 1, dt: .05, bands: 48, minHz: 40, maxHz: 12000, frames: [Array(48).fill(0), Array.from({ length: 48 }, (_, index) => index === 4 ? 255 : 0), Array.from({ length: 48 }, (_, index) => index === 38 ? 255 : 0)] };
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'showreel-cd-playlist-'));
const project = path.join(temp, 'project');
const reel = path.join(project, 'reel');
const images = path.join(project, 'assets/img');
fs.mkdirSync(images, { recursive: true });
fs.cpSync(template, reel, { recursive: true });
const index = path.join(reel, 'index.html');
fs.writeFileSync(index, await applyDesign(fs.readFileSync(index, 'utf8'), index, { ui: false }));
fs.writeFileSync(path.join(reel, 'timeline.js'), "window.TL={duration:84,cues:{'scene.focus':0,'scene.print':3.692,'scene.memory':5.712,'scene.bokeh':8.963,'scene.cd':10.17},music:{hits:[]},vo:[]};\n");
const server = http.createServer((request, response) => {
  const file = path.resolve(project, '.' + decodeURIComponent(new URL(request.url, 'http://localhost').pathname));
  if (!file.startsWith(project + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); fs.createReadStream(file).pipe(response);
});
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
const palettes = {
  archive: { paper:'#efe3cc', ink:'#34292d', light:'#fff8eb', dark:'#1e171a', accent:'#be5476' },
  noir: { paper:'#17181b', ink:'#ddd8ca', light:'#fff9ea', dark:'#101114', accent:'#bfc8cf' },
  neon: { paper:'#100623', ink:'#dfeeff', light:'#fff3ff', dark:'#08081d', accent:'#ff5bc4' },
  notebook: { paper:'#f7edcf', ink:'#3b4050', light:'#fffdf4', dark:'#424a5b', accent:'#c76d86' },
  prism: { paper:'#EDF3FF', ink:'#17243E', light:'#FFFFFF', dark:'#101D39', accent:'#43BDEE' }
};
function writeProject(variant, display, options = {}) {
  const presetDirectory = { archive:'autumn-archive', noir:'noir-contact', neon:'neon-afterhours', notebook:'lofi-notebook', prism:'chrome-prism' }[variant];
  const requiredAssets = ['photo-a.png','photo-b.png','photo-c.png','case.png','paper.png'];
  const fixtureDirectory = requiredAssets.every(name => fs.existsSync(path.join(skill, 'assets/presets', presetDirectory, name))) ? presetDirectory : 'neon-afterhours';
  const source = path.join(skill, 'assets/presets', fixtureDirectory);
  for (const name of requiredAssets) fs.copyFileSync(path.join(source, name), path.join(images, name));
  const config = { duration:84, fps:30, audio:null, display, playlist:{ schemaVersion:1, tracks }, preset:{ id:`test-${variant}`, name:variant, variant, discPeriodSeconds:6, caption:{ font:variant === 'archive' || variant === 'notebook' ? 'serif' : 'sans', size:57, effect:'underline' }, palette:{ ...palettes[variant], ...options.palette } }, assets:{ photoA:'../assets/img/photo-a.png', photoB:'../assets/img/photo-b.png', photoC:'../assets/img/photo-c.png', case:'../assets/img/case.png', paper:'../assets/img/paper.png' } };
  fs.writeFileSync(path.join(reel, 'config.js'), `window.CD_CONFIG=${JSON.stringify(config)};\n`);
  fs.writeFileSync(path.join(reel, 'spectrum.js'), `window.CD_SPECTRUM=${JSON.stringify(Object.hasOwn(options, 'spectrumData') ? options.spectrumData : spectrum)};\n`);
}
async function pageFor(browser, port) {
  const page = await browser.newPage({ viewport:{ width:1920, height:1080 } });
  const errors = []; page.on('pageerror', error => errors.push(String(error)));
  await page.goto(`http://127.0.0.1:${port}/reel/index.html?render=1`, { waitUntil:'load' });
  await page.waitForFunction(() => window.__ready === true, null, { timeout:60000 });
  return { page, errors };
}
let browser;
try {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless:true, channel:'chrome', args:['--force-color-profile=srgb','--hide-scrollbars','--font-render-hinting=none','--disable-lcd-text','--mute-audio'] });
  const report = [];
  for (const variant of variants) {
    writeProject(variant, { showSpectrum:true, showQueue:true, showNowPlaying:true, channelName:`${variant} CHANNEL` });
    const { page, errors } = await pageFor(browser, server.address().port);
    const read = async time => page.evaluate(t => { window.__seek(t); const now=document.querySelector('.cd-playlist-now-title'), queue=[...document.querySelectorAll('.cd-playlist-queue-item')].map(item=>item.dataset.trackId), empty=document.querySelector('.cd-playlist-queue-empty'), more=document.querySelector('.cd-playlist-queue-more'), spectrum=document.querySelector('.cd-playlist-spectrum'), lyric=document.querySelector('.cd-lyric'); return { now:now?.dataset.trackId || '', queue, empty:hiddenText(empty), more:hiddenText(more), spectrum:!!spectrum, bounds:{ spectrum:spectrum?.getBoundingClientRect().toJSON(), lyric:lyric.getBoundingClientRect().toJSON() }, clamp:getComputedStyle(now).webkitLineClamp }; function hiddenText(element){return element && !element.hidden ? element.textContent : '';} }, time);
    const zero = await read(0), at12 = await read(12), at36 = await read(36), last = await read(72);
    assert.equal(zero.now, 'track-001', `${variant}: current track at 0`); assert.deepEqual(zero.queue, ['track-002','track-003','track-004','track-005','track-006'], `${variant}: initial next queue`); assert.equal(zero.more, '+1곡', `${variant}: remaining queue count`); assert.equal(at12.now, 'track-002', `${variant}: exact half-open boundary`); assert.deepEqual(at12.queue.slice(0,2), ['track-003','track-004'], `${variant}: queue did not advance`); assert.equal(at36.now, 'track-004', `${variant}: fourth track at 36`); assert.equal(last.now, 'track-007', `${variant}: last track is not active`); assert.deepEqual(last.queue, [], `${variant}: invented a next track after the last song`); assert.equal(last.empty, '다음 곡 없음', `${variant}: final queue status is missing`); assert(zero.bounds.spectrum.bottom <= zero.bounds.lyric.top, `${variant}: spectrum overlaps lyric area`); assert.equal(zero.clamp, '2', `${variant}: long current title is not two-line bounded`);
    const pixels = async t => page.evaluate(time => { window.__seek(time); const canvas=document.querySelector('.cd-playlist-spectrum'),ctx=canvas.getContext('2d'); return [...ctx.getImageData(0,0,canvas.width,canvas.height).data]; }, t);
    const silent = hash(Buffer.from(await pixels(0))); const seekValues = await page.evaluate(() => { const before=window.CDPlaylistUI.spectrumValuesAt(window.CD_SPECTRUM,0); window.__seek(.1); window.__seek(0); return { before, after:window.CDPlaylistUI.spectrumValuesAt(window.CD_SPECTRUM,0) }; }); assert.deepEqual(seekValues.after, seekValues.before, `${variant}: spectrum seek is not deterministic`); assert.notEqual(silent, hash(Buffer.from(await pixels(.05))), `${variant}: FFT response did not change`);
    assert.deepEqual(errors, [], `${variant}: browser errors ${errors.join('\n')}`);
    report.push({ variant, currentAt0:zero.now, currentAt12:at12.now, queueAt0:zero.queue.length, spectrum:true });
    await page.close();
  }
  writeProject('neon', { showSpectrum:true, showQueue:true, showNowPlaying:true, channelName:'' }, { palette:{ paper:'#faf0d1', ink:'#124c78', light:'#e1fbff', dark:'#1b123d', accent:'#d02090' } });
  let run = await pageFor(browser, server.address().port);
  const customPalette = await run.page.evaluate(() => { window.__seek(0); const label=document.querySelector('.cd-playlist-label'), rail=document.querySelector('.cd-playlist-rail'); return { accent:getComputedStyle(label).color, text:getComputedStyle(rail).color, panel:getComputedStyle(rail).backgroundColor }; });
  assert.equal(customPalette.accent, 'rgb(208, 32, 144)', 'custom palette accent was not used'); assert.equal(customPalette.text, 'rgb(225, 251, 255)', 'custom palette light was not used'); assert.equal(customPalette.panel, 'rgba(27, 18, 61, 0.76)', 'custom palette dark was not used'); assert.deepEqual(run.errors, [], `custom palette browser errors ${run.errors.join('\n')}`); await run.page.close();
  writeProject('archive', { showSpectrum:false, showQueue:false, showNowPlaying:false, channelName:'' });
  run = await pageFor(browser, server.address().port);
  const off = await run.page.evaluate(() => { window.__seek(12); const disc=window.CD_TEMPLATE_DIAGNOSTICS().disc; return { playlistNodes:document.querySelectorAll('[class*="playlist"]').length, disc, now:window.CDPlaylistUI.stateAt(12).current?.id || '' }; });
  assert.equal(off.playlistNodes, 0, 'all skipped: playlist DOM was created'); assert.equal(off.disc.caseRect.width, 900, 'all skipped: CD layout changed'); assert.deepEqual(off.disc.discCenter, [1240,505], 'all skipped: CD center changed'); assert.equal(off.now, 'track-002', 'track model lost when visual metadata is skipped'); assert.deepEqual(run.errors, [], `all skipped browser errors ${run.errors.join('\n')}`); await run.page.close();
  writeProject('archive', { showSpectrum:false, showQueue:false, showNowPlaying:false, channelName:'채널만 표시' });
  run = await pageFor(browser, server.address().port);
  const channelOnly = await run.page.evaluate(() => { window.__seek(12); return { nodes:document.querySelectorAll('[class*="playlist"]').length, disc:window.CD_TEMPLATE_DIAGNOSTICS().disc }; });
  assert.equal(channelOnly.nodes, 0, 'channel-only: playlist DOM was created'); assert.equal(channelOnly.disc.caseRect.width, 900, 'channel-only: CD layout changed'); assert.deepEqual(run.errors, [], `channel-only browser errors ${run.errors.join('\n')}`); await run.page.close();
  writeProject('archive', { showSpectrum:true, showQueue:false, showNowPlaying:false, channelName:'' });
  run = await pageFor(browser, server.address().port);
  const spectrumOnly = await run.page.evaluate(() => { window.__seek(0); const spectrum=document.querySelector('.cd-playlist-spectrum'), lyric=document.querySelector('.cd-lyric'), disc=window.CD_TEMPLATE_DIAGNOSTICS().disc; return { rail:document.querySelector('.cd-playlist-rail'), width:spectrum.width, spectrum:spectrum.getBoundingClientRect().toJSON(), lyric:lyric.getBoundingClientRect().toJSON(), disc }; });
  assert.equal(spectrumOnly.rail, null, 'spectrum-only: information rail exists'); assert.equal(spectrumOnly.width, 1720, 'spectrum-only: spectrum was not widened'); assert.equal(spectrumOnly.disc.caseRect.x, 300, 'spectrum-only: CD case was not centered'); assert.deepEqual(spectrumOnly.disc.discCenter, [1240,505], 'spectrum-only: disc was not centered'); assert(spectrumOnly.spectrum.right <= 1920 && spectrumOnly.spectrum.bottom <= spectrumOnly.lyric.top, 'spectrum-only: spectrum is outside its safe area'); assert.deepEqual(run.errors, [], `spectrum-only browser errors ${run.errors.join('\n')}`); await run.page.close();
  writeProject('archive', { showSpectrum:false, showQueue:false, showNowPlaying:true, channelName:'' });
  run = await pageFor(browser, server.address().port);
  const nowOnly = await run.page.evaluate(() => { window.__seek(0); const rail=document.querySelector('.cd-playlist-rail'), disc=window.CD_TEMPLATE_DIAGNOSTICS().disc; return { queue:document.querySelector('.cd-playlist-queue'), now:document.querySelector('.cd-playlist-now-title')?.dataset.trackId || '', rail:rail.getBoundingClientRect().toJSON(), disc }; });
  assert.equal(nowOnly.queue, null, 'queue off: queue DOM exists'); assert.equal(nowOnly.now, 'track-001', 'now-playing-only title missing'); assert.equal(nowOnly.disc.caseRect.x, 140, 'now-only: compact CD layout missing'); assert(nowOnly.rail.left > nowOnly.disc.discCenter[0] + nowOnly.disc.discRadius, 'now-only: rail overlaps the CD'); assert.deepEqual(run.errors, [], `now-only browser errors ${run.errors.join('\n')}`); await run.page.close();
  const longChannel = '검증 채널 '.repeat(20).trim();
  writeProject('archive', { showSpectrum:false, showQueue:true, showNowPlaying:false, channelName:longChannel });
  run = await pageFor(browser, server.address().port); await run.page.evaluate(() => window.__seek(12)); const withChannel = hash(await run.page.screenshot({ type:'png' })); assert.deepEqual(run.errors, [], `channel browser errors ${run.errors.join('\n')}`); await run.page.close();
  writeProject('archive', { showSpectrum:false, showQueue:true, showNowPlaying:false, channelName:'' });
  run = await pageFor(browser, server.address().port); await run.page.evaluate(() => window.__seek(12)); const withoutChannel = hash(await run.page.screenshot({ type:'png' })); assert.notEqual(withChannel, withoutChannel, 'channel name did not change CD case pixels'); assert.deepEqual(run.errors, [], `channel-empty browser errors ${run.errors.join('\n')}`); await run.page.close();
  writeProject('archive', { showSpectrum:true, showQueue:false, showNowPlaying:false, channelName:'' }, { spectrumData:null });
  const invalidPage = await browser.newPage({ viewport:{ width:1920, height:1080 } }), invalidErrors = []; invalidPage.on('pageerror', error => invalidErrors.push(String(error))); await invalidPage.goto(`http://127.0.0.1:${server.address().port}/reel/index.html?render=1`, { waitUntil:'load' }); await invalidPage.waitForTimeout(100); assert(invalidErrors.some(message => message.includes('showSpectrum requires a valid CD_SPECTRUM FFT payload')), `invalid FFT did not fail clearly: ${invalidErrors.join('\n')}`); await invalidPage.close();
  console.log(JSON.stringify({ ok:true, checks:['5 variant palettes including prism','custom palette colors','FFT interpolation and silence response','half-open track switching','queue refresh and overflow','long title two-line clamp','spectrum/caption separation','all SKIP and channel-only keep original CD geometry','spectrum-only uses wide safe-area spectrum without rail','now-only compact rail clears the CD','queue-off has no queue DOM','long channel label changes CD case pixels without overflow','invalid FFT fails clearly','no browser errors'], report }));
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
  fs.rmSync(temp, { recursive:true, force:true });
}
