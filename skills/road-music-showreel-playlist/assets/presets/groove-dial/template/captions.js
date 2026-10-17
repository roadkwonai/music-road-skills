(() => {
  'use strict';
  const G=window.GROOVE,config=window.PLAYLIST_CONFIG;
  const lines=window.PLAYLIST_LYRICS, PANEL={x:260,y:913,w:1400,h:120};
  const cache=new Map();let layer,ctx,plate,measure,latest;
  const canvas=(w,h)=>{const c=document.createElement('canvas');c.width=w;c.height=h;return c;};
  function glyph(text,weight,color,width,font){const c=canvas(width*2,200),x=c.getContext('2d');x.scale(2,2);x.font=`${weight} ${font}px Paperlogy`;x.fillStyle=color;x.textAlign='center';x.textBaseline='alphabetic';x.fillText(text,width/2,73);return c;}
  function rowFor(index){
    if(cache.has(index))return cache.get(index);
    const line=lines[index],tokens=line.words?.length?line.words:[{text:line.text}],timed=Boolean(line.words?.length);
    let font=config.preset.caption.size,words,total;
    do{
      measure.font=`800 ${font}px Paperlogy`;
      words=tokens.map(word=>{const width=Math.ceil(measure.measureText(word.text).width+20);return {...word,width,cellWidth:Math.ceil(width*1.11+10)};});
      total=words.reduce((sum,w)=>sum+w.cellWidth,0)+(words.length-1)*10;
      if(total<=PANEL.w-64)break;font-=2;
    }while(font>=40);
    if(font<40)throw new Error('가사 안전 영역 초과: 실제 가창 경계로 큐를 나누세요. '+line.text);
    let x=960-total/2;
    for(const word of words){word.x=x+word.cellWidth/2;x+=word.cellWidth+10;word.images=[glyph(word.text,700,'#f5f5ef',word.width,font),glyph(word.text,700,'#bec6c6',word.width,font),glyph(word.text,800,'#ffc66f',word.width,font)];}
    const row={...line,words,font,timed};cache.set(index,row);if(cache.size>3)cache.delete(cache.keys().next().value);return row;
  }
  function setup(parent){
    layer=canvas(1920,1080);layer.className='lyric-canvas';layer.style.cssText='position:absolute;inset:0;pointer-events:none';parent.append(layer);ctx=layer.getContext('2d');
    plate=canvas(PANEL.w,PANEL.h);const p=plate.getContext('2d');p.fillStyle='rgba(18,21,25,.8)';p.strokeStyle='rgba(255,255,255,.13)';p.lineWidth=1;p.beginPath();p.roundRect(.5,.5,PANEL.w-1,PANEL.h-1,19);p.fill();p.stroke();measure=canvas(1,1).getContext('2d');
  }
  function render(t){
    ctx.clearRect(0,0,1920,1080);
    const activeLine=lines.findIndex(line=>t>=line.startSeconds && t<line.endSeconds);
    latest={t,activeLine,activeWord:-1,activeScale:1,activeTilt:0,text:'',panelAlpha:.8,font:'Paperlogy',fontSize:config.preset.caption.size,bounds:[],wordTiming:false};
    if(activeLine<0){layer.setAttribute('aria-label','');return;}
    const line=rowFor(activeLine),beat=G.impulse(t),profile=G.profileAt(t);ctx.drawImage(plate,PANEL.x,PANEL.y);layer.setAttribute('aria-label',line.text);
    latest.text=line.text;latest.fontSize=line.font;latest.wordTiming=line.timed;
    line.words.forEach((word,wi)=>{
      const active=line.timed && t>=word.startSeconds && t<word.endSeconds,past=line.timed && t>=word.endSeconds;
      const arrival=active?Math.exp(-(t-word.startSeconds)/.18):0;
      const scale=active?1.018+Math.min(.082,beat*.062*profile.impact+arrival*.025):1;
      const tilt=active?(wi%2?-1:1)*beat*profile.tilt:0,cy=PANEL.y+PANEL.h/2-(active?2*beat*profile.impact:0);
      ctx.save();ctx.translate(word.x,cy);ctx.rotate(tilt*Math.PI/180);ctx.scale(scale,scale);ctx.drawImage(word.images[active?2:past?1:0],-word.width/2,-50,word.width,100);ctx.restore();
      if(active){const progress=G.clamp((t-word.startSeconds)/Math.max(.01,word.endSeconds-word.startSeconds));ctx.fillStyle='rgba(255,198,111,.9)';ctx.fillRect(word.x-word.width*.34,PANEL.y+103,word.width*.68*progress,3);Object.assign(latest,{activeWord:wi,activeScale:scale,activeTilt:tilt});}
      const rad=Math.abs(tilt*Math.PI/180),hw=scale*(word.width*Math.cos(rad)+100*Math.sin(rad))/2,hh=scale*(word.width*Math.sin(rad)+100*Math.cos(rad))/2;
      latest.bounds.push({l:word.x-hw,r:word.x+hw,t:cy-hh,b:cy+hh});
    });
  }
  window.GrooveCaptions={setup,render,state:()=>latest,lines};
})();
