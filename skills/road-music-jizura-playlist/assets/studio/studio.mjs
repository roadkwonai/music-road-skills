const token = typeof location === 'undefined' ? '' : new URLSearchParams(location.search).get('token') || '';
const api = (path, options = {}) => fetch(`${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`, options);
const clone = value => value == null ? value : JSON.parse(JSON.stringify(value));
const $ = id => document.getElementById(id);
const fxLabels = { motion: '움직임', glitch: '글리치', chroma: '색수차', decor: '장식', density: '밀도', texture: '질감', bgSwitch: '배경 전환' };
const themeChoices = {
  '': ['테마 없음', '특정 테마로 제한하지 않고 재구성'],
  lyricpv: ['가사 영상', '글자 배치와 타이포그래피 중심'],
  kinetic: ['키네틱', '튀고 움직이는 글자와 기하학 연출'],
  wa: ['일본풍', '세로쓰기·먹·일본풍 장식 활용'],
  horror: ['호러', '깜박임·왜곡으로 긴장감 표현'],
  pop: ['팝', '밝고 경쾌한 움직임과 장식'],
  ballad: ['발라드', '차분한 움직임과 감성적인 여백'],
};
const choiceDescriptions = {
  moodSelect: { '': '분위기 필터 없이 현재 설정 사용', glitch: '깨짐·왜곡과 디지털 긴장감', calm: '잔잔한 흐름과 절제된 움직임', pop: '통통 튀는 경쾌한 리듬', graphic: '도형·선과 강한 화면 구성', editorial: '지면처럼 정돈된 글자 배치', emotional: '큰 글자와 잔상으로 감정 강조', horror: '불안한 깜박임과 어두운 긴장감', chaos: '다양한 기법을 폭넓게 혼합' },
  aspectSelect: { '16:9': '유튜브 가로 영상', '9:16': '쇼츠·릴스 세로 영상', '4:3': '클래식 화면 비율', '3:4': '짧은 세로 화면', '1:1': '정사각형 피드', '4:5': '세로형 피드', '21:9': '시네마 와이드 화면' },
  resSelect: { 720: '가벼운 미리보기·빠른 출력', 1080: '일반 유튜브용 선명한 출력', 1440: '더 세밀한 고해상도 출력', 2160: '4K 출력·렌더 부담 큼' },
  fpsSelect: { 24: '영화처럼 자연스러운 리듬', 30: '일반 영상의 부드러운 움직임', 60: '매끄러운 움직임·렌더 부담 증가' },
  keyBgSelect: { off: '현재 스타일의 배경 유지', green: '크로마키 합성용 녹색 배경', black: '합성용 흰 그래픽·검은 배경' },
};
const controlDescriptions = {
  styleSelect: '색·서체·질감과 선호 기법을 정하는 기본 화면 스타일입니다.',
  themeSelect: '자동 구성의 방향입니다. 선택 후 “선택한 방향으로 재구성”을 눌러 적용합니다.',
  moodSelect: '글자 배치와 움직임에 사용할 기법의 분위기를 고릅니다. 효과 강도는 아래에서 따로 조절합니다.',
  aspectSelect: '출력 영상의 가로와 세로 비율입니다. 게시할 화면에 맞춰 고르세요.',
  resSelect: '출력 화면의 크기입니다. 높일수록 세밀해지고 렌더 시간과 메모리 사용량이 늘어납니다.',
  fpsSelect: '1초당 출력 프레임 수입니다. 높일수록 움직임이 부드럽지만 처리량이 늘어납니다. 코마 연출은 별도로 유지됩니다.',
  'fx-motion': '높일수록 흔들림·줌 등 움직임의 강도와 발생 가능성이 커집니다.',
  'fx-glitch': '높일수록 화면 깨짐·잘림·디지털 왜곡 효과가 강해집니다.',
  'fx-chroma': '색 채널의 어긋남과 색 잔상 강도입니다. 낮추면 글자가 또렷해집니다.',
  'fx-decor': '선·도형·입자 등 장식의 양과 등장 가능성입니다.',
  'fx-density': '높일수록 가사를 더 짧은 컷으로 나누어 전개합니다. 무자막·고정 컷에서는 변화가 작을 수 있습니다.',
  'fx-texture': '입자·종이·스캔라인·빛 번짐 등 스타일 질감의 강도입니다.',
  'fx-bgSwitch': '컷 사이 배색·배경이 바뀔 가능성입니다. 높여도 일정 간격으로 전환되지는 않습니다.',
  audioToggle: 'MP4에 현재 연결한 원음을 함께 넣습니다.',
  centerToggle: '인물이나 다른 영상을 합성할 수 있도록 그래픽을 가장자리로 배치합니다.',
  keyBgSelect: '다른 영상 위에 합성하기 위한 배경입니다. 투명 배경 출력과는 별도입니다.',
  genreSearch: '장르 키워드로 추천 후보를 다시 찾습니다. 가사 의미를 자동 해석하는 기능은 아닙니다.',
  audioInput: '로컬 음원을 연결해 길이와 비트를 분석합니다. 다른 곡으로 바꾸면 기존 가사 싱크를 다시 확인하세요.',
  rebuildButton: '선택한 테마와 스타일로 세부 구성을 다시 만듭니다. 원문 가사·수동 시각·잠근 설정은 유지합니다.',
  saveButton: '현재 프로젝트와 업로드 글꼴을 새 버전으로 저장합니다. 원음 파일도 별도로 보관하세요.',
  exportButton: '전체 편집기의 현재 출력 설정으로 MP4 렌더를 시작합니다.',
  playButton: '현재 구성의 움직임을 재생하거나 일시정지합니다.',
  seekInput: '미리 볼 시점으로 이동합니다. 가사 시각이나 컷 길이는 바꾸지 않습니다.',
  rewindButton: '미리보기 재생 위치를 처음으로 돌립니다.',
};

export function choiceDetails(id, value, label, J) {
  if (id === 'themeSelect') return themeChoices[value] || [label, '자동 구성에 사용할 테마'];
  return [label, id === 'styleSelect' ? J.STYLES[value]?.desc || '배색·서체·기법의 기본 스타일' : choiceDescriptions[id]?.[value] || '현재 설정에 적용'];
}

function addControlHelp(control, text) {
  control.title = text;
  const label = control.labels?.[0];
  if (!label) return;
  const row = document.createElement('div'); row.className = 'control-label';
  label.replaceWith(row); row.append(label);
  const button = document.createElement('button'), tip = document.createElement('span');
  button.type = 'button'; button.className = 'help-button'; button.textContent = '?';
  button.setAttribute('aria-label', `${(label.querySelector('span')?.textContent || label.textContent).trim()} 도움말`);
  tip.id = `help-${control.id}`; tip.className = 'help-tooltip'; tip.popover = 'auto'; tip.role = 'tooltip'; tip.textContent = text;
  button.setAttribute('aria-describedby', tip.id); control.setAttribute('aria-describedby', tip.id);
  const open = () => {
    tip.showPopover();
    const rect = button.getBoundingClientRect(), width = tip.offsetWidth, height = tip.offsetHeight;
    tip.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - width - 8))}px`;
    tip.style.top = `${rect.bottom + height + 8 <= innerHeight ? rect.bottom + 6 : Math.max(8, rect.top - height - 6)}px`;
  };
  const close = event => { if (!row.contains(event.relatedTarget) && document.activeElement !== button) tip.hidePopover(); };
  button.addEventListener('mouseenter', open); button.addEventListener('focus', open); button.addEventListener('click', open);
  row.addEventListener('mouseleave', close); row.addEventListener('focusout', close);
  row.append(button, tip);
}

function addSettingsHelp() {
  const J = native();
  for (const select of document.querySelectorAll('select')) {
    for (const option of select.options) {
      const value = option.value, [name, description] = choiceDetails(select.id, value, option.textContent, J);
      option.value = value; option.textContent = `${name} — ${description}`; option.title = description;
    }
  }
  for (const [id, text] of Object.entries(controlDescriptions)) addControlHelp($(id), text);
  for (const option of $('engineFrame').contentDocument.querySelectorAll('.themeSel option')) {
    const [name, description] = choiceDetails('themeSelect', option.value, option.textContent, J);
    option.textContent = `${name} — ${description}`; option.title = description;
  }
}

export function rankProfiles(profiles = [], direction = {}, query = '', audio = null) {
  const words = `${query} ${(direction && (direction.genre || direction.genres || direction.style || direction.profile || '')) || ''}`.toLowerCase().split(/[\s,/]+/).filter(Boolean);
  const preferred = direction && (direction.profile || direction.profileId || direction.recommendedProfile);
  const energy = audio && audio.energy || [];
  const mean = energy.length ? energy.reduce((sum, value) => sum + value, 0) / energy.length : 0;
  const deviation = energy.length ? Math.sqrt(energy.reduce((sum, value) => sum + (value - mean) ** 2, 0) / energy.length) : 0;
  const motion = audio && Number.isFinite(audio.bpm) ? Math.max(.25, Math.min(.95, .3 + .5 * (audio.bpm - 70) / 110 + Math.min(.15, deviation * .6))) : null;
  return profiles.map((profile, index) => {
    const genres = (profile.genres || []).join(' ').toLowerCase();
    const rhythmScore = motion == null ? 0 : 5 * (1 - Math.abs((profile.fx?.motion ?? .5) - motion));
    const score = (profile.id === preferred ? 100 : 0) + rhythmScore + words.reduce((n, word) => n + (genres.includes(word) ? 9 : profile.name.toLowerCase().includes(word) ? 3 : 0), 0);
    return { profile, score, index };
  }).sort((a, b) => b.score - a.score || a.index - b.index).slice(0, 3).map(item => item.profile);
}

export function preserveRecommendationState(project = {}) {
  const overrides = clone(project.overrides || {});
  const locks = clone(project.locks || { tech: {}, params: {} });
  const enabled = {};
  for (const group of Object.keys((locks && locks.tech) || {})) if (locks.tech[group] && project.enabled && project.enabled[group]) enabled[group] = clone(project.enabled[group]);
  const fx = {};
  for (const key of Object.keys((locks && locks.params) || {})) if (locks.params[key] && project.fx && project.fx[key] != null) fx[key] = project.fx[key];
  return { overrides, locks, enabled, fx, lyrics: project.lyrics, timing: clone(project.timing) };
}

export function restoreRecommendationState(project, saved) {
  project.overrides = saved.overrides;
  project.locks = saved.locks;
  project.lyrics = saved.lyrics;
  project.timing = saved.timing;
  project.enabled = project.enabled || {};
  Object.assign(project.enabled, saved.enabled);
  project.fx = project.fx || {};
  Object.assign(project.fx, saved.fx);
  return project;
}
export function canBakeDirecting(score, source, audio) {
  return !!(score && source && audio && typeof source.sha256 === 'string' && typeof audio.sha256 === 'string' && source.sha256.toLowerCase() === audio.sha256.toLowerCase());
}
export function needsTimingReview(previousAudio, nextAudio) { return !!(previousAudio && nextAudio && previousAudio.sha256 && nextAudio.sha256 && previousAudio.sha256 !== nextAudio.sha256); }

const state = { config: null, profiles: [], direction: null, audio: null, sourceExtra: {}, initial: null, J: null, ready: false, selectedProfile: null, playRaf: 0, staticRenderer: null, unreviewed: false, timingReviewNeeded: false, busy: false, suppressNativeImport: false, hasUserContent: false, clock: null, clockStartedAt: 0, clockStartTime: 0 };
const DRAFT_SCHEMA_VERSION = 1;
const MAX_DRAFT_BYTES = 1024 * 1024;

function status(message, error = false) { const el = $('toast'); el.textContent = message; el.hidden = false; el.style.background = error ? '#8c3535' : '#17222d'; clearTimeout(status.timer); status.timer = setTimeout(() => { el.hidden = true; }, 3600); }
function fmt(seconds = 0) { const n = Math.max(0, Math.floor(seconds)); return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`; }
function native() { if (!state.J || !state.J.ui) throw new Error('공식 JIZURA 편집기가 아직 준비되지 않았습니다'); return state.J; }
function nativeProject() { return native().ui.project; }
function replan() { const J = native(); J.uiApi.syncUI(); J.uiApi.replan(); drawPreview(); reflect(); }
function isSame(a, b) { return JSON.stringify(a || {}) === JSON.stringify(b || {}); }
function isRecord(value) { return !!value && typeof value === 'object' && !Array.isArray(value); }
function audioSha(audio) { return audio && typeof audio.sha256 === 'string' && /^[0-9a-f]{64}$/i.test(audio.sha256) ? audio.sha256.toLowerCase() : null; }
export async function validateAudioFile(file, createDecoder = () => new OfflineAudioContext(1, 1, 44100)) {
  let decoder;
  try {
    if (!file || typeof file.arrayBuffer !== 'function') throw new Error('파일이 필요합니다');
    decoder = createDecoder();
    const decoded = await decoder.decodeAudioData(await file.arrayBuffer());
    if (!decoded || !Number.isFinite(decoded.duration) || decoded.duration <= 0) throw new Error('길이가 없는 음원입니다');
    return decoded.duration;
  } catch (_) {
    throw new Error('이 음원은 브라우저에서 디코드할 수 없습니다. 원본 파일을 확인해 주세요.');
  } finally {
    try { await decoder?.close?.(); } catch (_) {}
  }
}
export function studioDraft(project, sourceExtra, direction, selectedProfile, timingReviewNeeded, audio) {
  if (!isRecord(project) || !isRecord(sourceExtra) || (direction !== null && !isRecord(direction)) || (selectedProfile !== null && typeof selectedProfile !== 'string')) return null;
  const value = { schemaVersion: DRAFT_SCHEMA_VERSION, audioSha: audioSha(audio), project: clone(project), sourceExtra: clone(sourceExtra), direction: clone(direction), selectedProfile, timingReviewNeeded: !!timingReviewNeeded };
  try { return JSON.stringify(value).length <= MAX_DRAFT_BYTES ? value : null; } catch (_) { return null; }
}
export function restoreStudioDraft(value, audio) {
  if (!isRecord(value) || value.schemaVersion !== DRAFT_SCHEMA_VERSION || value.audioSha !== audioSha(audio) || !isRecord(value.project) || !isRecord(value.sourceExtra) || (value.direction !== null && !isRecord(value.direction)) || (value.selectedProfile !== null && typeof value.selectedProfile !== 'string') || typeof value.timingReviewNeeded !== 'boolean') return null;
  return { project: clone(value.project), sourceExtra: clone(value.sourceExtra), direction: clone(value.direction), selectedProfile: value.selectedProfile, timingReviewNeeded: value.timingReviewNeeded };
}
function draftKey() { return `road-music-jizura-draft:${token}`; }
function rememberDraft() {
  if (!state.ready) return true;
  const value = studioDraft(nativeProject(), state.sourceExtra, state.direction, state.selectedProfile, state.timingReviewNeeded || state.unreviewed, state.audio);
  try {
    if (!value) { sessionStorage.removeItem(draftKey()); return false; }
    sessionStorage.setItem(draftKey(), JSON.stringify(value));
    return true;
  } catch (_) { return false; }
}
function savedDraft() {
  try {
    const raw = sessionStorage.getItem(draftKey());
    if (!raw || raw.length > MAX_DRAFT_BYTES) return null;
    const value = restoreStudioDraft(JSON.parse(raw), state.audio);
    if (!value) sessionStorage.removeItem(draftKey());
    return value;
  } catch (_) { return null; }
}
function setBusy(on) { state.busy = on; ['saveButton', 'exportButton', 'audioInput'].forEach(id => { $(id).disabled = on; }); }
async function waitUntil(check, message, timeout = 10000) { const started = Date.now(); while (Date.now() - started < timeout) { if (check()) return; await new Promise(resolve => setTimeout(resolve, 80)); } throw new Error(message); }
function setClock(audio) { if (!audio || !audio.url) return; if (state.clock) state.clock.pause(); state.clock = new Audio(audio.url); state.clock.muted = true; state.clock.preload = 'auto'; state.clock.addEventListener('ended', () => { if (state.J && state.J.ui.playing) state.J.uiApi.pause(); }); }
function clockTime() { if (state.clock && !state.clock.paused && Number.isFinite(state.clock.currentTime)) return state.clock.currentTime; return state.clockStartTime + (performance.now() - state.clockStartedAt) / 1000; }
function sourceBaseline() { return state.audio || state.sourceExtra.source || (state.J && nativeProject().source) || null; }
function tokenizedFetch(url) { return api(String(url).replace(/[?&]token=[^&]+/, '')); }

async function waitForEngine(frame) {
  const started = Date.now();
  while (Date.now() - started < 12000) {
    try { if (frame.contentWindow && frame.contentWindow.J && frame.contentWindow.J.ui && frame.contentWindow.J.uiApi) return frame.contentWindow.J; } catch (_) {}
    await new Promise(resolve => setTimeout(resolve, 120));
  }
  throw new Error('공식 JIZURA 편집기를 시작하지 못했습니다');
}

function fileIntoInput(input, file) { const dt = new DataTransfer(); dt.items.add(file); input.files = dt.files; input.dispatchEvent(new Event('change', { bubbles: true })); }
async function importProject(raw) {
  if (!raw) return;
  state.hasUserContent = true;
  const project = raw.project && typeof raw.project === 'object' ? raw.project : raw;
  const extras = Object.assign({}, project, raw);
  state.sourceExtra = clone(extras); delete state.sourceExtra.project;
  const file = new File([JSON.stringify(project)], 'studio-source.jizura.json', { type: 'application/json' });
  const before = nativeProject(); state.suppressNativeImport = true;
  fileIntoInput($('engineFrame').contentDocument.getElementById('fileProject'), file);
  try { await waitUntil(() => nativeProject() !== before, '프로젝트를 불러오지 못했습니다'); await restoreSavedFonts(raw); } finally { state.suppressNativeImport = false; }
}
async function restoreSavedFonts(raw) {
  const J = native(), fonts = state.config && state.config.fonts || raw && raw.fontAssets || [];
  for (const font of fonts) {
    if (!font || !font.key || !font.url) continue;
    const response = await tokenizedFetch(font.url); if (!response.ok) continue;
    const saved = await J.saveFontData(font.key, await response.arrayBuffer());
    if (!saved) throw new Error('사용자 글꼴을 이 브라우저에 저장하지 못했습니다');
  }
  const missing = await J.restoreUserFonts(nativeProject().userFonts || []);
  if (missing.length) status(`글꼴 원본을 다시 불러오세요: ${missing.join(', ')}. 다른 프로젝트는 새 스튜디오로 열면 보관한 글꼴도 복원됩니다.`, true);
}
async function importAudio(audio) {
  if (!audio || !audio.url) return;
  const response = await tokenizedFetch(audio.url);
  if (!response.ok) throw new Error('현재 음원을 읽지 못했습니다');
  const blob = await response.blob();
  const file = new File([blob], audio.name || 'audio', { type: blob.type || 'audio/mpeg' });
  const J = native();
  const before = J.ui.audio;
  const timing = clone(J.ui.project.timing);
  await J.uiApi.loadAudioFile(file);
  await waitUntil(() => J.ui.audio && J.ui.audio !== before && J.ui.project.audioName === file.name, 'JIZURA가 음원을 분석하지 못했습니다', 20000);
  J.ui.project.timing = timing;
  J.uiApi.replan();
  state.audio = audio;
  setClock(audio);
  state.sourceExtra.source = Object.assign({}, state.sourceExtra.source || {}, { sha256: audio.sha256, path: audio.path });
}

function profileById(id) { return state.profiles.find(profile => profile.id === id) || null; }
function configureInstrumentalDefault() {
  if (state.hasUserContent && nativeProject().lyrics.trim()) return;
  const J = native(), P = nativeProject(), duration = (J.ui.audio && J.ui.audio.duration) || 4;
  const profile = profileById(state.selectedProfile) || rankProfiles(state.profiles, {}, '', J.ui.audio)[0];
  if (profile) state.selectedProfile = profile.id;
  P.title = ''; P.artist = ''; P.extra = true; P.wa = false; P.unify = true; P.typeset = false;
  P.timing = Object.assign({}, P.timing, { offset: 0, tail: 0, snap: false, useAudioLength: false });
  if (profile) { P.style = profile.style; P.mood = profile.mood; P.fx = Object.assign({}, P.fx, profile.fx || {}); }
  Object.assign(P.fx, { flash: false, hideNo: true, hideTime: true, hud: 'off' });
  const bounds = [0, ...(J.ui.audio?.beats || []).filter((t, i) => i % 8 === 0 && t >= .35 && t < duration - .35).map(t => Math.round(t * 1000) / 1000), duration];
  const stamp = t => `${String(Math.floor(t / 60)).padStart(2, '0')}:${(t % 60).toFixed(3).padStart(6, '0')}`;
  P.lyrics = bounds.slice(0, -1).map((start, i) => `[${stamp(start)}][간주 ${(bounds[i + 1] - start).toFixed(6)}초]`).join('\n');
  P.overrides = Object.fromEntries(bounds.slice(0, -1).map((_, i) => [i, { bg: profile?.interlude?.backgrounds?.[i % profile.interlude.backgrounds.length] || 'concentric', decor: profile?.interlude?.decor || ['beatRing'] }]));
}
async function bakeDirecting(raw) {
  const score = nativeProject().directing || (raw && raw.directing);
  if (!score) return;
  const source = state.sourceExtra.source || nativeProject().source || {};
  if (!canBakeDirecting(score, source, state.audio) || !native().ui.audio) { status('연출 스코어는 같은 원음이 연결된 뒤 적용할 수 있습니다.', true); return; }
  setBusy(true);
  try {
    const { browserBakeExpression } = await import(`/directing.mjs?token=${encodeURIComponent(token)}`);
    const doc = $('engineFrame').contentDocument, marker = '__roadMusicBakeResult';
    delete $('engineFrame').contentWindow[marker];
    const script = doc.createElement('script');
    script.textContent = `try { window.${marker} = ${browserBakeExpression(score, source.sha256, native().ui.audio.duration)}; } catch (error) { window.${marker} = { ok: false, error: String(error && error.message || error) }; }`;
    doc.head.append(script); script.remove();
    const result = $('engineFrame').contentWindow[marker];
    if (!result || !result.ok) throw new Error((result && result.error) || '연출 스코어를 고정하지 못했습니다');
    state.sourceExtra.directingProvenance = clone(nativeProject().directingProvenance || score);
    delete state.sourceExtra.directing; delete nativeProject().directing;
    replan(); status('비트 연출 스코어를 현재 컷에 고정했습니다.');
  } finally { setBusy(false); }
}
function directionText() {
  const d = state.direction || {};
  const bits = [d.genre || (Array.isArray(d.genres) ? d.genres.join(' · ') : ''), d.mood || d.summary || d.idea].filter(Boolean);
  return bits.length ? bits.join(' — ') : '분석된 장르·가사·리듬 정보를 바탕으로 추천 후보를 고릅니다.';
}
function populateCards(query = '') {
  const cards = $('profileCards'); cards.replaceChildren();
  const directed = !query && Array.isArray(state.direction && state.direction.recommendations) ? state.direction.recommendations : [];
  const audio = state.J && state.J.ui.audio;
  const entries = directed.map(item => ({ profile: profileById(item.profile), reason: item.reason, themeId: item.themeId })).filter(item => item.profile);
  entries.push(...rankProfiles(state.profiles, query ? {} : state.direction || {}, query, audio).map(profile => ({ profile, reason: profile.idea + (audio && !query ? ` · 추정 ${audio.bpm} BPM의 움직임 속도를 기준으로 제안` : '') })));
  const profiles = entries.filter((item, index, list) => list.findIndex(other => other.profile.style === item.profile.style) === index).slice(0, 3);
  $('recommendationSource').textContent = state.direction && (state.direction.profile || state.direction.profileId) ? '곡 해석 우선' : query ? '장르 보조 추천' : audio ? '리듬 보조 추천' : '기본 추천';
  $('recommendationHint').textContent = directed.length ? '곡의 해석을 바탕으로 세 방향을 비교합니다. 고른 뒤에도 모든 설정을 바꿀 수 있습니다.' : audio ? '추정 박자와 음량 변화로 모션 속도를 제안합니다. 장르 입력이나 Codex의 가사 해석을 더해 구체화할 수 있습니다.' : '음악을 추가하면 리듬에 맞는 세 방향을 제안합니다. 장르로 먼저 살펴볼 수도 있습니다.';
  for (const { profile, reason, themeId } of profiles) {
    const button = document.createElement('button'); button.type = 'button'; button.className = `profile-card${state.selectedProfile === profile.id ? ' selected' : ''}`;
    button.innerHTML = '<i class="bar"></i><span><strong></strong><small></small></span><b>미리보기 적용 →</b>';
    button.setAttribute('aria-pressed', String(state.selectedProfile === profile.id));
    button.querySelector('strong').textContent = profile.name;
    button.querySelector('small').textContent = reason || profile.idea || profile.genres.join(' · ');
    button.addEventListener('click', () => { state.selectedProfile = profile.id; if (themeId) nativeProject().themeId = themeId; applyProfile(profile); populateCards($('genreSearch').value); }); cards.append(button);
  }
}
function populateNativeChoices() {
  const J = native();
  $('styleSelect').replaceChildren(...J.STYLE_ORDER.map(key => new Option((J.STYLES[key] && J.STYLES[key].name) || key, key)));
  $('moodSelect').replaceChildren(new Option('자동', ''), ...Object.entries(J.MOODS || {}).map(([key, value]) => new Option(value.name || key, key)));
  $('themeSelect').replaceChildren(new Option('테마 없음', ''), ...Object.entries(J.THEMES || {}).map(([key, value]) => new Option(value.name || key, key)));
  const fx = $('fxControls'); fx.replaceChildren();
  for (const [key, label] of Object.entries(fxLabels)) {
    const wrap = document.createElement('div'); wrap.className = 'fx-control';
    const input = document.createElement('input'); input.type = 'range'; input.min = '0'; input.max = '1'; input.step = '.01'; input.dataset.fx = key;
    const output = document.createElement('output'); output.htmlFor = `fx-${key}`;
    const title = document.createElement('label'); title.textContent = label; title.htmlFor = input.id = `fx-${key}`;
    input.addEventListener('input', () => { nativeProject().fx[key] = Number(input.value); output.value = `${Math.round(Number(input.value) * 100)}%`; replan(); });
    wrap.append(title, output, input); fx.append(wrap);
  }
}
function reflect() {
  if (!state.ready) return;
  const J = native(), P = J.ui.project, plan = J.ui.plan || {};
  $('styleSelect').value = P.style || 'noir'; $('moodSelect').value = P.mood || ''; $('themeSelect').value = P.themeId || '';
  $('aspectSelect').value = P.aspect || '16:9'; $('resSelect').value = String(P.res || 1080); $('fpsSelect').value = String(P.fps || 24);
  $('audioToggle').checked = P.includeAudio !== false; $('centerToggle').checked = !!P.centerFree; $('keyBgSelect').value = P.keyBg || 'off';
  document.querySelectorAll('[data-fx]').forEach(input => { const value = Number(P.fx && P.fx[input.dataset.fx]); input.value = Number.isFinite(value) ? value : 0; input.previousElementSibling.value = `${Math.round(Number(input.value) * 100)}%`; });
  const duration = plan.duration || (J.ui.audio && J.ui.audio.duration) || 0, time = Math.min(J.ui.t || 0, duration);
  $('seekInput').value = duration ? Math.round(time / duration * 1000) : 0; $('timeOutput').value = `${fmt(time)} / ${fmt(duration)}`;
  $('previewDetail').textContent = `${(J.STYLES[P.style] || {}).name || P.style} · ${(P.mood && J.MOODS[P.mood] && J.MOODS[P.mood].name) || '사용자 설정'} · 컷 ${(plan.cuts || []).length}개`;
  state.unreviewed = state.timingReviewNeeded || (!!state.initial && (P.lyrics !== state.initial.lyrics || !isSame(P.timing, state.initial.timing)));
  $('projectStatus').textContent = `${P.title || state.audio?.name || '새 프로젝트'}${state.unreviewed ? ' · 가사/시각 변경 검수 필요' : ' · 현재 설정'}`;
}
function drawPreview() {
  if (!state.ready) return;
  const J = native(), plan = J.ui.plan; if (!plan) return;
  const canvas = $('preview'), ctx = canvas.getContext('2d');
  const width = canvas.clientWidth || 960, ratio = plan.W && plan.H ? plan.H / plan.W : 9 / 16;
  canvas.style.aspectRatio = `${plan.W} / ${plan.H}`;
  canvas.width = Math.max(2, Math.round(width * devicePixelRatio)); canvas.height = Math.max(2, Math.round(width * ratio * devicePixelRatio));
  const scale = canvas.width / plan.W; ctx.setTransform(1, 0, 0, 1, 0, 0);
  try { (state.staticRenderer || (state.staticRenderer = new J.Renderer())).frame(ctx, plan, J.ui.t || 0, { scale, fast: false }); } catch (error) { ctx.fillStyle = '#17222d'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = '#fff'; ctx.font = '16px sans-serif'; ctx.fillText('미리보기를 다시 준비하는 중입니다.', 24, 34); }
}
function runPlaybackLoop() {
  cancelAnimationFrame(state.playRaf);
  const tick = () => { const J = native(); if (J.ui.playing) J.ui.t = Math.min(clockTime(), J.ui.plan.duration || Infinity); drawPreview(); reflect(); if (J.ui.playing) state.playRaf = requestAnimationFrame(tick); };
  state.playRaf = requestAnimationFrame(tick);
}

function applyProfile(profile) {
  const J = native(), P = nativeProject(), keep = preserveRecommendationState(P);
  const theme = P.themeId && J.THEMES[P.themeId] ? P.themeId : null;
  const made = J.omakase(P, Math.random, theme);
  Object.assign(P, made, { style: profile.style, mood: profile.mood, fx: Object.assign({}, made.fx, profile.fx || {}) });
  restoreRecommendationState(P, keep);
  if (!state.hasUserContent) for (const line of J.ui.plan.lines.filter(line => line.interlude)) P.overrides[line.index] = { bg: profile.interlude.backgrounds[line.index % profile.interlude.backgrounds.length], decor: clone(profile.interlude.decor) };
  replan(); status(`${profile.name} 방향을 실제 JIZURA 구성에 적용했습니다.`);
}
function rebuild() {
  const profile = profileById(state.selectedProfile);
  if (profile) return applyProfile(profile);
  const J = native(), P = nativeProject(), keep = preserveRecommendationState(P), theme = P.themeId && J.THEMES[P.themeId] ? P.themeId : null, made = J.omakase(P, Math.random, theme);
  Object.assign(P, made); P.style = $('styleSelect').value; P.mood = $('moodSelect').value || null;
  restoreRecommendationState(P, keep); replan(); status('선택한 스타일과 테마로 다시 구성했습니다.');
}

async function saveFontAssets(project, J) {
  const known = new Map((project.fontAssets || []).filter(asset => asset && asset.key).map(asset => [asset.key, asset]));
  for (const font of project.userFonts || []) {
    const buffer = await J.loadFontData(font.key); if (!buffer) continue;
    const name = font.name || (known.get(font.key) && known.get(font.key).name) || `${font.label || font.key}.ttf`;
    const response = await api('/api/import-font', { method: 'POST', headers: { 'content-type': 'application/octet-stream', 'X-Font-Key': font.key, 'X-File-Name': encodeURIComponent(name) }, body: buffer });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok || !result.font) throw new Error(result.error || `글꼴 ${font.label || font.key}을 저장하지 못했습니다`);
    known.set(font.key, result.font);
  }
  project.fontAssets = [...known.values()];
}
async function save() {
  setBusy(true);
  try {
    const J = native(), P = Object.assign(clone(state.sourceExtra), clone(J.ui.project));
    if (state.audio && !J.ui.audio) throw new Error('현재 음원을 읽지 못했습니다. 음원을 다시 연결한 뒤 저장하세요.');
    if (state.audio) {
      const source = Object.assign({}, state.sourceExtra.source || {}, { sha256: state.audio.sha256, path: state.audio.path });
      if (J.ui.audio && Number.isFinite(J.ui.audio.duration)) source.duration = J.ui.audio.duration;
      state.sourceExtra.source = source;
      P.source = clone(source);
    }
    await saveFontAssets(P, J);
    state.timingReviewNeeded ||= state.unreviewed;
    const audioInfo = state.audio ? { name: state.audio.name, path: state.audio.path, sha256: state.audio.sha256, size: state.audio.size } : null;
    const studio = { schemaVersion: 1, selectedProfile: state.selectedProfile, audio: audioInfo, unreviewedLyricsOrTiming: state.unreviewed, timingReviewNeeded: state.timingReviewNeeded, savedAt: new Date().toISOString() };
    P.studio = clone(studio);
    const response = await api('/api/save', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ project: P, direction: state.direction || null, plan: clone(J.ui.plan), studio }) });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok) throw new Error(result.error || '설정 저장에 실패했습니다');
    state.sourceExtra.fontAssets = clone(P.fontAssets); state.sourceExtra.studio = clone(studio); state.initial = { lyrics: J.ui.project.lyrics, timing: clone(J.ui.project.timing) }; reflect(); status('설정을 새 버전으로 저장했습니다.');
  } finally { setBusy(false); }
}
async function uploadAudio(file) {
  if (!file) return;
  setBusy(true); $('projectStatus').textContent = '새 음원을 디코드하는 중…';
  try {
    await validateAudioFile(file);
    $('projectStatus').textContent = '새 음원을 복사하고 분석하는 중…';
    const response = await api('/api/import-audio', { method: 'POST', headers: { 'content-type': 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name) }, body: file });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok || !result.audio) throw new Error(result.error || '음원을 가져오지 못했습니다');
    const oldAudio = sourceBaseline();
    await importAudio(result.audio);
    state.timingReviewNeeded ||= needsTimingReview(oldAudio, result.audio); state.direction = null; state.selectedProfile = null;
    $('analysisText').textContent = '새 음원은 리듬 분석 기반 보조 방향으로 제안합니다. 장르와 가사 설명을 더하면 연출 근거가 선명해집니다.';
    configureInstrumentalDefault(); state.initial = { lyrics: nativeProject().lyrics, timing: clone(nativeProject().timing) }; replan(); populateCards(); status(`${file.name}을 연결했습니다.`);
  } finally { setBusy(false); if (state.ready) reflect(); }
}
const tabOrder = ['quick', 'editor', 'help'];
const tabNames = new Set(tabOrder);
export function tabForKey(current, key) {
  const index = tabOrder.indexOf(current);
  if (index < 0) return null;
  if (key === 'Home') return tabOrder[0];
  if (key === 'End') return tabOrder.at(-1);
  if (key === 'ArrowRight') return tabOrder[(index + 1) % tabOrder.length];
  if (key === 'ArrowLeft') return tabOrder[(index - 1 + tabOrder.length) % tabOrder.length];
  return null;
}
function switchTab(name, scroll = false) {
  if (!tabNames.has(name)) return;
  document.querySelectorAll('.tab').forEach(tab => {
    const selected = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(selected));
    tab.setAttribute('aria-pressed', String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== name; });
  if (name === 'quick') { reflect(); drawPreview(); }
  if (scroll) requestAnimationFrame(() => $(name).scrollIntoView({ block: 'start' }));
}
function switchTabFromHash(scroll = true) {
  const name = location.hash.slice(1);
  if (tabNames.has(name)) switchTab(name, scroll);
}
function openTab(name) {
  if (!tabNames.has(name)) return;
  if (location.hash === `#${name}`) switchTab(name, true);
  else location.hash = name;
}
async function syncNativeAudio(file, beforeAudio, timing) {
  if (!file || state.suppressNativeImport) return;
  setBusy(true);
  try {
    const J = native(), before = beforeAudio || J.ui.audio;
    await waitUntil(() => J.ui.audio && J.ui.audio !== before && J.ui.project.audioName === file.name, '공식 편집기가 음원을 불러오지 못했습니다', 20000);
    J.ui.project.timing = timing;
    J.uiApi.replan();
    const response = await api('/api/import-audio', { method: 'POST', headers: { 'content-type': 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name) }, body: file });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok || !result.audio) throw new Error(result.error || '현재 음원을 보관하지 못했습니다');
    state.timingReviewNeeded ||= needsTimingReview(sourceBaseline(), result.audio); state.audio = result.audio;
    setClock(result.audio);
    state.direction = null; state.selectedProfile = null;
    $('analysisText').textContent = '새 음원은 리듬 분석 기반 보조 방향으로 제안합니다. 장르와 가사 설명을 더하면 연출 근거가 선명해집니다.';
    state.sourceExtra.source = Object.assign({}, state.sourceExtra.source || {}, { sha256: result.audio.sha256, path: result.audio.path, duration: J.ui.audio.duration });
    configureInstrumentalDefault();
    replan(); populateCards(); status(`${file.name}을 현재 원음으로 연결했습니다.`);
  } finally { setBusy(false); }
}
async function syncNativeProject(file, before) {
  if (!file || state.suppressNativeImport) return;
  try {
    const raw = JSON.parse(await file.text());
    state.hasUserContent = true;
    state.timingReviewNeeded = !!(raw.studio?.timingReviewNeeded || raw.studio?.unreviewedLyricsOrTiming);
    await waitUntil(() => nativeProject() !== before, '공식 편집기가 프로젝트를 불러오지 못했습니다');
    state.sourceExtra = clone(raw); delete state.sourceExtra.project;
    await restoreSavedFonts(raw);
    const source = raw.source || nativeProject().source;
    const sourceMatches = !source || !state.audio || (typeof source.sha256 === 'string' && source.sha256.toLowerCase() === state.audio.sha256.toLowerCase());
    if (!sourceMatches) { state.timingReviewNeeded = true; status('열어 둔 프로젝트의 원음 해시가 현재 음원과 다릅니다.', true); }
    else await bakeDirecting(raw).catch(error => status(error.message, true));
    state.initial = { lyrics: nativeProject().lyrics, timing: clone(nativeProject().timing) }; reflect(); populateCards($('genreSearch').value);
  } catch (error) { status(error.message, true); }
}
function watchNativeImports() {
  const doc = $('engineFrame').contentDocument, J = native();
  doc.getElementById('lyrics').addEventListener('input', () => { state.hasUserContent = true; });
  doc.getElementById('fileLrc').addEventListener('change', () => { state.hasUserContent = true; }, true);
  doc.getElementById('audioFile').addEventListener('change', event => { const file = event.target.files && event.target.files[0]; const before = J.ui.audio, timing = clone(J.ui.project.timing); queueMicrotask(() => syncNativeAudio(file, before, timing).catch(error => status(error.message, true))); }, true);
  doc.getElementById('fileProject').addEventListener('change', event => { const file = event.target.files && event.target.files[0]; const before = J.ui.project; queueMicrotask(() => syncNativeProject(file, before)); }, true);
  doc.getElementById('fontFile').addEventListener('change', event => {
    const file = event.target.files && event.target.files[0]; if (!file) return;
    const key = `user_UF_${file.name.replace(/\.[^.]+$/, '').replace(/[^\w]/g, '_').slice(0, 60)}`;
    setBusy(true); queueMicrotask(() => waitUntil(() => J.FONTS[key] && J.FONTS[key].loaded && (J.ui.project.userFonts || []).some(font => font.key === key), '글꼴을 불러오지 못했습니다').then(() => { const font = J.ui.project.userFonts.find(item => item.key === key); if (font) font.name = file.name; }).catch(error => status(error.message, true)).finally(() => setBusy(false)));
  }, true);
}
function bind() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => openTab(tab.dataset.tab));
    tab.addEventListener('keydown', event => {
      const name = tabForKey(tab.dataset.tab, event.key);
      if (!name) return;
      event.preventDefault();
      document.getElementById(`tab-${name}`).focus();
      openTab(name);
    });
  });
  document.querySelectorAll('[data-road-music-nav] a[href^="#"]').forEach(link => link.addEventListener('click', event => {
    const name = link.getAttribute('href').slice(1);
    if (!tabNames.has(name)) return;
    event.preventDefault(); openTab(name);
  }));
  document.querySelectorAll('[data-road-music-nav] a:not([href^="#"])').forEach(link => link.addEventListener('click', event => {
    if (rememberDraft()) return;
    event.preventDefault();
    status('임시 설정을 보관하지 못했습니다. 설정을 저장한 뒤 페이지를 이동해 주세요.', true);
  }));
  window.addEventListener('hashchange', () => switchTabFromHash());
  window.addEventListener('pagehide', rememberDraft);
  $('genreSearch').addEventListener('input', event => populateCards(event.target.value));
  $('styleSelect').addEventListener('change', event => { state.selectedProfile = null; nativeProject().style = event.target.value; nativeProject().mood = null; replan(); populateCards($('genreSearch').value); });
  $('themeSelect').addEventListener('change', event => { nativeProject().themeId = event.target.value || null; replan(); status('테마를 골랐습니다. 재구성을 눌러 적용하세요.'); });
  $('moodSelect').addEventListener('change', event => { nativeProject().mood = event.target.value || null; replan(); });
  [['aspectSelect', 'aspect', String], ['resSelect', 'res', Number], ['fpsSelect', 'fps', Number]].forEach(([id, key, cast]) => $(id).addEventListener('change', event => { nativeProject()[key] = cast(event.target.value); replan(); }));
  $('audioToggle').addEventListener('change', event => { nativeProject().includeAudio = event.target.checked; replan(); });
  $('centerToggle').addEventListener('change', event => { nativeProject().centerFree = event.target.checked; replan(); });
  $('keyBgSelect').addEventListener('change', event => { nativeProject().keyBg = event.target.value; replan(); });
  $('rebuildButton').addEventListener('click', rebuild); $('saveButton').addEventListener('click', () => save().catch(error => status(error.message, true)));
  $('exportButton').addEventListener('click', () => { if (state.audio && !native().ui.audio && nativeProject().includeAudio !== false) { status('음원을 다시 연결한 뒤 MP4를 만들어 주세요.', true); return; } $('engineFrame').contentDocument.getElementById('btnMP4').click(); openTab('editor'); });
  $('audioInput').addEventListener('change', event => uploadAudio(event.target.files && event.target.files[0]).catch(error => status(error.message, true)));
  $('playButton').addEventListener('click', () => { const J = native(), wasPlaying = J.ui.playing; $('engineFrame').contentDocument.getElementById('btnPlay').click(); if (wasPlaying) state.clock?.pause(); else { state.clockStartTime = J.ui.t || 0; state.clockStartedAt = performance.now(); if (state.clock) { state.clock.currentTime = state.clockStartTime; state.clock.play().catch(() => {}); } } runPlaybackLoop(); });
  $('rewindButton').addEventListener('click', () => { native().uiApi.seek(0); if (state.clock) state.clock.currentTime = 0; state.clockStartTime = 0; state.clockStartedAt = performance.now(); drawPreview(); reflect(); });
  $('seekInput').addEventListener('input', event => { const duration = native().ui.plan.duration || 0, time = duration * Number(event.target.value) / 1000; native().uiApi.seek(time); if (state.clock) state.clock.currentTime = time; state.clockStartTime = time; state.clockStartedAt = performance.now(); drawPreview(); reflect(); });
  window.addEventListener('resize', drawPreview);
}

async function init() {
  try {
    const response = await api('/api/config'); if (!response.ok) throw new Error('스튜디오 설정을 읽지 못했습니다');
    state.config = await response.json(); state.profiles = state.config.profiles || []; state.direction = state.config.direction || null; state.audio = state.config.audio || null;
    state.timingReviewNeeded = !!(state.config.project?.studio?.timingReviewNeeded || state.config.project?.studio?.unreviewedLyricsOrTiming);
    $('analysisText').textContent = directionText();
    if (Array.isArray(state.config.fontWarnings) && state.config.fontWarnings.length) status(`글꼴을 다시 올려 주세요: ${state.config.fontWarnings.join(' · ')}`, true);
    const frame = $('engineFrame'); frame.src = `/engine/index.html?token=${encodeURIComponent(token)}`;
    state.J = await waitForEngine(frame);
    if (innerWidth >= 960) frame.contentDocument.getElementById('modePro').click();
    await importProject(state.config.project);
    const directed = state.direction && (state.direction.profile || state.direction.profileId); state.selectedProfile = profileById(directed) ? directed : null;
    await importAudio(state.audio);
    const initial = { lyrics: nativeProject().lyrics, timing: clone(nativeProject().timing) };
    const draft = savedDraft();
    if (draft) {
      await importProject(Object.assign({}, draft.sourceExtra, { project: draft.project }));
      state.sourceExtra = draft.sourceExtra; state.direction = draft.direction;
      state.selectedProfile = profileById(draft.selectedProfile) ? draft.selectedProfile : null;
      state.timingReviewNeeded = draft.timingReviewNeeded;
    }
    await bakeDirecting(draft ? draft.project : state.config.project).catch(error => status(error.message, true));
    if (!draft) configureInstrumentalDefault();
    state.initial = draft ? initial : { lyrics: nativeProject().lyrics, timing: clone(nativeProject().timing) }; state.ready = true;
    populateNativeChoices(); addSettingsHelp(); populateCards(); bind(); switchTabFromHash(false); watchNativeImports(); replan();
  } catch (error) { $('projectStatus').textContent = '스튜디오를 열지 못했습니다'; status(error.message, true); }
}

if (typeof document !== 'undefined') init();
