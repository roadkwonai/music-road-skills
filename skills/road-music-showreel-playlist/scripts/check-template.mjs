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
const source = process.env.SHOWREEL_CD_TEMPLATE_SOURCE || path.join(skill, 'assets/presets/autumn-archive');
const showreelHome = process.env.SHOWREEL_HOME || path.join(os.homedir(), '.local/share/roadmusic-video-tools/showreel');
const require = createRequire(path.join(showreelHome, 'scripts/package.json'));
const { chromium } = require('playwright-core');
const mime = { '.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png','.wav':'audio/wav','.woff2':'font/woff2','.ttf':'font/ttf' };
const variants = [
  ['archive', 'serif', 'underline'], ['noir', 'sans', 'bracket'],
  ['neon', 'sans', 'glow'], ['notebook', 'serif', 'marker'], ['prism', 'sans', 'glow']
];
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'showreel-cd-template-'));
const project = path.join(temporary, 'project');
const reel = path.join(project, 'reel');
const assets = path.join(project, 'assets/img');
const sourceAssets = source;
for (const name of ['photo-a.png','photo-b.png','photo-c.png','case.png','paper.png']) assert(fs.existsSync(path.join(sourceAssets,name)), `fixture asset missing: ${name}`);
fs.mkdirSync(assets, { recursive: true });
fs.cpSync(template, reel, { recursive: true });
for (const name of ['photo-a.png','photo-b.png','photo-c.png','case.png','paper.png']) fs.copyFileSync(path.join(sourceAssets,name),path.join(assets,name));
fs.writeFileSync(path.join(reel, 'timeline.js'), `window.TL={duration:30,cues:{'scene.focus':0,'scene.print':3.692,'scene.memory':5.712,'scene.bokeh':8.963,'scene.cd':10.17,'music.hit3':27,'music.hit9':29},music:{hits:[]},vo:[]};\n`);

const server = http.createServer((request, response) => {
  const file = path.resolve(project, '.' + decodeURIComponent(new URL(request.url, 'http://localhost').pathname));
  if (!file.startsWith(project + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); fs.createReadStream(file).pipe(response);
});
const json = value => JSON.stringify(value, null, 2);
const config = (variant, font, effect) => `window.CD_CONFIG=${JSON.stringify({duration:30,fps:30,audio:null,preset:{id:`check-${variant}`,name:variant,variant,discPeriodSeconds:6,caption:{font,size:57,effect},palette:variant==='prism'?{paper:'#EDF3FF',ink:'#17243E',light:'#FFFFFF',dark:'#101D39',accent:'#43BDEE'}:{paper:'#efe3cc',ink:'#34292d',light:'#fff8eb',dark:'#1e171a',accent:'#be5476'}},assets:{photoA:'../assets/img/photo-a.png',photoB:'../assets/img/photo-b.png',photoC:'../assets/img/photo-c.png',case:'../assets/img/case.png',paper:'../assets/img/paper.png'}})};\n`;
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
let browser;
try {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--force-color-profile=srgb','--hide-scrollbars','--font-render-hinting=none','--disable-lcd-text','--mute-audio'] });
  const report = [], introHashes = new Set(), introByVariant = new Map();
  for (const [variant, font, effect] of variants) {
    fs.writeFileSync(path.join(reel, 'config.js'), config(variant, font, effect));
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const errors = []; page.on('pageerror', error => errors.push(String(error)));
    await page.goto(`http://127.0.0.1:${server.address().port}/reel/index.html?render=1`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
    const frame = async time => { await page.evaluate(t => window.__seek(t), time); return hash(await page.screenshot({ type: 'png' })); };
    const forward = await frame(6.4), middle = await frame(12.4), back = await frame(6.4);
    assert.equal(back, forward, `${variant}: seek result is not deterministic`);
    assert.notEqual(middle, forward, `${variant}: intro and CD body are indistinguishable`);
    if (variant === 'prism') {
      const beforeWipe = await frame(7.3), afterWipe = await frame(8.1), restoredWipe = await frame(7.3);
      assert.notEqual(beforeWipe, afterWipe, 'prism: memory glass wipe did not change the image');
      assert.equal(restoredWipe, beforeWipe, 'prism: memory glass wipe is not seek deterministic');
    }
    const onset = await page.evaluate(() => {
      window.__seek(window.ARCHIVE_LYRICS[0].startSeconds);
      const line = document.querySelector('.cd-lyric .line');
      return { text: line.textContent, opacities: [...line.querySelectorAll('span')].map(el => getComputedStyle(el).opacity), font: getComputedStyle(document.querySelector('.cd-lyric')).fontFamily };
    });
    assert.equal(onset.text, '가사를 여기에 넣습니다');
    assert(onset.opacities.every(value => Number(value) === 1), `${variant}: caption is delayed at onset: ${onset.opacities}`);
    assert(onset.font.includes(font === 'serif' ? 'Noto Serif KR' : 'Pretendard'), `${variant}: configured caption font was not applied`);
    const cueEnd = await page.evaluate(() => {
      const line = window.ARCHIVE_LYRICS[0], frame = 1 / window.__meta.fps;
      window.__seek(line.endSeconds - frame);
      const inside = [...document.querySelectorAll('.cd-lyric .line span')].map(el => getComputedStyle(el).opacity);
      window.__seek(line.endSeconds);
      const lines = [...document.querySelectorAll('.cd-lyric .line')];
      return { inside, previousDisplay: getComputedStyle(lines[0]).display, nextText: lines[1]?.textContent || '', outer: getComputedStyle(document.querySelector('.cd-lyric')).opacity };
    });
    assert(cueEnd.inside.every(value => Number(value) === 1), `${variant}: caption faded before cue end: ${cueEnd.inside}`);
    assert.equal(cueEnd.previousDisplay, 'none', `${variant}: previous caption remains visible at cue end`);
    assert.equal(cueEnd.nextText, '시작 시각에 전체 줄이 보입니다', `${variant}: next cue did not take over at the exact boundary`);
    const diagnostics = await page.evaluate(() => window.CD_TEMPLATE_DIAGNOSTICS());
    assert.equal(diagnostics.variant, variant); assert.equal(diagnostics.disc.discPeriodSeconds, 6);
    assert.equal(diagnostics.validatedHits.focusSwap, (diagnostics.boundaries.focus + diagnostics.boundaries.print) / 2, `${variant}: out-of-scene hit3 was not replaced`);
    assert.equal(diagnostics.validatedHits.memoryCut, diagnostics.boundaries.memory + (diagnostics.boundaries.bokeh - diagnostics.boundaries.memory) * .65, `${variant}: out-of-scene hit9 was not replaced`);
    assert.equal(diagnostics.disc.discDegrees, 0);
    assert.equal(diagnostics.discAtHalfTurn.discDegrees, 180, `${variant}: disc does not reach the opposite phase after three seconds`);
    assert.equal(diagnostics.discAtFullTurn.discDegrees, diagnostics.disc.discDegrees, `${variant}: disc does not return after six seconds`);
    assert.deepEqual(errors, [], `${variant}: page errors: ${errors.join('\n')}`);
    introHashes.add(forward);
    introByVariant.set(variant, forward);
    report.push({ variant, deterministic: forward, captionOnset: onset.opacities, cueEnd: cueEnd.inside, discPeriodSeconds: diagnostics.disc.discPeriodSeconds });
    await page.close();
  }
  assert.equal(introHashes.size, variants.length, 'preset variants rendered the same intro frame');
  assert.notEqual(introByVariant.get('prism'), introByVariant.get('archive'), 'prism modern staging matched archive');
  console.log(json({ ok: true, checks: ['5 variants load skill preset fixture assets','visually distinct preset intros including modern prism','seek determinism','caption full opacity across each active cue','configured caption font','out-of-scene music hits fall back inside their scene','6-second disc phase','no page errors'], report }));
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
  fs.rmSync(temporary, { recursive: true, force: true });
}
