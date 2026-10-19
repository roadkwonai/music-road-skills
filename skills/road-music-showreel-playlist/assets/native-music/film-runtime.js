/* Native 음악 프로젝트의 공통 입력·오버레이. 장면 미술은 scenes.js의 저자 코드만 등록한다. */
(function () {
  'use strict';
  const input = window.FILM_INPUT;
  const plan = window.FILM_PLAN;
  const fail = message => { throw new Error(`[native music] ${message}`); };
  if (!input || input.schemaVersion !== 1) fail('FILM_INPUT이 없습니다.');
  if (!plan || plan.schemaVersion !== 1 || !Array.isArray(plan.scenes)) fail('해결된 FILM_PLAN이 없습니다.');
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  for (const key of ['duration', 'fps', 'width', 'height']) if (!finite(input[key]) || input[key] <= 0) fail(`${key} 값이 유효하지 않습니다.`);
  const scenes = plan.scenes;
  if (!scenes.length) fail('장면이 없습니다.');
  const media = Array.isArray(plan.media) ? plan.media : [];
  const display = input.display || {};
  const tracks = Array.isArray(input.playlist?.tracks) ? input.playlist.tracks : [];
  const cues = Array.isArray(input.captions?.cues) ? input.captions.cues : [];
  const spectrumData = input.spectrum;
  if (display.showSpectrum === true) {
    if (!spectrumData || spectrumData.schemaVersion !== 1 || !finite(spectrumData.dt) || spectrumData.dt <= 0 || !Number.isInteger(spectrumData.bands) || spectrumData.bands < 1 || !Array.isArray(spectrumData.frames) || !spectrumData.frames.length || !spectrumData.frames.every(frame => Array.isArray(frame) && frame.length === spectrumData.bands && frame.every(value => finite(value) && value >= 0 && value <= 255))) fail('스펙트럼 데이터가 유효하지 않습니다.');
  }
  const images = Object.create(null);
  const captionLayouts = new Map();
  const mediaById = new Map(media.map(asset => [asset.id, asset]));
  const isImage = asset => asset && typeof asset.id === 'string' && typeof asset.src === 'string' && asset.src.length > 0;
  if (media.some(asset => !isImage(asset))) fail('미디어 정보가 유효하지 않습니다.');
  const loadImage = asset => new Promise((resolve, reject) => {
    const image = new Image();
    image.decoding = 'sync';
    image.onload = () => image.decode().then(() => {
      if (!image.naturalWidth || !image.naturalHeight) reject(new Error(`이미지 크기를 읽을 수 없습니다: ${asset.id}`));
      else { images[asset.id] = image; resolve(image); }
    }).catch(reject);
    image.onerror = () => reject(new Error(`이미지를 읽을 수 없습니다: ${asset.id}`));
    image.src = asset.src;
  });
  const required = new Set();
  for (const scene of scenes) for (const id of (scene.assets || [])) required.add(id);
  if (plan.opening?.thumbnailId) required.add(plan.opening.thumbnailId);
  for (const id of required) if (!mediaById.has(id)) fail(`참조한 미디어가 없습니다: ${id}`);
  // 선언된 자산 전체를 먼저 decode한다. 장면에서 쓰는 자산만 늦게 실패하면 렌더 proof가 불완전해진다.
  const ready = Promise.all(media.map(loadImage));
  window.FILM_IMAGES = images;
  window.FILM_MEDIA_READY = ready;
  REEL.preload(ready);
  REEL.config({ duration: input.duration, fps: input.fps, width: input.width, height: input.height, audio: input.audio || null });

  const state = { cueId: null, text: '', captionBounds: [], captionFontSize: 64, trackId: null, showflags: display, thumbnailVisible: false };
  window.__filmUiState = () => ({ ...state, captionBounds: state.captionBounds.map(bounds => ({ ...bounds })) });
  const trackAt = t => tracks.find(track => t >= track.startSeconds && t < track.endSeconds) || (tracks.length && t >= tracks.at(-1).endSeconds && t < input.duration ? tracks.at(-1) : null);
  const renderTarget = new URLSearchParams(location.search).has('render');
  const cueAt = t => {
    const clock = renderTarget ? Math.round(t * input.fps) / input.fps : t;
    return cues.find(cue => clock >= cue.startSeconds && clock < cue.endSeconds) || null;
  };
  const measureCaption = (element, text) => {
    element.textContent = text;
    element.style.fontSize = '64px';
    element.style.maxWidth = '1728px';
    // 원문을 두 줄 안에 담되, 줄 구분 외에는 어떤 글자도 바꾸지 않는다.
    for (let size = 64; size >= 42; size--) {
      element.style.fontSize = `${size}px`;
      if (element.getClientRects().length && element.scrollHeight <= 159) return size;
    }
    return 42;
  };
  const rects = element => {
    const range = document.createRange();
    range.selectNodeContents(element);
    return [...range.getClientRects()].map(rect => ({ l: rect.left, r: rect.right, t: rect.top, b: rect.bottom })).filter(rect => rect.r > rect.l && rect.b > rect.t);
  };
  const spectrumAt = t => {
    const signal = spectrumData;
    const frames = signal?.frames || [];
    if (!Array.isArray(frames) || !frames.length) return [];
    const dt = finite(signal.dt) && signal.dt > 0 ? signal.dt : 1 / input.fps;
    const index = Math.max(0, Math.min(frames.length - 1, Math.floor((t - (signal.t0 || 0)) / dt)));
    return Array.isArray(frames[index]) ? frames[index] : [];
  };
  let caption, spectrum, now, queue, channel, thumbnail, context, renderedCaptionKey = null;
  REEL.overlay(t => {
    const track = trackAt(t);
    const cue = cueAt(t);
    state.trackId = track?.id || null;
    state.showflags = display;
    state.cueId = cue?.id ?? null;
    state.text = cue?.text || '';
    caption.hidden = !cue;
    if (cue) {
      const key = `${cue.id}\u0000${cue.text}`;
      let layout = captionLayouts.get(key);
      if (renderedCaptionKey !== key) {
        if (!layout) {
          layout = { fontSize: measureCaption(caption, cue.text), bounds: rects(caption) };
          captionLayouts.set(key, layout);
        } else {
          caption.textContent = cue.text;
          caption.style.fontSize = `${layout.fontSize}px`;
          caption.style.maxWidth = '1728px';
        }
        renderedCaptionKey = key;
      }
      state.captionFontSize = layout.fontSize;
      state.captionBounds = layout.bounds;
    } else {
      if (renderedCaptionKey !== null) caption.textContent = '';
      renderedCaptionKey = null;
      state.captionBounds = [];
      state.captionFontSize = 64;
    }
    now.hidden = display.showNowPlaying !== true;
    now.textContent = display.showNowPlaying === true ? (track?.title || track?.name || track?.id || '') : '';
    queue.hidden = display.showQueue !== true;
    queue.textContent = '';
    if (display.showQueue === true) {
      const upcoming = tracks.filter(item => item.startSeconds > (track?.startSeconds ?? -Infinity));
      for (const item of upcoming.slice(0, 5)) { const li = document.createElement('li'); li.textContent = item.title || item.name || item.id; queue.append(li); }
      if (!upcoming.length) { const li = document.createElement('li'); li.textContent = '다음 곡 없음'; queue.append(li); }
      else if (upcoming.length > 5) { const li = document.createElement('li'); li.textContent = `+${upcoming.length - 5}`; queue.append(li); }
    }
    channel.hidden = !(typeof display.channelName === 'string' && display.channelName && display.channelName !== 'SKIP');
    channel.textContent = channel.hidden ? '' : display.channelName;
    spectrum.hidden = display.showSpectrum !== true;
    if (display.showSpectrum === true) {
      const values = spectrumAt(t); context.clearRect(0, 0, spectrum.width, spectrum.height);
      if (values.length) { const width = spectrum.width / values.length; context.fillStyle = 'rgba(255,255,255,.82)'; values.forEach((value, index) => { const height = Math.max(0, Math.min(spectrum.height, Number(value) / 255 * spectrum.height)); context.fillRect(index * width, spectrum.height - height, Math.max(1, width - 1), height); }); }
    }
    const opening = plan.opening;
    const suppress = Number(track?.source?.cutStartSeconds || 0) > 0;
    // 렌더러의 프레임 중심 sub-sample은 카드 경계에서 다음 target frame을 따라야 한다.
    const thumbnailTime = Math.round(t * input.fps) / input.fps;
    const showThumbnail = !!(opening && opening.thumbnailId && finite(opening.seconds) && opening.seconds > 0 && thumbnailTime >= 0 && thumbnailTime < opening.seconds && !suppress);
    thumbnail.hidden = !showThumbnail;
    if (showThumbnail && thumbnail.dataset.id !== opening.thumbnailId) {
      const image = images[opening.thumbnailId], raster = thumbnail.getContext('2d');
      const scale = Math.max(input.width / image.naturalWidth, input.height / image.naturalHeight);
      const width = input.width / scale, height = input.height / scale;
      raster.clearRect(0, 0, input.width, input.height); raster.imageSmoothingQuality = 'high';
      raster.drawImage(image, (image.naturalWidth - width) / 2, (image.naturalHeight - height) / 2, width, height, 0, 0, input.width, input.height);
      thumbnail.dataset.id = opening.thumbnailId;
    }
    state.thumbnailVisible = showThumbnail;
  }, { layer: 'top', setup(parent) {
    caption = document.createElement('div'); caption.className = 'film-caption'; parent.append(caption);
    spectrum = document.createElement('canvas'); spectrum.className = 'film-spectrum'; spectrum.width = 380; spectrum.height = 88; context = spectrum.getContext('2d', { alpha: true }); parent.append(spectrum);
    now = document.createElement('div'); now.className = 'film-now'; parent.append(now);
    queue = document.createElement('ol'); queue.className = 'film-queue'; parent.append(queue);
    channel = document.createElement('div'); channel.className = 'film-channel'; parent.append(channel);
    thumbnail = document.createElement('canvas'); thumbnail.className = 'film-thumbnail'; thumbnail.width = input.width; thumbnail.height = input.height; parent.append(thumbnail);
  } });
})();
