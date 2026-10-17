/* 정적 음반 레이어: create 뒤 매 프레임에는 캐시 이미지만 변환해 찍는다. */
(() => {
  'use strict';

  const TAU = Math.PI * 2;
  const RAD = Math.PI / 180;
  const DISC = 1024;
  const CASE = 1200; // drawCase의 size는 그림자 여백을 포함한 이 투명 캔버스 한 변이다.
  const CARD_W = 1200;
  const CARD_H = 880;
  const sourceSize = (image, name, minWidth, minHeight) => {
    const width = Number(image && (image.naturalWidth || image.videoWidth || image.width));
    const height = Number(image && (image.naturalHeight || image.videoHeight || image.height));
    if (!Number.isFinite(width) || !Number.isFinite(height) || width < minWidth || height < minHeight) {
      throw new TypeError(`${name} 소스 PNG는 최소 ${minWidth}×${minHeight}여야 합니다.`);
    }
    return { width, height };
  };
  const canvas = (width, height) => {
    if (!globalThis.document) throw new Error('RecordLayers.create는 브라우저 Canvas가 필요합니다.');
    const node = document.createElement('canvas');
    node.width = width;
    node.height = height;
    return node;
  };
  const cover = (ctx, image, outWidth, outHeight, x = 0, y = 0) => {
    const { width, height } = sourceSize(image, '이미지', 1, 1);
    const scale = Math.max(outWidth / width, outHeight / height);
    const drawWidth = width * scale;
    const drawHeight = height * scale;
    ctx.drawImage(image, x + (outWidth - drawWidth) / 2, y + (outHeight - drawHeight) / 2, drawWidth, drawHeight);
  };
  const tear = (ctx, x, y, width, height) => {
    if (window.PLAYLIST_CONFIG.preset.variant === 'prism') { ctx.beginPath(); ctx.rect(x,y,width,height); return; }
    const step = 48;
    ctx.beginPath();
    ctx.moveTo(x, y + 8);
    for (let i = 0; i <= width; i += step) ctx.lineTo(x + i, y + ((i * 13) % 19));
    for (let i = 0; i <= height; i += step) ctx.lineTo(x + width - ((i * 11) % 14), y + i);
    for (let i = width; i >= 0; i -= step) ctx.lineTo(x + i, y + height - ((i * 17) % 17));
    for (let i = height; i >= 0; i -= step) ctx.lineTo(x + ((i * 7) % 16), y + i);
    ctx.closePath();
  };

  function makeDisc(photo) {
    const node = canvas(DISC, DISC);
    const ctx = node.getContext('2d');
    ctx.save();
    ctx.beginPath(); ctx.arc(512, 512, 502, 0, TAU); ctx.clip();
    cover(ctx, photo, DISC, DISC);
    const shade = ctx.createRadialGradient(512, 512, 330, 512, 512, 510);
    shade.addColorStop(0, 'rgba(15,10,18,0)');
    shade.addColorStop(1, 'rgba(12,9,16,.36)');
    ctx.fillStyle = shade; ctx.fillRect(0, 0, DISC, DISC);
    ctx.restore();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath(); ctx.arc(512, 512, 30, 0, TAU); ctx.fill();
    ctx.globalCompositeOperation = 'source-over';
    return node;
  }

  function makeGlass() {
    const node = canvas(DISC, DISC);
    const ctx = node.getContext('2d');
    const metal = ctx.createLinearGradient(90, 80, 930, 950);
    metal.addColorStop(0, '#f5f1e8'); metal.addColorStop(.22, '#8d9697');
    metal.addColorStop(.5, '#f8f4e9'); metal.addColorStop(.74, '#879092'); metal.addColorStop(1, '#ece7dc');
    ctx.strokeStyle = metal; ctx.lineWidth = 10;
    ctx.beginPath(); ctx.arc(512, 512, 500, 0, TAU); ctx.stroke();
    ctx.strokeStyle = 'rgba(255,255,250,.45)'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(512, 512, 491, -2.46, -1.56); ctx.stroke();
    ctx.strokeStyle = 'rgba(130,220,230,.3)';
    ctx.beginPath(); ctx.arc(512, 512, 415, .38, 1.24); ctx.stroke();
    const hub = ctx.createRadialGradient(496, 493, 4, 512, 512, 54);
    hub.addColorStop(0, 'rgba(255,255,248,.92)'); hub.addColorStop(.28, 'rgba(183,191,191,.9)');
    hub.addColorStop(.72, 'rgba(73,85,89,.92)'); hub.addColorStop(1, 'rgba(244,236,222,.86)');
    ctx.fillStyle = hub; ctx.beginPath(); ctx.arc(512, 512, 54, 0, TAU); ctx.arc(512, 512, 19, 0, TAU, true); ctx.fill('evenodd');
    ctx.strokeStyle = 'rgba(255,255,250,.58)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(512, 512, 43, 0, TAU); ctx.stroke();
    return node;
  }

  function makeCase(image) {
    const node = canvas(CASE, CASE);
    const ctx = node.getContext('2d');
    ctx.save();
    ctx.shadowColor = 'rgba(18,12,18,.46)'; ctx.shadowBlur = 48; ctx.shadowOffsetY = 30;
    cover(ctx, image, 920, 920, 140, 120); ctx.restore();
    cover(ctx, image, 920, 920, 140, 120);
    return node;
  }

  function makeCard(photo, paper, index) {
    const node = canvas(CARD_W, CARD_H);
    const ctx = node.getContext('2d');
    ctx.save(); tear(ctx, 82, 68, 1036, 704); ctx.shadowColor = 'rgba(22,14,16,.42)'; ctx.shadowBlur = 32; ctx.shadowOffsetY = 24;
    ctx.fillStyle = 'rgba(35,25,28,.7)'; ctx.fill(); ctx.restore();
    ctx.save(); tear(ctx, 82, 68, 1036, 704); ctx.clip();
    cover(ctx, paper, CARD_W, CARD_H);
    ctx.fillStyle = 'rgba(250,243,226,.32)'; ctx.fillRect(82, 68, 1036, 704);
    ctx.save(); ctx.beginPath(); ctx.rect(150, 126, 900, 518); ctx.clip(); cover(ctx, photo, 900, 518, 150, 126); ctx.restore();
    ctx.fillStyle = [window.PLAYLIST_CONFIG.preset.palette.accent, window.PLAYLIST_CONFIG.preset.palette.ink, window.PLAYLIST_CONFIG.preset.palette.light][index]; ctx.globalAlpha = .68; ctx.fillRect(150, 674, 436, 18);
    ctx.globalAlpha = .18; ctx.fillStyle = '#20171d'; ctx.fillRect(150, 714, 720, 9); ctx.fillRect(150, 738, 510, 7);
    ctx.restore();
    return node;
  }

  const validNumber = (value, name) => {
    if (!Number.isFinite(value)) throw new TypeError(`${name}은(는) 유한한 숫자여야 합니다.`);
    return value;
  };
  const validOpacity = value => {
    validNumber(value, 'opacity');
    if (value < 0 || value > 1) throw new RangeError('opacity는 0~1이어야 합니다.');
    return value;
  };
  const draw = (ctx, image, x, y, width, height, angle, opacity) => {
    if (!ctx || typeof ctx.drawImage !== 'function') throw new TypeError('2D CanvasRenderingContext2D가 필요합니다.');
    ctx.save(); ctx.translate(x, y); ctx.rotate(angle * RAD); ctx.globalAlpha = opacity;
    ctx.drawImage(image, -width / 2, -height / 2, width, height); ctx.restore();
  };

  function create(assets = {}) {
    if (!Array.isArray(assets.photos) || assets.photos.length !== 3) throw new TypeError('photos는 3개 소스 PNG 배열이어야 합니다.');
    assets.photos.forEach((photo, index) => sourceSize(photo, `photos[${index}]`, 1024, 700));
    sourceSize(assets.case, 'case', 1024, 1024);
    sourceSize(assets.paper, 'paper', 1024, 700);
    const discs = assets.photos.map(makeDisc);
    const glass = makeGlass();
    const caseLayer = makeCase(assets.case);
    const cards = assets.photos.map((photo, index) => makeCard(photo, assets.paper, index));
    const values = (opts, sizeName, fallbackIndex) => {
      const value = opts || {};
      const index = value.index === undefined ? fallbackIndex : value.index;
      validNumber(value.x, 'x'); validNumber(value.y, 'y'); validNumber(value.angle === undefined ? 0 : value.angle, 'angle');
      validOpacity(value.opacity === undefined ? 1 : value.opacity); validNumber(value[sizeName], sizeName);
      if (value[sizeName] <= 0) throw new RangeError(`${sizeName}는 0보다 커야 합니다.`);
      return { index, angle: value.angle === undefined ? 0 : value.angle, opacity: value.opacity === undefined ? 1 : value.opacity };
    };
    return {
      discs, glass, case: caseLayer, cards,
      drawDisc(ctx, opts) {
        const value = values(opts, 'r', 0); if (!Number.isInteger(value.index) || !discs[value.index]) throw new RangeError('disc index는 0~2여야 합니다.');
        draw(ctx, discs[value.index], opts.x, opts.y, opts.r * 2, opts.r * 2, value.angle, value.opacity);
        draw(ctx, glass, opts.x, opts.y, opts.r * 2, opts.r * 2, 0, value.opacity);
      },
      drawCase(ctx, opts) {
        const value = values(opts, 'size', 0); draw(ctx, caseLayer, opts.x, opts.y, opts.size, opts.size, value.angle, value.opacity);
      },
      drawCard(ctx, index, opts) {
        const value = values(opts, 'width', index); if (!Number.isInteger(index) || !cards[index]) throw new RangeError('card index는 0~2여야 합니다.');
        draw(ctx, cards[index], opts.x, opts.y, opts.width, opts.width * CARD_H / CARD_W, value.angle, value.opacity);
      },
    };
  }

  window.RecordLayers = { create };
})();
