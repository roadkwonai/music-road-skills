import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const assets = path.join(root, 'assets', 'native-music');
const showreel = process.env.SHOWREEL_HOME || path.join(os.homedir(), '.local/share/roadmusic-video-tools/showreel');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'native-runtime-'));
const project = path.join(tmp, 'project');
const qa = path.join(project, 'qa');

function write(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, value);
}

function copy(from, to) { fs.copyFileSync(from, to); }

function global(name, value) { return `window.${name}=${JSON.stringify(value)};\n`; }
function sha(value) { return crypto.createHash('sha256').update(value).digest('hex'); }
function stamp(seconds) { const ms = Math.round(seconds * 1000); const s = Math.floor(ms / 1000); return `00:00:${String(s % 60).padStart(2, '0')},${String(ms % 1000).padStart(3, '0')}`; }

function fixture({ captions, display, tracks, opening, media = [], duration = 8, spectrum, invalidCanvas = false, silentLead = false }) {
  const reel = path.join(project, 'reel');
  fs.mkdirSync(reel, { recursive: true });
  for (const file of ['index.html', 'film-runtime.js', 'scenes.js']) copy(path.join(assets, file), path.join(reel, file));
  const index = path.join(reel, 'index.html');
  const design = path.join(reel, 'road-music-design');
  fs.cpSync(path.join(root, '..', 'road-music-video-studio', 'assets', 'design'), design, { recursive: true });
  fs.writeFileSync(path.join(design, 'styles.css'), fs.readFileSync(path.join(design, 'fonts.css'), 'utf8') + '\n' + fs.readFileSync(path.join(design, 'design.css'), 'utf8'));
  fs.writeFileSync(index, fs.readFileSync(index, 'utf8').replace('</head>', '<link rel="stylesheet" href="road-music-design/styles.css"></head>'));
  fs.cpSync(path.join(root, 'assets', 'template', 'fonts'), path.join(reel, 'fonts'), { recursive: true });
  copy(path.join(showreel, 'assets', 'engine', 'engine.js'), path.join(reel, 'engine.js'));
  copy(path.join(showreel, 'assets', 'engine', 'fx.js'), path.join(reel, 'fx.js'));
  write(path.join(reel, 'timeline.js'), global('TL', { cues: {} }));
  const hasCaptions = Array.isArray(captions) && captions.length > 0;
  const captionStatus = hasCaptions ? (tracks.length > 1 ? 'mixed' : 'ready') : 'instrumental-no-lyrics';
  const inputTracks = tracks.map((track, index) => {
    const music = `inputs/music/${track.id}.wav`;
    const pcm = tracks.length > 1 ? `audio/tracks/${track.id}.wav` : 'audio/music/music.wav';
    const trackDuration = track.endSeconds - track.startSeconds;
    write(path.join(project, music), `source-${track.id}`);
    write(path.join(project, pcm), `pcm-${track.id}`);
    const captionPath = index === 0 && hasCaptions ? `inputs/captions/${track.id}.json` : null;
    if (captionPath) write(path.join(project, captionPath), JSON.stringify({ schemaVersion: 1, status: 'ready', cues: captions }));
    const cutStartSeconds = track.source?.cutStartSeconds || 0;
    return {
      id: track.id,
      title: track.id,
      titleSource: 'fixture',
      startSeconds: track.startSeconds,
      endSeconds: track.endSeconds,
      durationSeconds: trackDuration,
      startSample: Math.round(track.startSeconds * 48000),
      endSample: Math.round(track.endSeconds * 48000),
      instrumental: !captionPath,
      captionStatus: captionPath ? 'ready' : 'instrumental-no-lyrics',
      source: {
        path: music,
        sha256: sha(fs.readFileSync(path.join(project, music))),
        cutStartSeconds,
        cutEndSeconds: cutStartSeconds + trackDuration,
        requestedDurationSeconds: trackDuration,
      },
      audio: { path: pcm, sha256: sha(fs.readFileSync(path.join(project, pcm))), samples: Math.round(trackDuration * 48000) },
      inputTiming: captionPath ? { path: captionPath, sha256: sha(fs.readFileSync(path.join(project, captionPath))), originSeconds: 0 } : null,
      casting: null,
    };
  });
  const displayedCaptions = hasCaptions ? captions.map(cue => inputTracks.length > 1 ? { ...cue, id: `${inputTracks[0].id}:${cue.id}`, sourceCueId: cue.id, trackId: inputTracks[0].id } : cue) : [];
  const actualDuration = inputTracks.at(-1).endSeconds;
  if (inputTracks.length > 1) write(path.join(project, 'audio', 'music', 'music.wav'), 'fixture-pcm');
  write(path.join(project, 'audio', 'mix.wav'), 'fixture-mix');
  const spectrumData = display.showSpectrum ? (spectrum === undefined ? {
    schemaVersion: 1,
    dt: .1,
    requestedDt: .1,
    bands: 16,
    minHz: 40,
    maxHz: 12000,
    sampleRate: 48000,
    windowSamples: 2048,
    hopSamples: 4800,
    windowAlignment: 'center',
    durationSeconds: actualDuration,
    frames: Array.from({ length: 81 }, (_, i) => Array.from({ length: 16 }, (_, n) => (i + n) % 11)),
  } : spectrum) : null;
  if (silentLead && spectrumData) for (const frame of spectrumData.frames.slice(0, 3)) frame.fill(0);
  const spectrumPath = path.join(project, 'audio', 'spectrum.json');
  if (spectrumData) write(spectrumPath, JSON.stringify(spectrumData));
  else fs.rmSync(spectrumPath, { force: true });
  const mediaRoot = path.join(project, 'assets', 'media');
  fs.rmSync(mediaRoot, { recursive: true, force: true });
  fs.rmSync(path.join(project, 'assets', 'media.json'), { force: true });
  const nativeMedia = media.map(asset => {
    const src = `../assets/media/${asset.id}.png`;
    const target = path.join(reel, src);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    // 1x1 PNG: checker tests browser decode, not art direction.
    fs.writeFileSync(target, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAMAAAAoyzS7AAAABGdBTUEAALGPC/xhBQAAAANQTFRFAAAAp3o92gAAAAF0Uk5TAEDm2GYAAAALSURBVHicY2AAAQAABgAB/oxnyAAAAABJRU5ErkJggg==', 'base64'));
    return { id: asset.id, src, width: 1, height: 1, sha256: sha(fs.readFileSync(target)), roles: ['fixture'], source: { kind: 'provided' }, requireAlpha: false };
  });
  if (nativeMedia.length) write(path.join(project, 'assets', 'media.json'), JSON.stringify({ schemaVersion: 1, assets: Object.fromEntries(nativeMedia.map(({ id, ...asset }) => [id, asset])) }));
  const scenes = inputTracks.map((track, index) => ({
    id: `${track.id}.scene`,
    startSeconds: track.startSeconds,
    endSeconds: track.endSeconds,
    sourceStartSeconds: track.source.cutStartSeconds,
    sourceEndSeconds: track.source.cutEndSeconds,
    originStartSeconds: track.startSeconds,
    originEndSeconds: track.endSeconds,
    trackId: track.id,
    lyricCueIds: index === 0 && hasCaptions ? captions.map(cue => cue.id) : [],
    meaning: 'fixture',
    subject: 'fixture',
    action: 'fixture',
    medium: 'fixture',
    composition: 'fixture',
    transition: 'cut',
    assets: [],
  }));
  write(path.join(reel, 'film-input.js'), global('FILM_INPUT', {
    schemaVersion: 1, duration, fps: 30, width: 1920, height: 1080, audio: '../audio/mix.wav',
    display, playlist: { tracks: inputTracks }, captions: { status: captionStatus, cues: displayedCaptions }, spectrum: spectrumData,
  }));
  write(path.join(reel, 'film-plan.js'), global('FILM_PLAN', {
    schemaVersion: 1, concept: 'fixture', opening, media: nativeMedia, scenes,
  }));
  write(path.join(reel, 'scenes.js'), tracks.map(track => `REEL.scene({id:${JSON.stringify(`${track.id}.scene`)},start:${track.startSeconds},end:${track.endSeconds},setup(parent){const canvas=document.createElement('canvas');canvas.width=1920;canvas.height=1080;parent.append(canvas);this.context=canvas.getContext('2d');},render(_,ctx){this.context.fillStyle=ctx.t<4?'#171721':'#211717';${invalidCanvas ? 'this.context.translate(NaN,0);' : ''}this.context.fillRect(0,0,1920,1080);}});`).join('\n'));
  write(path.join(project, 'composition.json'), JSON.stringify({ schemaVersion: 1, concept: 'fixture', opening, scenes }));
  write(path.join(project, 'display.json'), JSON.stringify(display));
  write(path.join(project, 'playlist.json'), JSON.stringify({ schemaVersion: 1, sampleRate: 48000, durationSeconds: actualDuration, tracks: inputTracks }));
  write(path.join(project, 'captions', 'lyrics.json'), JSON.stringify({ schemaVersion: 1, status: captionStatus, cues: displayedCaptions, sources: hasCaptions ? [{ trackId: inputTracks[0].id, status: 'ready', source: null }] : [] }));
  write(path.join(project, 'captions', 'lyrics.srt'), (captions || []).map((cue, index) => `${index + 1}\n${stamp(cue.startSeconds)} --> ${stamp(cue.endSeconds)}\n${cue.text}`).join('\n\n') + (hasCaptions ? '\n' : ''));
  write(path.join(project, 'timeline.json'), JSON.stringify({ scenes: scenes.map(scene => ({ id: scene.id, start: scene.startSeconds, end: scene.endSeconds })) }));
  const audioSha256 = sha(fs.readFileSync(path.join(project, 'audio', 'mix.wav')));
  write(path.join(project, 'production.json'), JSON.stringify({
    schemaVersion: 1,
    mode: 'native-composition',
    durationSeconds: actualDuration,
    renderDurationSeconds: duration,
    expectedFrames: Math.round(duration * 30),
    audio: { path: 'audio/mix.wav', sha256: audioSha256 },
    spectrum: spectrumData ? { path: 'audio/spectrum.json', sha256: sha(fs.readFileSync(spectrumPath)), audioSha256 } : null,
    playlistInput: inputTracks.length > 1,
    inputs: inputTracks.map(track => ({ id: track.id, music: track.source.path, sha256: track.source.sha256, captions: track.inputTiming?.path || null, captionsSha256: track.inputTiming?.sha256 || null })),
  }));
}

function check(name, expectPass = true) {
  const out = path.join(qa, name);
  let failed = false;
  try { execFileSync(process.execPath, [path.join(root, 'scripts', 'check-native-project.mjs'), project, out], { stdio: 'pipe', env: process.env }); }
  catch (error) { failed = true; if (expectPass) throw error; }
  assert.equal(failed, !expectPass, name);
}

try {
  const display = { showSpectrum: false, showQueue: false, showNowPlaying: false, channelName: 'SKIP' };
  const tracks = [
    { id: 'one', startSeconds: 0, endSeconds: 4, source: { cutStartSeconds: 0 } },
    { id: 'two', startSeconds: 4, endSeconds: 8, source: { cutStartSeconds: 2 } },
  ];
  const singleTrack = [{ id: 'one', startSeconds: 0, endSeconds: 8, source: { cutStartSeconds: 0 } }];
  fixture({ captions: [{ id: 'cue-1', startSeconds: .1, endSeconds: 3, text: '원문 가사는 즉시 모두 보여야 합니다.' }], display: { showSpectrum: true, showQueue: true, showNowPlaying: true, channelName: '채널' }, tracks, opening: { thumbnailId: 'cover', seconds: .5 }, media: [{ id: 'cover', src: 'assets/cover.png' }] });
  check('lyrics-two-tracks-thumbnail');
  fixture({ captions: [], display: { ...display, showSpectrum: true }, tracks: singleTrack, opening: null, silentLead: true });
  check('silent-intro-uses-audible-fft-frame');
  for (let mask = 0; mask < 8; mask++) {
    fixture({ captions: [], display: { showSpectrum: !!(mask & 1), showQueue: !!(mask & 2), showNowPlaying: !!(mask & 4), channelName: 'SKIP' }, tracks, opening: null });
    check(`display-${mask}`);
  }
  fixture({ captions: null, display, tracks, opening: null });
  check('instrumental');
  fixture({ captions: [{ id: 'first', startSeconds: 1, endSeconds: 2, text: '첫 줄' }, { id: 'next', startSeconds: 2, endSeconds: 4, text: '다음 줄' }], display, tracks, opening: null });
  check('adjacent-cues-and-track-boundary');
  fixture({ captions: [{ id: 'fractional', startSeconds: .62, endSeconds: 2, text: '소수 시작 시각의 원문' }, { id: 'next', startSeconds: 2, endSeconds: 4, text: '다음 원문' }], display, tracks: singleTrack, opening: null });
  check('fractional-cue-target-frame-gate');
  fixture({ captions: [], display, tracks: [{ ...tracks[0], endSeconds: 7.99 }], opening: null, duration: 8 });
  check('last-track-padding');
  fixture({ captions: [], display, tracks: tracks.map((track, index) => ({ ...track, source: { cutStartSeconds: index === 0 ? 2 : 0 } })), opening: { thumbnailId: 'cover', seconds: .5 }, media: [{ id: 'cover', src: 'assets/cover.png' }] });
  check('cut-proof-suppresses-thumbnail');
  fixture({ captions: [{ id: 'long', startSeconds: 0, endSeconds: 8, text: '아주 긴 원문도 바꾸지 않고 두 줄 안에서 안전 영역에 맞춰 표시해야 합니다 그리고 끝까지 보존합니다' }], display, tracks: singleTrack, opening: null });
  check('long-caption');
  fixture({ captions: [{ id: 'two-line', startSeconds: 0, endSeconds: 8, text: '첫 줄 원문\n둘째 줄 원문' }], display, tracks: singleTrack, opening: null });
  check('explicit-two-line-caption');
  fixture({ captions: [], display: { ...display, showSpectrum: true }, tracks, opening: null, spectrum: { schemaVersion: 1, dt: .1, bands: 2, frames: [[0, Number.NaN]] } });
  check('invalid-spectrum-rejected', false);
  fixture({ captions: [], display, tracks, opening: null, invalidCanvas: true });
  check('nan-canvas-operation-rejected', false);
  write(path.join(project, 'reel', 'scenes.js'), '/* intentionally empty */\n');
  check('empty-scenes-rejected', false);
  fixture({ captions: [], display, tracks, opening: { thumbnailId: 'missing', seconds: .5 }, media: [] });
  check('missing-asset-rejected', false);
  fixture({ captions: [], display, tracks, opening: { thumbnailId: 'broken', seconds: .5 }, media: [{ id: 'broken', src: 'assets/broken.png' }] });
  write(path.join(project, 'reel', 'assets', 'broken.png'), 'not an image');
  check('decode-error-rejected', false);
  console.log(JSON.stringify({ ok: true, project: tmp }));
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
