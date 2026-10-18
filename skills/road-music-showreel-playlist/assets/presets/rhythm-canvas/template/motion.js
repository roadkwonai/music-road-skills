/* Rhythm Canvas: 모든 화면은 시각 t와 제공된 분석 데이터만으로 다시 그린다. */
(() => {
  'use strict';
  const W = 1920, H = 1080, TAU = Math.PI * 2;
  const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
  const mix = (a, b, amount) => a + (b - a) * amount;
  const smooth = value => { const x = clamp(value); return x * x * (3 - 2 * x); };
  const hash = (index, salt = 0) => { const value = Math.sin(index * 12.9898 + salt * 78.233) * 43758.5453; return value - Math.floor(value); };
  const hexPattern = /^#[\da-f]{6}$/i;
  const styles = new Set(['orbit', 'ribbons', 'grid', 'tiles']);
  const motifs = new Set(['stars', 'rain', 'petals', 'none']);
  const accentKinds = new Set(['ring', 'rays', 'sweep', 'punch']);
  const visibleFailure = message => {
    window.__ready = false;
    const show = () => {
      const wrap = document.getElementById('wrap'), stage = document.getElementById('stage');
    if (wrap) wrap.style.cssText = `width:${W}px;height:${H}px`;
    if (stage) {
      stage.style.cssText = `width:${W}px;height:${H}px`;
      stage.replaceChildren();
      const error = document.createElement('div'); error.id = 'direction-error';
      error.textContent = 'Rhythm Canvas 방향 데이터가 필요합니다.';
      const note = document.createElement('small'); note.textContent = message;
      error.append(note); stage.append(error);
    }
    };
    show();
    // engine.js는 load 시 __ready를 true로 바꾸므로, 오류 장면의 setup을 거부해 그 경로도 닫는다.
    if (window.REEL) {
      REEL.config({ duration: 1, fps: 30, width: W, height: H, audio: null, push: 0 });
      REEL.scene({ id: 'rhythm-canvas-direction-error', start: 0, end: 1, setup() { show(); return Promise.reject(new Error(`[Rhythm Canvas] ${message}`)); } });
    }
    throw new Error(`[Rhythm Canvas] ${message}`);
  };
  const validColor = (color, name) => {
    if (typeof color !== 'string' || !hexPattern.test(color)) visibleFailure(`${name}은 #RRGGBB 색상이어야 합니다.`);
    return color;
  };
  const finite = (value, name) => {
    if (!Number.isFinite(value)) visibleFailure(`${name}은 유한한 숫자여야 합니다.`);
    return value;
  };
  const config = window.PLAYLIST_CONFIG;
  const direction = window.PLAYLIST_DIRECTION;
  const renderMode = new URLSearchParams(location.search).has('render');
  if (!config || !Number.isFinite(config.duration) || config.duration <= 0) visibleFailure('유효한 PLAYLIST_CONFIG.duration이 필요합니다.');
  if (!direction || direction.schemaVersion !== 1) visibleFailure('direction.js를 곡별 PLAYLIST_DIRECTION(schemaVersion: 1)으로 교체해야 합니다.');
  finite(direction.durationSeconds, 'PLAYLIST_DIRECTION.durationSeconds');
  if (Math.abs(direction.durationSeconds - config.duration) > .08) visibleFailure('방향 데이터 길이와 PLAYLIST_CONFIG.duration이 다릅니다.');
  if (!Array.isArray(direction.sections) || !direction.sections.length) visibleFailure('최소 한 개의 방향 sections 항목이 필요합니다.');
  if (!Array.isArray(direction.accents)) visibleFailure('PLAYLIST_DIRECTION.accents는 배열이어야 합니다.');
  const safeMediaSrc = /^assets\/motion\/[A-Za-z0-9_-]+\.(?:png|jpe?g|webp)$/i;
  const mediaImages = new Map();
  let thumbnail = null;
  const loadLocalImage = (item, name) => {
    if (!item || typeof item.src !== 'string' || !safeMediaSrc.test(item.src)) visibleFailure(`${name}.src는 프로젝트 assets/motion의 PNG/JPEG/WebP여야 합니다.`);
    const image = new Image(); image.decoding = 'sync';
    REEL.preload(new Promise((resolve, reject) => {
      image.onload = () => image.decode().then(() => resolve(image), () => reject(new Error(`${name} 이미지 디코드 실패`)));
      image.onerror = () => reject(new Error(`${name} 이미지 로드 실패`));
      image.src = new URL(`../${item.src}`, document.baseURI).href;
    }));
    return image;
  };
  if (direction.media !== undefined) {
    if (!direction.media || typeof direction.media !== 'object' || !Array.isArray(direction.media.images)) visibleFailure('direction.media.images가 필요합니다.');
    direction.media.images.forEach((item, index) => {
      if (!item || typeof item.id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(item.id) || mediaImages.has(item.id)) visibleFailure(`media.images[${index}].id가 올바르지 않습니다.`);
      mediaImages.set(item.id, loadLocalImage(item, `media.images[${index}]`));
    });
    if (direction.media.thumbnail !== undefined) {
      const item = direction.media.thumbnail;
      if (!item || Math.abs(finite(item.durationSeconds, 'media.thumbnail.durationSeconds') - .5) > 1e-9) visibleFailure('media.thumbnail.durationSeconds는 0.5초여야 합니다.');
      thumbnail = { image: loadLocalImage(item, 'media.thumbnail'), duration: item.durationSeconds };
    }
  }
  const sectionList = direction.sections.map((section, index) => {
    if (!section || typeof section !== 'object') visibleFailure(`sections[${index}]가 객체가 아닙니다.`);
    const start = finite(section.startSeconds, `sections[${index}].startSeconds`);
    const end = finite(section.endSeconds, `sections[${index}].endSeconds`);
    if (start < 0 || end <= start || end > config.duration + .08) visibleFailure(`sections[${index}]의 시간 범위가 올바르지 않습니다.`);
    if (typeof section.trackId !== 'string' || !section.trackId) visibleFailure(`sections[${index}].trackId가 필요합니다.`);
    if (!styles.has(section.style)) visibleFailure(`sections[${index}].style은 orbit/ribbons/grid/tiles 중 하나여야 합니다.`);
    if (!motifs.has(section.motif)) visibleFailure(`sections[${index}].motif이 올바르지 않습니다.`);
    const intensity = finite(section.intensity, `sections[${index}].intensity`);
    if (intensity < 0 || intensity > 1) visibleFailure(`sections[${index}].intensity는 0~1이어야 합니다.`);
    const palette = section.palette || {};
    const imageId = section.imageId;
    if (imageId !== undefined && (typeof imageId !== 'string' || !mediaImages.has(imageId))) visibleFailure(`sections[${index}].imageId는 media.images의 id여야 합니다.`);
    const imageOpacity = imageId === undefined ? 0 : finite(section.imageOpacity ?? .8, `sections[${index}].imageOpacity`);
    if (imageOpacity < 0 || imageOpacity > 1) visibleFailure(`sections[${index}].imageOpacity는 0~1이어야 합니다.`);
    return { start, end, trackId: section.trackId, style: section.style, motif: section.motif, intensity, imageId: imageId || null, imageOpacity,
      palette: { background: validColor(palette.background, `sections[${index}].palette.background`), foreground: validColor(palette.foreground, `sections[${index}].palette.foreground`), accent: validColor(palette.accent, `sections[${index}].palette.accent`), secondary: validColor(palette.secondary, `sections[${index}].palette.secondary`) } };
  }).sort((a, b) => a.start - b.start);
  sectionList.forEach((section, index) => {
    const previous = sectionList[index - 1];
    if (previous && section.start < previous.end - .001) visibleFailure('방향 sections가 겹칩니다.');
  });
  if (sectionList[0].start > .01 || sectionList.at(-1).end < config.duration - .01) visibleFailure('방향 sections가 원곡 전체 길이를 덮어야 합니다.');
  const accents = direction.accents.map((accent, index) => {
    if (!accent || typeof accent !== 'object') visibleFailure(`accents[${index}]가 객체가 아닙니다.`);
    const time = finite(accent.timeSeconds, `accents[${index}].timeSeconds`), strength = finite(accent.strength, `accents[${index}].strength`);
    if (time < 0 || time > config.duration || strength < 0 || strength > 1 || !accentKinds.has(accent.kind) || !['native-hit', 'manual-choice', 'lyric-phrase'].includes(accent.origin)) visibleFailure(`accents[${index}] 값이 올바르지 않습니다.`);
    return { time, strength, kind: accent.kind, origin: accent.origin };
  }).sort((a, b) => a.time - b.time);
  const lyrics = Array.isArray(window.PLAYLIST_LYRICS) ? window.PLAYLIST_LYRICS.filter(cue => cue && Number.isFinite(cue.startSeconds) && Number.isFinite(cue.endSeconds) && cue.endSeconds > cue.startSeconds && typeof cue.text === 'string' && cue.text.trim()) : [];
  const tracks = Array.isArray(config.playlist?.tracks) ? config.playlist.tracks.filter(track => track && typeof track.id === 'string' && Number.isFinite(track.startSeconds) && Number.isFinite(track.endSeconds)) : [];
  const display = { showSpectrum: config.display?.showSpectrum === true, showQueue: config.display?.showQueue === true, showNowPlaying: config.display?.showNowPlaying === true, channelName: typeof config.display?.channelName === 'string' ? config.display.channelName.trim() : '' };
  const spectrum = window.PLAYLIST_SPECTRUM;
  if (display.showSpectrum && (!spectrum || !Number.isFinite(spectrum.dt) || spectrum.dt <= 0 || !Array.isArray(spectrum.frames) || !spectrum.frames.length || !Number.isFinite(spectrum.bands) || spectrum.bands < 1)) visibleFailure('showSpectrum에는 실제 PLAYLIST_SPECTRUM FFT 데이터가 필요합니다.');
  const rgb = color => ({ r: parseInt(color.slice(1, 3), 16), g: parseInt(color.slice(3, 5), 16), b: parseInt(color.slice(5, 7), 16) });
  const color = (value, alpha = 1) => { const c = typeof value === 'string' ? rgb(value) : value; return `rgba(${Math.round(c.r)},${Math.round(c.g)},${Math.round(c.b)},${clamp(alpha)})`; };
  const blend = (a, b, amount) => ({ r: mix(a.r, b.r, amount), g: mix(a.g, b.g, amount), b: mix(a.b, b.b, amount) });
  const palette = (from, to, amount) => ({ background: blend(rgb(from.background), rgb(to.background), amount), foreground: blend(rgb(from.foreground), rgb(to.foreground), amount), accent: blend(rgb(from.accent), rgb(to.accent), amount), secondary: blend(rgb(from.secondary), rgb(to.secondary), amount) });
  const energyAt = time => {
    const env = window.TL?.music?.energy;
    if (!env || !Array.isArray(env.v) || !env.v.length || !Number.isFinite(env.dt) || env.dt <= 0) return 0;
    const position = (time - (Number.isFinite(env.t0) ? env.t0 : 0)) / env.dt;
    const left = Math.floor(position);
    if (left < 0 || left >= env.v.length) return 0;
    const right = Math.min(env.v.length - 1, left + 1), amount = clamp(position - left);
    return clamp(mix(Number(env.v[left]) || 0, Number(env.v[right]) || 0, amount));
  };
  const spectrumAt = time => {
    if (!spectrum) return [];
    const position = Math.max(0, (time - (Number.isFinite(spectrum.t0) ? spectrum.t0 : 0)) / spectrum.dt);
    const left = Math.min(spectrum.frames.length - 1, Math.floor(position)), right = Math.min(spectrum.frames.length - 1, left + 1), amount = clamp(position - left);
    const normalize = value => clamp((Number(value) || 0) / 255);
    return Array.from({ length: spectrum.bands }, (_, index) => mix(normalize(spectrum.frames[left]?.[index]), normalize(spectrum.frames[right]?.[index]), amount));
  };
  const sectionAt = time => sectionList.find(section => time >= section.start && time < section.end) || sectionList.at(-1);
  const sectionState = time => {
    const current = sectionAt(time), index = sectionList.indexOf(current), next = sectionList[index + 1];
    const span = next ? Math.min(.7, Math.max(.18, (current.end - current.start) * .08)) : 0;
    const amount = next && time >= current.end - span ? smooth((time - (current.end - span)) / span) : 0;
    return { current, next: amount ? next : null, amount, colors: palette(current.palette, amount ? next.palette : current.palette, amount) };
  };
  const trackAt = time => tracks.find(track => time >= track.startSeconds && time < track.endSeconds) || tracks.at(-1) || null;
  const cueAt = time => lyrics.find(cue => time >= cue.startSeconds && time < cue.endSeconds) || null;
  const accentPulse = (time, kind) => accents.reduce((value, accent) => {
    if (accent.kind !== kind || time < accent.time) return value;
    const age = time - accent.time, duration = kind === 'sweep' ? .8 : kind === 'ring' ? .7 : .42;
    return age > duration ? value : Math.max(value, accent.strength * (1 - age / duration));
  }, 0);
  const activeAccents = time => accents.filter(accent => time >= accent.time && time - accent.time < (accent.kind === 'sweep' ? .8 : accent.kind === 'ring' ? .7 : .42));
  const accentKick = time => accents.reduce((value, accent) => {
    if (time < accent.time) return value;
    const duration = accent.kind === 'sweep' ? .8 : accent.kind === 'ring' ? .7 : .5, age = time - accent.time;
    return age > duration ? value : Math.max(value, accent.strength * (1 - age / duration));
  }, 0);
  const latestAccent = time => accents.filter(accent => accent.time <= time && time - accent.time < .8).at(-1) || null;
  const contrast = colours => (colours.foreground.r * .299 + colours.foreground.g * .587 + colours.foreground.b * .114 > 155 ? 'rgba(0,0,0,.26)' : 'rgba(255,255,255,.26)');
  const frame = (ctx, colours) => {
    const gradient = ctx.createLinearGradient(0, 0, W, H); gradient.addColorStop(0, color(colours.background)); gradient.addColorStop(.55, color(blend(colours.background, colours.secondary, .23))); gradient.addColorStop(1, color(blend(colours.background, colours.accent, .12))); ctx.fillStyle = gradient; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = color(colours.background, .18); for (let y = 0; y < H; y += 36) ctx.fillRect(0, y, W, 1);
  };
  function drawImageCover(ctx, time, section, colours, impact) {
    const image = section.imageId ? mediaImages.get(section.imageId) : null;
    if (!image) return false;
    const scale = Math.max(W / image.naturalWidth, H / image.naturalHeight) * (1.045 + Math.sin(time * .18 + section.start * .7) * .015 + impact * .025);
    const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
    const x = (W - width) / 2 + Math.sin(time * .23 + section.start) * 18, y = (H - height) / 2 + Math.cos(time * .17 + section.start) * 12;
    ctx.save(); ctx.globalAlpha = section.imageOpacity; ctx.drawImage(image, x, y, width, height); ctx.fillStyle = color(colours.background, .16); ctx.fillRect(0, 0, W, H); ctx.restore();
    return true;
  }
  function drawThumbnail(ctx, time) {
    const frameTime = renderMode ? Math.round(time * config.fps) / config.fps : time;
    if (!thumbnail || frameTime < 0 || frameTime >= thumbnail.duration) return false;
    const image = thumbnail.image, scale = Math.max(W / image.naturalWidth, H / image.naturalHeight), width = image.naturalWidth * scale, height = image.naturalHeight * scale;
    ctx.drawImage(image, (W - width) / 2, (H - height) / 2, width, height);
    return true;
  }
  const resetFrame = ctx => {
    if (typeof ctx.reset === 'function') { ctx.reset(); return; }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
    ctx.fillStyle = '#000'; ctx.strokeStyle = '#000'; ctx.lineWidth = 1; ctx.lineCap = 'butt'; ctx.lineJoin = 'miter'; ctx.miterLimit = 10; ctx.setLineDash([]); ctx.lineDashOffset = 0;
    ctx.shadowOffsetX = 0; ctx.shadowOffsetY = 0; ctx.shadowBlur = 0; ctx.shadowColor = 'rgba(0, 0, 0, 0)';
    ctx.font = '10px Paperlogy,sans-serif'; ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic'; ctx.beginPath(); ctx.clearRect(0, 0, W, H);
  };
  function orbit(ctx, time, colours, intensity, energy, alpha) {
    const centerX = 960, centerY = 486, max = 440 + intensity * 150;
    ctx.save(); ctx.globalAlpha = alpha;
    for (let ring = 0; ring < 5; ring++) { const radius = max * (.34 + ring * .15) + Math.sin(time * (1.1 + ring * .08) + ring) * (9 + energy * 18); ctx.strokeStyle = color(ring % 2 ? colours.secondary : colours.foreground, .1 + intensity * .11); ctx.lineWidth = 1 + (ring === 2 ? energy * 3 : 0); ctx.beginPath(); ctx.ellipse(centerX, centerY, radius, radius * (.38 + ring * .035), time * (.08 + ring * .012), 0, TAU); ctx.stroke(); }
    const count = 40 + Math.round(intensity * 50); for (let index = 0; index < count; index++) { const angle = time * (.34 + hash(index, 2) * .36) + index * 2.399; const radius = max * (.26 + hash(index, 3) * .72); const x = centerX + Math.cos(angle) * radius, y = centerY + Math.sin(angle) * radius * .42; const size = 2 + hash(index, 4) * 5 + energy * 7 * (index % 7 === 0 ? 1 : .18); ctx.fillStyle = color(index % 3 ? colours.foreground : colours.accent, .25 + hash(index, 5) * .55); ctx.beginPath(); ctx.arc(x, y, size, 0, TAU); ctx.fill(); }
    ctx.restore();
  }
  function ribbons(ctx, time, colours, intensity, energy, alpha) {
    ctx.save(); ctx.globalAlpha = alpha; const count = 8 + Math.round(intensity * 9);
    for (let index = 0; index < count; index++) { const y = 170 + index * (710 / Math.max(1, count - 1)); const wave = 55 + intensity * 115 + energy * 58; const phase = time * (.65 + index * .04) + index * .8; ctx.strokeStyle = color(index % 3 === 0 ? colours.accent : index % 3 === 1 ? colours.secondary : colours.foreground, .12 + intensity * .16); ctx.lineWidth = 2 + (index % 3) * 2; ctx.beginPath(); for (let x = -40; x <= W + 40; x += 42) { const py = y + Math.sin(x * .005 + phase) * wave + Math.sin(x * .013 - phase * 1.7) * wave * .22; if (x < 3) ctx.moveTo(x, py); else ctx.lineTo(x, py); } ctx.stroke(); }
    for (let index = 0; index < 18; index++) { const x = (hash(index, 21) * W + time * (90 + hash(index, 22) * 90)) % (W + 120) - 60, y = 150 + hash(index, 23) * 690; ctx.fillStyle = color(colours.accent, .2 + energy * .38); ctx.fillRect(x, y, 32 + energy * 72, 2); }
    ctx.restore();
  }
  function grid(ctx, time, colours, intensity, energy, alpha, impact = 0) {
    const high = clamp((intensity - .65) / .35), cols = 12, rows = 10, horizon = 210 - impact * 88, bottom = 885, drift = (latestAccent(time)?.kind === 'sweep' ? -1 : 1) * impact * 100, scroll = (time * (.012 + intensity * .035 + high * .22)) % 1;
    const point = (column, depth) => { const spread = .15 + .85 * depth; return { x: W / 2 + ((column / cols) - .5) * W * 1.16 * spread + drift * depth, y: horizon + (bottom - horizon) * Math.pow(depth, 1.72) }; };
    ctx.save(); ctx.globalAlpha = alpha;
    for (let row = 0; row < rows; row++) { const near = (row / rows + scroll) % 1, far = near + 1 / rows; if (far > 1) continue; const fade = clamp(Math.min(near, 1 - far) * rows * 1.35); for (let column = 0; column < cols; column++) { const index = row * cols + column, a = point(column, near), b = point(column + 1, near), c = point(column + 1, far), d = point(column, far); const level = .18 + hash(index, 71) * .22 + energy * (index % 4 === 0 ? .28 : .08); ctx.fillStyle = color(index % 5 === 0 ? colours.accent : index % 3 === 0 ? colours.secondary : colours.foreground, fade * (.035 + level * (.17 + intensity * .24) + high * .76)); ctx.beginPath(); ctx.moveTo(a.x + 3, a.y + 3); ctx.lineTo(b.x - 3, b.y + 3); ctx.lineTo(c.x - 3, c.y - 3); ctx.lineTo(d.x + 3, d.y - 3); ctx.closePath(); ctx.fill(); ctx.strokeStyle = color(colours.foreground, fade * (.08 + intensity * .13 + impact * .14 + high * .16)); ctx.lineWidth = 1 + impact * 1.5; ctx.stroke(); } }
    ctx.restore();
  }
  function tiles(ctx, time, colours, intensity, energy, alpha, impact = 0) {
    const high = clamp((intensity - .65) / .35), cols = 3, rows = 3, tileW = 442, tileH = 206, left = 297, top = 190, accent = latestAccent(time), age = accent ? time - accent.time : 1, order = accent ? accents.indexOf(accent) : 0;
    ctx.save(); ctx.globalAlpha = alpha;
    for (let index = 0; index < cols * rows; index++) { const row = Math.floor(index / cols), column = index % cols, stagger = clamp((age - (index % 3) * .055) / .55), move = Math.sin(stagger * Math.PI) * impact, target = (index * 5 + order * 2 + 1) % 9, targetRow = Math.floor(target / cols), targetColumn = target % cols, breath = Math.sin(time * (.42 + intensity * .32) + index * 1.7) * (2 + intensity * 9) * (.35 + energy * .65), drive = Math.sin(time * .68 + index * .9) * high * 88; const x = left + column * tileW + ((targetColumn - column) * tileW * .62 + (index % 2 ? -48 : 48)) * move + breath * (column - 1) + drive * (column - 1), y = top + row * tileH + ((targetRow - row) * tileH * .62 + (row - 1) * 58) * move + breath * (row - 1) + drive * .36 * (row - 1), flip = 1 - move * (.72 + intensity * .12), width = (tileW - 24) * flip, fill = index % 3 === 0 ? colours.accent : index % 3 === 1 ? colours.secondary : colours.foreground; ctx.save(); ctx.translate(x + tileW / 2, y + tileH / 2); ctx.rotate((index % 2 ? -1 : 1) * (move * .055 + breath * .0008 + drive * .00018)); ctx.fillStyle = color(fill, .11 + intensity * .18 + (index % 4 === 0 ? energy * .12 : 0) + high * .76); ctx.fillRect(-width / 2, -tileH / 2 + 9, width, tileH - 18); ctx.strokeStyle = color(colours.foreground, .13 + intensity * .17 + move * .22 + high * .12); ctx.lineWidth = 1 + move * 2; ctx.strokeRect(-width / 2, -tileH / 2 + 9, width, tileH - 18); if (move > .03) { ctx.fillStyle = color(colours.background, .22 + move * .2); ctx.fillRect(-width / 2, -tileH / 2 + 9, width, (tileH - 18) * .12); } ctx.restore(); }
    ctx.restore();
  }
  function motif(ctx, time, name, colours, intensity, energy, alpha = 1) {
    if (name === 'none') return;
    ctx.save(); ctx.globalAlpha = alpha;
    if (name === 'stars') { for (let index = 0; index < 80; index++) { const x = hash(index, 41) * W, y = hash(index, 42) * H; const glint = .24 + .76 * (Math.sin(time * (1.1 + hash(index, 43)) + index) + 1) * .5; ctx.fillStyle = color(index % 5 ? colours.foreground : colours.accent, .07 + glint * (.18 + intensity * .22)); ctx.fillRect(x, y, 1 + glint * 3 + energy * (index % 11 === 0 ? 3 : 0), 1 + glint * 3); } }
    if (name === 'rain') { for (let index = 0; index < 76; index++) { const speed = 230 + hash(index, 51) * 340, x = (hash(index, 52) * (W + 260) - time * speed * .22) % (W + 260) - 130, y = (hash(index, 53) * H + time * speed) % (H + 140) - 70; ctx.strokeStyle = color(index % 6 ? colours.secondary : colours.accent, .11 + intensity * .17); ctx.lineWidth = 1 + energy * (index % 9 === 0 ? 1 : 0); ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 28, y + 88); ctx.stroke(); } }
    if (name === 'petals') { for (let index = 0; index < 42; index++) { const cycle = 90 + hash(index, 61) * 65, x = (hash(index, 62) * (W + 200) + time * cycle) % (W + 200) - 100, y = (hash(index, 63) * H + time * (40 + hash(index, 64) * 50)) % (H + 100) - 50; ctx.save(); ctx.translate(x, y); ctx.rotate(time * (1.4 + hash(index, 65)) + index); ctx.fillStyle = color(index % 3 ? colours.secondary : colours.accent, .14 + intensity * .22); ctx.beginPath(); ctx.ellipse(0, 0, 6 + energy * 4, 14 + energy * 5, .5, 0, TAU); ctx.fill(); ctx.restore(); } }
    ctx.restore();
  }
  function drawAccents(ctx, time, colours) {
    activeAccents(time).forEach(accent => {
      const age = time - accent.time, strength = accent.strength;
      if (accent.kind === 'ring') { const p = clamp(age / .7), radius = 90 + 1240 * p; ctx.strokeStyle = color(colours.accent, (1 - p) * (.19 + strength * .42)); ctx.lineWidth = 3 + strength * 6; ctx.beginPath(); ctx.arc(960, 500, radius, 0, TAU); ctx.stroke(); ctx.strokeStyle = color(colours.secondary, (1 - p) * (.08 + strength * .18)); ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(960, 500, radius * .68, 0, TAU); ctx.stroke(); }
      if (accent.kind === 'rays') { const p = clamp(age / .5); ctx.save(); ctx.globalAlpha = (1 - p) * (.12 + strength * .34); for (let index = 0; index < 24; index++) { const angle = index / 24 * TAU + age * .7; ctx.strokeStyle = color(index % 2 ? colours.accent : colours.foreground, 1); ctx.lineWidth = 1.5 + strength * 4; ctx.beginPath(); ctx.moveTo(960 + Math.cos(angle) * 45, 500 + Math.sin(angle) * 45); ctx.lineTo(960 + Math.cos(angle) * (850 + p * 560), 500 + Math.sin(angle) * (850 + p * 560)); ctx.stroke(); } ctx.restore(); }
      if (accent.kind === 'sweep') { const p = clamp(age / .8), x = -650 + p * 3220; const gradient = ctx.createLinearGradient(x - 470, 0, x + 470, H); gradient.addColorStop(0, color(colours.accent, 0)); gradient.addColorStop(.5, color(colours.accent, .08 + strength * .17)); gradient.addColorStop(1, color(colours.accent, 0)); ctx.fillStyle = gradient; ctx.fillRect(x - 520, 0, 1040, H); }
      if (accent.kind === 'punch') { const p = clamp(age / .5), size = 180 + p * 1120; ctx.strokeStyle = color(colours.accent, (1 - p) * (.12 + strength * .3)); ctx.lineWidth = 2 + strength * 4; ctx.strokeRect(960 - size / 2, 500 - size * .31, size, size * .62); }
    });
  }
  function drawStyle(ctx, time, section, colours, energy, alpha, impact) {
    if (section.style === 'orbit') orbit(ctx, time, colours, section.intensity, energy, alpha);
    if (section.style === 'ribbons') ribbons(ctx, time, colours, section.intensity, energy, alpha);
    if (section.style === 'grid') grid(ctx, time, colours, section.intensity, energy, alpha, impact);
    if (section.style === 'tiles') tiles(ctx, time, colours, section.intensity, energy, alpha, impact);
    motif(ctx, time, section.motif, colours, section.intensity, energy, alpha);
  }
  const wrapLines = (ctx, text, maxWidth) => {
    let fontSize = 64, lines = [];
    while (fontSize >= 32) { ctx.font = `800 ${fontSize}px Paperlogy,sans-serif`; const units = [...text]; const candidate = ['']; units.forEach(unit => { const line = candidate.at(-1); if (line && ctx.measureText(line + unit).width > maxWidth && candidate.length < 2) candidate.push(unit); else candidate[candidate.length - 1] += unit; }); if (candidate.length <= 2 && candidate.every(line => ctx.measureText(line).width <= maxWidth)) { lines = candidate; break; } fontSize -= 2; }
    if (!lines.length) { fontSize = 30; ctx.font = `800 ${fontSize}px Paperlogy,sans-serif`; const units = [...text], midpoint = Math.ceil(units.length / 2); lines = [units.slice(0, midpoint).join(''), units.slice(midpoint).join('')]; }
    return { lines, fontSize };
  };
  function drawCaption(ctx, time, cue, cueIndex, colours, energy) {
    if (!cue) return { activeCue: -1, text: '', activeWord: -1, wordTiming: false, captionBounds: [] };
    const hasQueueRail = display.showQueue, maxWidth = hasQueueRail ? 1120 : 1500;
    const result = wrapLines(ctx, cue.text, maxWidth), scale = 1 + Math.min(.05, energy * .025 + accentPulse(time, 'punch') * .025), lineHeight = result.fontSize * 1.24, baseY = result.lines.length === 2 ? 477 : 515;
    const widths = result.lines.map(line => { ctx.font = `800 ${result.fontSize}px Paperlogy,sans-serif`; return ctx.measureText(line).width; }); const boxWidth = Math.max(...widths) + 106, boxHeight = result.lines.length * lineHeight + 72, x = hasQueueRail ? 748 : 960, y = baseY - boxHeight / 2;
    ctx.save(); ctx.translate(x, baseY); ctx.scale(scale, scale); ctx.translate(-x, -baseY); ctx.fillStyle = color(colours.background, .52); ctx.strokeStyle = color(colours.foreground, .2); ctx.lineWidth = 1; ctx.fillRect(x - boxWidth / 2, y, boxWidth, boxHeight); ctx.strokeRect(x - boxWidth / 2, y, boxWidth, boxHeight); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.font = `800 ${result.fontSize}px Paperlogy,sans-serif`; ctx.fillStyle = contrast(colours); result.lines.forEach((line, index) => { const lineY = baseY + (index - (result.lines.length - 1) / 2) * lineHeight; ctx.fillText(line, x + 3, lineY + 4); }); ctx.fillStyle = color(colours.foreground); result.lines.forEach((line, index) => { const lineY = baseY + (index - (result.lines.length - 1) / 2) * lineHeight; ctx.fillText(line, x, lineY); }); ctx.restore();
    const validWords = Array.isArray(cue.words) && cue.words.length && cue.words.every(word => word && typeof word.text === 'string' && Number.isFinite(word.startSeconds) && Number.isFinite(word.endSeconds) && word.endSeconds > word.startSeconds) && cue.words.map(word => word.text).join('').replace(/\s/g, '') === cue.text.replace(/\s/g, '');
    const activeWord = validWords ? cue.words.findIndex(word => time >= word.startSeconds && time < word.endSeconds) : -1;
    return { activeCue: cueIndex, text: cue.text, activeWord, wordTiming: Boolean(validWords), captionBounds: [{ l: x - boxWidth * scale / 2, r: x + boxWidth * scale / 2, t: y - (scale - 1) * boxHeight / 2, b: y + boxHeight * scale }] };
  }
  function drawSpectrum(ctx, time, colours) {
    if (!display.showSpectrum) return; const values = spectrumAt(time), width = 1600, x = 160, y = 966, height = 78, gap = 5, bar = (width - gap * Math.max(0, values.length - 1)) / Math.max(1, values.length); ctx.fillStyle = color(colours.background, .5); ctx.fillRect(x - 18, y - height - 20, width + 36, height + 34); values.forEach((value, index) => { const h = Math.max(2, value * height); const gradient = ctx.createLinearGradient(0, y - h, 0, y); gradient.addColorStop(0, color(colours.accent)); gradient.addColorStop(1, color(colours.foreground, .65)); ctx.fillStyle = gradient; ctx.fillRect(x + index * (bar + gap), y - h, bar, h); });
  }
  function drawMetadata(ctx, time, colours) {
    const track = trackAt(time); ctx.save(); ctx.textBaseline = 'top';
    const fit = (text, width) => { const value = String(text || ''); if (ctx.measureText(value).width <= width) return value; let out = ''; for (const character of value) { if (ctx.measureText(`${out}${character}…`).width > width) break; out += character; } return `${out}…`; };
    if (display.channelName) { ctx.font = '700 25px Paperlogy,sans-serif'; ctx.fillStyle = color(colours.foreground, .78); ctx.fillText(fit(display.channelName, 620), 84, 74); }
    if (display.showNowPlaying && track) { ctx.fillStyle = color(colours.background, .82); ctx.fillRect(82, 124, 470, 116); ctx.strokeStyle = color(colours.foreground, .2); ctx.strokeRect(82, 124, 470, 116); ctx.font = '700 16px Paperlogy,sans-serif'; ctx.fillStyle = color(colours.accent); ctx.fillText('NOW PLAYING', 108, 150); ctx.font = '800 28px Paperlogy,sans-serif'; ctx.fillStyle = color(colours.foreground); ctx.fillText(fit(typeof track.title === 'string' ? track.title : '', 410), 108, 181); }
    if (display.showQueue) { const queue = tracks.filter(item => item.startSeconds >= time && item.id !== track?.id).slice(0, 4); const x = 1460, y = 130; ctx.fillStyle = color(colours.background, .82); ctx.fillRect(x, y, 372, 58 + Math.max(1, queue.length) * 61); ctx.strokeStyle = color(colours.foreground, .2); ctx.strokeRect(x, y, 372, 58 + Math.max(1, queue.length) * 61); ctx.font = '700 16px Paperlogy,sans-serif'; ctx.fillStyle = color(colours.accent); ctx.fillText('UP NEXT', x + 24, y + 21); ctx.font = '600 21px Paperlogy,sans-serif'; ctx.fillStyle = color(colours.foreground, .9); (queue.length ? queue : [{ title: '다음 곡 없음' }]).forEach((item, index) => ctx.fillText(fit(typeof item.title === 'string' ? item.title : '', 324), x + 24, y + 64 + index * 58)); }
    ctx.restore();
  }
  let canvas, context, diagnostics = { section: -1, trackId: null, style: null, motif: null, intensity: 0, imageId: null, thumbnailActive: false, thumbnailDurationSeconds: thumbnail?.duration || 0, activeCue: -1, text: '', energy: 0, pulse: 0, accentCount: 0, activeAccents: [], lastAccentTime: null, captionBounds: [], display, wordTiming: false, activeWord: -1 };
  window.MOTION_DIAGNOSTICS = () => diagnostics;
  REEL.config({ duration: config.duration, fps: Number.isFinite(config.fps) ? config.fps : 30, width: W, height: H, audio: config.audio || null, push: 0 });
  REEL.scene({ id: 'rhythm-canvas', start: 0, end: config.duration, setup(parent) { canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H; canvas.className = 'rhythm-canvas'; canvas.style.cssText = 'position:absolute;inset:0;width:1920px;height:1080px;pointer-events:none'; parent.append(canvas); context = canvas.getContext('2d'); }, render(_, state) {
    const time = state.t, section = sectionState(time), current = section.current, energy = energyAt(time), selected = activeAccents(time), accentEnergy = selected.reduce((value, accent) => Math.max(value, accent.strength), 0), impact = accentKick(time), punch = accentPulse(time, 'punch'), pulse = clamp(energy * (.35 + current.intensity * .65) + accentEnergy * .42), ctx = context;
    resetFrame(ctx); frame(ctx, section.colors); const hasImage = drawImageCover(ctx, time, current, section.colors, impact); ctx.save(); ctx.translate(W / 2, H / 2); const zoom = 1 + impact * .055; ctx.scale(zoom, zoom); ctx.translate(-W / 2, -H / 2);
    const geometryAlpha = hasImage ? .42 : 1; drawStyle(ctx, time, current, section.colors, energy, (1 - section.amount) * geometryAlpha, impact); if (section.next) drawStyle(ctx, time, section.next, section.colors, energy, section.amount * (section.next.imageId ? .42 : 1), impact); ctx.restore(); drawAccents(ctx, time, section.colors); const cue = cueAt(time), cueIndex = cue ? lyrics.indexOf(cue) : -1; const caption = drawCaption(ctx, time, cue, cueIndex, section.colors, energy); drawMetadata(ctx, time, section.colors); drawSpectrum(ctx, time, section.colors); const thumbnailActive = drawThumbnail(ctx, time);
    diagnostics = { section: sectionList.indexOf(current), trackId: current.trackId, style: current.style, motif: current.motif, intensity: current.intensity, imageId: current.imageId, thumbnailActive, thumbnailDurationSeconds: thumbnail?.duration || 0, activeCue: caption.activeCue, text: caption.text, energy, pulse, accentCount: selected.length, activeAccents: selected.map(accent => ({ timeSeconds: accent.time, kind: accent.kind, strength: accent.strength, origin: accent.origin })), lastAccentTime: accents.filter(accent => accent.time <= time).at(-1)?.time ?? null, captionBounds: caption.captionBounds, display, wordTiming: caption.wordTiming, activeWord: caption.activeWord };
  } });
})();
