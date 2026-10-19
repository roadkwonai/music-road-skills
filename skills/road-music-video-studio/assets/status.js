'use strict';
const statusBoot = window.__STUDIO_BOOTSTRAP__;
const status$ = selector => document.querySelector(selector);
const statusBusyTargets = ['#cliStatus', '#runtimeStatus', '#storageCapabilityStatus', '#skillStatus'];
const statusEscape = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
const statusUrl = path => `${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(statusBoot.token)}`;
const statusLabel = value => ({ enabled: '활성화', disabled: '비활성화', connected: '연결됨', available: '확인됨', 'not-running': '연결된 서비스 없음', 'not-checked': '확인하지 않음', missing: '찾지 못함', unavailable: '사용 불가', failed: '확인 실패', timeout: '시간 초과', 'invalid-response': '응답 형식 오류', stopping: '종료 중' }[value] || value || '상태 미기록');
const statusBadge = state => `<span class="status-badge" data-state="${statusEscape(state)}">${statusEscape(statusLabel(state))}</span>`;
async function statusRequest() {
  const response = await fetch(statusUrl('/api/status'), { signal: AbortSignal.timeout(40000) });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '환경 상태를 읽지 못했습니다.');
  return data;
}
function statusRows(value) {
  if (!value || typeof value !== 'object') return '<p class="status-empty">표시할 세부 정보가 없습니다.</p>';
  const items = Object.entries(value);
  if (!items.length) return '<p class="status-empty">표시할 세부 정보가 없습니다.</p>';
  const visible = items.slice(0, 6);
  const more = items.length - visible.length;
  return `<dl>${visible.map(([key, item]) => `<dt>${statusEscape(statusKeyLabel(key))}</dt><dd>${statusValue(item)}</dd>`).join('')}${more ? `<dt>추가 항목</dt><dd>${more}개 · 아래 전체 응답에서 확인</dd>` : ''}</dl>`;
}
function statusKeyLabel(key) {
  return ({ version: '버전', cliVersion: 'CLI 버전', appVersion: '앱 버전', protocolVersion: '프로토콜', commandCount: '공개 명령 수', groups: '명령 그룹', name: '이름', id: 'ID', state: '상태', root: 'CLI 위치', status: '상태', platform: '플랫폼', installed: '설치됨', available: '사용 가능', ready: '준비됨', running: '실행 중', renderer: '렌더러', ffmpeg: 'FFmpeg', count: '개수', checks: '검사 항목' })[key] || key;
}
function statusValue(value) {
  const text = statusReadable(value);
  return statusEscape(text.length > 160 ? text.slice(0, 160) + '…' : text);
}
function statusReadable(value, depth = 0) {
  if (depth > 3) return '…';
  if (Array.isArray(value)) return value.slice(0, 6).map(item => statusReadable(item, depth + 1)).filter(Boolean).join(' · ') || '없음';
  if (value && typeof value === 'object') return Object.entries(value).slice(0, 6).map(([key, item]) => `${statusKeyLabel(key)}: ${statusReadable(item, depth + 1)}`).join(' · ') || '없음';
  if (value === true) return '예';
  if (value === false) return '아니요';
  const text = String(value ?? '없음');
  return text.length > 160 ? `${text.slice(0, 160)}…` : text;
}
function statusRaw(value) {
  try { return JSON.stringify(value, null, 2); } catch { return String(value ?? ''); }
}
function statusNeedsDetails(value) {
  return (value && typeof value === 'object') || String(value ?? '').length > 160;
}
function statusCard(title, state, details) {
  const raw = statusRaw(details);
  const full = statusNeedsDetails(details) ? `<details class="status-details"><summary>전체 응답 보기</summary><pre>${statusEscape(raw)}</pre></details>` : '';
  return `<article class="status-card"><h3>${statusEscape(title)} ${statusBadge(state)}</h3>${statusRows(details)}${full}</article>`;
}
function renderStatus(data) {
  const cli = data.cli || {}, service = data.service || {}, runtime = data.runtime || {};
  status$('#cliStatus').innerHTML = statusCard('로컬 CLI', cli.state, { root: cli.root || '경로를 찾지 못했습니다', ...(cli.version || {}), ...(cli.schema || {}) }) + statusCard('기존 서비스', service.state, { 안내: service.state === 'connected' ? '기존 서비스만 조회했습니다.' : '서비스를 새로 시작하지 않았습니다.' });
  status$('#cliStatus').setAttribute('aria-busy', 'false');
  const checks = runtime.checks || {};
  status$('#runtimeStatus').innerHTML = runtime.state === 'available'
    ? Object.entries(checks).map(([command, value]) => statusCard(command, value.state, value.data || {})).join('')
    : `<div class="empty-state"><h3>기존 서비스에 연결되지 않았습니다</h3><p>이 페이지는 서비스 시작을 시도하지 않습니다. 서비스를 명시적으로 시작한 뒤 다시 확인하세요.</p></div>`;
  status$('#runtimeStatus').setAttribute('aria-busy', 'false');
  const storage = data.storage || {};
  const capabilities = storage.data?.capabilities || {};
  const labels = { projectCache: '등록 프로젝트 캐시', projectFinish: '완료한 프로젝트 작업 자료', workspaceScan: '작업 폴더 용량', retirement: '최종본 외 제작 자료', verification: '과거 설치 검증 복제본', artifacts: '과거 참조·검수 자료', sharedVideoCache: '공용 영상 캐시', git: 'Git 저장공간' };
  status$('#storageCapabilityStatus').innerHTML = storage.state === 'available' && Object.keys(capabilities).length
    ? Object.entries(capabilities).map(([key, value]) => statusCard(labels[key] || key, value.enabled === true ? 'enabled' : 'disabled', { 안내: value.reason || (value.enabled !== true ? '현재 설치에서는 사용할 수 없는 검사입니다.' : key === 'git' ? '사용 가능합니다. Git 객체 분석은 이 항목을 명시해 점검할 때만 실행합니다.' : '사용 가능한 검사입니다. 정리 실행 전 대상과 보호 상태를 확인합니다.') })).join('')
    : `<p class="status-empty">저장공간 검사 상태를 확인하지 못했습니다. ${statusEscape(statusLabel(storage.state))}</p>`;
  status$('#storageCapabilityStatus').setAttribute('aria-busy', 'false');
  status$('#skillStatus').innerHTML = (data.skills || []).map(skill => `<li><span>${statusEscape(skill.label)}</span>${statusBadge(skill.state)}</li>`).join('') || '<li class="status-empty">확인할 제작 스킬이 없습니다.</li>';
  status$('#skillStatus').setAttribute('aria-busy', 'false');
  status$('#statusMessage').textContent = `최근 확인 ${new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(data.checkedAt))}`;
}
async function refreshStatus() {
  const button = status$('#refreshStatus'), message = status$('#statusMessage'); button.disabled = true; message.classList.remove('message-error'); message.textContent = '상태를 확인하는 중…'; statusBusyTargets.forEach(selector => status$(selector).setAttribute('aria-busy', 'true'));
  try { renderStatus(await statusRequest()); } catch (error) { message.classList.add('message-error'); message.textContent = ['AbortError', 'TimeoutError'].includes(error.name) ? '상태 확인 시간이 초과되었습니다. 잠시 후 상태 새로 고침을 누르세요.' : error.name === 'TypeError' ? '제작실에 연결할 수 없습니다. 연결을 확인한 뒤 상태 새로 고침을 누르세요.' : error.name === 'SyntaxError' ? '상태 응답을 읽지 못했습니다. 상태 새로 고침을 다시 누르세요.' : error.message || '환경 상태를 읽지 못했습니다. 상태 새로 고침을 다시 누르세요.'; } finally { statusBusyTargets.forEach(selector => status$(selector).setAttribute('aria-busy', 'false')); button.disabled = false; }
}
status$('#referenceLink').href = statusUrl('/reference/');
status$('#refreshStatus').addEventListener('click', refreshStatus);
refreshStatus();
