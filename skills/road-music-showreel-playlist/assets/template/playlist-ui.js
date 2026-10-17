/* FFT 프레임과 전역 합성 시계만 사용한다. 장식용 난수/레벨 데이터는 쓰지 않는다. */
(() => {
  'use strict';
  const W = 1920;
  const bool = value => value === true;
  const display = () => {
    const value = (window.CD_CONFIG && window.CD_CONFIG.display) || {};
    return { showSpectrum: bool(value.showSpectrum), showQueue: bool(value.showQueue), showNowPlaying: bool(value.showNowPlaying) };
  };
  const cleanTrack = (track, index) => {
    if (!track || typeof track.title !== 'string' || typeof track.id !== 'string') return null;
    const start = Number(track.startSeconds), end = Number(track.endSeconds);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
    return { id: track.id, title: track.title, startSeconds: start, endSeconds: end, durationSeconds: Number(track.durationSeconds) || end - start, index };
  };
  const tracks = () => {
    const playlist = window.CD_CONFIG && window.CD_CONFIG.playlist;
    if (!playlist || playlist.schemaVersion !== 1 || !Array.isArray(playlist.tracks)) return [];
    return playlist.tracks.map(cleanTrack).filter(Boolean).sort((a, b) => a.startSeconds - b.startSeconds || a.index - b.index);
  };
  function stateAt(time) {
    const now = Number.isFinite(time) ? time : 0;
    const list = tracks();
    const current = list.find(track => now >= track.startSeconds && now < track.endSeconds) || null;
    const next = list.filter(track => track.startSeconds >= now && (!current || track.id !== current.id));
    return { current, queue: next };
  }
  function spectrum() {
    const source = window.CD_SPECTRUM;
    if (!source || source.schemaVersion !== 1 || !Number.isFinite(source.dt) || source.dt <= 0 || !Number.isInteger(source.bands) || source.bands < 1 || !Array.isArray(source.frames) || source.frames.length < 1) return null;
    if (!source.frames.every(frame => Array.isArray(frame) && frame.length === source.bands)) return null;
    return source;
  }
  function withAlpha(color, alpha, fallback) {
    const value = String(color || '');
    const hex = value.match(/^#([\da-f]{3}|[\da-f]{6})$/i);
    if (!hex) return fallback;
    const source = hex[1].length === 3 ? [...hex[1]].map(char => char + char).join('') : hex[1];
    return `rgba(${parseInt(source.slice(0, 2), 16)},${parseInt(source.slice(2, 4), 16)},${parseInt(source.slice(4, 6), 16)},${alpha})`;
  }
  function valuesAt(source, time) {
    const position = Math.max(0, time / source.dt), first = Math.min(source.frames.length - 1, Math.floor(position)), second = Math.min(source.frames.length - 1, first + 1), mix = Math.min(1, position - first);
    return source.frames[first].map((value, index) => {
      const a = Math.max(0, Math.min(255, Number(value) || 0)), b = Math.max(0, Math.min(255, Number(source.frames[second][index]) || 0));
      return a + (b - a) * mix;
    });
  }
  const palette = () => {
    const preset = window.CD_CONFIG.preset, colors = preset.palette || {};
    const dark = colors.dark || '#1e171a', light = colors.light || '#fff8eb', ink = colors.ink || '#34292d', paper = colors.paper || '#efe3cc', accent = colors.accent || '#be5476';
    const darkLook = preset.variant === 'neon' || preset.variant === 'noir';
    return { line: darkLook ? light : ink, edge: accent, panel: withAlpha(darkLook ? dark : paper, .76, darkLook ? 'rgba(30,23,26,.76)' : 'rgba(239,227,204,.76)'), text: darkLook ? light : ink, faint: withAlpha(darkLook ? light : ink, darkLook ? .30 : .22, darkLook ? 'rgba(255,248,235,.30)' : 'rgba(52,41,45,.22)'), glow: preset.variant === 'neon' || preset.variant === 'prism' };
  };
  function install(R) {
    const options = display(), hasMetadata = options.showSpectrum || options.showQueue || options.showNowPlaying;
    if (!hasMetadata) return;
    const source = options.showSpectrum ? spectrum() : null;
    if (options.showSpectrum && !source) throw new Error('showSpectrum requires a valid CD_SPECTRUM FFT payload');
    let spectrumCanvas, spectrumContext, nowTitle, queueList, queueEmpty, queueMore;
    const drawSpectrum = time => {
      if (!spectrumContext || !source) return;
      const ctx = spectrumContext, width = spectrumCanvas.width, height = spectrumCanvas.height, color = palette(), values = valuesAt(source, time);
      ctx.clearRect(0, 0, width, height);
      ctx.strokeStyle = color.faint; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, height - 3.5); ctx.lineTo(width, height - 3.5); ctx.stroke();
      const gap = 4, bandWidth = (width - gap * (values.length - 1)) / values.length;
      values.forEach((value, index) => {
        const amount = value / 255, bar = Math.max(1, amount * (height - 12)), x = index * (bandWidth + gap), y = height - 4 - bar;
        const gradient = ctx.createLinearGradient(0, y, 0, height); gradient.addColorStop(0, color.edge); gradient.addColorStop(1, color.line); ctx.fillStyle = gradient; ctx.shadowBlur = color.glow ? 6 : 0; ctx.shadowColor = color.edge; ctx.fillRect(x, y, bandWidth, bar);
      });
      ctx.shadowBlur = 0;
    };
    const setTitle = (element, track) => { element.textContent = track ? track.title : ''; element.dataset.trackId = track ? track.id : ''; };
    const drawPlaylist = time => {
      const state = stateAt(time);
      if (nowTitle) setTitle(nowTitle, state.current);
      if (!queueList) return;
      const visible = state.queue.slice(0, 5);
      while (queueList.firstChild) queueList.removeChild(queueList.firstChild);
      visible.forEach((track, index) => {
        const item = document.createElement('li'), number = document.createElement('span'), title = document.createElement('span');
        item.className = 'cd-playlist-queue-item'; item.dataset.trackId = track.id; number.className = 'cd-playlist-queue-number'; number.textContent = String(index + 1).padStart(2, '0'); title.className = 'cd-playlist-queue-title'; title.textContent = track.title; item.append(number, title); queueList.appendChild(item);
      });
      queueEmpty.hidden = visible.length > 0; queueEmpty.textContent = '다음 곡 없음';
      queueMore.hidden = state.queue.length <= visible.length; queueMore.textContent = `+${state.queue.length - visible.length}곡`;
    };
    R.overlay(time => { drawSpectrum(time); drawPlaylist(time); }, { layer: 'top', setup(host) {
      const color = palette();
      if (source) {
        const spectrumWidth = options.showQueue || options.showNowPlaying ? 1240 : 1720;
        spectrumCanvas = document.createElement('canvas'); spectrumCanvas.className = 'cd-playlist-spectrum'; spectrumCanvas.width = spectrumWidth; spectrumCanvas.height = 75; spectrumCanvas.setAttribute('aria-hidden', 'true'); spectrumCanvas.style.cssText = `position:absolute;left:100px;top:840px;width:${spectrumWidth}px;height:75px;pointer-events:none`; spectrumContext = spectrumCanvas.getContext('2d'); host.appendChild(spectrumCanvas);
      }
      if (!options.showQueue && !options.showNowPlaying) return;
      const rail = document.createElement('aside'); rail.className = 'cd-playlist-rail'; rail.style.cssText = `position:absolute;left:1420px;top:116px;width:400px;padding:22px 22px 18px;border:1px solid ${color.faint};background:${color.panel};color:${color.text};box-shadow:0 12px 34px rgba(0,0,0,.18);font-family:Pretendard,sans-serif;pointer-events:none`;
      if (options.showNowPlaying) {
        const label = document.createElement('div'); label.className = 'cd-playlist-label'; label.textContent = 'NOW PLAYING'; label.style.cssText = `font:700 12px/1.2 Pretendard,sans-serif;letter-spacing:.13em;color:${color.edge};margin-bottom:10px`;
        nowTitle = document.createElement('div'); nowTitle.className = 'cd-playlist-now-title'; nowTitle.style.cssText = `display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;font:700 29px/1.22 "Noto Serif KR",serif;word-break:keep-all;margin-bottom:${options.showQueue ? '30px' : '0'}`;
        rail.append(label, nowTitle);
      }
      if (options.showQueue) {
        const label = document.createElement('div'); label.className = 'cd-playlist-label'; label.textContent = 'UP NEXT'; label.style.cssText = `font:700 12px/1.2 Pretendard,sans-serif;letter-spacing:.13em;color:${color.edge};margin-bottom:12px`;
        queueList = document.createElement('ol'); queueList.className = 'cd-playlist-queue'; queueList.style.cssText = 'list-style:none;padding:0;margin:0';
        queueEmpty = document.createElement('div'); queueEmpty.className = 'cd-playlist-queue-empty'; queueEmpty.style.cssText = 'font:500 17px/1.45 Pretendard,sans-serif;opacity:.72';
        queueMore = document.createElement('div'); queueMore.className = 'cd-playlist-queue-more'; queueMore.style.cssText = `margin-top:12px;font:700 14px/1 Pretendard,sans-serif;color:${color.edge}`;
        rail.append(label, queueList, queueEmpty, queueMore);
      }
      host.appendChild(rail);
      const style = document.createElement('style'); style.textContent = '.cd-playlist-queue-item{display:grid;grid-template-columns:30px minmax(0,1fr);gap:8px;margin:0 0 11px}.cd-playlist-queue-number{font:700 12px/1.4 Pretendard,sans-serif;opacity:.56}.cd-playlist-queue-title{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;font:600 17px/1.35 Pretendard,sans-serif;word-break:keep-all}'; host.appendChild(style);
    }});
  }
  window.CDPlaylistUI = { install, stateAt, spectrumValuesAt: valuesAt };
})();
