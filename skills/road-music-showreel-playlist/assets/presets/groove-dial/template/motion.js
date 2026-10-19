(() => {
  'use strict';
  const runtime = window.GrooveRuntime, {config} = runtime;
  const clamp=x=>Math.max(0,Math.min(1,x)),mix=(a,b,p)=>a+(b-a)*p;
  const smooth=(t,a,b)=>{const p=clamp((t-a)/(b-a));return p*p*(3-2*p);};
  const out=x=>1-Math.pow(1-clamp(x),4);
  function profileAt(t=0) {
    const name = runtime.trackAt(t).motionMode || config.preset.motionMode;
    const soft=name==='soft',drive=name==='drive';
    return {name,impact:soft?.28:drive?1.2:.85,decay:soft?.28:.13,tilt:soft?.45:drive?2:1.5};
  }
  const energy=t=>{
    const e=runtime.music.energy;if(!e?.v?.length)return 0;
    const p=Math.max(0,(t-(e.t0||0))/e.dt),i=Math.min(e.v.length-1,Math.floor(p)),j=Math.min(e.v.length-1,i+1);
    return mix(e.v[i],e.v[j],clamp(p-i));
  };
  const impulse=(t,channel='strength',decay=profileAt(t).decay)=>{
    let value=0;for(const e of runtime.spanEvents(t,decay*6)){const age=t-e.time;value=Math.max(value,Math.min(1,age/.018)*Math.exp(-Math.max(0,age-.018)/decay));}return value*energy(t);
  };
  const majorPulse=t=>impulse(t,'strength',profileAt(t).name==='soft'?.35:.18);
  function settle(t,start,duration){const p=clamp((t-start)/duration);return profileAt(t).name==='soft'?smooth(t,start,start+duration):1+2.15*Math.pow(p-1,3)+1.15*Math.pow(p-1,2);}
  // 회전은 일정 속도이며 이전 프레임에 의존하지 않는다.
  const snap=()=>0;
  function state(t){const beat=impulse(t);return {t,bass:beat,snare:beat,high:beat,beat,hit:majorPulse(t),angle:t*360/config.preset.discPeriodSeconds,profile:profileAt(t).name};}
  window.GROOVE={clamp,mix,smooth,out,settle,profileAt,impulse,state,majorPulse,snap};
})();
