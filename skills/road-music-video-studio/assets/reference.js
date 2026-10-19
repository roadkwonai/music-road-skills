'use strict';
const referenceBoot = window.__STUDIO_BOOTSTRAP__;
const reference$ = selector => document.querySelector(selector);
const referenceEscape = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
const referenceUrl = path => {
  const [base, hash = ''] = path.split('#', 2);
  return `${base}${base.includes('?') ? '&' : '?'}token=${encodeURIComponent(referenceBoot.token)}${hash ? `#${hash}` : ''}`;
};
const referenceKind = { read: '읽기', change: '변경', delete: '삭제' };
let referenceCommands = [];
let referenceGuides = [];

async function referenceRequest() {
  const response = await fetch(referenceUrl('/api/reference'), { signal: AbortSignal.timeout(40000) });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '공개 명령을 읽지 못했습니다.');
  return data;
}

function referenceField(field) {
  const flags = [field.required ? '필수' : '선택', field.type, field.enum ? `허용값: ${field.enum.join(', ')}` : '', field.minimum !== undefined ? `최소 ${field.minimum}` : '', field.maximum !== undefined ? `최대 ${field.maximum}` : '', field.maxLength !== undefined ? `최대 ${field.maxLength}자` : '', field.nullable ? 'null 허용' : ''].filter(Boolean).join(' · ');
  return `<li><strong>${referenceEscape(field.name)}</strong><span>${referenceEscape(flags)}</span></li>`;
}

function referenceTags(values) {
  return `<div class="reference-tags" aria-label="분류 태그">${values.map(value => `<span class="reference-tag">${referenceEscape(value)}</span>`).join('')}</div>`;
}

function referenceCommandCard(command) {
  const help = command.help || {};
  const example = help.example || command.example;
  const label = help.example ? '입력 예시 복사' : 'schema 조회 예시 복사';
  const guide = help.guide ? `<p><a class="text-link" href="${referenceUrl(`/${help.guide}`)}">상세 활용 가이드 보기</a></p>` : '';
  const notes = help.useWhen ? `<div class="reference-guide-notes"><div><strong>이럴 때 사용</strong><span>${referenceEscape(help.useWhen)}</span></div><div><strong>사용 전 주의할 점</strong><span>${referenceEscape(help.avoidWhen)}</span></div><div><strong>예상 응답</strong><span>${referenceEscape(help.expected)}</span></div></div>` : '<p class="hint">세부 목적과 입력 범위는 schema를 펼쳐 확인하세요.</p>';
  return `<article class="panel reference-card"><header><div><h4><code>${referenceEscape(command.command)}</code></h4><p><strong>무엇을 하나요:</strong> ${referenceEscape(command.description || '설명 없음')}</p></div><span class="reference-class" data-kind="${referenceEscape(command.classification)}">${referenceEscape(referenceKind[command.classification] || command.classification)}</span></header>${referenceTags([`그룹: ${command.group}`, referenceKind[command.classification] || command.classification])}${notes}${guide}<details class="reference-details"><summary>입력 필드와 schema 조회 보기</summary><h5>입력값</h5>${command.fields.length ? `<ul class="reference-fields">${command.fields.map(referenceField).join('')}</ul>` : '<p class="hint">입력이 없습니다.</p>'}</details><div class="reference-example"><code>${referenceEscape(example)}</code><button class="secondary reference-copy" type="button" data-example="${referenceEscape(command.command)}">${label}</button></div></article>`;
}

function referenceGuideCard(guide) {
  return `<article class="panel reference-card"><header><div><h4>${referenceEscape(guide.title)}</h4><p>${referenceEscape(guide.summary)}</p></div><span class="reference-class">${referenceEscape(guide.category)}</span></header>${referenceTags(guide.tags || [])}<ul class="reference-fields"><li><strong>관련 입력과 명령</strong><span>${referenceEscape((guide.fields || []).join(' · '))}</span></li><li><strong>근거</strong><span>${referenceEscape(guide.source || '현재 설치 문서')}</span></li></ul><div class="reference-guide-notes"><div><strong>이럴 때 사용</strong><span>${referenceEscape(guide.useWhen)}</span></div><div><strong>사용 전 주의할 점</strong><span>${referenceEscape(guide.avoidWhen)}</span></div><div><strong>예상되는 결과</strong><span>${referenceEscape(guide.expected)}</span></div></div><div class="reference-example"><code>${referenceEscape(guide.prompt)}</code><button class="secondary reference-copy" type="button" data-guide="${referenceEscape(guide.id)}">요청 예시 복사</button></div></article>`;
}

function referenceMatches(guide, search, category, tag) {
  const text = [guide.title, guide.summary, guide.category, ...(guide.tags || []), ...(guide.fields || []), guide.prompt].join(' ').toLocaleLowerCase('ko-KR');
  return (!search || text.includes(search)) && (!category || guide.category === category) && (!tag || (guide.tags || []).includes(tag));
}

function renderReference() {
  const search = reference$('#referenceSearch').value.trim().toLocaleLowerCase('ko-KR');
  const group = reference$('#referenceGroup').value;
  const kind = reference$('#referenceKind').value;
  const category = reference$('#referenceCategory').value;
  const tag = reference$('#referenceTag').value;
  const commands = referenceCommands.filter(command => (!search || `${command.command} ${command.description}`.toLocaleLowerCase('ko-KR').includes(search)) && (!group || command.group === group) && (!kind || command.classification === kind));
  const guides = referenceGuides.filter(guide => referenceMatches(guide, search, category, tag));
  reference$('#referenceList').innerHTML = commands.map(referenceCommandCard).join('') || '<div class="empty-state"><h4>조건에 맞는 공개 명령이 없습니다</h4><p>검색어나 명령 필터를 바꿔 보세요.</p></div>';
  reference$('#referenceGuideList').innerHTML = guides.map(referenceGuideCard).join('') || '<div class="empty-state"><h4>조건에 맞는 활용 참고가 없습니다</h4><p>검색어나 카테고리·태그 필터를 바꿔 보세요.</p></div>';
  reference$('#referenceList').setAttribute('aria-busy', 'false');
  reference$('#referenceGuideList').setAttribute('aria-busy', 'false');
  reference$('#referenceStatus').textContent = `공개 명령 ${commands.length}개 / 전체 ${referenceCommands.length}개 · 활용 참고 ${guides.length}개 / 전체 ${referenceGuides.length}개`;
}

function referenceOptions(selector, values, label) {
  reference$(selector).innerHTML = `<option value="">${label}</option>` + values.map(value => `<option value="${referenceEscape(value)}">${referenceEscape(value)}</option>`).join('');
}

async function copyExample(event) {
  const guide = referenceGuides.find(item => item.id === event.currentTarget.dataset.guide);
  const command = referenceCommands.find(item => item.command === event.currentTarget.dataset.example);
  const text = guide ? guide.prompt : command && (command.help && command.help.example || command.example);
  if (!text) return;
  const fallback = reference$('#referenceCopyFallback');
  try { await navigator.clipboard.writeText(text); fallback.hidden = true; reference$('#referenceCopyStatus').textContent = guide ? `${guide.title} 예시 요청을 복사했습니다.` : `${command.command} schema 조회 예시를 복사했습니다.`; } catch { fallback.hidden = false; fallback.value = text; fallback.focus(); fallback.select(); reference$('#referenceCopyStatus').textContent = '자동 복사를 허용하지 않아 예시를 선택했습니다. 직접 복사해 주세요.'; }
}

async function refreshReference() {
  const button = reference$('#refreshReference');
  button.disabled = true;
  reference$('#referenceStatus').textContent = 'schema와 활용 참고를 읽는 중…';
  try {
    const data = await referenceRequest();
    referenceCommands = Array.isArray(data.commands) ? data.commands : [];
    referenceGuides = Array.isArray(data.guides) ? data.guides : [];
    referenceOptions('#referenceGroup', [...new Set(referenceCommands.map(item => item.group))].sort(), '모든 그룹');
    referenceOptions('#referenceCategory', [...new Set(referenceGuides.map(item => item.category))].sort(), '전체');
    referenceOptions('#referenceTag', [...new Set(referenceGuides.flatMap(item => item.tags || []))].sort(), '전체');
    renderReference();
  } catch (error) {
    reference$('#referenceStatus').textContent = error.message;
    reference$('#referenceList').setAttribute('aria-busy', 'false');
    reference$('#referenceGuideList').setAttribute('aria-busy', 'false');
  } finally { button.disabled = false; }
}

reference$('#statusLink').href = referenceUrl('/status/');
reference$('#referenceGuideLink').href = referenceUrl('/recipes/');
reference$('#referenceCcmLink').href = referenceUrl('/ccm/');
for (const selector of ['#referenceSearch', '#referenceGroup', '#referenceKind', '#referenceCategory', '#referenceTag']) reference$(selector).addEventListener(selector === '#referenceSearch' ? 'input' : 'change', renderReference);
for (const selector of ['#referenceList', '#referenceGuideList']) reference$(selector).addEventListener('click', event => { if (event.target.matches('.reference-copy')) copyExample({ currentTarget: event.target }); });
reference$('#refreshReference').addEventListener('click', refreshReference);
refreshReference();
