'use strict';
window.RoadMusicRecipes=(()=>{
  const escape=value=>String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const match=(item,filters)=>{
    const text=JSON.stringify(item).toLocaleLowerCase('ko-KR');
    return (!filters.search||text.includes(filters.search.toLocaleLowerCase('ko-KR')))&&['engine','purpose','category','style'].every(key=>!filters[key]||item[key]===filters[key]||(key==='engine'&&item[key]==='공통'))&&(!filters.tag||(item.tags||[]).includes(filters.tag));
  };
  const tags=(values,selected='')=>`<div class="recipe-tags">${[...new Set(values)].filter(tag=>!/^(ACE|YuE)$/i.test(tag)).map(tag=>`<button type="button" class="recipe-tag" aria-pressed="${tag===selected}" data-recipe-tag="${escape(tag)}" aria-label="${escape(tag)} 태그로 찾기">${escape(tag)}</button>`).join('')}</div>`;
  const enginePrompt=(item,text,engine)=>item.engine==='공통'&&['ACE','YuE'].includes(engine)?(engine==='ACE'?'engine:"ace"를 유지해 줘.':'사용자가 선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시하고 그대로 유지해 줘.')+' 아래에서 요청한 범위 안에서만 작업해 줘.\n\n'+text:text;
  function card(item,selectedTag='',engine=''){
    const ingredients=(item.ingredients||[]).map(x=>`<li><strong>${escape(x.label)}</strong><span>${escape(x.detail)}</span></li>`).join('');
    const commands=(item.commands||[]).map(x=>`<li><code>${escape(x.command)}</code><span>${escape(x.why)}</span></li>`).join('');
    const variants=(item.variations||[]).map((x,index)=>`<section class="recipe-variation"><h5>${escape(x.title)}</h5><p>${escape(x.prompt)}</p><button class="secondary recipe-copy" type="button" data-recipe-id="${escape(item.id)}" data-variation="${index}">기본 요청과 변경 내용 복사</button></section>`).join('');
    const checks=(item.checks||[]).map(x=>`<li>${escape(x)}</li>`).join('');
    return `<article class="panel recipe-card"><header><p class="hint">${escape([item.engine==='공통'&&engine?engine+' · 공통 작업':item.engine,item.purpose,item.style].filter(Boolean).join(' · '))}</p><h3>${escape(item.title)}</h3><p>${escape(item.summary)}</p></header>${tags(item.tags||[],selectedTag)}<p class="recipe-expected"><strong>어떤 결과를 기대할 수 있나요</strong> ${escape(item.expected)}</p><details><summary>프롬프트와 사용 방법 자세히 보기</summary><h4>기본 요청 예시</h4><pre class="recipe-prompt">${escape(enginePrompt(item,item.prompt,engine))}</pre><h4>어떤 요소를 조합했나요</h4><ul class="recipe-explanations">${ingredients}</ul><h4>공개 명령의 순서와 역할</h4><ol class="recipe-commands">${commands}</ol><div class="recipe-guide-notes"><p><strong>이럴 때 사용</strong>${escape(item.useWhen)}</p><p><strong>사용 전 주의할 점</strong>${escape(item.avoidWhen)}</p></div><h4>조건을 바꾼 요청 예시</h4>${variants}<h4>제작 후 확인</h4><ul>${checks}</ul><p class="hint">관련 옵션과 확인할 항목: ${escape((item.fields||[]).join(' · '))}</p><p class="hint">근거: ${escape(Array.isArray(item.source)?item.source.join(" · "):item.source)}</p></details><button class="secondary recipe-copy" type="button" data-recipe-id="${escape(item.id)}">기본 프롬프트 복사</button></article>`;
  }
  function styleRequest(item,engine='YuE'){
    if(typeof item?.stylePrompt!=='string'||!item.stylePrompt.trim()||!['ACE','YuE'].includes(engine))return null;
    const lines=[`${item.title} 분위기의 CCM ${item.instrumental?'연주곡':'보컬곡'}을 준비해 줘.`,`${item.description}`,`참고할 설정: ${item.purpose}.`];
    if(item.instrumental)lines.push('새 연주곡 입력은 instrumental:true, lyrics:""로 준비해 줘. 기존 보컬곡이나 승인 가사를 연주곡으로 자동 전환하지 마.');
    else lines.push('제공하거나 승인한 가사는 그대로 유지해 줘. 가사가 없을 때만 주제에 맞는 새 가사 초안을 제안해 줘.');
    if(item.instruments?.length)lines.push('악기는 '+item.instruments.join(', ')+' 중심으로 요청하되 실제 편성과 음색을 보장하는 설정으로 설명하지 마.');
    lines.push('다음 영문 태그를 style에 반영해 줘.\n'+item.stylePrompt);
    lines.push(engine==='YuE'?'yue:capabilities와 song:prepare로 실제 전달되는 가사와 style, 실효 옵션을 보여 줘. 목표 초는 기록용이며 실제 길이와 보컬 포함 여부는 생성 후 따로 확인해 줘.':'song:prepare로 실제 전달되는 가사와 style을 보여 줘. 최종 caption 512자와 정리된 가사 4,096자 이내인지 확인해 줘.');
    lines.push('먼저 가사와 최종 입력을 검토할 수 있게 보여 주고, 승인 전에는 생성하거나 모델을 설치하지 마.');
    return enginePrompt({engine:'공통'},lines.join('\n\n'),engine);
  }
  function styleCard(item,selectedTag='',engine='YuE'){
    const request=styleRequest(item,engine),settings=String(item.purpose||'').replace(String(item.title||'')+' · ','');
    const content=request?`<details><summary>스타일 태그와 제작 요청 보기</summary><h4>영문 스타일 태그</h4><p class="hint">음악의 장르와 분위기, 편곡을 설명하는 문구입니다. style 입력에 사용할 수 있습니다.</p><pre class="recipe-prompt">${escape(item.stylePrompt)}</pre><h4>${escape(engine)}용 제작 요청</h4><p class="hint">위 태그에 선택한 모델과 가사 보존, 입력 검토 조건을 더한 요청입니다.</p><pre class="recipe-prompt">${escape(request)}</pre></details><div class="recipe-style-actions"><button type="button" class="secondary recipe-copy" data-style-id="${escape(item.id)}" data-style-copy="tags">영문 스타일 태그 복사</button><button type="button" class="secondary recipe-copy" data-style-id="${escape(item.id)}" data-style-copy="request">${escape(engine)} 제작 요청 복사</button></div>`:'<p class="activity-warning">스타일 태그를 찾지 못했습니다. 가이드를 새로 고쳐 주세요.</p>';
    return `<article class="recipe-style-card"><p class="hint">${escape(item.id)} · ${escape(item.style)} · ${item.instrumental?'연주곡':'보컬곡'}</p><h3>${escape(item.title)}</h3><p>${escape(item.description)}</p><p class="hint">참고 설정: ${escape(settings)}</p>${tags(item.tags||[],selectedTag)}${content}</article>`;
  }
  function styleCopyValue(styles,id,kind,engine){const item=styles.find(x=>x.id===id);if(typeof item?.stylePrompt!=='string'||!item.stylePrompt.trim())return null;return kind==='tags'?item.stylePrompt:kind==='request'?styleRequest(item,engine):null}
  function copyValue(guides,id,variation,engine){const item=guides.find(x=>x.id===id);if(!item)return null;const base=enginePrompt(item,item.prompt,engine);if(variation===undefined)return base;const change=item.variations?.[Number(variation)]?.prompt;return change?base+'\n\n위 기본 요청에서 아래에 적은 내용만 바꿔 줘. 나머지 엔진 선택과 원문 보존, 검토 범위는 그대로 유지해 줘.\n'+change:null}
  return {escape,match,tags,card,copyValue,styleRequest,styleCard,styleCopyValue};
})();
{
  const host=document.querySelector('#recipeList');
  if(host){
    const $=selector=>document.querySelector(selector),ui=window.RoadMusicRecipes,boot=window.__STUDIO_BOOTSTRAP__,ccm=boot.recipeCollection==='ccm';
    const url=path=>{const result=new URL(path,location.href);result.searchParams.set('token',boot.token);return result.pathname+result.search+result.hash};
    const controls={search:'#recipeSearch',engine:'#recipeEngine',purpose:'#recipePurpose',category:'#recipeCategory',style:'#recipeStyle',tag:'#recipeTag'};
    let guides=[],styles=[],shown=12,loaded=false;
    document.title=ccm?'Road Music CCM 전문 제작 가이드':'Road Music 공개 명령 상세 활용 가이드';$('#recipeTitle').textContent=ccm?'CCM 전문 제작 가이드':'공개 명령 상세 활용 가이드';$('#recipeIntro').textContent=ccm?'ACE·YuE의 CCM 지식과 회중·특송·기도·묵상용 편곡, 고급 공개 명령을 연결한 활용 예시입니다.':'장르·스타일·악기·옵션과 공개 명령을 조합한 상세 요청 예시입니다. 요소별 역할과 바꿔 쓰는 방법을 함께 확인하세요.';
    $('#ccmPrimer').hidden=!ccm;$('#recipeOther').textContent=ccm?'일반 명령 조합 가이드':'CCM 전문 가이드';$('#recipeOther').href=url(ccm?'/recipes/':'/ccm/');$('#recipeReference').href=url('/reference/');$('#recipeGuide').href=url(ccm?'/guide/ccm/':'/guide/reference/');$('#ccmKnowledge').href=url('/guide/ccm/');$('#recipeYueAdvanced').href=url('/guide/yue-advanced/?engine=YuE');$('#ccmFoundations').href=url('/guide/ccm-library/');$('#ccmAdvanced').href=url('/guide/ccm-advanced/');
    const filters=()=>Object.fromEntries(Object.entries(controls).map(([key,selector])=>[key,$(selector).value.trim()]));
    function render(){
      if(!['ACE','YuE'].includes($('#recipeEngine').value))$('#recipeEngine').value='YuE';
      const values=filters();for(const button of [$('#recipeEngineAce'),$('#recipeEngineYue')])button.setAttribute('aria-pressed',String(button.dataset.engine===values.engine));
      for(const article of document.querySelectorAll('[data-recipe-model]'))article.hidden=article.dataset.recipeModel!==values.engine;
      $('#ccmPrimerTitle').textContent=values.engine+' CCM 제작 기본 안내';
      for(const id of ['recipeGuide','ccmKnowledge','ccmFoundations','ccmAdvanced']){const link=$('#'+id),target=new URL(link.href,location.href);target.searchParams.set('engine',values.engine);link.href=target.href}
      $('#recipeYueAdvanced').hidden=values.engine!=='YuE';$('#recipeYueAdvanced').href=url('/guide/yue-advanced/?engine=YuE');
      const matches=guides.filter(item=>ui.match(item,values));host.innerHTML=matches.slice(0,shown).map(item=>ui.card(item,values.tag,values.engine)).join('')||'<div class="empty-state"><h3>조건에 맞는 예시가 없습니다</h3><p>태그나 검색어를 바꾸거나 전체 보기로 돌아가세요.</p></div>';
      $('#recipeMore').hidden=shown>=matches.length;$('#recipeStatus').textContent=`활용 예시 ${matches.length}개 / 전체 ${guides.length}개 · ${Math.min(shown,matches.length)}개 표시`;
      const styleMatches=styles.filter(item=>ui.match(item,{...values,engine:'',category:''}));$('#recipeStyles').hidden=!styles.length;$('#recipeStyleStatus').textContent=`스타일 ${styleMatches.length}개 / 전체 ${styles.length}개`;
      $('#recipeStyleList').innerHTML=styleMatches.map(item=>ui.styleCard(item,values.tag,values.engine)).join('')||'<p>현재 필터에 맞는 스타일이 없습니다. 전체 보기로 돌아가세요.</p>';
      const state=new URL(location.href);for(const [key,value]of Object.entries(values)){if(value)state.searchParams.set(key,value);else state.searchParams.delete(key)}history.replaceState(null,'',state.pathname+state.search);
    }
    function options(){for(const key of ['purpose','category','style','tag']){const select=$(controls[key]),old=select.value,values=[...new Set((['purpose','style','tag'].includes(key)?guides.concat(styles):guides).flatMap(x=>key==='tag'?(x.tags||[]).filter(tag=>!/^(ACE|YuE)$/i.test(tag)):(x[key]?[x[key]]:[])))].sort((a,b)=>a.localeCompare(b,'ko'));select.innerHTML=select.innerHTML.split('</option>')[0]+'</option>'+values.map(x=>`<option value="${ui.escape(x)}">${ui.escape(x)}</option>`).join('');if(values.includes(old))select.value=old}}
    async function load(){const refresh=$('#recipeRefresh');refresh.disabled=true;host.setAttribute('aria-busy','true');$('#recipeStatus').classList.remove('message-error');$('#recipeStatus').textContent='프롬프트 예시를 불러오는 중…';try{const response=await fetch(url(ccm?'/api/ccm':'/api/recipes'),{signal:AbortSignal.timeout(10000)}),data=await response.json();if(!response.ok||data.state!=='ready')throw Error(data.error||'활용 자료를 읽지 못했습니다.');guides=data.guides||[];styles=data.styles||[];options();if(!loaded){const params=new URL(location.href).searchParams;for(const [key,selector]of Object.entries(controls)){const value=params.get(key)||'';if(key==='engine'){$(selector).value=['ACE','YuE'].includes(value)?value:'YuE'}else if(key==='search'||[...$(selector).options].some(x=>x.value===value))$(selector).value=value}loaded=true}render()}catch(error){$('#recipeStatus').classList.add('message-error');$('#recipeStatus').textContent='가이드를 불러오지 못했습니다: '+(error.message||'연결을 확인하세요.')+' 새로 고침으로 다시 확인할 수 있습니다.'}finally{refresh.disabled=false;host.setAttribute('aria-busy','false')}}
    async function copy(button){const text=button.dataset.styleId?ui.styleCopyValue(styles,button.dataset.styleId,button.dataset.styleCopy,$('#recipeEngine').value):ui.copyValue(guides,button.dataset.recipeId,button.dataset.variation,$('#recipeEngine').value),fallback=$('#recipeCopyFallback');if(text===null){$('#recipeCopyStatus').textContent='복사할 예시를 찾지 못했습니다. 가이드를 새로 고쳐 주세요.';return}try{await navigator.clipboard.writeText(text);fallback.hidden=true;$('#recipeCopyStatus').textContent=button.dataset.styleCopy==='tags'?'영문 스타일 태그를 복사했습니다. style 입력에 붙여 넣어 사용하세요.':button.dataset.styleCopy==='request'?$('#recipeEngine').value+'용 제작 요청을 복사했습니다. 가사와 설정을 검토한 뒤 사용하세요.':'프롬프트를 복사했습니다. 새 요청에 붙여 넣고 필요한 부분을 바꿔 쓰세요.';const label=button.textContent;button.textContent='복사했습니다';setTimeout(()=>{button.textContent=label},1600)}catch{fallback.hidden=false;fallback.value=text;fallback.focus();fallback.select();$('#recipeCopyStatus').textContent='자동 복사를 허용하지 않았습니다. 선택된 프롬프트를 직접 복사해 주세요.'}}
    $('#recipeFilters').addEventListener('submit',event=>event.preventDefault());for(const [key,selector]of Object.entries(controls).filter(([key])=>key!=='engine'))$(selector).addEventListener(key==='search'?'input':'change',()=>{shown=12;if(loaded)render()});$('#recipeReset').addEventListener('click',()=>{for(const [key,selector] of Object.entries(controls))$(selector).value=key==='engine'?'YuE':'';shown=12;if(loaded)render()});$('#recipeMore').addEventListener('click',()=>{shown+=12;render()});$('#recipeRefresh').addEventListener('click',load);
    for(const parent of [host,$('#recipeStyleList')])parent.addEventListener('click',event=>{const button=event.target.closest('button');if(button?.matches('.recipe-copy'))copy(button);else if(button?.dataset.recipeTag){$('#recipeTag').value=button.dataset.recipeTag;shown=12;render();$('#recipeStatus').scrollIntoView({block:'nearest'})}});
    for(const button of [$('#recipeEngineAce'),$('#recipeEngineYue')])button.addEventListener('click',()=>{$('#recipeEngine').value=button.dataset.engine;shown=12;if(loaded)render()});
    load();
  }
}
