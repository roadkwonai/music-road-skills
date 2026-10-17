import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import os from 'node:os';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire(path.join(process.env.SHOWREEL_HOME || path.join(os.homedir(),'.local/share/roadmusic-video-tools/showreel'),'scripts/package.json'));
const {chromium}=require('playwright-core');
const project=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);fs.mkdirSync(out,{recursive:true});
const readGlobal=(name,prefix)=>JSON.parse(fs.readFileSync(path.join(project,'reel',name),'utf8').replace(prefix,'').trim().replace(/;$/,''));
const original=readGlobal('config.js','window.PLAYLIST_CONFIG=');
assert.equal(original.playlist.tracks.length,2,'이 QA는 곡 경계를 가진 2트랙 검수 프로젝트가 필요합니다.');
const boundaryTime=original.playlist.tracks[1].startSeconds,endTime=original.duration;
const originalLyrics=readGlobal('lyrics.js','window.PLAYLIST_LYRICS=');
let config=structuredClone(original),lyrics=originalLyrics;
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png','.woff2':'font/woff2','.wav':'audio/wav'};
const server=http.createServer((req,res)=>{
  const name=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const special=name==='/reel/config.js'?`window.PLAYLIST_CONFIG=${JSON.stringify(config)};`:name==='/reel/lyrics.js'?`window.PLAYLIST_LYRICS=${JSON.stringify(lyrics)};`:null;
  if(special){res.writeHead(200,{'Content-Type':'text/javascript','Cache-Control':'no-store'});res.end(special);return;}
  const file=path.resolve(project,'.'+name);if(!file.startsWith(project+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--force-color-profile=srgb','--hide-scrollbars','--disable-lcd-text','--mute-audio']});
const report=[];let page;
async function open(){if(page)await page.close();page=await browser.newPage({viewport:{width:1920,height:1080}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));await page.goto(`http://127.0.0.1:${server.address().port}/reel/index.html?render=1`);await page.waitForFunction(()=>window.__ready===true,null,{timeout:60000});assert.deepEqual(errors,[]);return errors;}
async function frame(t){await page.evaluate(t=>window.__seek(t),t);return crypto.createHash('sha256').update(await page.screenshot()).digest('hex');}
try{
 const errors=await open();
 const times=[0,.9,2.2,6.5,boundaryTime-.01,boundaryTime,boundaryTime+.01,Math.min(endTime-.02,boundaryTime+5.5),endTime-.02],hashes=new Map();
 for(const t of times){hashes.set(t,await frame(t));await page.screenshot({path:path.join(out,`frame-${t}.png`)});}
 for(const t of times.toReversed())assert.equal(await frame(t),hashes.get(t),`reverse seek ${t}`);
 const boundary=await page.evaluate(([b,e])=>[b-.01,b,b+.01,e].map(t=>{window.__seek(t);return {t,art:GROOVE_DIAGNOSTICS().activeTrack,state:GroovePlaylistUI.stateAt(t),intro:GROOVE_DIAGNOSTICS().introActive};}),[boundaryTime,endTime]);
 assert.equal(boundary[0].art,0);assert.equal(boundary[1].art,1);assert.equal(boundary[3].art,1);assert.equal(boundary[1].intro,false);assert.equal(boundary[0].state.queue.length,1);assert.equal(boundary[1].state.queue.length,0);
 const words=await page.evaluate(()=>PLAYLIST_LYRICS.flatMap((line,li)=>(line.words||[]).map((w,wi)=>{window.__seek((w.startSeconds+w.endSeconds)/2);return {li,wi,...GrooveCaptions.state()};})));
 for(const w of words){assert.equal(w.activeLine,w.li);assert.equal(w.activeWord,w.wi);assert(w.activeScale<=1.100001);assert(Math.abs(w.activeTilt)<=2);assert(w.bounds.every(b=>b.l>=260 && b.r<=1660 && b.t>=913 && b.b<=1033));}
 const gaps=await page.evaluate(()=>PLAYLIST_LYRICS.flatMap(line=>{const ws=line.words||[],samples=[];for(let i=0;i<ws.length-1;i++)if(ws[i+1].startSeconds-ws[i].endSeconds>.06)samples.push((ws[i].endSeconds+ws[i+1].startSeconds)/2);return samples;}).map(t=>{__seek(t);return GrooveCaptions.state().activeWord;}));assert(gaps.every(v=>v===-1));
 assert(await page.evaluate(()=>document.fonts.check('800 66px Paperlogy')));
 const spectrum=await page.evaluate(()=>{const s=PLAYLIST_SPECTRUM;return [s.frames.length,s.frames[0].length,new Set(s.frames.map(f=>f.join(','))).size];});assert(spectrum[0]>1 && spectrum[1]===48 && spectrum[2]>1);
 report.push({check:'original options, captions, art boundary, FFT, seek',words:words.length,boundary});
 for(let mask=0;mask<8;mask++){
  config=structuredClone(original);config.display={showSpectrum:Boolean(mask&1),showQueue:Boolean(mask&2),showNowPlaying:Boolean(mask&4),channelName:''};await open();
  const options=await page.evaluate(()=>({s:!!document.querySelector('.cd-playlist-spectrum'),q:!!document.querySelector('.cd-playlist-queue'),n:!!document.querySelector('.cd-playlist-now-title'),channel:GROOVE_DIAGNOSTICS().channelName}));
  assert.deepEqual(options,{s:Boolean(mask&1),q:Boolean(mask&2),n:Boolean(mask&4),channel:''});
 }
 report.push({check:'all 8 display combinations and empty channel',ok:true});
 for(const mode of ['balanced','drive','soft']){
  config=structuredClone(original);config.preset.motionMode=mode;for(const track of config.playlist.tracks)track.motionMode=mode;await open();await frame(2.2);await page.screenshot({path:path.join(out,`mode-${mode}.png`)});
  assert.equal(await page.evaluate(()=>GROOVE_DIAGNOSTICS().profile.name),mode);
 }
 config=structuredClone(original);config.playlist.tracks[0].motionMode='drive';config.playlist.tracks[1].motionMode='soft';await open();
 const trackModes=await page.evaluate(b=>[b-.01,b+.01].map(t=>{__seek(t);return GROOVE_DIAGNOSTICS().profile.name;}),boundaryTime);assert.deepEqual(trackModes,['drive','soft']);
 report.push({check:'motion mode changes with track',trackModes});
 for(const variant of ['archive','noir','neon','notebook','prism']){
  config=structuredClone(original);config.preset.variant=variant;await open();await frame(7.8);await page.screenshot({path:path.join(out,`material-${variant}.png`)});const a=await frame(8);await frame(22);assert.equal(await frame(8),a);
 }
 // 긴 곡의 끝으로 바로 이동해도 같은 프레임을 재현한다.
 config=structuredClone(original);config.duration=3600;config.playlist.tracks[1].endSeconds=3600;lyrics=[];await open();
 const long=await frame(3598.5);await frame(23.5);assert.equal(await frame(3598.5),long);assert.equal(await page.evaluate(()=>GrooveCaptions.state().activeLine),-1);
 report.push({check:'3 motion modes, 5 variant smoke checks, 1-hour direct seek',ok:true});
 // 줄 단위 SRT로 가짜 어절 시각을 만들지 않는다.
 config=structuredClone(original);lyrics=[{startSeconds:0,endSeconds:4,text:'줄 자막은 전체가 즉시 보입니다'}];await open();await frame(.01);const lineOnly=await page.evaluate(()=>GrooveCaptions.state());assert.equal(lineOnly.activeWord,-1);assert.equal(lineOnly.wordTiming,false);assert.equal(lineOnly.text,lyrics[0].text);
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({ok:true,report},null,2));console.log(JSON.stringify({ok:true,report}));
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
