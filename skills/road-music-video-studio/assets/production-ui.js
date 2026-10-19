'use strict';
window.RoadMusicProductionUI=(()=>{
  const number=new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1});
  const time=new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  const domains={music:'음악 제작',motion:'모션그래픽',mixed:'음악·모션그래픽'};
  const statuses={queued:'대기 중',running:'진행 중',succeeded:'완료',failed:'실패',cancelled:'취소'};
  const tasks={create:'제작 요청','image-generation':'이미지 생성',generation:'음악 생성',generate:'음악 생성',render:'영상 렌더',prepare:'제작 준비',composition:'장면 구성',finalize:'완성본 정리',title:'제목 변경',lyrics:'가사 변경',revision:'수정 제작',review:'결과 검수',verification:'검증',verify:'결과 검증',assemble:'장면 조립',compose:'장면 구성',load:'모델 준비',plan:'악보 설계',semantic:'음악 구성',synth:'음악 합성',decode:'음원 변환',encode:'영상 압축',frames:'영상 프레임 제작',analysis:'음악 분석',audio:'음원 준비',mux:'영상·음원 결합',replace:'음원 교체',restore:'음원 복원'};
  const measured=value=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value));
  const label=(labels,value,fallback)=>labels[value]||value||fallback;
  function timeLabel(value){const date=new Date(value);return value===null||value===undefined||value===''||!Number.isFinite(date.getTime())?'시각 미기록':time.format(date)}
  function formatMs(value,{unitGap=' ',minutes=true}={}){const ms=Number(value);if(!measured(value)||ms<0)return '측정값 없음';if(ms>0&&ms<.1)return `<0.1${unitGap}ms`;if(ms<1000)return `${number.format(ms)}${unitGap}ms`;return minutes&&ms>=60000?`${number.format(ms/60000)}분`:`${number.format(ms/1000)}초`}
  function formatBytes(value){const bytes=Number(value);if(!measured(value)||bytes<0)return '용량 미기록';return bytes>=1048576?`${number.format(bytes/1048576)} MiB`:`${number.format(Math.ceil(bytes/1024))} KiB`}
  function copyNotice(host){let notice=host?.querySelector('[data-production-copy-status]');if(!notice&&host){notice=document.createElement('p');notice.className='hint';notice.dataset.productionCopyStatus='true';notice.setAttribute('role','status');host.append(notice)}return notice}
  function copyButton(value,{label='프롬프트 복사',fallbackHost}={}){
    const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent=label;
    button.addEventListener('click',async()=>{
      const host=fallbackHost||button.closest('article')||button.parentElement;
      try{
        await navigator.clipboard.writeText(String(value||''));
        host?.querySelector('[data-production-copy-fallback]')?.remove();
        const status=copyNotice(host);if(status)status.textContent='프롬프트를 복사했습니다.';
        button.textContent='복사했습니다';setTimeout(()=>{button.textContent=label},1600);
      }catch{
        if(!host)return;
        let fallback=host.querySelector('[data-production-copy-fallback]');
        if(!fallback){fallback=document.createElement('textarea');fallback.className='copy-fallback';fallback.readOnly=true;fallback.setAttribute('aria-label','프롬프트 원문');fallback.dataset.productionCopyFallback='true';host.append(fallback)}
        fallback.value=String(value||'');
        const notice=copyNotice(host);
        notice.textContent='자동 복사를 허용하지 않았습니다. 프롬프트 원문을 선택해 직접 복사해 주세요.';
        fallback.focus();fallback.select();button.textContent='원문을 선택했습니다';
      }
    });
    return button;
  }
  function timeBreakdown(items=[]){
    const figure=document.createElement('figure'),legend=document.createElement('ul');figure.className='production-time-breakdown';legend.className='production-time-legend';
    const rows=items.filter(item=>item&&typeof item==='object'),total=rows.reduce((sum,item)=>sum+(measured(item.elapsedMs)&&item.elapsedMs>0?Number(item.elapsedMs):0),0);
    const percent=ms=>ms>0&&ms/total*100<.1?'<0.1':number.format(ms/total*100);
    const labels=new Set(rows.map((item,index)=>({index,ms:measured(item.elapsedMs)?Number(item.elapsedMs):0})).sort((a,b)=>b.ms-a.ms).slice(0,4).map(item=>item.index));
    const colors=['#087f5b','#2563a6','#b45309','#9d3945','#526473','#537a16'];
    if(total>0){
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 200 200');svg.setAttribute('role','img');svg.setAttribute('aria-label',`제작 과정별 실측 시간 비중 · 누적 ${formatMs(total)}`);let angle=-Math.PI/2;
      rows.forEach((item,index)=>{
        const ms=measured(item.elapsedMs)?Number(item.elapsedMs):0;if(ms<=0)return;
        const end=angle+ms/total*Math.PI*2,path=document.createElementNS('http://www.w3.org/2000/svg',ms===total?'circle':'path');
        if(ms===total){path.setAttribute('cx','100');path.setAttribute('cy','100');path.setAttribute('r','92')}
        else path.setAttribute('d',`M100 100 L${100+92*Math.cos(angle)} ${100+92*Math.sin(angle)} A92 92 0 ${ms/total>.5?1:0} 1 ${100+92*Math.cos(end)} ${100+92*Math.sin(end)} Z`);
        path.setAttribute('fill',colors[index%colors.length]);svg.append(path);
        if(ms/total>=.12&&labels.has(index)){
          const text=document.createElementNS('http://www.w3.org/2000/svg','text'),mid=(angle+end)/2,x=100+53*Math.cos(mid),y=100+53*Math.sin(mid);text.setAttribute('x',String(x));text.setAttribute('y',String(y-4));text.setAttribute('text-anchor','middle');text.setAttribute('class','production-pie-label');const title=document.createElementNS('http://www.w3.org/2000/svg','tspan'),value=document.createElementNS('http://www.w3.org/2000/svg','tspan'),name=label(tasks,item.taskType,'작업');title.textContent=name.length>8?name.slice(0,7)+'…':name;value.setAttribute('x',String(x));value.setAttribute('dy','15');value.textContent=percent(ms)+'%';text.append(title,value);svg.append(text);
        }angle=end;
      });figure.append(svg);
    }else{const empty=document.createElement('p');empty.className='hint';empty.textContent='아직 비중을 표시할 실측 시간이 없습니다.';figure.append(empty)}
    rows.forEach((item,index)=>{const row=document.createElement('li'),swatch=document.createElement('span'),text=document.createElement('span');swatch.className='production-time-swatch';swatch.setAttribute('style',`background:${colors[index%colors.length]}`);swatch.setAttribute('aria-hidden','true');const known=measured(item.elapsedMs),share=known&&total>0?` · ${percent(Number(item.elapsedMs))}%`:'';text.textContent=`${label(domains,item.domain,'제작')} · ${label(tasks,item.taskType,'작업')} · ${formatMs(item.elapsedMs)}${share}${item.missingElapsedCount?` · 미측정 ${item.missingElapsedCount}건`:''}`;row.append(swatch,text);legend.append(row)});figure.append(legend);return figure;
  }
  return {domainLabel:(value,fallback='제작')=>label(domains,value,fallback),statusLabel:(value,fallback='상태 미기록')=>label(statuses,value,fallback),taskLabel:value=>String(value||'').startsWith('stage:')?'제작 단계 · '+label(tasks,String(value).slice(6),'작업'):label(tasks,value,'작업'),timeLabel,formatMs,formatBytes,measured,copyButton,timeBreakdown};
})();
