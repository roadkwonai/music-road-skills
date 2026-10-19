#!/usr/bin/env node
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const skill = path.resolve(import.meta.dirname, '..');
const template = path.join(skill, 'assets/template');
const showreelHome = process.env.SHOWREEL_HOME || path.join(os.homedir(), '.local/share/roadmusic-video-tools/showreel');
const require = createRequire(path.join(showreelHome, 'scripts/package.json'));
const { chromium } = require('playwright-core');
const mime = { '.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png','.woff2':'font/woff2','.ttf':'font/ttf' };
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'showreel-cd-track-art-'));
const project = path.join(temp, 'project'), reel = path.join(project, 'reel'), assets = path.join(project, 'assets');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
fs.mkdirSync(assets, { recursive:true }); fs.cpSync(template, reel, { recursive:true });
for (const [folder, preset] of Object.entries({ neon:'neon-afterhours', noir:'noir-contact' })) {
  const output = path.join(assets, folder); fs.mkdirSync(output, { recursive:true });
  for (const name of ['photo-a.png','photo-b.png','photo-c.png','case.png','paper.png']) fs.copyFileSync(path.join(skill, 'assets/presets', preset, name), path.join(output, name));
}
fs.writeFileSync(path.join(reel, 'timeline.js'), "window.TL={duration:3600,cues:{'scene.focus':0,'scene.print':3.692,'scene.memory':5.712,'scene.bokeh':8.963,'scene.cd':10.17},music:{hits:[]},vo:[]};\n");
fs.writeFileSync(path.join(reel, 'spectrum.js'), 'window.CD_SPECTRUM=null;\n');
const paths = folder => Object.fromEntries(['photoA','photoB','photoC','case','paper'].map(name => [name, `../assets/${folder}/${name.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`)}.png`]));
const noir = paths('noir'), neon = paths('neon');
function writeConfig(includeTrackArt = true) {
  const track = (id, title, startSeconds, endSeconds, art) => ({ id, title, startSeconds, endSeconds, durationSeconds:endSeconds - startSeconds, ...(includeTrackArt ? { assets:art } : {}) });
  const config = { duration:3600, fps:30, audio:null, display:{ showSpectrum:false, showQueue:false, showNowPlaying:true, channelName:'ART CHECK' }, playlist:{ schemaVersion:1, tracks:[track('track-neon-first','네온 첫 곡',0,6,neon),track('track-noir','누아르 두 번째 곡',6,12,noir),track('track-neon-last','네온 긴 마지막 곡',12,3600,neon)] }, preset:{ id:'track-art-check',name:'track art check',variant:'archive',discPeriodSeconds:6,caption:{ font:'serif',size:57,effect:'underline' },palette:{ paper:'#efe3cc',ink:'#34292d',light:'#fff8eb',dark:'#1e171a',accent:'#be5476' } }, assets:noir };
  fs.writeFileSync(path.join(reel, 'config.js'), `window.CD_CONFIG=${JSON.stringify(config)};\n`);
}
const server = http.createServer((request, response) => {
  const file = path.resolve(project, '.' + decodeURIComponent(new URL(request.url, 'http://localhost').pathname));
  if (!file.startsWith(project + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { 'Content-Type':mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control':'no-store' }); fs.createReadStream(file).pipe(response);
});
async function open(browser, port, suffix = '') {
  const page = await browser.newPage({ viewport:{ width:1920, height:1080 } }), errors=[]; page.on('pageerror', error => errors.push(String(error)));
  await page.goto(`http://127.0.0.1:${port}/reel/index.html?render=1&${suffix}`, { waitUntil:'load' }); await page.waitForFunction(() => window.__ready === true, null, { timeout:60000 }); return { page, errors };
}
async function capture(page, t, clip) { await page.evaluate(time => window.__seek(time), t); return hash(await page.screenshot({ type:'png', ...(clip ? { clip } : {}) })); }
let browser;
try {
  writeConfig(true); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless:true, channel:'chrome', args:['--force-color-profile=srgb','--hide-scrollbars','--font-render-hinting=none','--disable-lcd-text','--mute-audio'] });
  let { page, errors } = await open(browser, server.address().port, 'with-art');
  const inspect = async t => page.evaluate(time => { window.__seek(time); return { art:window.CD_TRACK_ART_DIAGNOSTICS(time), caption:getComputedStyle(document.querySelector('.cd-lyric')).opacity, current:document.querySelector('.cd-playlist-now-title')?.dataset.trackId || '' }; }, t);
  const firstFrame = await capture(page, 0);
  const first = await inspect(0), beforeShort = await inspect(5.9), second = await inspect(6), beforeSwitch = await inspect(11.9), afterSwitch = await inspect(12), at30m = await inspect(1800), at59m = await inspect(3540), padded = await inspect(3600);
  assert.equal(first.art.id, 'track-neon-first'); assert(first.art.paths.photoA.includes('/neon/'), 'first intro did not select first track art'); assert.equal(first.caption, '1', 'caption display changed'); assert.equal(first.current, 'track-neon-first', 'current title changed');
  assert.equal(beforeShort.art.id, 'track-neon-first'); assert.equal(second.art.id, 'track-noir'); assert.equal(second.art.forcedBody, true, 'short first track did not interrupt intro'); assert.equal(Math.round(second.art.disc.discDegrees), 0, 'second track disc did not start from zero phase');
  assert.equal(beforeSwitch.art.id, 'track-noir'); assert.equal(afterSwitch.art.id, 'track-neon-last'); assert.equal(Math.round(afterSwitch.art.disc.discDegrees), 0, 'next track disc did not restart from zero phase');
  assert.equal(at30m.art.id, 'track-neon-last'); assert.equal(at59m.art.id, 'track-neon-last'); assert.equal(padded.art.id, 'track-neon-last', 'padding returned to common art');
  const noirCase = await capture(page, 11.9, { x:100,y:50,width:820,height:800 }), neonCase = await capture(page, 12, { x:100,y:50,width:820,height:800 }); assert.notEqual(noirCase, neonCase, 'track boundary did not change the CD case');
  const neonBody = await capture(page, 12), reverse = await capture(page, 11.9), restored = await capture(page, 12); assert.notEqual(neonBody, reverse, 'track boundary did not change body art'); assert.equal(restored, neonBody, 'reverse seek did not restore track art deterministically');
  const minute30 = await capture(page, 1800), minute59 = await capture(page, 3540); assert.equal(minute30.length, 64, '30-minute capture failed'); assert.equal(minute59.length, 64, '59-minute capture failed'); assert.deepEqual(errors, [], `track art browser errors: ${errors.join('\n')}`); await page.close();
  writeConfig(false); ({ page, errors } = await open(browser, server.address().port, 'common-art')); const commonFirst = await capture(page, 0); assert.notEqual(commonFirst, firstFrame, 'first track art did not affect the initial frame'); assert.deepEqual(errors, [], `common fallback browser errors: ${errors.join('\n')}`); await page.close();
  console.log(JSON.stringify({ ok:true, checks:['first track asset replaces common intro art','short first track interrupts intro at second-track boundary','CD case and printed disc change together','reverse seek restores track art','per-track disc phase restarts','30-minute and 59-minute capture','padding keeps final art','captions/current title/channel mode remain active','no browser errors'] }));
} finally {
  await browser?.close(); await new Promise(resolve => server.close(resolve)); fs.rmSync(temp, { recursive:true, force:true });
}
