/* 곡 길이·자산·박·가사 시계는 프로젝트 입력에서만 읽는다. */
(() => {
  'use strict';
  const config = window.PLAYLIST_CONFIG;
  if (!config || !Number.isFinite(config.duration) || config.duration < 12) throw new Error('유효한 PLAYLIST_CONFIG가 필요합니다.');
  const music = window.TL?.music || {};
  const hits = (music.hits || []).filter(Number.isFinite).sort((a,b) => a-b);
  const beats = (music.beats || []).filter(Number.isFinite).sort((a,b) => a-b);
  const tracks = config.playlist.tracks;
  const trackAt = t => tracks.find(v => t >= v.startSeconds && t < v.endSeconds) || tracks.at(-1);
  const spb = Math.max(.3, Math.min(1.1, 60 / (music.bpm || 100)));
  const near = (target, radius, low, high) => {
    const candidates = hits.filter(t => Math.abs(t-target) <= radius && t >= low && t <= high);
    return candidates.length ? candidates.reduce((a,b) => Math.abs(a-target) <= Math.abs(b-target) ? a : b) : target;
  };
  const body = near(Math.min(6.4,tracks[0].endSeconds*.65),.65,2.5,tracks[0].endSeconds-.2);
  const assemble = near(body*.58,.45,.8,body-1);
  const fan = near(assemble*.45,.25,.35,assemble-.5);
  const cycle = Math.max(12, Math.min(28, spb*32));
  function timing(t, track=trackAt(t)) {
    const start = track === tracks[0] ? body : track.startSeconds;
    const base = start + Math.max(0,Math.floor((t-start)/cycle))*cycle;
    return {assemble,body,fan,fanSwap:near(fan+.8,.25,fan+.4,assemble),expand:base+cycle*.25,answer:base+cycle*.5,recall:base+cycle*.75,turn:base+cycle*.4,cycleEnd:base+cycle};
  }
  const spanEvents = (t, seconds=1) => {
    // 긴 플레이리스트에서도 이진 탐색으로 직전 타격음만 읽는다.
    let lo=0,hi=hits.length;
    while(lo<hi){const mid=(lo+hi)>>1;if(hits[mid]<t-seconds)lo=mid+1;else hi=mid;}
    const result=[];for(let i=lo;i<hits.length && hits[i]<=t;i++)result.push({time:hits[i],index:i,strength:1});
    return result;
  };
  const rgba = (hex,alpha) => {const n=parseInt(hex.slice(1),16);return `rgba(${n>>16},${n>>8&255},${n&255},${alpha})`;};
  window.GrooveRuntime = {config,music,hits,beats,spb,body,trackAt,timing,spanEvents,rgba};
})();
