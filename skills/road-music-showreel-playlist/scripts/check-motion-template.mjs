import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import os from 'node:os';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';

const project=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
assert(!fs.existsSync(out),'QA 출력은 새 폴더를 사용하세요.');
const require=createRequire(path.join(process.env.SHOWREEL_HOME||path.join(os.homedir(),'.local/share/roadmusic-video-tools/showreel'),'scripts/package.json'));
const {chromium}=require('playwright-core');
const readGlobal=(file,prefix)=>{
  const source=fs.readFileSync(path.join(project,'reel',file),'utf8'),name=prefix.replace('=','');
  assert(source.trimStart().startsWith(name),`유효하지 않은 전역: ${file}`);
  return JSON.parse(source.slice(source.indexOf('=')+1).trim().replace(/;$/,''));
};
const original=readGlobal('config.js','window.PLAYLIST_CONFIG=');
const originalDirection=readGlobal('direction.js','window.PLAYLIST_DIRECTION=');
const originalLyrics=readGlobal('lyrics.js','window.PLAYLIST_LYRICS=');
assert(originalDirection?.sections?.length,'먼저 direction을 적용하세요.');
let config=structuredClone(original),direction=structuredClone(originalDirection),lyrics=originalLyrics;
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.woff2':'font/woff2','.wav':'audio/wav','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'};
const server=http.createServer((req,res)=>{
  let name;try{name=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}catch{res.writeHead(400);res.end();return;}
  const special={'/reel/config.js':['PLAYLIST_CONFIG',config],'/reel/direction.js':['PLAYLIST_DIRECTION',direction],'/reel/lyrics.js':['PLAYLIST_LYRICS',lyrics]}[name];
  if(special){res.writeHead(200,{'Content-Type':'text/javascript','Cache-Control':'no-store'});res.end(`window.${special[0]}=${JSON.stringify(special[1])};`);return;}
  const file=path.resolve(project,'.'+name);
  if(!file.startsWith(project+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser,page;const errors=[],checks=[];
async function open(){
  if(page)await page.close();
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}/reel/index.html?render=1`);
  await page.waitForFunction(()=>window.__ready===true,null,{timeout:30000});
  assert.deepEqual(errors,[]);
}
async function sample(t){await page.evaluate(t=>__seek(t),t);return page.evaluate(()=>MOTION_DIAGNOSTICS());}
async function frame(t){await sample(t);return crypto.createHash('sha256').update(await page.screenshot()).digest('hex');}
function bounds(state){
  if(!state.text)return;
  assert(state.captionBounds.length>0,'본문이 있으면 실제 글자 영역을 제공해야 합니다.');
  for(const b of state.captionBounds)assert(b.l>=60&&b.r<=1860&&b.t>=60&&b.b<=1040,`글자 영역 ${JSON.stringify(b)}`);
}
try{
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--force-color-profile=srgb','--hide-scrollbars','--disable-lcd-text','--mute-audio']});
  fs.mkdirSync(out,{recursive:true});await open();
  if(direction.media?.thumbnail){
    const duration=direction.media.thumbnail.durationSeconds;
    const initial=await frame(0),lastFrame=Math.ceil(duration*config.fps)-1;
    assert.equal((await sample(0)).thumbnailActive,true);
    assert.equal((await sample(lastFrame/config.fps)).thumbnailActive,true);
    assert.equal(await frame(lastFrame/config.fps),initial,'썸네일 구간은 고정 이미지여야 합니다.');
    assert.equal((await sample(duration)).thumbnailActive,false);
    assert.notEqual(await frame(duration),initial);
    const subframes=await page.evaluate(({fps,lastFrame})=>[lastFrame,lastFrame+1].map(f=>[-.375,-.125,.125,.375].map(off=>{__seek(Math.max(0,(f+off)/fps));return MOTION_DIAGNOSTICS().thumbnailActive;})),{fps:config.fps,lastFrame});
    assert(subframes[0].every(Boolean)&&subframes[1].every(value=>!value),'모션 블러 샘플에서도 썸네일이 다음 프레임에 섞이면 안 됩니다.');
    checks.push({check:'thumbnail frame interval, still image and unchanged audio clock',durationSeconds:duration,thumbnailFrames:lastFrame+1});
  }
  const hashes=new Map(),sections=[];
  for(const [i,s] of direction.sections.entries()){
    const t=(s.startSeconds+s.endSeconds)/2,state=await sample(t);
    assert.equal(state.style,s.style);assert.equal(state.motif,s.motif);assert.equal(state.trackId,s.trackId);assert.equal(state.intensity,s.intensity);bounds(state);
    if(s.imageId)assert.equal(state.imageId,s.imageId,'구간별 생성 이미지가 실제 합성되어야 합니다.');
    hashes.set(t,await frame(t));await page.screenshot({path:path.join(out,`section-${i}-${s.style}.png`)});sections.push(state.style);
    if(s.startSeconds>0){const before=await sample(s.startSeconds-1e-4),after=await sample(s.startSeconds+1e-4);assert.equal(after.style,s.style);assert.equal(after.trackId,s.trackId);assert(before.style);}
  }
  for(const [t,hash] of [...hashes].reverse())assert.equal(await frame(t),hash,`역순 seek ${t}`);
  checks.push({check:'section style, motif, intensity, track and reverse seek',styles:sections});
  for(const cue of lyrics){
    for(const t of [Math.max(0,cue.startSeconds-.001),cue.startSeconds+.001,cue.endSeconds-.001,cue.endSeconds+.001]){
      if(t>=config.duration)continue;
      const state=await sample(t),expected=lyrics.find(c=>t>=c.startSeconds&&t<c.endSeconds);
      assert.equal(state.text,expected?.text||'',`가사 gate ${t}`);bounds(state);
    }
  }
  const accent=direction.accents.find(a=>a.timeSeconds+.07<config.duration);
  if(accent){
    const t=accent.timeSeconds+.05,state=await sample(t),withAccent=await frame(t);
    assert(state.pulse>0&&state.activeAccents.length>0,'선택한 타격음의 효과가 활성화되어야 합니다.');
    direction.accents=[];await open();assert.notEqual(await frame(t),withAccent,'선택 효과가 실제 픽셀을 바꿔야 합니다.');
    direction=structuredClone(originalDirection);await open();
  }
  assert(await page.evaluate(()=>document.fonts.check('800 66px Paperlogy')));
  checks.push({check:'exact lyric onset/end, caption bounds, font, selected accent',cues:lyrics.length,accents:direction.accents.length});
  const optionHashes=new Set();
  for(let mask=0;mask<8;mask++){
    config=structuredClone(original);config.display={showSpectrum:!!(mask&1),showQueue:!!(mask&2),showNowPlaying:!!(mask&4),channelName:''};await open();
    const t=Math.min(3,config.duration/2),state=await sample(t);
    assert.deepEqual(state.display,config.display);optionHashes.add(await frame(t));
  }
  assert.equal(optionHashes.size,8,'각 표시 조합이 실제 화면에 반영되어야 합니다.');
  checks.push({check:'all eight display combinations change pixels',distinctFrames:optionHashes.size});
  config=structuredClone(original);config.display={showSpectrum:false,showQueue:false,showNowPlaying:false,channelName:''};
  direction=structuredClone(originalDirection);lyrics=[{startSeconds:1,endSeconds:5,text:'오늘 하루도 여기까지 잘 걸어왔어 우리 함께 천천히 내일을 기다리면 작은 용기가 다시 피어날 거야'}];await open();
  const long=await sample(2);assert.equal(long.text,lyrics[0].text);bounds(long);assert(long.captionBounds.length<=2);
  await page.screenshot({path:path.join(out,'long-korean-caption.png')});
  direction.accents=[];lyrics=[];await open();await page.evaluate(()=>{if(TL.music?.energy?.v)TL.music.energy.v.fill(0);});
  const silent=await sample(2);assert.equal(silent.text,'');assert.equal(silent.pulse,0);assert.equal(silent.energy,0);
  checks.push({check:'long Korean caption fits, no fake lyric or acoustic pulse in silent fixture',ok:true});
  assert.deepEqual(errors,[]);
  direction=null;
  await page.close();page=await browser.newPage({viewport:{width:1920,height:1080}});
  const expectedErrors=[];page.on('pageerror',e=>expectedErrors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}/reel/index.html?render=1`,{waitUntil:'networkidle'});
  assert(await page.locator('#direction-error').isVisible());
  assert.equal(await page.evaluate(()=>window.__ready===true),false,'방향 누락을 렌더 준비 완료로 표시하면 안 됩니다.');
  assert(expectedErrors.some(e=>e.includes('Rhythm Canvas')));
  checks.push({check:'missing direction fails before native render ready',ok:true});
  const report={ok:true,project,checks,errors};fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
