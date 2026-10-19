import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const context=vm.createContext({window:{},document:{querySelector(){return null}},String,JSON,Object});
const script=readFileSync(new URL('../assets/recipe-library.js',import.meta.url),'utf8');vm.runInContext(script,context);
const ui=context.window.RoadMusicRecipes;
const guide={id:'example',engine:'YuE',purpose:'회중',style:'모던 워십',category:'고급 활용',title:'<script>고백</script>',summary:'명확한 가사',tags:['CCM','기도'],expected:'절제된 편성',prompt:'승인 가사를 유지해줘.',useWhen:'작은 공동체',avoidWhen:'가사 교체 금지',source:'docs/ccm-advanced.md',fields:['cot'],ingredients:[{label:'편성',detail:'피아노와 작은 밴드'}],commands:[{command:'song:prepare',why:'전달본 확인'}],variations:[{title:'다른 편성',prompt:'첼로만 더해줘.'}],checks:['실제 가창 확인']};
assert.ok(ui.match(guide,{search:'피아노',engine:'YuE',purpose:'회중',style:'모던 워십',tag:'기도'}));
assert.ok(!ui.match(guide,{engine:'ACE'}));assert.ok(!ui.match(guide,{tag:'가스펠'}));
assert.ok(ui.match({...guide,engine:'공통'},{engine:'ACE'}));
const html=ui.card(guide);assert.ok(html.includes('&lt;script&gt;고백&lt;/script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(html.includes('<details>'));assert.ok(html.includes('song:prepare'));assert.ok(html.includes('전달본 확인'));assert.ok(html.includes('피아노와 작은 밴드'));assert.ok(html.includes('data-variation="0"'));assert.ok(html.includes('실제 가창 확인'));
assert.equal(ui.copyValue([guide],'example'),guide.prompt);assert.ok(ui.copyValue([guide],'example','0').startsWith(guide.prompt));assert.ok(ui.copyValue([guide],'example','0').endsWith('첼로만 더해줘.'));
assert.ok(ui.copyValue([{...guide,engine:'공통'}],'example',undefined,'YuE').includes('engine:"yue-mlx"'));assert.equal(ui.copyValue([guide],'example','9'),null);assert.equal(ui.copyValue([guide],'missing'),null);
assert.ok(!script.includes('song:generate --'));assert.ok(script.includes('history.replaceState'));assert.ok(script.includes('shown=12'));
console.log('recipe UI: combined filters, shared-engine cases, escaped content, ordered command rationale, copy variants and bounded initial cards pass');
const style={id:'C01',title:'포크 신앙고백',style:'복음성가·찬송',purpose:'포크 신앙고백 · 92 BPM · 180초',tags:['CCM','보컬'],description:'따뜻한 통기타 반주로 감사의 고백을 전하는 포크 찬양입니다.',stylePrompt:'Korean Christian folk, warm male lead, simple chorus',instruments:['acoustic guitar','piano'],instrumental:false};
const styleHtml=ui.styleCard(style,'','YuE');
assert.ok(styleHtml.includes(style.description));assert.ok(styleHtml.includes('영문 스타일 태그 복사'));assert.ok(styleHtml.includes('제작 요청 복사'));assert.ok(styleHtml.includes('data-style-id="C01"'));assert.ok(styleHtml.includes(style.stylePrompt));
assert.equal(ui.styleCopyValue([style],'C01','tags','ACE'),style.stylePrompt);
assert.equal(ui.styleCopyValue([style],'missing','tags','YuE'),null);
assert.equal(ui.styleCopyValue([style],'C01','invalid','YuE'),null);
const yueRequest=ui.styleCopyValue([style],'C01','request','YuE');assert.ok(yueRequest.includes('engine:"yue-mlx"'));assert.ok(!yueRequest.includes('engine:"ace"'));assert.ok(yueRequest.includes(style.stylePrompt));assert.ok(yueRequest.includes('승인'));
const aceRequest=ui.styleCopyValue([style],'C01','request','ACE');assert.ok(aceRequest.includes('engine:"ace"'));assert.ok(!aceRequest.includes('engine:"yue-mlx"'));
const instrumentalRequest=ui.styleRequest({...style,instrumental:true},'YuE');assert.ok(instrumentalRequest.includes('instrumental:true'));assert.ok(instrumentalRequest.includes('lyrics:""'));assert.ok(instrumentalRequest.includes('보컬'));
assert.equal(ui.styleCopyValue([{...style,stylePrompt:''}],'C01','request','YuE'),null);
assert.equal(ui.styleCopyValue([{...style,stylePrompt:{}}],'C01','tags','YuE'),null);
assert.ok(!ui.styleCard({...style,title:'<script>안전</script>'},'','ACE').includes('<script>'));
console.log('style prompts: distinct raw/request copies, selected model, instrumental scope, missing data and escaped display pass');
const bundled=JSON.parse(readFileSync(new URL('../assets/knowledge/ccm-recipes.json',import.meta.url),'utf8'));
assert.equal(bundled.styles.length,48);
for(const item of bundled.styles){
  assert.ok(item.description&&item.stylePrompt,item.id);
  for(const engine of ['YuE','ACE']){
    assert.equal(ui.styleCopyValue(bundled.styles,item.id,'tags',engine),item.stylePrompt);
    const request=ui.styleCopyValue(bundled.styles,item.id,'request',engine);
    assert.ok(request.includes(item.stylePrompt),item.id);
    assert.ok(request.includes(engine==='YuE'?'engine:"yue-mlx"':'engine:"ace"'),item.id);
    const markup=ui.styleCard(item,'',engine);
    assert.equal((markup.match(/data-style-copy=/g)||[]).length,2,item.id);
  }
}
console.log('all 48 styles expose their descriptions and both correct copy actions for YuE and ACE');
