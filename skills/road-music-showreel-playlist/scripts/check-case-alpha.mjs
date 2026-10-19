#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';

if (!process.argv[2] || !process.argv[3]) throw new Error('usage: check-case-alpha.mjs <records.js> <result.json>');
const records = path.resolve(process.argv[2]);
const output = path.resolve(process.argv[3]);
if (!records || !output) throw new Error('usage: check-case-alpha.mjs <records.js> <result.json>');
const require = createRequire(path.join(process.env.SHOWREEL_HOME || path.join(os.homedir(),'.local/share/roadmusic-video-tools/showreel'),'scripts/package.json'));
const { chromium } = require('playwright-core');
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--force-color-profile=srgb'] });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.setContent('<!doctype html><html><body></body></html>');
  await page.evaluate(() => { window.PLAYLIST_CONFIG = { preset: { variant: 'archive', palette: { accent: '#cc6644', ink: '#222222', light: '#eeeeee' } } }; });
  await page.addScriptTag({ path: records });
  const result = await page.evaluate(() => {
    const solid = (width, height, color) => {
      const node = document.createElement('canvas'); node.width = width; node.height = height;
      const ctx = node.getContext('2d'); ctx.fillStyle = color; ctx.fillRect(0, 0, width, height);
      return node;
    };
    const caseImage = document.createElement('canvas'); caseImage.width = caseImage.height = 1254;
    const source = caseImage.getContext('2d'); source.fillStyle = '#7a8da2'; source.fillRect(126, 126, 1002, 1002);
    const layers = window.RecordLayers.create({ photos: [solid(1200, 800, '#884466'), solid(1200, 800, '#446688'), solid(1200, 800, '#668844')], case: caseImage, paper: solid(1200, 800, '#d8ccb8') });
    const pixel = layers.case.getContext('2d').getImageData(150, 130, 1, 1).data;
    return { sample: { x: 150, y: 130, rgba: [...pixel] }, layer: { width: layers.case.width, height: layers.case.height } };
  });
  if (result.sample.rgba[3] > 10) throw new Error(`투명 case 여백이 불투명하게 합성됨: alpha=${result.sample.rgba[3]}`);
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
