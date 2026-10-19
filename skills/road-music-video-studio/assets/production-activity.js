'use strict';
window.RoadMusicActivity=(()=>{
  const ui=window.RoadMusicProductionUI,boot=window.__STUDIO_BOOTSTRAP__;
  const clock=new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  const e=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node};
  const duration=value=>ui.measured(value)?ui.formatMs(value):'예측 근거 부족';
  const at=value=>ui.measured(value)?clock.format(new Date(Number(value))):'확인 필요';
  function estimateLabel(value={}){if(!ui.measured(value.estimatedMs))return '완료 표본이 없어 예측할 수 없습니다.';const range=ui.measured(value.lowerMs)&&ui.measured(value.upperMs)?` · 과거 범위 ${duration(value.lowerMs)}~${duration(value.upperMs)}`:'';const basis=value.basis==='expectedMediaSeconds'?'목표 길이 환산':value.basis==='expectedFrameCount'?'프레임 수 환산':'동일 작업 기록';const average=ui.measured(value.avgMs)?` · ${basis} 평균 ${duration(value.avgMs)}`:'';return `약 ${duration(value.estimatedMs)}${average}${range} · 표본 ${value.sampleCount||0}건${value.confidence==='low'?' · 참고 수준':''}`}
  function workLabel(summary={}){if(summary.unknownCount&&Number(summary.knownWorkMs)===0)return `예측 불가 ${summary.unknownCount}건`;const known=ui.measured(summary.knownWorkMs)?`약 ${duration(summary.knownWorkMs)}`:'예측 근거 부족';return summary.unknownCount?`${known} + 예측 불가 ${summary.unknownCount}건`:known}
  function progress(value,estimated,label){const box=e('div','activity-progress'),bar=e('progress',''),text=e('p','hint');bar.max=100;bar.setAttribute('aria-label',label);if(ui.measured(value)){bar.value=Math.max(0,Math.min(100,Number(value)*100));text.textContent=`${label} ${Math.round(bar.value)}%${estimated?' · 시간 기반 추정':''}`}else text.textContent=`${label} · ${estimated?'예측 근거 부족':'진행률 확인 중'}`;box.append(bar,text);return box}
  function projectCard(project){
    const card=e('article','activity-project'),heading=e('h3','',project.title||'제작 프로젝트'),current=project.currentTask,next=project.nextQueuedTask,stage=project.nextStage;
    card.append(heading,progress(project.progress?.ratio,project.progress?.estimated!==false,'현재 요청의 예상 진행률'));
    if(project.progress?.unknownTaskCount)card.append(e('p','hint',`시간을 알 수 없는 작업 ${project.progress.unknownTaskCount}건은 진행률 계산에서 제외됩니다.`));
    if(current){card.append(e('p','','현재 · '+ui.taskLabel(current.taskType)+(current.currentStage?' / '+ui.taskLabel(current.currentStage):'')));if(current.summary){const message=String(current.summary);if(message.length>240){const details=e('details',''),title=e('summary','','전체 작업 상태 보기');details.append(title,e('p','hint',message));card.append(details)}else card.append(e('p','hint',message))}if(current.stale)card.append(e('p','activity-warning','마지막 기록이 오래됐거나 실행 상태를 확인하지 못했습니다.'));if(ui.measured(current.progress))card.append(progress(current.progress,current.progressEstimated===true,'현재 단계 진행률'));card.append(e('p','activity-time',`경과 ${duration(current.elapsedMs)} · 남은 시간 ${duration(current.estimate?.remainingMs)}`));if(current.estimate?.overrun)card.append(e('p','activity-warning','기존 예상 시간을 넘었습니다. 실제 완료 신호를 기다리는 중입니다.'))}
    else card.append(e('p','','시작 대기 중입니다.'));
    if(next)card.append(e('p','','다음 대기 작업 · '+ui.taskLabel(next.taskType)+' · '+estimateLabel(next.estimate)));
    else if(stage)card.append(e('p','hint',`다음 ${stage.inferred?'추정 단계':'단계'} · ${ui.taskLabel(stage.taskType)} · ${duration(stage.estimatedMs)}${stage.inferred?' (과거 흐름 참고 · 실행 예약 아님)':''}`));
    else card.append(e('p','hint','다음 단계가 아직 등록되지 않았거나, 추정할 과거 흐름이 없습니다.'));
    return card;
  }
  function queueRow(item,index){
    const row=e('tr',''),estimate=item.estimate||{},job=e('td',''),name=e('strong','',item.title||'제작 프로젝트');job.append(name,e('p','hint',`${ui.domainLabel(item.domain)} · ${ui.taskLabel(item.taskType)}`));
    const state=e('td','',item.status==='running'?'진행 중':'대기 중');if(item.currentStage)state.append(e('p','hint',ui.taskLabel(item.currentStage)));if(item.stale)state.append(e('p','activity-warning','실행 상태 확인 필요'));
    const expected=e('td','',estimateLabel(estimate)),remaining=e('td','',duration(estimate.remainingMs)),wait=e('td','',duration(item.estimatedWaitMs)),finish=e('td','',at(item.estimatedFinishAtMs));
    if(estimate.overrun)remaining.append(e('p','activity-warning','예상 초과'));
    wait.append(e('p','hint',(item.status==='running'?'실제 시작 ':'시작 예상 ')+at(item.estimatedStartAtMs)));row.append(e('td','',String(Number.isInteger(item.position)?item.position+1:index+1)),job,state,expected,remaining,wait,finish);return row;
  }
  function mount(host){
    const heading=e('div','section-heading'),copy=e('div',''),actions=e('div','activity-actions'),refresh=e('button','secondary','진행 새로 고침'),autoLabel=e('label',''),auto=e('input',''),status=e('p','hint','제작 상태를 불러오는 중…'),summary=e('div','activity-summary'),projects=e('div','activity-projects'),queue=e('div','activity-queue'),filter=e('select',''),filterLabel=e('label','','표시 범위 상태'),pageLabel=e('p','hint'),previous=e('button','secondary','앞 작업 보기'),next=e('button','secondary','다음 작업 보기'),pager=e('div','activity-actions');
    copy.append(e('h2','','제작 진행 상황·대기열'),e('p','hint',boot.groupId?'이 음악의 현재 요청과 작업을 표시합니다. 전체 순서의 앞선 다른 작업도 대기 시간에 반영합니다.':'현재 작업·다음 단계·대기열의 예상 시간을 확인합니다. 예상 시간은 실제 완료 시각을 보장하지 않습니다.'));
    refresh.type=previous.type=next.type='button';auto.type='checkbox';auto.checked=true;autoLabel.append(auto,document.createTextNode(' 자동 갱신'));actions.append(refresh,autoLabel);heading.append(copy,actions);status.setAttribute('role','status');filter.setAttribute('aria-label','표시 범위 작업 상태');for(const [value,label] of [['','전체'],['running','진행 중'],['queued','대기 중']]){const option=e('option','',label);option.value=value;filter.append(option)}filterLabel.append(filter);pager.append(previous,next);host.append(heading,status,summary,projects,filterLabel,queue,pageLabel,pager);
    let timer=null,busy=false,offset=0,lastData=null;
    function render(data){
      const scope=data.scope||{},global=data.globalQueue||scope,items=data.queue?.items||[];summary.replaceChildren();projects.replaceChildren();queue.replaceChildren();
      const pending=Number(global.queuedCount||0)+Number(global.runningCount||0);
      if(pending){const list=e('dl','activity-stats');for(const [name,value] of [['진행 중',`${scope.runningCount||0}건`],['대기 중',`${scope.queuedCount||0}건`],['대기 작업이 있는 프로젝트',`${(data.projects||[]).filter(project=>project.nextQueuedTask).length}개`],['이 범위의 남은 작업',workLabel(scope)],['전체 대기열 남은 작업',workLabel(global)],['전체 완료 예상 시각',at(global.completionEtaMs)]]){const pair=e('div','');pair.append(e('dt','',name),e('dd','',value));list.append(pair)}summary.append(list,e('p','hint','순차 처리 기준 추정입니다. 동시에 실행하면 달라집니다. 모르는 시간이 앞에 있거나 일시정지·상태 미확인이면 완료 시각은 표시하지 않습니다. 등록되지 않은 추정 단계는 총시간에 포함하지 않습니다.'))}
      else summary.append(e('p','activity-empty','진행 중이거나 대기 중인 제작 기록이 없습니다. 새 작업이 등록되면 여기에 표시합니다.'));
      const runningProjects=(data.projects||[]).filter(project=>project.currentTask);for(const project of runningProjects.slice(0,20))projects.append(projectCard(project));if(runningProjects.length>20)projects.append(e('p','hint','진행 카드 20개까지 표시합니다. 나머지는 아래 대기열에서 확인하세요.'));
      const visible=items.filter(item=>!filter.value||item.status===filter.value);filterLabel.hidden=pageLabel.hidden=pager.hidden=!pending;
      if(visible.length){const wrapper=e('div','activity-table-wrap'),table=e('table',''),thead=e('thead',''),header=e('tr',''),body=e('tbody','');wrapper.setAttribute('role','region');wrapper.setAttribute('aria-label','작업 대기열, 좌우로 이동해 확인');wrapper.tabIndex=0;for(const label of ['순서','프로젝트·작업','상태·현재 단계','작업 전체 예상·근거','남은 작업 시간','앞선 작업 대기','완료 예상 시각']){const cell=e('th','',label);cell.scope='col';header.append(cell)}thead.append(header);visible.forEach(item=>body.append(queueRow(item,offset+items.indexOf(item))));table.append(thead,body);wrapper.append(table);queue.append(wrapper)}
      else if(pending)queue.append(e('p','activity-empty','이 범위와 상태에 맞는 작업이 없습니다. 상태를 전체로 바꾸거나 다른 작업 범위를 확인하세요.'));
      pageLabel.textContent=`전체 범위 ${data.queue?.totalCount??items.length}건 · ${offset+1}번부터 ${items.length}건을 불러왔습니다. 상태 필터는 불러온 범위에 적용됩니다.`;previous.disabled=offset===0;next.disabled=data.queue?.nextOffset==null;
      if(data.runtime?.paused)status.textContent='앱 대기열이 일시정지돼 있습니다. 남은 작업량만 추정하며 완료 시각은 확정할 수 없습니다.';
      else if(data.runtime?.state&&data.runtime.state!=='available')status.textContent='앱의 실시간 대기열을 확인하지 못했습니다. 제작 원장에 기록된 상태를 표시합니다.';
      else status.textContent='최근 확인 '+at(data.generatedAtMs);
      if(data.queue?.truncated)summary.append(e('p','activity-warning','작업 수가 안전 조회 범위를 넘었습니다. 전체 완료 시각은 확정할 수 없습니다.'));
      if(Array.isArray(data.warnings)&&data.warnings.length)summary.append(e('p','activity-warning',data.warnings.join(' ')));
    }
    function schedule(){clearTimeout(timer);if(auto.checked&&!document.hidden)timer=setTimeout(refreshData,(lastData?.globalQueue?.runningCount||lastData?.globalQueue?.queuedCount)?5000:15000)}
    async function refreshData(){if(busy)return;busy=true;refresh.disabled=true;status.classList.remove('message-error');status.textContent='진행 단계와 대기 시간을 확인하는 중…';try{const query=new URLSearchParams({token:boot.token,limit:'100',offset:String(offset),...(boot.groupId?{groupId:boot.groupId}:{})}),response=await fetch('/api/production/activity?'+query,{signal:AbortSignal.timeout(10000)}),data=await response.json();if(!response.ok)throw Error(data.error||'제작 상태를 읽지 못했습니다.');lastData=data;render(data)}catch(error){status.classList.add('message-error');status.textContent=['TimeoutError','AbortError'].includes(error.name)?'상태 응답이 늦어지고 있습니다. 이전 표시를 유지합니다. 진행 새로 고침으로 다시 확인하세요.':'제작 상태 확인 실패: '+(error.message||'연결을 확인하세요.');}finally{busy=false;refresh.disabled=false;schedule()}}
    refresh.addEventListener('click',refreshData);filter.addEventListener('change',()=>{if(lastData)render(lastData)});auto.addEventListener('change',schedule);previous.addEventListener('click',()=>{offset=Math.max(0,offset-100);refreshData()});next.addEventListener('click',()=>{if(lastData?.queue?.nextOffset!=null){offset=lastData.queue.nextOffset;refreshData()}});document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if(!document.hidden&&auto.checked)refreshData()});window.addEventListener('beforeunload',()=>clearTimeout(timer));refreshData();
  }
  for(const host of document.querySelectorAll('[data-production-activity]'))mount(host);
  return {estimateLabel,workLabel,projectCard,queueRow};
})();
