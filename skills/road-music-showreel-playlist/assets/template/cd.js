/* 사진 인쇄면만 회전하고, 케이스·허브·반사는 고정한다. */
(() => {
  'use strict';
  const W = 1920, H = 1080, TAU = Math.PI * 2;
  const FULL_CASE = { x: 210, y: 54, width: 900, height: 900 };
  const FULL_DISC = { x: 1240, y: 505, radius: 440 };
  const COMPACT_CASE = { x: 140, y: 70, width: 750, height: 750 };
  const COMPACT_DISC = { x: 1050, y: 505, radius: 330 };
  const SPECTRUM_CASE = { x: 300, y: 70, width: 750, height: 750 };
  const SPECTRUM_DISC = { x: 1240, y: 505, radius: 330 };
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const size = image => ({ width: image && (image.naturalWidth || image.width) || 0, height: image && (image.naturalHeight || image.height) || 0 });
  const cfg = () => window.CD_CONFIG;
  const hex = (name, fallback) => (cfg().preset.palette[name] || fallback);
  function display() {
    const value = cfg().display || {};
    return {
      showSpectrum: value.showSpectrum === true,
      showQueue: value.showQueue === true,
      showNowPlaying: value.showNowPlaying === true,
      channelName: typeof value.channelName === 'string' ? value.channelName : ''
    };
  }
  function layout() {
    const value = display();
    if (value.showQueue || value.showNowPlaying) return { caseRect: COMPACT_CASE, disc: COMPACT_DISC };
    if (value.showSpectrum) return { caseRect: SPECTRUM_CASE, disc: SPECTRUM_DISC };
    return { caseRect: FULL_CASE, disc: FULL_DISC };
  }

  function cover(ctx, image, x, y, w, h) {
    const source = size(image);
    if (!source.width || !source.height) throw new Error('CD preset asset is not decoded');
    const scale = Math.max(w / source.width, h / source.height);
    ctx.drawImage(image, x + (w - source.width * scale) / 2, y + (h - source.height * scale) / 2, source.width * scale, source.height * scale);
  }
  function discPrint(photo, variant) {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1024;
    const ctx = canvas.getContext('2d'), c = 512, r = 505;
    ctx.save(); ctx.beginPath(); ctx.arc(c, c, r, 0, TAU); ctx.clip(); cover(ctx, photo, 0, 0, 1024, 1024);
    const shade = ctx.createRadialGradient(c, c, 280, c, c, r); shade.addColorStop(0, 'rgba(20,10,16,0)'); shade.addColorStop(1, 'rgba(8,5,9,.34)'); ctx.fillStyle = shade; ctx.fillRect(0, 0, 1024, 1024); ctx.restore();
    const rim = ctx.createLinearGradient(110, 100, 900, 930); (variant === 'prism' ? [['#ffffff',0],['#91a9bd',.22],['#f9ffff',.48],['#87a3bd',.74],['#ffffff',1]] : [['#f3f0e8',0],['#9da4a2',.27],['#e5e1d8',.52],['#aeb4b0',.76],['#f3f0e8',1]]).forEach(([color, stop]) => rim.addColorStop(stop, color));
    ctx.lineWidth = 9; ctx.strokeStyle = rim; ctx.beginPath(); ctx.arc(c, c, 498, 0, TAU); ctx.stroke();
    ctx.globalCompositeOperation = 'destination-out'; ctx.beginPath(); ctx.arc(c, c, 19, 0, TAU); ctx.fill(); ctx.globalCompositeOperation = 'source-over'; return canvas;
  }
  function paper(ctx, image, variant, t) {
    ctx.fillStyle = hex('paper', '#efe3cc'); ctx.fillRect(0, 0, W, H); cover(ctx, image, 0, 0, W, H);
    if (variant === 'noir') { ctx.fillStyle = 'rgba(5,7,9,.74)'; ctx.fillRect(0, 0, W, H); }
    if (variant === 'neon') { const g = ctx.createLinearGradient(0, 0, W, H); g.addColorStop(0, 'rgba(19,4,47,.7)'); g.addColorStop(.48, 'rgba(5,15,36,.2)'); g.addColorStop(1, 'rgba(255,32,170,.22)'); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); }
    if (variant === 'notebook') { ctx.fillStyle = 'rgba(255,247,227,.38)'; ctx.fillRect(0, 0, W, H); }
    if (variant === 'prism') { const wash=ctx.createLinearGradient(0,0,W,H);wash.addColorStop(0,'rgba(255,255,255,.58)');wash.addColorStop(.44,'rgba(187,224,255,.16)');wash.addColorStop(1,'rgba(255,255,255,.48)');ctx.fillStyle=wash;ctx.fillRect(0,0,W,H);const glint=420+Math.sin((Number(t)||0)*.45)*190,g=ctx.createLinearGradient(glint-150,0,glint+150,0);g.addColorStop(0,'rgba(255,255,255,0)');g.addColorStop(.5,'rgba(255,255,255,.28)');g.addColorStop(1,'rgba(255,255,255,0)');ctx.fillStyle=g;ctx.fillRect(0,0,W,H); }
  }
  function pieces(ctx, variant) {
    ctx.save();
    if (variant === 'noir') { ctx.strokeStyle = 'rgba(245,241,225,.34)'; ctx.lineWidth = 2; ctx.strokeRect(48, 36, 1824, 1008); ctx.fillStyle = 'rgba(245,241,225,.32)'; for (let x = 86; x < 1834; x += 48) { ctx.fillRect(x, 53, 20, 7); ctx.fillRect(x, 1020, 20, 7); } }
    if (variant === 'neon') { ctx.globalCompositeOperation = 'screen'; ctx.strokeStyle = hex('accent','#ff4db8'); ctx.globalAlpha = .42; ctx.lineWidth = 10; ctx.beginPath(); ctx.moveTo(80, 160); ctx.lineTo(1770, 350); ctx.stroke(); ctx.strokeStyle = '#35e6ff'; ctx.beginPath(); ctx.moveTo(190, 920); ctx.lineTo(1690, 640); ctx.stroke(); }
    if (variant === 'notebook') { ctx.translate(116, 124); ctx.rotate(-.06); ctx.fillStyle = 'rgba(255,250,234,.74)'; ctx.fillRect(0, 0, 820, 740); ctx.strokeStyle = 'rgba(83,111,146,.22)'; ctx.lineWidth = 2; for (let y = 70; y < 740; y += 46) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(820,y); ctx.stroke(); } }
    if (variant === 'archive') { ctx.translate(107,128); ctx.rotate(-.075); ctx.fillStyle = 'rgba(255,248,230,.64)'; ctx.fillRect(0,0,834,750); ctx.strokeStyle='rgba(91,64,45,.15)';ctx.lineWidth=2;ctx.strokeRect(0,0,834,750); }
    ctx.restore();
  }
  function drawDisc(ctx, image, degrees, disc, variant) {
    const {x,y,radius:r} = disc; ctx.save(); ctx.shadowColor='rgba(25,12,26,.38)';ctx.shadowBlur=34;ctx.shadowOffsetX=8;ctx.shadowOffsetY=18;ctx.fillStyle='rgba(29,18,33,.3)';ctx.beginPath();ctx.arc(x,y,r,0,TAU);ctx.fill();ctx.restore();
    ctx.save();ctx.translate(x,y);ctx.rotate(degrees*Math.PI/180);ctx.drawImage(image,-r,-r,r*2,r*2);ctx.restore();
    const hub=ctx.createRadialGradient(x-12,y-14,7,x,y,58);if(variant==='prism'){hub.addColorStop(0,'rgba(255,255,255,.98)');hub.addColorStop(.32,'rgba(202,220,233,.94)');hub.addColorStop(.76,'rgba(91,122,149,.88)');hub.addColorStop(1,'rgba(255,255,255,.94)');}else{hub.addColorStop(0,'rgba(255,255,246,.9)');hub.addColorStop(.23,'rgba(179,185,182,.85)');hub.addColorStop(.73,'rgba(83,93,95,.85)');hub.addColorStop(1,'rgba(240,230,213,.78)');}ctx.fillStyle=hub;ctx.beginPath();ctx.arc(x,y,58,0,TAU);ctx.arc(x,y,19,0,TAU,true);ctx.fill('evenodd');ctx.strokeStyle=variant==='prism'?'rgba(255,255,255,.9)':'rgba(255,255,246,.62)';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,46,0,TAU);ctx.stroke();
  }
  function fitText(ctx, text, maxWidth, start, minimum) {
    let size = start;
    while (size > minimum) { ctx.font = `700 ${size}px Pretendard`; if (ctx.measureText(text).width <= maxWidth) break; size -= 1; }
    ctx.font = `700 ${size}px Pretendard`;
  }
  function ellipsize(ctx, text, maxWidth) {
    if (ctx.measureText(text).width <= maxWidth) return text;
    const chars = Array.from(text); let visible = '';
    while (chars.length && ctx.measureText(visible + chars[0] + '…').width <= maxWidth) visible += chars.shift();
    return visible ? visible + '…' : '…';
  }
  function drawCase(ctx, image, rect) {
    const {x,y,width:w,height:h,rotationDegrees=-1.25}=rect;ctx.save();ctx.translate(x+w/2,y+h/2);ctx.rotate(rotationDegrees*Math.PI/180);ctx.translate(-w/2,-h/2);ctx.shadowColor='rgba(25,12,26,.35)';ctx.shadowBlur=35;ctx.shadowOffsetY=20;ctx.drawImage(image,0,0,w,h);ctx.shadowColor='transparent';ctx.save();ctx.beginPath();ctx.rect(24,24,w-48,h-48);ctx.clip();const reflection=ctx.createLinearGradient(40,0,510,900);reflection.addColorStop(0,'rgba(255,255,247,.2)');reflection.addColorStop(.5,'rgba(255,255,247,0)');ctx.fillStyle=reflection;ctx.fillRect(0,0,w,h);ctx.restore();const channel=display().channelName.trim();if(channel){const pad=Math.round(w*.035),labelW=Math.round(w*.43),labelH=Math.round(h*.052),labelX=pad,labelY=Math.round(h*.9);ctx.fillStyle='rgba(19,18,22,.76)';ctx.fillRect(labelX,labelY,labelW,labelH);ctx.strokeStyle='rgba(255,251,237,.52)';ctx.lineWidth=1;ctx.strokeRect(labelX+.5,labelY+.5,labelW-1,labelH-1);ctx.fillStyle='rgba(255,251,237,.96)';ctx.textBaseline='middle';fitText(ctx,channel,labelW-pad*2,Math.round(labelH*.48),11);const label=ellipsize(ctx,channel,labelW-pad*2);ctx.save();ctx.beginPath();ctx.rect(labelX+pad,labelY+1,labelW-pad*2,labelH-2);ctx.clip();ctx.fillText(label,labelX+pad,labelY+labelH/2);ctx.restore();}
    ctx.restore();
  }
  function snapshot(t) { const period = Number(cfg().preset.discPeriodSeconds),variant=cfg().preset.variant; const seconds=Number.isFinite(t)?t:0; const current=layout(); return { discDegrees: ((seconds*360/period)%360+360)%360, discPeriodSeconds:period, caseRect:{...current.caseRect,rotationDegrees:variant==='prism'?-0.12:-1.25}, discCenter:[current.disc.x,current.disc.y],discRadius:current.disc.radius }; }
  function create(assets) { const required=['photoA','photoB','photoC','case','paper']; for (const key of required) if (!size(assets[key]).width) throw new Error(`CD preset required asset failed to decode: ${key}`); const variant=cfg().preset.variant,printed=discPrint(assets.photoA,variant); return { draw(ctx,t,entry=1) { const settle=clamp(Number(entry)||0,0,1),frame=snapshot(t),darkBody=['noir','neon'].includes(variant);ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,W,H);paper(ctx,assets.paper,variant,t);pieces(ctx,variant);drawDisc(ctx,printed,frame.discDegrees,{x:frame.discCenter[0],y:frame.discCenter[1],radius:frame.discRadius},variant);ctx.save();ctx.globalAlpha=settle;ctx.translate((1-settle)*-34,(1-settle)*12);drawCase(ctx,assets.case,frame.caseRect);ctx.restore();const footer=ctx.createLinearGradient(0,930,0,H);footer.addColorStop(0,'rgba(0,0,0,0)');footer.addColorStop(1,`${darkBody ? hex('dark','#141417') : hex('paper','#efe3cc')}dd`);ctx.fillStyle=footer;ctx.fillRect(0,930,W,150);ctx.restore(); }, state:snapshot }; }
  window.ArchiveCD = { create };
})();
