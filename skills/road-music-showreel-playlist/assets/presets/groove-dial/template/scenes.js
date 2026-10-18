(function () {
  'use strict';
  const R = window.REEL, G = window.GROOVE, runtime = window.GrooveRuntime;
  const {config} = runtime, palette = config.preset.palette;
  const rail = config.display.showQueue;
  const lyrics = Array.isArray(window.PLAYLIST_LYRICS) ? window.PLAYLIST_LYRICS.filter(cue => cue && typeof cue.text === 'string' && cue.text.trim()) : [];
  const clean = value => typeof value === 'string' ? value.trim() : '';
  const { mix, smooth, out, settle } = G;
  let profile = G.profileAt(0);
  const W = 1920, H = 1080, TAU = Math.PI * 2;
  let T = runtime.timing(0), FAN = T.fan, TURN = T.turn;
  R.config({ duration: config.duration, fps: config.fps, width: W, height: H, push: 0, audio: config.audio });
  const load = paths => ({photos: ['photoA','photoB','photoC'].map(role=>R.img(paths[role])),case:R.img(paths.case),paper:R.img(paths.paper)});
  const bundles = config.playlist.tracks.map(track=>load(track.assets || config.assets));
  function canvas(w = W, h = H) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
  const background = canvas(), dark = canvas(), ring = canvas(1100, 1100), discShadow = canvas(1100, 1100);
  const introDiscs = [];
  let records, picture, ctx;
  const cover = (c, im, x, y, w, h) => { const s = Math.max(w / im.width, h / im.height); c.drawImage(im, x + (w - im.width * s) / 2, y + (h - im.height * s) / 2, im.width * s, im.height * s); };
  let activeTrack = -1;
  function editorialFor(track) {
    const configured = config.editorial?.quotes;
    const explicit = Array.isArray(configured) && config.playlist.tracks.length === 1 ? configured : configured && Array.isArray(configured[track.id]) ? configured[track.id] : null;
    const source = explicit || lyrics.filter(cue => cue.trackId ? cue.trackId === track.id : cue.startSeconds >= track.startSeconds && cue.startSeconds < track.endSeconds).map(cue => cue.text);
    return { title: clean(track.title), channel: clean(config.display?.channelName), quotes: source.map(clean).filter(Boolean).slice(0, 3) };
  }
  function activate(time) {
    const index = config.playlist.tracks.indexOf(runtime.trackAt(time));
    if (activeTrack === index) return;
    activeTrack = index;
    const track = config.playlist.tracks[index], assets = bundles[index];
    introDiscs.length = 0;
    ring.width = 1100; discShadow.width = 1100;
    records = RecordLayers.create(assets, editorialFor(track));
    const b = background.getContext('2d'); cover(b, assets.paper, 0, 0, W, H);
    b.fillStyle = runtime.rgba(palette.paper,.18); b.fillRect(0, 0, W, H);
    const d = dark.getContext('2d'); d.drawImage(background, 0, 0); d.fillStyle = runtime.rgba(palette.dark,.92); d.fillRect(0, 0, W, H);
    for (const image of records.discs) { const c = canvas(1024, 1024), ic = c.getContext('2d'); ic.filter = config.preset.variant === 'prism' ? 'none' : 'contrast(.85) saturate(.9)'; ic.drawImage(image, 0, 0); introDiscs.push(c); }
    const r = ring.getContext('2d'); r.translate(550, 550);
    for (let i = 0; i < 24; i++) { r.strokeStyle = runtime.rgba(palette.ink,i % 4 ? .08 : .22); r.lineWidth = i % 4 ? 1 : 2; r.beginPath(); r.arc(0, 0, 405 + i * 4.5, 0, TAU); r.stroke(); }
    const s = discShadow.getContext('2d'); s.shadowBlur = 32; s.shadowOffsetY = 24; s.shadowColor = 'rgba(20,23,23,.28)'; s.fillStyle = '#222'; s.beginPath(); s.arc(550, 550, 487, 0, TAU); s.fill();
    s.globalCompositeOperation = 'destination-out'; s.beginPath(); s.arc(550, 550, 487, 0, TAU); s.fill();
  }
  R.preload(Promise.all(bundles.flatMap(a=>[...a.photos,a.case,a.paper]).map(im=>im.decode())).then(()=>activate(0)));
  function sprite(image, x, y, width, angle = 0, alpha = 1) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(angle * Math.PI / 180); ctx.globalAlpha *= alpha;
    ctx.drawImage(image, -width / 2, -width * image.height / image.width / 2, width, width * image.height / image.width); ctx.restore();
  }
  function arcs(x, y, r, t, s, darkMode = false) {
    ctx.save(); ctx.translate(x, y); ctx.lineCap = 'round';
    const colors = [palette.accent, palette.ink, palette.light];
    for (let i = 0; i < 3; i++) {
      const start = t * (.12 + i * .04) + i * 2.1;
      ctx.globalAlpha = .52 + s.high * .25;
      ctx.lineWidth = i ? 3 : 7;
      ctx.strokeStyle = colors[i]; ctx.beginPath(); ctx.arc(0, 0, r + 28 + i * 16 + s.high * 12 * profile.impact, start, start + .5 + s.snare * .7); ctx.stroke();
    }
    ctx.restore();
  }
  function ink(x, y, r, t, darkMode) {
    ctx.save(); ctx.translate(x, y);
    const events = runtime.spanEvents(t,.9);
    for (let j = 0; j < events.length; j++) {
      const event = events[j], age = t - event.time, dur = profile.name === 'soft' ? .7 : .45;
      if (age < 0 || age >= dur) continue;
      const p = age / dur, a = Math.sin(p * Math.PI) * profile.impact;
      ctx.globalAlpha = a * .72; ctx.strokeStyle = darkMode ? palette.light : palette.accent;
      for (let i = 0; i < 7; i++) {
        const theta = j * .77 + i * .82, inner = r + 40 + p * 42, outer = inner + (1 - p) * (20 + i * 4);
        ctx.lineWidth = 2 + i % 3; ctx.beginPath(); ctx.moveTo(Math.cos(theta) * inner, Math.sin(theta) * inner); ctx.lineTo(Math.cos(theta) * outer, Math.sin(theta) * outer); ctx.stroke();
      }
    }
    ctx.restore();
  }
  function titleStamp(t, s) {
    const alpha = out(t / .44) * (1 - smooth(t, T.body - .7, T.body - .12));
    if (alpha <= 0 || !records.titleStamp) return;
    const hit = s.hit * profile.impact;
    records.drawTitleStamp(ctx, { x: 318, y: 182, width: 630 * (1 + hit * .025), angle: -3 + hit * .35, opacity: alpha });
  }
  function caseSprite(opts) {
    records.drawCase(ctx,opts);
    const name = config.display.channelName;
    if (!name) return;
    ctx.save();ctx.translate(opts.x,opts.y);ctx.rotate((opts.angle||0)*Math.PI/180);ctx.globalAlpha=opts.opacity ?? 1;
    const w=opts.size*.61,h=opts.size*.085,y=opts.size*.265;
    ctx.fillStyle='rgba(18,21,25,.85)';ctx.beginPath();ctx.roundRect(-w/2,y,w,h,h*.14);ctx.fill();
    ctx.font=`700 ${opts.size*.038}px Paperlogy`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle=palette.light;
    let label=name;while(ctx.measureText(label).width>w-20 && label.length>1)label=label.slice(0,-2)+'…';
    ctx.fillText(label,0,y+h/2);ctx.restore();
  }
  function disc(x, y, r, angle, index = 0, opacity = 1) {
    sprite(discShadow, x, y, r * 2.24, 0, opacity); records.drawDisc(ctx, { x, y, r, angle, index, opacity });
  }
  function opening(t, s) {
    const gather = smooth(t, T.assemble, T.body), impact = s.hit * profile.impact;
    const x = mix(1045, 1030, gather), y = mix(402, 470, gather);
    const r = mix(750, 350, gather) * (1 + s.bass * .023 * profile.impact);
    sprite(ring, x, y, r * 2.7, t * 5, .55);
    const firstHit = (runtime.hits[0] ?? Infinity), age = t - firstHit;
    const burst = age > 0 && age < 1.2 ? Math.sin(Math.min(1, age / .28) * Math.PI / 2) * Math.exp(-Math.max(0, age - .28) / .28) : 0;
    const split = (1 - gather) * (10 + burst * 75 * profile.impact + impact * 10);
    const angle = 25 + s.angle;
    for (let i = 0; i < 3; i++) {
      const theta = i * TAU / 3 + angle * Math.PI / 180;
      const entry = out((t - (.08 + i * .12)) / .6), travel = (1 - entry) * 180;
      ctx.save(); ctx.translate(x + Math.cos(theta + 1) * (split + travel), y + Math.sin(theta + 1) * (split + travel));
      ctx.rotate(angle * Math.PI / 180); ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, r, i * TAU / 3, (i + 1) * TAU / 3 + .003); ctx.closePath(); ctx.clip();
      ctx.drawImage(introDiscs[i], -r, -r, r * 2, r * 2); ctx.restore();
    }
    sprite(records.discs[0], x, y, r * 2, angle, smooth(gather, .3, .96));
    sprite(records.glass, x, y, r * 2);
    arcs(x, y, r, t, s); ink(x, y, r, t, false); titleStamp(t, s);
    if (t >= FAN && t < T.assemble + .95) {
      const exit = smooth(t, T.assemble, T.assemble + .95);
      for (let i = 0; i < 3; i++) {
        const entry = smooth(t, FAN + i * .12, FAN + i * .12 + (profile.name === 'soft' ? .95 : .65));
        const turn = smooth(t, T.fanSwap + i * .12, T.fanSwap + .9 + i * .12);
        const width = 920 - i * 45, height = width * 880 / 1200;
        ctx.save(); ctx.translate(430 + i * 530, 430 + (i % 2 ? -44 : 44)); ctx.rotate((i - 1) * 12 * Math.PI / 180);
        ctx.beginPath(); ctx.rect(-width / 2, -height / 2, width * Math.min(entry, 1 - exit), height); ctx.clip();
        records.drawCard(ctx, i, { x: 0, y: 0, width, angle: 0 });
        if (turn > 0) { ctx.beginPath(); ctx.rect(-width / 2, -height / 2, width * turn, height); ctx.clip(); records.drawCard(ctx, (i + 1) % 3, { x: 0, y: 0, width, angle: 0 }); }
        ctx.restore();
      }
    }
    if (gather > 0) {
      caseSprite({ x: mix(-450, 380, gather), y: 456 + (1 - gather) * 160, size: 590, angle: -10 + impact * 1.5, opacity: gather });
      for (let i = 2; i >= 0; i--) records.drawCard(ctx, i, { x: mix(2360 + i * 80, 1500 + i * 12, gather), y: 425 + i * 55, width: 525, angle: 10 - i * 11 + (1 - gather) * 38, opacity: gather });
    }
  }
  function gallery(t, s) {
    const expanded = smooth(t, T.expand, T.expand + .8) * (1 - smooth(t, T.answer, T.answer + .85));
    const answer = smooth(t, T.answer, T.answer + .8) * (1 - smooth(t, T.recall, T.recall + .8));
    const recall = smooth(t, T.recall, T.recall + .9) * (1-smooth(t,T.cycleEnd-1,T.cycleEnd));
    const hit = s.hit * profile.impact, breath = Math.sin(t * .7) * (profile.name === 'soft' ? 5 : 8);
    let x = 1030 - expanded * 460 + answer * 280 - recall * 120;
    let y = 466 + breath, r = 350 + expanded * 28 + answer * 54 + recall * 26;
    r *= 1 + s.bass * .028 * profile.impact;
    const darkMode = expanded > .5;
    const caseX = 380 + expanded * 40 - answer * 70, caseSize = 590 - expanded * 170;
    caseSprite({ x: caseX, y: 460 + expanded * 140, size: caseSize * (1 + hit * .02), angle: -10 + hit * 1.3, opacity: 1 - expanded * .65 });
    const fan = .5 + smooth(t, T.body, T.body + .8) * .5;
    for (let i = 2; i >= 0; i--) {
      const stagger = settle(t, T.answer + i * .095, .85) * (1 - smooth(t, T.recall, T.recall + .8));
      const cx = mix(1515 + i * 8, 1390 + i * 24, expanded) - stagger * (970 - i * 28);
      const flip = i === 0 ? smooth(t, TURN, TURN + .85) : 0;
      const lift = Math.sin(flip * Math.PI);
      const cy = 410 + i * 55 - expanded * i * 12 + Math.sin(t * .45 + i) * 5 - lift * 100 * (profile.name === 'soft' ? .5 : 1);
      const width = 525 + expanded * 310 - answer * 5;
      const sign = i % 2 ? 1 : -1;
      const angle = (10 - i * 10) * fan + sign * (s.snare * 3.2 + hit * 2.5) * profile.impact + expanded * (i - 1) * 1.5;
      ctx.save(); ctx.translate(cx + sign * hit * 28 + lift * 85, cy - hit * (8 + i * 3)); ctx.rotate((angle + lift * 12) * Math.PI / 180); ctx.scale(Math.max(.025, Math.abs(Math.cos(flip * Math.PI))), 1);
      records.drawCard(ctx, (i + (answer > .5 ? 1 : 0) + (flip > .5 ? 1 : 0)) % 3, { x: 0, y: 0, width, angle: 0 }); ctx.restore();
    }
    sprite(ring, x, y, r * 2.85, t * 3, darkMode ? .2 : .75);
    disc(x, y, r, 25 + s.angle, recall > .7 ? 2 : 0);
    arcs(x, y, r, t, s, darkMode); ink(x, y, r, t, darkMode);
    // Short print fragments continue to answer selected hits in the later half.
    if (t > T.expand && hit > .02) {
      for (let i = 0; i < 2; i++) {
        const theta = t * .19 + i * Math.PI, rr = r + 120 + hit * 65;
        records.drawCard(ctx, i + 1, { x: x + Math.cos(theta) * rr, y: y + Math.sin(theta) * rr * .65, width: 170 + hit * 25, angle: theta * 180 / Math.PI + 80, opacity: hit * .8 });
      }
    }
    if (recall > 0) {
      const p = smooth(t, T.recall, T.cycleEnd); ctx.save(); ctx.globalAlpha = p * .6; ctx.strokeStyle = palette.accent; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x, y, r + 52, -.7, TAU * p - .7); ctx.stroke(); ctx.restore();
    }
  }
  function render(t) {
    activate(t); profile = G.profileAt(t); T = runtime.timing(t); FAN = T.fan; TURN = T.turn;
    const s = G.state(t); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.drawImage(background, 0, 0);
    const shade = smooth(t,T.expand,T.expand+.8)*(1-smooth(t,T.answer,T.answer+.85));
    if(shade>0){ctx.globalAlpha=shade;ctx.drawImage(dark,0,0);ctx.globalAlpha=1;}
    ctx.save();
    if (rail) ctx.transform(.70,0,0,.70,35,95);
    const shake = s.hit * profile.impact * (t < T.body ? 5 : 2);
    ctx.translate(Math.sin(t * 38) * shake, Math.cos(t * 31) * shake * .5);
    if (t < T.body - .5 / 30) opening(t, s); else gallery(t, s);
    ctx.restore();
  }
  R.scene({ id: 'groove', start: 0, end: config.duration, push: 0, setup(el) { picture = canvas(); picture.className = 'picture'; el.append(picture); ctx = picture.getContext('2d'); }, render(lt, c) { render(c.t); } });
  R.overlay(t => GrooveCaptions.render(t), { layer: 'top', setup: GrooveCaptions.setup });
  GroovePlaylistUI.install(R);
  window.GROOVE_DIAGNOSTICS = () => ({ duration: config.duration, profile, cues: T, activeTrack, introActive: window.__t < runtime.body, selectedOnsets: runtime.hits, captions: GrooveCaptions.state(), cached: Boolean(records), discAngle: G.state(window.__t || 0).angle, channelName: config.display.channelName, rail, editorial: records?.editorial || null, spriteCounts: records ? { discs: records.discs.length, cards: records.cards.length, titleStamp: Boolean(records.titleStamp) } : null });
})();
