'use strict';
const storageBoot = window.__STUDIO_BOOTSTRAP__;
const storage$ = selector => document.querySelector(selector);
const storageState = { data: null, overview: null, capabilities: {}, projectId: null, events: [], eventCursor: null, eventRequest: 0, tracking: null, trackingPlan: null, entityPlan: null, plan: null, sweepPlan: null, legacyPlan: null, sharedPlan: null, restructurePlan: null, maintenancePlan: null, fileRemovePlan: null, projectFinishPlan: null, activePlan: null, previewRequest: 0, confirming: false, maintenance: null, retirementStatus: {}, openMusicGroups: new Set(), helpTrigger: null, confirmTrigger: null };
const storageBytes = value => {
  const bytes = Math.max(0, Number(value) || 0);
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  const index = Math.min(units.length - 1, Math.floor(bytes ? Math.log(bytes) / Math.log(1024) : 0));
  const amount = bytes / 1024 ** index;
  return `${amount.toLocaleString('ko-KR', { maximumFractionDigits: amount < 10 && index ? 2 : 1 })} ${units[index]}`;
};
const storageKinds = { cache: '캐시', intermediate: '중간본', history: '히스토리', source: '원음', music: '음원', video: '영상', lyrics: '가사', captions: '자막', storyboard: '스토리보드', artifact: '제작 자료' };
const storageActions = { register: '프로젝트 등록', track: '파일 등록', policy: '보존 정책 변경', pin: '보존 핀 변경', cleanup: '정리', sweep: '자동 일괄 정리', 'cleanup-intent': '정리 계획 실행', 'legacy-adopt': '과거 캐시 이전', 'legacy-adopt-intent': '과거 캐시 이전 계획', 'music-change': '사용 음악 변경', 'selection-change': '영상 제작 설정 변경', 'feedback-change': '검수 의견 변경', 'title-change': '제목 변경', 'lyrics-change': '가사 변경', 'song-renamed': '노래 제목 변경', 'song-lyrics-updated': '가사 변경', 'song-generated': '음악 생성', 'song-generation-started':'음악 제작 시작', 'song-planned':'악보 계획 저장', 'song-published':'완성본 보관', 'song-replaced':'음원 교체', 'song-restored':'음원 복원', 'production-failed':'실패한 새 작업 정리', 'video.composition': '모션그래픽 영상 변경', 'project-remove': '프로젝트 제거', 'group-remove': '음악 그룹 제거', reconcile: '미연결 자료 정리' };
const storageKind = value => storageKinds[value] || value || '분류 미기록';
const storageTime = value => {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(date) : String(value || '시각 미기록');
};
const storageRequest = async (path, body, timeout = 30000) => {
  const query = path.includes('?') ? '&' : '?';
  const options = { signal: AbortSignal.timeout(timeout) };
  if (body !== undefined) options.headers = { 'Content-Type': 'application/json', Origin: location.origin, 'X-Studio-Token': storageBoot.token }, options.method = 'POST', options.body = JSON.stringify(body);
  try {
    const response = await fetch(path + query + 'token=' + encodeURIComponent(storageBoot.token), options);
    const data = await response.json();
    if (!response.ok) throw Error(data.error || '저장공간 정보를 처리하지 못했습니다.');
    return data;
  } catch (error) {
    if (error.name === 'AbortError' || error.name === 'TimeoutError') throw Error('저장공간 처리 시간이 초과되었습니다. 잠시 후 다시 시도하세요.');
    if (error.name === 'TypeError') throw Error('제작실에 연결할 수 없습니다. 연결을 확인한 뒤 다시 시도하세요.');
    throw error;
  }
};
const storageNode = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const overviewProjects = () => [
  ...(storageState.overview?.groups || []).flatMap(group => group.projects || []),
  ...(storageState.overview?.otherProjects || []).filter(project => project.kind === 'project')
];
const groupedProjects = () => (storageState.overview?.groups || []).flatMap(group => group.projects || []);
const allProjects = () => overviewProjects().length ? overviewProjects() : (storageState.data?.projects || []);
const selectedProject = () => allProjects().find(project => project.id === storageState.projectId) || null;
const selectionKey = () => 'road-music-storage-selection:' + (storageState.projectId || '');
const selectedEntryIds = () => {
  try { return new Set(JSON.parse(sessionStorage.getItem(selectionKey()) || '[]')); } catch { return new Set(); }
};
const rememberEntries = () => {
  const ids = [...document.querySelectorAll('[data-storage-entry]:checked')].map(input => input.dataset.storageEntry);
  try { sessionStorage.setItem(selectionKey(), JSON.stringify(ids)); } catch {}
  return ids;
};
const status = (message, error = false) => {
  const node = storage$('#storageStatus');
  node.textContent = message;
  node.classList.toggle('message-error', error);
};
const setBusy = busy => {
  for (const selector of ['#refreshStorage', '#previewSweep', '#saveStoragePolicy', '#previewStorage', '#previewAllStorage', '#previewProjectFinish', '#previewSharedCache', '#previewRestructure', '#trackStorage', '#confirmStorageCleanup', '#recoverStorageEntity']) {
    const node = storage$(selector); if (node) node.disabled = busy;
  }
  for (const node of document.querySelectorAll('[data-sweep-mv]')) node.disabled = busy;
  storage$('#storageProjects').setAttribute('aria-busy', String(busy));
};
const storageUrl = path => path + '?token=' + encodeURIComponent(storageBoot.token);
const projectLabel = project => project.name || project.path || '이름 없는 프로젝트';
const planKeys = ['trackingPlan', 'entityPlan', 'plan', 'sweepPlan', 'legacyPlan', 'sharedPlan', 'restructurePlan', 'maintenancePlan', 'fileRemovePlan', 'projectFinishPlan'];
function resetAllPlans() {
  for (const key of planKeys) storageState[key] = null;
  storageState.activePlan = null;
  storageState.previewRequest += 1;
  const recover = storage$('#recoverStorageEntity');
  if (recover) recover.hidden = true;
}
function invalidatePlans() {
  const dialog = storage$('#storageConfirmDialog');
  if (dialog?.open) dialog.close();
  resetAllPlans();
}
function beginPreview() {
  invalidatePlans();
  return storageState.previewRequest;
}
function activatePlan(type, plan, request) {
  if (request !== storageState.previewRequest) return false;
  storageState[type] = plan;
  storageState.activePlan = { type, plan };
  return true;
}
function blockConfirmClose(event) {
  if (!storageState.confirming) return false;
  event?.preventDefault();
  storage$('#storageConfirmSummary').textContent = '정리를 실행 중이므로 취소할 수 없습니다. 완료를 기다리세요.';
  return true;
}
function setConfirming(value) {
  storageState.confirming = value;
  storage$('#closeStorageConfirm').disabled = value;
}
function resetLegacy() { storageState.legacyPlan = null; storage$('#legacyCandidates')?.replaceChildren(); if (storage$('#previewLegacy')) storage$('#previewLegacy').disabled = true; if (storage$('#legacyStatus')) storage$('#legacyStatus').textContent = ''; }
function resetSharedCache() { storageState.sharedPlan = null; if (storage$('#sharedCacheStatus')) storage$('#sharedCacheStatus').textContent = '점검 버튼을 눌러야 현재 앱 프로필의 과거 공용 캐시를 조회합니다.'; }
function resetEntity() { storageState.entityPlan = null; const recover = storage$('#recoverStorageEntity'); if (recover) recover.hidden = true; }
function resetSweep() { storageState.sweepPlan = null; storageState.restructurePlan = null; resetProjectFinish(); resetEntity(); }
function resetMaintenancePlan() { storageState.maintenancePlan = null; }
function resetFileRemove() { storageState.fileRemovePlan = null; }
function resetProjectFinish() { storageState.projectFinishPlan = null; }
function setMaintenanceBusy(busy) {
  if (busy) {
    for (const selector of ['#loadMaintenance', '#maintenanceScope', '#selectMaintenanceCandidates', '#previewMaintenance', '#confirmStorageCleanup']) {
      const node = storage$(selector); if (node && (selector !== '#confirmStorageCleanup' || storageState.maintenancePlan?.planId)) node.disabled = true;
    }
    for (const node of document.querySelectorAll('[data-maintenance-candidate]')) node.disabled = true;
  } else {
    const scan = storageState.maintenance?.scan; const scope = maintenanceScope();
    const ready = Boolean(scan?.complete && scan?.scanId); const gitReady = ready && !storageState.maintenance?.git?.blocked;
    const selectionReady = ready && (storageState.maintenance?.candidates || []).some(item => item.scope === scope);
    storage$('#loadMaintenance').disabled = false;
    storage$('#maintenanceScope').disabled = !ready;
    storage$('#selectMaintenanceCandidates').disabled = scope === 'git' || !selectionReady;
    storage$('#previewMaintenance').disabled = scope === 'git' ? !gitReady : !selectionReady;
    for (const node of document.querySelectorAll('[data-maintenance-candidate]')) node.disabled = false;
    if (storageState.maintenancePlan?.planId) storage$('#confirmStorageCleanup').disabled = false;
  }
  storage$('#maintenanceSummary')?.setAttribute('aria-busy', String(busy));
}
function previewDetails(entries) {
  const shown = (entries || []).slice(0, 100).map(item => {
    const project = storageState.data?.projects?.find(project => project.id === item.projectId) || {};
    const entry = project.entries?.find(entry => entry.id === item.id);
    return `${projectLabel(project)} · ${item.relativePath || item.source || ''} · ${storageKind(item.kind || entry?.kind)} · ${storageBytes(item.bytes)}`;
  });
  return shown.join(' / ') + ((entries || []).length > 100 ? ` / 외 ${entries.length - 100}개` : '');
}

const maintenanceScope = () => storage$('#maintenanceScope')?.value || 'git';
const maintenanceSelectionKey = () => `road-music-maintenance-selection:${maintenanceScope()}`;
const maintenanceCandidateIds = () => [...document.querySelectorAll('[data-maintenance-candidate]:checked')].map(node => node.dataset.maintenanceCandidate);
function rememberMaintenanceCandidates() {
  try { sessionStorage.setItem(maintenanceSelectionKey(), JSON.stringify(maintenanceCandidateIds())); } catch {}
}
function selectMaintenanceCandidates() {
  const boxes = [...document.querySelectorAll('[data-maintenance-candidate]')];
  for (const box of boxes) box.checked = true;
  rememberMaintenanceCandidates();
  if (boxes.length) storage$('#previewMaintenance').disabled = false;
  storage$('#maintenanceStatus').textContent = boxes.length ? `${boxes.length}개 후보를 선택했습니다. 미리 보기로 범위를 확인하세요.` : '선택할 후보가 없습니다.';
}
function savedMaintenanceCandidates() {
  try { return new Set(JSON.parse(sessionStorage.getItem(maintenanceSelectionKey()) || '[]')); } catch { return new Set(); }
}
function maintenanceKind(value) { return value === 'git' ? 'Git 미참조 객체' : value === 'artifacts' ? '과거 제작·참조 자료' : value === 'retirement' ? '최종본 외 제작 자료' : '과거 설치 검증 복제본'; }
function maintenanceEvidence(evidence) {
  if (typeof evidence === 'string') return storageNode('span', evidence, 'hint');
  if (!evidence || typeof evidence !== 'object') return null;
  const details = storageNode('details'); const summary = storageNode('summary', '보존·근거 자세히 보기');
  details.append(summary);
  if (typeof evidence.policy === 'string') details.append(storageNode('p', evidence.policy, 'hint'));
  const append = (title, values, describe) => {
    if (!Array.isArray(values) || !values.length) return;
    const group = storageNode('div'); const list = storageNode('ul');
    group.append(storageNode('strong', title));
    for (const value of values) list.append(storageNode('li', describe(value), 'hint'));
    group.append(list); details.append(group);
  };
  append('보존되는 자료', evidence.preserved, value => typeof value === 'string' ? value : String(value?.path || '보존 항목'));
  append('근거 파일', evidence.proof, value => typeof value === 'string' ? value : `${value?.path || '근거 파일'}${value?.sha256 ? ' · 해시 확인' : ''}`);
  append('복구 근거', evidence.recovery, value => typeof value === 'string' ? value : `${value?.path || '복구 항목'}${value?.archiveMember ? ` · ${value.archiveMember}` : ''}`);
  return details;
}
function retirementFileList(item) {
  const files = Array.isArray(item.retirementFileList) ? item.retirementFileList : [];
  if (!files.length) return null;
  const details = storageNode('details');
  details.append(storageNode('summary', `삭제 파일 목록 (${files.length}개)`));
  details.addEventListener('toggle', () => {
    if (!details.open || details.dataset.loaded === 'true') return;
    const list = storageNode('pre', files.map(file => `${file.path || '경로 미기록'} · ${storageBytes(file.bytes)}`).join('\n'));
    list.className = 'hint'; list.tabIndex = 0; list.style.maxHeight = '20rem'; list.style.overflow = 'auto'; list.style.whiteSpace = 'pre-wrap'; list.style.fontFamily = 'Paperlogy, sans-serif';
    details.append(list); details.dataset.loaded = 'true';
  });
  return details;
}
function maintenanceTable(title, rows, columns) {
  const details = storageNode('details'); const caption = storageNode('summary', `${title} ${rows.length}개`); const table = storageNode('table'); const head = storageNode('thead'); const header = storageNode('tr'); const body = storageNode('tbody');
  for (const column of columns) header.append(storageNode('th', column.label));
  head.append(header); table.append(head);
  for (const row of rows) { const line = storageNode('tr'); for (const column of columns) line.append(storageNode('td', column.value(row))); body.append(line); }
  table.append(body); details.append(caption, table); return details;
}
function renderMaintenance() {
  const summary = storage$('#maintenanceSummary'); const candidates = storage$('#maintenanceCandidates'); const preview = storage$('#previewMaintenance');
  if (!summary || !candidates || !preview) return;
  summary.replaceChildren(); candidates.replaceChildren(); preview.disabled = true; storage$('#selectMaintenanceCandidates').disabled = true;
  const data = storageState.maintenance;
  const capabilities = data?.capabilities || storageState.capabilities;
  const scopeSelect = storage$('#maintenanceScope');
  const disabled = [];
  for (const option of scopeSelect.options) {
    const capability = capabilities[option.value];
    option.disabled = capability?.enabled !== true;
    option.title = option.disabled ? capability?.reason || '검사 가능 상태를 확인하지 못했습니다.' : '';
    if (option.disabled) disabled.push(`${maintenanceKind(option.value)}: ${option.title}`);
  }
  const enabledOption = [...scopeSelect.options].find(option => !option.disabled);
  scopeSelect.disabled = !enabledOption;
  if (scopeSelect.selectedOptions[0]?.disabled) scopeSelect.value = enabledOption?.value || '';
  if (disabled.length) summary.append(storageNode('p', `비활성 검사 · ${disabled.join(' / ')}`, 'hint'));
  if (!data) return;
  const scan = data.scan;
  if (!scan?.complete || !scan.scanId) {
    summary.append(storageNode('p', '전체 스캔이 완료되지 않아 정리 후보를 표시하지 않습니다.', 'hint'));
    storage$('#maintenanceScope').disabled = true;
    storage$('#maintenanceStatus').textContent = '작업 폴더 전체 스캔이 완료된 뒤 다시 시도하세요.';
    return;
  }
  const totals = scan.totals || {};
  summary.append(storageNode('p', `스캔 완료 · 파일 ${Number(totals.fileCount || 0).toLocaleString('ko-KR')}개 · 폴더 ${Number(totals.directoryCount || 0).toLocaleString('ko-KR')}개 · 논리 ${storageBytes(totals.logicalBytes)} · 할당 ${storageBytes(totals.allocatedBytes)} · symlink ${Number(totals.symlinkCount || 0).toLocaleString('ko-KR')}개(크기 미추적)`, 'hint'));
  const folderRows = Array.isArray(scan.folders) ? scan.folders : [];
  const largestRows = Array.isArray(scan.largestFiles) ? scan.largestFiles : [];
  const categoryRows = Array.isArray(scan.categories) ? scan.categories : [];
  const retirementRows = Array.isArray(data.retirementReview) ? data.retirementReview : [];
  if (folderRows.length) summary.append(maintenanceTable('상위 폴더', folderRows, [{ label: '경로', value: row => row.path || row.relativePath || '' }, { label: '할당 용량', value: row => storageBytes(row.allocatedBytes ?? row.bytes) }, { label: '파일', value: row => String(row.fileCount || 0) }]));
  if (largestRows.length) summary.append(maintenanceTable('대용량 파일', largestRows, [{ label: '경로', value: row => row.path || row.relativePath || '' }, { label: '용량', value: row => storageBytes(row.bytes) }, { label: '분류', value: row => row.classification || row.kind || '' }]));
  if (categoryRows.length) summary.append(maintenanceTable('분류', categoryRows, [{ label: '종류', value: row => row.label || row.kind || '' }, { label: '할당 용량', value: row => storageBytes(row.allocatedBytes ?? row.bytes) }, { label: '파일', value: row => String(row.fileCount || 0) }]));
  if (retirementRows.length) summary.append(maintenanceTable('최종본 외 제작 자료 검토', retirementRows, [{ label: '유형', value: row => row.label || '' }, { label: '전체', value: row => `${row.fileCount || 0}개 · ${storageBytes(row.allocatedBytes)}` }, { label: '선택 가능', value: row => `${row.eligibleFiles || 0}개 · ${storageBytes(row.eligibleAllocatedBytes)}` }, { label: '보호', value: row => `${row.protectedFiles || 0}개 · ${storageBytes(row.protectedAllocatedBytes)}` }, { label: '이유', value: row => row.reason || '' }]));
  if (scan.externalLinksCount) summary.append(storageNode('p', `외부 symlink ${scan.externalLinksCount}개는 추적·삭제하지 않습니다.`, 'hint'));
  if (scan.inventoryPath) summary.append(storageNode('p', `스캔 목록: ${scan.inventoryPath}`, 'hint'));
  if ((scan.errors || []).length) summary.append(storageNode('p', `스캔 보호·오류 ${(scan.errors || []).length}건: ${(scan.errors || []).slice(0, 3).map(item => item.message || item.reason || item.path || item).join(' · ')}`, 'hint'));
  if (data.otherFiles) summary.append(storageNode('p', `보호: ${data.otherFiles}`, 'hint'));
  const scope = maintenanceScope(); const selected = savedMaintenanceCandidates();
  const values = (data.candidates || []).filter(item => item.scope === scope);
  const git = data.git || {};
  const details = scope === 'git'
    ? `Git 미참조 객체의 논리 상한 ${git.unreachableObjects ?? git.objects?.unreachableCount ?? 0}개 · ${storageBytes(git.estimatedReclaimableLogicalBytes ?? data.summary?.gitEstimatedLogicalBytes)} 논리 예상`
    : `${maintenanceKind(scope)} 후보 ${values.length}개 · ${storageBytes(values.reduce((sum, item) => sum + (Number(item.bytes) || 0), 0))} 예상`;
  summary.append(storageNode('p', details, 'hint'));
  if (scope === 'git') summary.append(storageNode('p', 'Git 객체의 논리 크기와 실제 디스크 회수량은 packfile 구조 때문에 다를 수 있습니다.', 'hint'));
  if (scope === 'retirement') summary.append(storageNode('p', '선택한 이전 버전·중간 자료를 제거합니다. 최종본·원음·현재 모델·프로그램·최소 이력은 유지하며 일부 제작 캐시는 다시 만들어야 합니다.', 'hint'));
  if (scope === 'git' && git.inspection !== 'requested') {
    summary.append(storageNode('p', 'Git 객체는 이 목록에서 Git을 직접 선택했을 때만 점검합니다. 자동 정리나 Git 명령 실행은 하지 않습니다.', 'hint'));
  } else if (scope === 'git') {
    const row = storageNode('div', undefined, 'work-file'); const copy = storageNode('span');
    copy.append(storageNode('strong', 'Git 보호 상태와 미참조 객체'));
    copy.append(storageNode('span', git.blocked ? `보호 조건 확인 필요 · ${(git.reasons || []).join(' · ')}` : '현재 refs·reflog·모든 worktree index·최근 24시간 객체를 보존한 상태로만 미리보기를 만들 수 있습니다.', 'hint'));
    row.append(copy); candidates.append(row); preview.disabled = Boolean(git.blocked);
  }
  for (const item of scope !== 'git' ? values : []) {
    const row = storageNode('label', undefined, 'work-file'); const box = storageNode('input'); const copy = storageNode('div');
    box.type = 'checkbox'; box.dataset.maintenanceCandidate = item.id; box.checked = selected.has(item.id); box.addEventListener('change', rememberMaintenanceCandidates);
    copy.append(storageNode('strong', item.path || item.absolutePath || item.description || '정리 후보'));
    copy.append(storageNode('span', `${storageBytes(item.bytes)} · ${item.fileCount || 0}개 · ${item.description || maintenanceKind(scope)}`, 'hint'));
    if (item.kind === 'retired-distribution') copy.append(storageNode('span', '설치 ZIP 컨테이너는 제거하지만 내부 파일 내용은 공통 보관본과 고유 변경분으로 보존합니다. 원래 ZIP 바이트와 동일한 재생성은 보장하지 않습니다.', 'hint'));
    const evidence = maintenanceEvidence(item.evidence);
    if (evidence) copy.append(evidence);
    const fileList = scope === 'retirement' ? retirementFileList(item) : null;
    if (fileList) copy.append(fileList);
    row.append(box, copy); candidates.append(row);
  }
  for (const item of data.blocked || []) candidates.append(storageNode('p', `보호: ${item.path || item.relativePath || ''} · ${item.reason || '보호 항목'}`, 'hint'));
  if (scope !== 'git') { preview.disabled = !values.length; storage$('#selectMaintenanceCandidates').disabled = !values.length; }
  storage$('#maintenanceStatus').textContent = scope === 'git'
    ? (git.blocked ? 'Git 보호 조건을 확인한 뒤 다시 점검하세요.' : 'Git 미참조 객체 미리보기를 만들 수 있습니다.')
    : (values.length ? `${maintenanceKind(scope)} 후보를 선택한 뒤 미리 보기를 만드세요.` : `${maintenanceKind(scope)} 정리 후보가 없습니다.`);
}

async function loadMaintenanceHistory() {
  const node = storage$('#maintenanceHistory');
  if (!node) return;
  node.replaceChildren();
  try {
    const result = await storageRequest('/api/storage/maintenance-history');
    const events = (result.events || []).filter(event => ['maintenance-cleanup', 'mv-project-cleanup', 'sweep-cleanup'].includes(event.action) || /(?:cleanup|sweep)-(?:partial-)?failed$/.test(event.action || '')).slice(-20).reverse();
    if (!events.length) node.append(storageNode('li', '아직 확인할 정리 이력이 없습니다.', 'hint'));
    for (const event of events) {
      const label = event.action.startsWith('mv-project-cleanup') ? 'M/V 프로젝트 전체 정리' : event.action.startsWith('sweep-cleanup') ? '자동 일괄 정리' : maintenanceKind(event.scope);
      const counts = [];
      if (event.scope === 'git') counts.push(`${event.removedObjects || 0}개 객체`);
      if (Number.isFinite(event.removedProjects)) counts.push(`${event.removedProjects}개 프로젝트`);
      if (Number.isFinite(event.removedFiles)) counts.push(`${event.removedFiles}개 파일`);
      if (!counts.length) counts.push('정리 결과 수 미기록');
      const allocated = Number.isFinite(event.freedAllocatedBytes) ? storageBytes(event.freedAllocatedBytes) : '미측정';
      const disk = Number.isFinite(event.diskFreeDeltaBytes) ? ` · 디스크 여유 ${event.diskFreeDeltaBytes < 0 ? '-' : '+'}${storageBytes(Math.abs(event.diskFreeDeltaBytes))}` : '';
      const failed = /(?:cleanup|sweep)-(?:partial-)?failed$/.test(event.action || '');
      const detail = failed ? `부분 실패·보호: ${event.message || '정리 상태를 확인하세요.'}` : `${counts.join(' · ')} · 파일 할당량 감소 ${allocated}${disk}`;
      node.append(storageNode('li', `${storageTime(event.at)} · ${label} · ${detail}`));
    }
  } catch (error) { node.append(storageNode('li', error.message, 'message-error')); }
}

async function loadMaintenance(scope) {
  setMaintenanceBusy(true);
  const retirementOnly = scope === 'retirement';
  storage$('#maintenanceStatus').textContent = retirementOnly ? '이 음악의 이전 제작 자료를 빠르게 스캔하고 보호 상태를 점검하는 중…' : '작업 폴더 전체를 스캔하고 정리 후보를 점검하는 중…';
  try {
    const view = captureStorageViewState();
    invalidatePlans();
    storageState.maintenance = await storageRequest(retirementOnly ? '/api/storage/maintenance?scope=retirement' : '/api/storage/maintenance', undefined, 180000);
    renderMaintenance();
    renderProjects(); restoreStorageViewState(view);
    await loadMaintenanceHistory();
    return storageState.maintenance;
  } catch (error) { storage$('#maintenanceStatus').textContent = error.message; return null; }
  finally { setMaintenanceBusy(false); }
}

function storageVisualValue(value) { return value === null || value === undefined || value === '' ? null : (Number.isFinite(Number(value)) && Number(value) >= 0 ? Number(value) : null); }
function storageVisualChart(title, total, parts, unavailable) {
  const chart = storageNode('section', undefined, 'storage-chart');
  chart.append(storageNode('h3', title));
  if (!Number.isFinite(total) || total <= 0) {
    chart.append(storageNode('p', unavailable, 'storage-chart-unavailable'));
    chart.setAttribute('aria-label', `${title}: ${unavailable}`);
    return chart;
  }
  const safeParts = parts.filter(part => Number.isFinite(part.bytes) && part.bytes > 0);
  const bar = storageNode('div', undefined, 'storage-chart-bar');
  const label = `${title}: ${safeParts.map(part => `${part.label} ${storageBytes(part.bytes)} ${Math.round(part.bytes / total * 100)}%`).join(', ')}. 전체 ${storageBytes(total)}`;
  bar.setAttribute('role', 'img'); bar.setAttribute('aria-label', label);
  for (const part of safeParts) {
    const segment = storageNode('span', undefined, 'storage-chart-segment');
    segment.append(storageNode('span', part.label, 'storage-chart-label'));
    segment.style.color = part.textColor || '#111';
    segment.title = `${part.label} · ${storageBytes(part.bytes)} · ${Math.round(part.bytes / total * 100)}%`;
    segment.style.flexBasis = `${part.bytes / total * 100}%`; segment.style.background = part.color;
    segment.setAttribute('aria-hidden', 'true'); bar.append(segment);
  }
  const summary = storageNode('p', `전체 ${storageBytes(total)} · ${safeParts.reduce((sum, part) => sum + part.bytes, 0) === total ? '100' : Math.round(safeParts.reduce((sum, part) => sum + part.bytes, 0) / total * 100)}% 분류됨`);
  const legend = storageNode('ul', undefined, 'storage-chart-legend');
  for (const part of parts) {
    const item = storageNode('li');
    const marker = storageNode('span', undefined, 'storage-chart-mark'); marker.style.background = part.color; marker.setAttribute('aria-hidden', 'true');
    item.append(marker, storageNode('span', `${part.label} · ${storageBytes(part.bytes)} · ${Math.round(part.bytes / total * 100)}%`)); legend.append(item);
  }
  chart.append(bar, summary, legend); return chart;
}
function renderStorageVisual(disk, workspace, groups) {
  const node = storage$('#storageVisual'); if (!node) return;
  node.replaceChildren();
  const diskTotal = storageVisualValue(disk?.totalBytes);
  const diskFree = storageVisualValue(disk?.freeBytes);
  const diskUsed = storageVisualValue(disk?.usedBytes) ?? (Number.isFinite(diskTotal) && Number.isFinite(diskFree) ? Math.max(0, diskTotal - diskFree) : null);
  const diskParts = Number.isFinite(diskTotal) && Number.isFinite(diskUsed) ? [
    { label: '사용 중', bytes: Math.min(diskTotal, diskUsed), color: '#303030', textColor: '#fff' },
    { label: '남은 공간', bytes: Math.max(0, diskTotal - Math.min(diskTotal, diskUsed)), color: '#06c755' }
  ] : [];
  node.append(storageVisualChart('디스크 사용량', diskTotal, diskParts, '디스크 전체 용량을 확인할 수 없어 사용량 그래프를 표시하지 않습니다.'));
  const workspaceTotal = storageVisualValue(workspace?.allocatedBytes);
  const groupBytes = storageVisualValue(workspace?.groupBytes) ?? groups.reduce((sum, group) => sum + (storageVisualValue(group.workspaceBytes) || 0), 0);
  const parts = [
    { label: '음악 그룹', bytes: groupBytes, color: '#06c755' },
    { label: '모델·프로그램', bytes: storageVisualValue(workspace?.systemBytes) || 0, color: '#626262', textColor: '#fff' },
    { label: '테스트 입력', bytes: storageVisualValue(workspace?.testInputBytes) || 0, color: '#e9a820' },
    { label: '미연결 자료', bytes: storageVisualValue(workspace?.unattributedBytes) || 0, color: '#d84d4d' }
  ];
  const known = parts.reduce((sum, part) => sum + part.bytes, 0);
  if (Number.isFinite(workspaceTotal) && workspaceTotal > known) parts.push({ label: '기타·분류 미기록', bytes: workspaceTotal - known, color: '#8c8c8c' });
  if (Number.isFinite(workspaceTotal)) { let remaining = workspaceTotal; for (const part of parts) { part.bytes = Math.min(part.bytes, remaining); remaining -= part.bytes; } }
  node.append(storageVisualChart('작업 폴더 분류', workspaceTotal, parts, '작업 폴더 전체 스캔 후 음악·모델·테스트·미연결 자료를 분류해 표시합니다.'));
}
function renderProjects() {
  const projects = storage$('#storageProjects');
  const totals = storage$('#storageTotals');
  projects.replaceChildren(); totals.replaceChildren();
  const overview = storageState.overview || {};
  const groups = Array.isArray(overview.groups) ? overview.groups : [];
  renderOtherProjects(overview.otherProjects || []);
  if (!groups.length) {
    projects.append(storageNode('p', '음악별로 묶을 수 있는 제작 작업이 없습니다. 현재 제작실 또는 내 작업물에서 실제 음악 작업을 열어 주세요.', 'hint'));
    return;
  }
  const disk = overview.disk || storageState.data?.disk || {};
  const workspace = overview.overall?.workspace || overview.workspace || {};
  renderStorageVisual(disk, workspace, groups);
  const totalProjects = groups.reduce((count, group) => count + (group.projects || []).length + (group.mvProjects || []).length, 0);
  if (workspace.available === false && workspace.cacheState) {
    totals.append(storageNode('p', `작업 폴더 전체 용량은 ${workspace.cacheState === 'scan-required' ? '전체 스캔 후' : '새 스캔 후'} 표시됩니다.`, 'storage-workspace-total'));
  } else if (Number.isFinite(workspace.allocatedBytes)) {
    totals.append(storageNode('p', `작업 폴더 전체 ${storageBytes(workspace.allocatedBytes)} · 파일 ${Number(workspace.fileCount || 0).toLocaleString('ko-KR')}개`, 'storage-workspace-total'));
    totals.append(storageNode('p', `미연결 자료 ${storageBytes(workspace.unattributedBytes)} · 모델·프로그램 ${storageBytes(workspace.systemBytes)}${workspace.scanCreatedAt ? ` · 스캔 ${storageTime(workspace.scanCreatedAt)}` : ''}`, 'hint'));
  } else if (workspace.cacheState) {
    totals.append(storageNode('p', `작업 폴더 전체 용량은 ${workspace.cacheState === 'scan-required' ? '전체 스캔 후' : '새 스캔 후'} 표시됩니다.`, 'storage-workspace-total'));
  }
  const unattributed = unattributedFolderDetails(workspace); if (unattributed) totals.append(unattributed);
  totals.append(storageNode('p', `음악 ${groups.length}개 · 연결된 제작 작업 ${totalProjects}개 · 음악별 전체 사용량 ${workspace.available === false ? '소유권 색인 필요' : storageBytes(workspace.groupBytes ?? overview.totals?.totalBytes)} · 자동 정리 가능 ${storageBytes(overview.totals?.reclaimableBytes)} · 디스크 여유 ${storageBytes(disk.freeBytes)}`, 'hint'));
  const otherCount = Array.isArray(overview.otherProjects) ? overview.otherProjects.length : 0;
  if (otherCount) totals.append(storageNode('p', `음악에 연결되지 않은 관리 항목 ${otherCount}개는 아래 ‘기타 정리 대상·고급 관리’에서 확인할 수 있습니다.`, 'hint'));
  for (const group of groups) {
    const card = storageNode('details', undefined, 'work-row storage-music-group');
    card.open = storageState.openMusicGroups.has(group.groupId);
    card.addEventListener('toggle', () => {
      if (card.open) storageState.openMusicGroups.add(group.groupId);
      else storageState.openMusicGroups.delete(group.groupId);
    });
    const summary = storageNode('summary', undefined, 'storage-music-summary');
    const title = storageNode('strong', group.title || group.name || '이름 없는 음악');
    const meta = storageNode('span', undefined, 'storage-music-meta');
    meta.append(storageNode('span', `작업 ${(group.projects || []).length + (group.mvProjects || []).length}개`));
    const groupBytes = workspace.available === false ? null : group.workspaceBytes ?? group.totalBytes;
    meta.append(storageNode('span', Number.isFinite(groupBytes) ? `작업 폴더 ${storageBytes(groupBytes)} · ${Number(group.workspaceFileCount || 0).toLocaleString('ko-KR')}개` : '작업 폴더 소유권 색인 필요'));
    if (workspace.available !== false) meta.append(storageNode('span', `관리 캐시·이력 ${storageBytes(group.managedWorkspaceBytes ?? group.totalBytes)} · 완성본 등 ${storageBytes(group.unmanagedBytes)}`));
    meta.append(storageNode('span', `등록 캐시 정리 가능 ${storageBytes(group.reclaimableBytes)}`));
    meta.append(storageNode('span', retirementSummaryForGroup(group)));
    summary.append(title, meta); card.append(summary);
    const body = storageNode('div', undefined, 'storage-music-body');
    body.append(storageNode('p', '원음·최종본은 유지합니다. 등록 캐시와 제작 폴더의 미등록 자료를 구분해 확인할 수 있습니다.', 'hint'));
    if (/^[a-f0-9]{64}$/i.test(String(group.groupId || ''))) { const versions = storageNode('a', '이 음악의 버전·변경 이력 보기', 'button secondary'); versions.href = storageUrl(`/works/${group.groupId}/`) + '#work-versions'; body.append(versions); }
    const files = groupFileDetails(group); if (files) body.append(files);
    const producer = producerProjectDetails(group); if (producer) body.append(producer);
    for (const project of group.projects || []) body.append(projectCard(project));
    const mvProjects = group.mvProjects || [];
    if (mvProjects.length) {
      const mvTitle = storageNode('h3', 'M/V·애니매틱 프로젝트');
      body.append(mvTitle);
      for (const mv of mvProjects) body.append(mvProjectRow(mv));
      const action = storageNode('button', '선택한 M/V 프로젝트 전체 정리 미리 보기');
      action.type = 'button'; action.className = 'secondary'; action.dataset.sweepMv = 'true';
      action.addEventListener('click', event => previewSweep(event, selectedMvProjectIds(card)));
      body.append(action);
    }
    const retirement = storageNode('button', '이 음악의 이전 제작 자료 선택', 'secondary');
    retirement.type = 'button'; retirement.addEventListener('click', event => selectRetirementForGroup(group, event.currentTarget));
    const retirementStatus = storageNode('p', storageState.retirementStatus[group.groupId] || '스캔 후 이 음악에 연결된 이전 제작 자료만 선택합니다.', 'hint'); retirementStatus.dataset.groupRetirementStatus = group.groupId; retirementStatus.setAttribute('role', 'status');
    const removeGroup = storageNode('button', '이 음악 그룹 전체 제거', 'secondary');
    removeGroup.type = 'button';
    const removeStatus = storageNode('p', '완성본·버전·변경 이력도 함께 제거되는 범위를 먼저 확인합니다.', 'hint'); removeStatus.setAttribute('role', 'status');
    removeGroup.addEventListener('click', event => previewEntityRemoval('group', group.groupId, event.currentTarget, removeStatus));
    body.append(retirement, retirementStatus, removeGroup, removeStatus);
    card.append(body); projects.append(card);
  }
}

function unattributedFolderDetails(workspace) {
  const values = Array.isArray(workspace.unattributedFolders) ? workspace.unattributedFolders : [];
  if (!values.length) return null;
  const details = storageNode('details'); const list = storageNode('ul');
  details.append(storageNode('summary', `미연결 폴더 ${values.length}개 자세히 보기`));
  for (const item of values) list.append(storageNode('li', `${item.path || '경로 미기록'} · ${storageBytes(item.allocatedBytes)} · ${Number(item.fileCount || 0).toLocaleString('ko-KR')}개${item.reason ? ` · ${item.reason}` : ''}`, 'hint'));
  details.append(list); return details;
}

function producerProjectDetails(group) {
  const values = Array.isArray(group.producerProjects) ? group.producerProjects : [];
  if (!values.length) return null;
  const details = storageNode('details'); const list = storageNode('ul');
  details.append(storageNode('summary', `이 음악의 제작 폴더 ${values.length}개 · ${storageBytes(group.workspaceBytes)} · ${Number(group.workspaceFileCount || 0).toLocaleString('ko-KR')}개`));
  for (const item of values) list.append(storageNode('li', `${item.role || '제작 자료'} · ${storageBytes(item.bytes)} · ${Number(item.fileCount || 0).toLocaleString('ko-KR')}개 · ${item.path || '경로 미기록'}`, 'hint'));
  details.append(list); return details;
}

function groupFileDetails(group) {
  const values = Array.isArray(group.files) ? group.files : [];
  if (!values.length || !/^[a-f0-9]{64}$/i.test(String(group.groupId || ''))) return null;
  const details = storageNode('details'); const list = storageNode('div', undefined, 'work-files');
  details.append(storageNode('summary', `등록된 원음·완성 파일 ${values.length}개`));
  for (const file of values) {
    if (!file || typeof file.id !== 'string' || typeof file.kind !== 'string') continue;
    const row = storageNode('div', undefined, 'work-file'); const copy = storageNode('div');
    const available = file.available === true;
    copy.append(storageNode('strong', file.name || `${storageKind(file.kind)} 파일`));
    copy.append(storageNode('span', `${storageKind(file.kind)} · ${storageBytes(file.size)} · ${available ? '검증됨' : '경로·해시 확인 필요'}`, 'hint'));
    if (file.path) copy.append(storageNode('span', file.path, 'hint'));
    if (available && ['source', 'music', 'video'].includes(file.kind)) {
      const media = document.createElement(file.kind === 'video' ? 'video' : 'audio');
      media.className = 'storage-file-media'; media.controls = true; media.preload = 'metadata'; media.src = storageUrl(`/works/${group.groupId}/files/${file.id}`);
      if (file.kind === 'video') media.playsInline = true;
      media.setAttribute('aria-label', `${file.name || storageKind(file.kind)} 재생`); copy.append(media);
    }
    if (available) {
      const actions = storageNode('div', undefined, 'storage-file-actions');
      const download = storageNode('a', '다운로드', 'button secondary'); download.href = storageUrl(`/works/${group.groupId}/files/${file.id}`) + '&download=1'; download.download = file.name || ''; actions.append(download);
      const remove = storageNode('button', file.removeDisabled === false ? '이 파일 정리' : '보호됨', 'secondary'); remove.type = 'button';
      const removeStatus = storageNode('p', '', 'hint'); removeStatus.dataset.fileRemoveStatus = `${group.groupId}:${file.id}`; removeStatus.setAttribute('role', 'status');
      if (file.removeDisabled !== false) {
        remove.disabled = true; remove.title = file.protectedReason || '현재 참조·원음·완성본 또는 보호 파일입니다.';
        removeStatus.textContent = `보호: ${remove.title}`;
      } else remove.addEventListener('click', event => previewFileRemoval(group, file, event.currentTarget, removeStatus));
      actions.append(remove); copy.append(actions, removeStatus);
    }
    row.append(copy); list.append(row);
  }
  details.append(list); return details;
}

async function previewFileRemoval(group, file, trigger, inline) {
  try {
    trigger.disabled = true;
    if (inline) inline.textContent = '파일과 연결을 점검하는 중…';
    const request = beginPreview();
    const plan = await storageRequest('/api/storage/file-remove-preview', { groupId: group.groupId, fileId: file.id });
    if (request !== storageState.previewRequest) return;
    if (!plan?.planId) throw Error(plan?.file?.protectedReason || plan?.protectedReason || '이 파일은 현재 정리할 수 없습니다.');
    if (!activatePlan('fileRemovePlan', plan, request)) return;
    storage$('#storageConfirmTitle').textContent = '등록된 파일을 정리할까요?';
    storage$('#confirmStorageCleanup').textContent = '이 파일 정리';
    storage$('#storageConfirmSummary').textContent = `${plan.file?.name || file.name || '파일'} · ${storageBytes(plan.file?.size ?? file.size)}를 정리할 계획입니다.`;
    storage$('#storageBlocked').textContent = [...(plan.dependencies || []).map(item => `보호: ${item.path || item.name || ''} · ${item.reason || '현재 참조 파일'}`), ...(plan.metadataReferences || []).map(item => `함께 갱신: ${item.path || item.project || item.name || '현재 프로젝트 완성본 목록'}`), ...(plan.warnings || []).map(item => `주의: ${item}`), plan.protectedReason ? `보호: ${plan.protectedReason}` : ''].filter(Boolean).join(' / ');
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = '등록 파일의 해시·참조·활성 작업을 다시 확인합니다. 원음, 현재 편집 입력과 보호 파일은 정리하지 않습니다.';
    if (inline) inline.textContent = '정리 계획을 만들었습니다. 확인 창에서 범위와 경고를 확인하세요.';
    openDialog(storage$('#storageConfirmDialog'), trigger);
  } catch (error) { if (inline) inline.textContent = `정리 계획을 만들지 못했습니다: ${error.message}`; status(error.message, true); }
  finally { trigger.disabled = false; }
}

function entityPlanDetails(plan) {
  return [
    ...(plan.targets || []).map(item => `제거: ${item.path || '경로 미기록'} · ${item.fileCount || 0}개 · ${storageBytes(item.allocatedBytes ?? item.bytes)}`),
    ...(plan.preserved || []).map(item => `보존: ${item.path || '경로 미기록'} · ${item.reason || '공유 또는 외부 원본'}`),
    ...(plan.blocked || []).map(item => `차단: ${item.path || item.projectId || ''} · ${item.reason || '보호 상태'}`),
    ...(plan.warnings || []).map(item => `주의: ${item}`)
  ].filter(Boolean).join(' / ');
}
async function previewEntityRemoval(scope, id, trigger, inline) {
  try {
    trigger.disabled = true; if (inline) inline.textContent = '프로젝트·완성본·이력·공유 참조를 확인하는 중…';
    const request = beginPreview();
    const plan = await storageRequest('/api/storage/' + (scope === 'group' ? 'group-remove-preview' : 'project-remove-preview'), scope === 'group' ? { groupId: id } : { projectId: id }, 180000);
    if (request !== storageState.previewRequest) return;
    if (plan.eligible !== true || !plan.planId) {
      if (inline) inline.textContent = `전체 제거를 시작하지 않았습니다: ${(plan.blocked || []).map(item => item.reason || '보호 상태').join(' · ') || '제거할 수 없는 범위입니다.'}`;
      return;
    }
    if (!activatePlan('entityPlan', plan, request)) return;
    storage$('#storageConfirmTitle').textContent = scope === 'group' ? '이 음악 그룹 전체를 제거할까요?' : '이 작업 전체를 제거할까요?';
    storage$('#confirmStorageCleanup').textContent = scope === 'group' ? '음악 그룹 영구 제거' : '작업 영구 제거';
    storage$('#recoverStorageEntity').hidden = true;
    const summary = plan.summary || {};
    storage$('#storageConfirmSummary').textContent = `프로젝트 ${summary.projectCount || 0}개 · 음악 그룹 ${summary.groupCount || 0}개 · 파일 ${summary.fileCount || 0}개 · ${storageBytes(summary.allocatedBytes ?? summary.bytes)} · 납품 버전 ${summary.versionCount || 0}개를 영구 제거합니다.`;
    storage$('#storageBlocked').textContent = entityPlanDetails(plan);
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = '등록된 완성본, 버전·변경 이력, 연결 경로도 함께 영구 제거합니다. 다른 음악과 공유하는 파일, 외부 원음, 모델·프로그램, 활성 작업과 핀한 자료는 보존하거나 차단합니다.';
    if (inline) inline.textContent = '전체 제거 계획을 만들었습니다. 완성본과 이력까지 포함한 범위를 확인하세요.';
    openDialog(storage$('#storageConfirmDialog'), trigger);
  } catch (error) { if (inline) inline.textContent = `전체 제거 계획을 만들지 못했습니다: ${error.message}`; status(error.message, true); }
  finally { trigger.disabled = false; }
}

function pathInside(candidate, root) {
  const normalize = value => String(value || '').replace(/\\/g, '/').replace(/\/+$/, '');
  const child = normalize(candidate); const parent = normalize(root);
  return Boolean(child && parent && (child === parent || child.startsWith(parent + '/')));
}

function retirementCandidatesForGroup(group) {
  const roots = (group.producerProjects || []).map(item => item.path).filter(Boolean);
  return (storageState.maintenance?.candidates || []).filter(item => item.scope === 'retirement' && roots.some(root => pathInside(item.absolutePath || item.path, root)));
}

function retirementSummaryForGroup(group) {
  const scan = storageState.maintenance?.scan;
  if (!scan?.complete || !scan.scanId) return '이전 제작 자료: 스캔 필요';
  const candidates = retirementCandidatesForGroup(group);
  const files = candidates.reduce((total, item) => total + (Number(item.fileCount) || 0), 0);
  const bytes = candidates.reduce((total, item) => total + (Number(item.allocatedBytes ?? item.bytes) || 0), 0);
  return candidates.length ? `이전 제작 자료: 후보 ${candidates.length}개 · 파일 ${files.toLocaleString('ko-KR')}개 · ${storageBytes(bytes)}` : '이전 제작 자료: 정리 후보 없음';
}

async function selectRetirementForGroup(group, trigger) {
  const setInline = message => {
    storageState.retirementStatus[group.groupId] = message;
    const inline = document.querySelector(`[data-group-retirement-status="${group.groupId}"]`);
    if (inline) inline.textContent = message;
  };
  storageState.openMusicGroups.add(group.groupId);
  setInline('이 음악의 이전 제작 자료를 확인하는 중…');
  if (trigger) trigger.disabled = true;
  let scan = storageState.maintenance?.scan;
  try {
    if (!scan?.complete || !scan.scanId) {
      storage$('#otherCleanup').open = true;
      const loaded = await loadMaintenance('retirement');
      scan = loaded?.scan;
      if (!scan?.complete || !scan.scanId) throw Error('작업 폴더 스캔을 완료하지 못했습니다. 보호 자료는 유지합니다.');
    }
    const candidates = retirementCandidatesForGroup(group);
    if (!candidates.length) {
      setInline('선택 가능한 이전 제작 자료가 없습니다. 원음·완성본·현재 참조 파일은 보호합니다.');
      storage$('#maintenanceStatus').textContent = storageState.retirementStatus[group.groupId];
      return;
    }
    const scope = storage$('#maintenanceScope'); scope.value = 'retirement'; invalidatePlans(); storage$('#otherCleanup').open = true; renderMaintenance();
    const selected = new Set(candidates.map(item => item.id));
    for (const box of document.querySelectorAll('[data-maintenance-candidate]')) box.checked = selected.has(box.dataset.maintenanceCandidate);
    rememberMaintenanceCandidates();
    storage$('#previewMaintenance').disabled = false;
    const message = `${group.title || group.name || '이 음악'}의 이전 제작 자료 ${selected.size}개를 선택했습니다. 아래 고급 관리에서 미리 보기로 범위를 확인하세요.`;
    setInline(message);
    storage$('#maintenanceStatus').textContent = message;
  } catch (error) {
    setInline(`선택하지 못했습니다: ${error.message}`);
    storage$('#maintenanceStatus').textContent = storageState.retirementStatus[group.groupId];
  } finally { if (trigger) trigger.disabled = false; }
}

function renderOtherProjects(items) {
  const node = storage$('#otherStorageProjects');
  if (!node) return;
  node.replaceChildren();
  if (!items.length) {
    node.append(storageNode('p', '음악에 연결되지 않은 정리 대상이 없습니다.', 'hint'));
    return;
  }
  const shown = new Set();
  for (const item of items) {
    const identity = `${item.role || item.kind || ''}\0${item.path || ''}`;
    if (shown.has(identity)) continue;
    shown.add(identity);
    const row = storageNode('div', undefined, 'work-file');
    const copy = storageNode('div');
    copy.append(storageNode('strong', item.title || item.name || (item.kind === 'ai-mv' ? '미분류 M/V 프로젝트' : '미분류 프로젝트')));
    const reason = item.reason || item.error || (item.kind === 'ai-mv' ? '음악 원음을 확인하지 못해 자동 일괄 정리에서 제외됩니다.' : '음악 작업에 연결되지 않아 자동 일괄 정리에서 제외됩니다.');
    copy.append(storageNode('span', `${storageBytes(item.allocatedBytes ?? item.totalBytes ?? item.bytes)} · ${item.fileCount || 0}개 · ${reason}`, 'hint'));
    if (item.path) copy.append(storageNode('span', item.path, 'hint'));
    row.append(copy); node.append(row);
  }
}

function projectCard(project) {
  const wrapper = storageNode('div', undefined, 'storage-project-actions');
  const card = storageNode('button', undefined, 'storage-project-card secondary');
  const unavailable = project.availability === false;
  card.type = 'button'; card.dataset.projectId = project.id;
  card.disabled = unavailable;
  card.setAttribute('aria-pressed', String(project.id === storageState.projectId));
  const title = storageNode('strong', projectLabel(project));
  const detail = storageNode('span', unavailable ? `경로 확인 필요 · ${project.error || '오프라인 보호'}` : `${project.state === 'editing' ? '편집 중' : project.state === 'completed' ? '완료됨' : '보관됨'} · ${storageBytes(project.totalBytes)} · 정리 가능 ${storageBytes(project.reclaimableBytes)}`, 'hint');
  const purpose = storageNode('span', project.description || '세부 보존 정책과 캐시 정리를 열어 확인', 'hint');
  card.append(title, detail, purpose);
  card.addEventListener('click', () => {
    storageState.projectId = project.id; storageState.events = []; storageState.eventCursor = null; invalidatePlans(); resetLegacy(); resetSharedCache();
    storage$('#projectManagement').open = true; renderStorage(); loadHistory(); loadEvents();
  });
  const remove = storageNode('button', unavailable ? '작업 전체 제거 불가' : '작업 전체 제거', 'secondary');
  remove.type = 'button'; remove.disabled = unavailable;
  const removeStatus = storageNode('p', '완성본·버전·변경 이력도 영구 제거됩니다. 공유 파일과 외부 원음은 보존합니다.', 'hint'); removeStatus.setAttribute('role', 'status');
  remove.addEventListener('click', event => previewEntityRemoval('project', project.id, event.currentTarget, removeStatus));
  wrapper.append(card, remove, removeStatus); return wrapper;
}

function mvProjectRow(project) {
  const row = storageNode('div', undefined, 'work-file');
  const box = storageNode('input'); box.type = 'checkbox'; box.dataset.mvProject = project.id;
  const version = mvVersionLabel(project);
  box.disabled = Boolean(project.blocked); box.setAttribute('aria-label', `${project.title || project.name || 'M/V 프로젝트'} ${version} 전체 정리 선택`);
  const copy = storageNode('div');
  copy.append(storageNode('strong', `${project.title || project.name || '이름 없는 M/V 프로젝트'} · ${version}`));
  const shared = project.sharedAssets || project.newMVsharedAsset ? ' · 공유 캐릭터·룩 개발 자료 포함' : '';
  const summary = project.blocked ? `보호됨 · ${(project.reasons || []).join(' · ') || '사용 중이거나 확인이 필요합니다.'}` : `${storageBytes(project.allocatedBytes ?? project.bytes)} · ${project.fileCount || 0}개${shared} · 최종 영상·애니매틱을 포함한 프로젝트 전체 정리는 직접 선택한 뒤에만 실행됩니다.`;
  copy.append(storageNode('span', summary, 'hint'));
  if (project.path) {
    const location = storageNode('details');
    location.append(storageNode('summary', '경로 보기'), storageNode('span', project.path, 'hint'));
    copy.append(location);
  }
  row.append(box, copy); return row;
}

function mvVersionLabel(project) {
  const basename = String(project.path || project.dir || '').split('/').filter(Boolean).at(-1) || '';
  const match = basename.match(/(?:^|[-_.\s])(원본[-_\s]?제작|v\d+|ver(?:sion)?[-_\s]?\d+|final|draft|animatic)(?=$|[-_.\s])/iu);
  if (!match) return '제작본';
  const value = match[1].replace(/[-_]/g, ' ');
  return /^v\d+$/iu.test(value) ? `버전 ${value}` : value;
}

function selectedMvProjectIds(scope = document) {
  return [...scope.querySelectorAll('[data-mv-project]:checked')].map(node => node.dataset.mvProject).filter(Boolean);
}

function renderPolicy(project) {
  const form = storage$('#storagePolicy');
  const disabled = !project || project.availability === false;
  for (const field of form.elements) field.disabled = disabled;
  if (storage$('#previewProjectFinish')) storage$('#previewProjectFinish').disabled = disabled;
  if (!project) return;
  form.elements.state.value = project.state || 'editing';
  form.elements.preserveHistory.checked = project.preserveHistory !== false;
  form.elements.autoCleanup.checked = project.autoCleanup !== false;
  form.elements.retainDays.value = Number.isInteger(project.retainDays) ? project.retainDays : 7;
  form.elements.maxCacheGiB.value = Number.isInteger(project.maxCacheBytes) ? project.maxCacheBytes / 1024 ** 3 : 2;
  form.elements.maxCacheFiles.value = Number.isInteger(project.maxCacheFiles) ? project.maxCacheFiles : 20000;
  const warnings = Array.isArray(project.warnings) ? project.warnings : [];
  if (project.budgetExceeded) warnings.unshift('캐시 예산을 초과했습니다. 자동 삭제가 완료됐다는 뜻은 아니므로 미리 보기를 확인하세요.');
  storage$('#storageWarnings').textContent = warnings.join(' ');
}

function renderEntries(project) {
  const entries = storage$('#storageEntries');
  const track = storage$('#storageTrack');
  entries.replaceChildren();
  for (const field of track.elements) field.disabled = !project || project.busy || project.availability === false;
  if (!project) return;
  if (project.unknownScanRequired || project.totalBytesPartial) entries.append(storageNode('p', '이 프로젝트의 미등록 파일은 아직 SQLite 소유권 색인이 필요합니다. 용량 0B나 미연결 자료 없음으로 확정하지 않으며 자동 정리 대상에도 넣지 않습니다.', 'hint'));
  const chosen = selectedEntryIds();
  const values = Array.isArray(project.entries) ? project.entries : [];
  if (!values.length) {
    entries.append(storageNode('p', '등록된 캐시·중간본·히스토리가 없습니다. 재생성 가능한 캐시는 .roadmusic/cache에 분리한 뒤 제작 도구가 등록합니다.', 'hint'));
  }
  for (const entry of values) {
    const row = storageNode('label', undefined, 'work-file');
    const checkbox = storageNode('input');
    checkbox.type = 'checkbox'; checkbox.dataset.storageEntry = entry.id;
    const manualOnly = entry.kind === 'intermediate' || entry.kind === 'history';
    checkbox.checked = chosen.has(entry.id);
    checkbox.disabled = Boolean(entry.protected || project.busy || (manualOnly && project.preserveHistory !== false));
    checkbox.addEventListener('change', rememberEntries);
    const copy = storageNode('span');
    copy.append(storageNode('strong', entry.relativePath || entry.path || '등록 항목'));
    copy.append(storageNode('span', `${storageKind(entry.kind)} · ${storageBytes(entry.bytes)} · ${entry.fileCount || 0}개`, 'hint'));
    if (entry.description) copy.append(storageNode('span', entry.description, 'hint'));
    if (entry.protected || entry.reason) copy.append(storageNode('span', entry.reason || '보호된 항목', 'hint'));
    const pin = storageNode('button', entry.pinned ? '핀 해제' : '보존 핀', 'secondary');
    pin.type = 'button'; pin.disabled = project.busy;
    pin.addEventListener('click', async event => {
      event.preventDefault();
      try { await storageRequest('/api/storage/pin', { projectId: project.id, entryId: entry.id, pinned: !entry.pinned }); await refreshStorage('핀 상태를 저장했습니다.'); }
      catch (error) { status(error.message, true); }
    });
    row.append(checkbox, copy, pin); entries.append(row);
  }
  for (const entry of project.unmanagedEntries || []) {
    const row = storageNode('div', undefined, 'work-file');
    const copy = storageNode('span');
    copy.append(storageNode('strong', entry.relativePath || '미등록 파일'));
    copy.append(storageNode('span', `${storageBytes(entry.bytes)} · ${entry.reason || '미등록 파일은 보호됩니다'}`, 'hint'));
    row.append(copy); entries.append(row);
  }
  if (project.unknownTruncated) entries.append(storageNode('p', '미등록 보호 파일이 더 있습니다. 프로젝트 내부 경로를 직접 입력해도 보호 규칙은 우회할 수 없습니다.', 'hint'));
}

function renderStorage() {
  renderProjects();
  const project = selectedProject();
  renderPolicy(project); renderEntries(project);
  const preview = storage$('#storagePreviewStatus');
  preview.textContent = storageState.plan ? `정리 계획: ${storageState.plan.fileCount || 0}개 · ${storageBytes(storageState.plan.bytes)}` : '캐시만 기본 정리 대상입니다. 중간본·히스토리는 항목을 직접 선택해야 합니다.';
}

function trackingCheck(check) {
  const row = storageNode('div', undefined, 'work-file');
  const copy = storageNode('div');
  const enabled = check?.enabled === true;
  copy.append(storageNode('strong', `${enabled ? '활성' : '비활성'} · ${check?.label || check?.id || '관리 검사'}`));
  copy.append(storageNode('span', check?.reason || (enabled ? '필요한 대상만 점검합니다.' : '현재 설치 환경에는 실행할 대상이 없습니다.'), 'hint'));
  if (check?.required) copy.append(storageNode('span', '필수 관리 항목', 'hint'));
  row.append(copy); return row;
}
function renderTracking() {
  const node = storage$('#storageTracking'); if (!node) return;
  node.replaceChildren();
  const result = storageState.tracking || {};
  const statusInfo = Array.isArray(result.status) ? result.status : (result.status || {});
  const tracking = result.tracking || result;
  const checks = Array.isArray(statusInfo) ? statusInfo : (Array.isArray(statusInfo.checks) ? statusInfo.checks : (Array.isArray(result.checks) ? result.checks : []));
  if (!checks.length) { node.append(storageNode('p', '관리 상태를 아직 불러오지 못했습니다. 새로 고침으로 현재 설치 환경만 다시 확인할 수 있습니다.', 'hint')); return; }
  for (const check of checks) node.append(trackingCheck(check));
  const ownership = tracking.ownership || tracking.summary || tracking;
  const unknown = ownership.unknown || result.unknown || {};
  const count = Array.isArray(unknown.folders) ? unknown.folders.length : Number(unknown.count ?? unknown.folderCount ?? ownership.unknownCount ?? 0);
  const bytes = Number(unknown.bytes ?? ownership.unknownBytes ?? 0);
  node.append(storageNode('p', result.scanRequired || tracking.scanRequired ? '소유권 색인을 아직 만들지 않았습니다. ‘새로 고침’에서만 작업 폴더를 색인하며, 그 전에는 미연결 자료가 없다고 판단하지 않습니다.' : count ? `미연결 자료 ${count.toLocaleString('ko-KR')}개 · ${storageBytes(bytes)}는 보호 중입니다. 자동 정리에는 포함하지 않습니다.` : '미연결 자료가 없습니다. 등록된 음악·프로젝트·정책 범위만 관리합니다.', 'hint'));
  if (tracking.lastIndexedAt || tracking.indexedAt || result.indexedAt || result.refreshedAt) node.append(storageNode('p', `경로 색인 ${storageTime(tracking.lastIndexedAt || tracking.indexedAt || result.indexedAt || result.refreshedAt)} · 평소에는 SQLite 색인을 사용하고 ‘새로 고침’에서만 다시 확인합니다.`, 'hint'));
  const reconcile = storageNode('button', 'Finder 표시 설정 정리 미리 보기', 'secondary');
  const ready = result.ready ?? (typeof result.workspace === 'string' && result.workspace.length > 0) ?? statusInfo.ready;
  reconcile.type = 'button'; reconcile.disabled = ready === false;
  reconcile.title = '프로젝트와 무관한 Finder .DS_Store만 계획으로 확인합니다. 미연결 자료는 삭제하지 않습니다.';
  reconcile.addEventListener('click', previewTrackingReconcile); node.append(reconcile);
}

function eventDetail(event) {
  const details = storageNode('details');
  details.append(storageNode('summary', '전후 값 보기'));
  const before = event?.before, after = event?.after;
  const value = item => item === undefined || item === null ? '없음' : typeof item === 'string' ? item : JSON.stringify(item, null, 2);
  details.append(storageNode('p', `이전: ${value(before)}`, 'hint'));
  details.append(storageNode('p', `변경: ${value(after)}`, 'hint'));
  if (event?.reason) details.append(storageNode('p', `사유: ${event.reason}`, 'hint'));
  return details;
}
function renderEvents() {
  const node = storage$('#storageEvents'); if (!node) return;
  node.replaceChildren();
  const events = storageState.events;
  if (!events.length) node.append(storageNode('li', '아직 기록된 변경이 없습니다. 다음 실제 저장부터 이력에 표시합니다.', 'hint'));
  for (const event of events) {
    const item = storageNode('li');
    item.append(storageNode('strong', storageActions[event.action] || event.action || '관리 변경'));
    item.append(storageNode('span', ` · ${storageTime(event.at || event.createdAt || event.time)}`, 'hint'));
    if (event.path) item.append(storageNode('span', ` · ${event.path}`, 'hint'));
    if (event.before !== undefined || event.after !== undefined || event.reason) item.append(eventDetail(event));
    node.append(item);
  }
  if (storageState.eventCursor) {
    const more = storageNode('button', '이전 변경 이력 더 보기', 'secondary'); more.type = 'button';
    more.addEventListener('click', () => loadEvents(true)); node.append(more);
  }
}
async function loadEvents(append = false) {
  const node = storage$('#storageEvents'); if (!node) return;
  const projectId = storageState.projectId;
  if (!projectId) { storageState.events = []; storageState.eventCursor = null; renderEvents(); return; }
  if (!append) { storageState.events = []; storageState.eventCursor = null; renderEvents(); }
  const cursor = append ? storageState.eventCursor : null;
  if (append && !cursor) return;
  const request = ++storageState.eventRequest;
  try {
    const path = '/api/storage/events?projectId=' + encodeURIComponent(projectId) + '&limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '');
    const result = await storageRequest(path);
    if (request !== storageState.eventRequest || storageState.projectId !== projectId) return;
    const incoming = Array.isArray(result.events) ? result.events : [];
    const seen = new Set(storageState.events.map(event => event.id));
    storageState.events = append ? [...storageState.events, ...incoming.filter(event => !seen.has(event.id))] : incoming;
    storageState.eventCursor = result.nextCursor || null; renderEvents();
  } catch (error) { if (request === storageState.eventRequest && storageState.projectId === projectId) { node.replaceChildren(storageNode('li', error.message, 'message-error')); } }
}

async function previewTrackingReconcile(event) {
  try {
    setBusy(true); const request = beginPreview();
    const plan = await storageRequest('/api/storage/reconcile-preview', {}); const summary = plan.summary || {};
    if (request !== storageState.previewRequest) return;
    if (!summary.fileCount) return status('정리할 Finder 표시 설정이 없습니다. 미연결 자료는 보호 상태로 유지합니다.');
    if (!activatePlan('trackingPlan', plan, request)) return;
    storage$('#storageConfirmTitle').textContent = 'Finder 표시 설정을 정리할까요?';
    storage$('#confirmStorageCleanup').textContent = '표시 설정 정리';
    storage$('#storageConfirmSummary').textContent = `${summary.fileCount}개 · ${storageBytes(summary.allocatedBytes)}를 정리할 계획입니다.`;
    storage$('#storageBlocked').textContent = (plan.candidates || []).map(item => `${item.relativePath || item.path || '.DS_Store'} · ${storageBytes(item.allocatedBytes)}`).join(' / ');
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = plan.protected || '미연결 자료와 원음·완성본·도구 상태는 이 정리 대상에 포함하지 않습니다.';
    openDialog(storage$('#storageConfirmDialog'), event.currentTarget);
  } catch (error) { status(error.message, true); }
  finally { setBusy(false); }
}

async function loadHistory() {
  const node = storage$('#storageHistory'); node.replaceChildren();
  if (!storageState.projectId) return;
  try {
    const result = await storageRequest('/api/storage/history?projectId=' + encodeURIComponent(storageState.projectId));
    const events = Array.isArray(result.events) ? result.events : [];
    if (!events.length) node.append(storageNode('li', '아직 기록이 없습니다.', 'hint'));
    for (const event of events) {
      const action = storageActions[event.action] || event.action || '저장공간 기록';
      const kind = event.kind ? ` · ${storageKind(event.kind)}` : '';
      const detail = event.action === 'cleanup' ? ` · ${event.removedFiles || 0}개 정리 · ${storageBytes(event.freedBytes)} 확보 · ${event.skippedCount || 0}건 건너뜀` : '';
      node.append(storageNode('li', `${storageTime(event.at || event.time)} · ${action}${kind}${detail}${event.summary ? ` · ${event.summary}` : ''}`));
    }
  } catch (error) { node.append(storageNode('li', error.message, 'message-error')); }
}

function captureStorageViewState() {
  const policy = storage$('#storagePolicy');
  return {
    projectManagement: storage$('#projectManagement')?.open,
    otherCleanup: storage$('#otherCleanup')?.open,
    groups: new Set([...document.querySelectorAll('#storageProjects .storage-music-group[open] > summary strong')].map(node => node.textContent)),
    policy: policy ? { state: policy.elements.state.value, preserveHistory: policy.elements.preserveHistory.checked, autoCleanup: policy.elements.autoCleanup.checked, retainDays: policy.elements.retainDays.value, maxCacheGiB: policy.elements.maxCacheGiB.value, maxCacheFiles: policy.elements.maxCacheFiles.value } : null
  };
}
function restoreStorageViewState(view) {
  if (!view) return;
  if (storage$('#projectManagement')) storage$('#projectManagement').open = Boolean(view.projectManagement);
  if (storage$('#otherCleanup')) storage$('#otherCleanup').open = Boolean(view.otherCleanup);
  for (const card of document.querySelectorAll('#storageProjects .storage-music-group')) if (view.groups.has(card.querySelector('summary strong')?.textContent)) card.open = true;
  const policy = storage$('#storagePolicy');
  if (!policy || !view.policy) return;
  policy.elements.state.value = view.policy.state; policy.elements.preserveHistory.checked = view.policy.preserveHistory; policy.elements.autoCleanup.checked = view.policy.autoCleanup;
  policy.elements.retainDays.value = view.policy.retainDays; policy.elements.maxCacheGiB.value = view.policy.maxCacheGiB; policy.elements.maxCacheFiles.value = view.policy.maxCacheFiles;
}
async function refreshStorage(message = '저장공간 정보를 새로 고쳤습니다.', refreshWorkspace = true) {
  setBusy(true);
  try {
    invalidatePlans();
    const view = captureStorageViewState();
    resetFileRemove();
    resetLegacy();
    let overview, inspectionStatus, tracking;
    if (refreshWorkspace) {
      [tracking, inspectionStatus] = await Promise.all([storageRequest('/api/storage/tracking?refreshWorkspace=1'), storageRequest('/api/storage/status')]);
      overview = await storageRequest('/api/storage/overview');
    } else {
      [overview, inspectionStatus, tracking] = await Promise.all([storageRequest('/api/storage/overview'), storageRequest('/api/storage/status'), storageRequest('/api/storage/tracking')]);
    }
    storageState.overview = overview;
    storageState.capabilities = inspectionStatus.capabilities || {};
    storageState.tracking = tracking;
    storageState.data = { projects: overviewProjects(), disk: overview.disk, totals: overview.totals };
    const projects = allProjects();
    const previousProjectId = storageState.projectId;
    if (!storageState.projectId || !projects.some(project => project.id === storageState.projectId && project.availability !== false)) storageState.projectId = projects.find(project => project.id === storageBoot.currentProjectId && project.availability !== false)?.id || projects.find(project => project.availability !== false)?.id || null;
    if (previousProjectId !== storageState.projectId) { storageState.events = []; storageState.eventCursor = null; }
    renderStorage(); renderTracking(); renderMaintenance(); restoreStorageViewState(view); await Promise.all([loadHistory(), loadEvents(), loadRestructureStatus()]); status(message);
  } catch (error) { status(error.message, true); }
  finally { setBusy(false); }
}

async function loadRestructureStatus() {
  const node = storage$('#restructureStatus'); if (!node) return;
  try {
    const result = await storageRequest('/api/storage/restructure-status');
    node.textContent = result.structured
      ? `완성본 전용 구조 적용됨 · 버전 ${Number(result.versionCount || 0).toLocaleString('ko-KR')}개 · 작업 경로 ${result.workingRoot || '.roadmusic/work'} · 이력 ${result.dbPath || '.roadmusic/history.sqlite3'}`
      : `기존 구조 감지됨 · 정리 미리 보기에서 보존할 완성본과 정리할 테스트 이력을 먼저 확인하세요.`;
  } catch (error) { node.textContent = error.message; }
}

function openDialog(dialog, trigger) { storageState[dialog.id === 'storageConfirmDialog' ? 'confirmTrigger' : 'helpTrigger'] = trigger; dialog.showModal(); }
function closeDialog(dialog, force = false) {
  if (dialog.id === 'storageConfirmDialog' && !force && blockConfirmClose()) return;
  dialog.close(); const trigger = storageState[dialog.id === 'storageConfirmDialog' ? 'confirmTrigger' : 'helpTrigger']; if (trigger) trigger.focus();
}
function bindInlineHelp(button) {
  const tip = button?.nextElementSibling; if (!button || !tip) return;
  const open = () => button.setAttribute('aria-expanded', 'true');
  button.addEventListener('click', open); button.addEventListener('focus', open); button.addEventListener('blur', () => button.setAttribute('aria-expanded', 'false'));
}

storage$('#refreshStorage').addEventListener('click', () => refreshStorage());
storage$('#storagePolicy').addEventListener('submit', async event => {
  event.preventDefault(); const project = selectedProject(); if (!project) return;
  const form = event.currentTarget;
  const maxCacheGiB = Number(form.elements.maxCacheGiB.value);
  const maxCacheFiles = Number(form.elements.maxCacheFiles.value);
  if (!Number.isInteger(maxCacheGiB) || !Number.isInteger(maxCacheFiles)) return status('캐시 예산은 정수로 입력하세요.', true);
  try {
    await storageRequest('/api/storage/policy', { projectId: project.id, state: form.elements.state.value, preserveHistory: form.elements.preserveHistory.checked, autoCleanup: form.elements.autoCleanup.checked, retainDays: Number(form.elements.retainDays.value), maxCacheBytes: maxCacheGiB * 1024 ** 3, maxCacheFiles });
    await refreshStorage('보존 정책을 저장했습니다.');
  } catch (error) { status(error.message, true); }
});
function sweepDetails(plan) {
  return [
    ...(plan.entries || []).map(entry => `${entry.description || entry.title || entry.path || '정리 대상'} · ${storageBytes(entry.bytes)}`),
    ...(plan.blocked || []).map(entry => `보호: ${entry.description || entry.title || entry.path || ''} · ${entry.reason || '보호 항목'}`),
    ...(plan.excluded || []).map(entry => `제외: ${typeof entry === 'string' ? entry : `${entry.description || entry.title || entry.path || ''} · ${entry.reason || '자동 정리 제외'}`}`)
  ].filter(Boolean).join(' / ');
}

async function previewSweep(event, mvProjectIds = []) {
  const mvOnly = Array.isArray(mvProjectIds) && mvProjectIds.length > 0;
  if (Array.isArray(mvProjectIds) && !mvProjectIds.length && event?.currentTarget?.textContent?.includes('M/V')) {
    return status('정리할 M/V 프로젝트를 하나 이상 선택하세요.', true);
  }
  try {
    setBusy(true); status(mvOnly ? '선택한 M/V 프로젝트를 스캔하고 전체 정리 계획을 만드는 중…' : '자동 일괄 정리 대상을 스캔하고 보호 상태를 확인하는 중…');
    const request = beginPreview();
    const plan = await storageRequest('/api/storage/sweep-preview', mvOnly ? { mvProjectIds } : {} , 180000);
    if (request !== storageState.previewRequest) return;
    const files = Number(plan.fileCount || 0);
    const bytes = plan.estimatedReclaimableBytes ?? plan.bytes;
    if (!files && !(plan.entries || []).length) {
      resetSweep();
      return status(mvOnly ? '선택한 M/V 프로젝트에서 정리할 수 있는 파일이 없습니다. 보호 파일은 유지합니다.' : '현재 보존 정책으로 정리할 대상이 없습니다. 편집 중이거나 보호된 자료는 유지합니다.');
    }
    if (!activatePlan('sweepPlan', plan, request)) return;
    storage$('#storageConfirmTitle').textContent = mvOnly ? '선택한 M/V 프로젝트 전체를 정리할까요?' : '자동 일괄 정리를 실행할까요?';
    storage$('#confirmStorageCleanup').textContent = mvOnly ? '선택한 M/V 프로젝트 전체 정리' : '자동 일괄 정리 실행';
    storage$('#storageConfirmSummary').textContent = `${files}개, ${storageBytes(bytes)}를 정리할 계획입니다.`;
    storage$('#storageBlocked').textContent = sweepDetails(plan);
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = mvOnly
      ? '선택한 M/V 프로젝트의 최종 영상·애니매틱·중간 렌더를 포함해 정리합니다. 원음, 설치 모델과 다른 음악 작업은 보존합니다.'
      : '재생성 가능한 캐시와 검증된 잔재만 정리합니다. 최종 영상·애니매틱·원음은 자동 일괄 정리에서 삭제하지 않습니다.';
    openDialog(storage$('#storageConfirmDialog'), event.currentTarget);
  } catch (error) { status(error.message, true); }
  finally { setBusy(false); }
}
async function previewStorage(event, all = false) {
  const project = selectedProject(); if (!project && !all) return;
  const entryIds = rememberEntries();
  if (!all && entryIds.length && project.preserveHistory !== false && (project.entries || []).some(entry => entryIds.includes(entry.id) && ['intermediate', 'history'].includes(entry.kind))) return status('중간본·히스토리는 히스토리 보존을 끈 뒤에만 직접 선택할 수 있습니다.', true);
  try {
    const request = all ? { kinds: ['cache'] } : entryIds.length ? { projectId: project.id, entryIds } : { projectId: project.id, kinds: ['cache'] };
    const previewRequest = beginPreview(); storage$('#storageConfirmTitle').textContent = '정리를 실행할까요?'; storage$('#confirmStorageCleanup').textContent = '선택한 계획 삭제';
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = '계획을 만든 뒤 파일·정책·보호 상태·작업 잠금이 바뀐 항목은 삭제하지 않습니다.';
    const plan = await storageRequest('/api/storage/preview', request);
    if (!activatePlan('plan', plan, previewRequest)) return;
    renderStorage();
    storage$('#storageConfirmSummary').textContent = `${plan.fileCount || 0}개, ${storageBytes(plan.bytes)}를 정리할 계획입니다.`;
    storage$('#storageBlocked').textContent = [previewDetails(plan.entries), ...(plan.blocked || []).map(item => {
      const project = storageState.data?.projects?.find(project => project.id === item.projectId) || {};
      const entry = project.entries?.find(entry => entry.id === item.entryId);
      return `보호: ${projectLabel(project)} · ${entry?.relativePath || item.relativePath || ''} · ${item.reason || '보호 항목'}`;
    })].filter(Boolean).join(' / ');
    openDialog(storage$('#storageConfirmDialog'), event.currentTarget);
  } catch (error) { status(error.message, true); }
}
storage$('#previewStorage').addEventListener('click', event => previewStorage(event));
storage$('#previewAllStorage').addEventListener('click', event => previewStorage(event, true));
storage$('#previewProjectFinish').addEventListener('click', async event => {
  const project = selectedProject(); if (!project) return;
  const statusNode = storage$('#storagePreviewStatus');
  try {
    setBusy(true); statusNode.textContent = '완성본·원음·핀·활성 작업을 확인하고 작업 자료 정리 계획을 만드는 중…';
    const request = beginPreview();
    const plan = await storageRequest('/api/storage/project-finish-preview', { projectId: project.id });
    if (request !== storageState.previewRequest) return;
    if (plan.alreadyFinished) { resetProjectFinish(); statusNode.textContent = plan.message || '이미 작업 자료 정리가 끝났으며 완성본과 최소 이력만 남아 있습니다.'; return; }
    if (!activatePlan('projectFinishPlan', plan, request)) return;
    const summary = plan.summary || {};
    storage$('#storageConfirmTitle').textContent = '완성 후 작업 자료를 정리할까요?';
    storage$('#confirmStorageCleanup').textContent = '작업 자료 정리';
    storage$('#storageConfirmSummary').textContent = `${summary.fileCount || 0}개 · ${storageBytes(summary.allocatedBytes)}를 정리하고 canonical 완성본 ${summary.canonicalFiles || 0}개와 최소 이력을 남깁니다.`;
    storage$('#storageBlocked').textContent = [...(plan.blocked || []).map(item => `보호: ${item.path || item.name || ''} · ${item.reason || '정리할 수 없음'}`), plan.retainedHistoryPath ? `보존 이력: ${plan.retainedHistoryPath}` : ''].filter(Boolean).join(' / ');
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = '완료·보관 상태의 private 작업 폴더만 정리합니다. Output의 canonical 완성본과 원음, 핀한 자료와 활성 작업은 유지합니다.';
    statusNode.textContent = '완성 후 작업 자료 정리 계획을 확인한 뒤 실행하세요.';
    openDialog(storage$('#storageConfirmDialog'), event.currentTarget);
  } catch (error) { statusNode.textContent = error.message; }
  finally { setBusy(false); }
});
storage$('#previewSweep').addEventListener('click', event => previewSweep(event));
storage$('#previewRestructure').addEventListener('click', async event => {
  const statusNode = storage$('#restructureStatus');
  try {
    setBusy(true); statusNode.textContent = '완성본·원음·모델 보호 상태와 기존 테스트 폴더를 점검하는 중…';
    const request = beginPreview();
    const plan = await storageRequest('/api/storage/restructure-preview', {}, 180000);
    if (!activatePlan('restructurePlan', plan, request)) return;
    const summary = plan.summary || {};
    storage$('#storageConfirmTitle').textContent = '완성본 전용 구조로 정리할까요?';
    storage$('#confirmStorageCleanup').textContent = '검증된 구조 정리 실행';
    storage$('#storageConfirmSummary').textContent = `기존 폴더 ${summary.legacyRoots || 0}개 · ${Number(summary.legacyFileCount || 0).toLocaleString('ko-KR')}개 파일 · ${storageBytes(summary.legacyAllocatedBytes)} · 사라진 임시 등록 ${summary.obsoleteRegistrations || 0}개를 계획에 넣었습니다.`;
    storage$('#storageBlocked').textContent = [
      ...(plan.legacyRoots || []).map(item => `정리 후보: ${item.path || '경로 미기록'} · ${Number(item.fileCount || 0).toLocaleString('ko-KR')}개 · ${storageBytes(item.allocatedBytes)}`),
      ...(plan.obsoleteRegistrations || []).map(item => `파일 삭제 없이 등록 해제: ${item.path}`),
      ...(plan.preserved || []).map(item => `보존: ${typeof item === 'string' ? item : `${item.path || item.name || '보호 항목'}${item.reason ? ` · ${item.reason}` : ''}`}`),
      ...(plan.warnings || []).map(item => `알림: ${typeof item === 'string' ? item : item.message || item.reason || ''}`),
      ...(plan.blocked || []).map(item => `보호: ${item.path || item.name || ''} · ${item.reason || '확인 필요'}`)
    ].filter(Boolean).join(' / ');
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = '검증된 원음·모델·현재 프로그램·완성 파일·최소 이력은 보존합니다. 활성 작업 또는 변경된 파일은 정리하지 않습니다.';
    statusNode.textContent = '구조 정리 계획을 확인한 뒤 실행하세요.'; openDialog(storage$('#storageConfirmDialog'), event.currentTarget);
  } catch (error) { statusNode.textContent = error.message; }
  finally { setBusy(false); }
});
storage$('#previewSharedCache').addEventListener('click', async event => {
  try {
    const request = beginPreview();
    const plan = await storageRequest('/api/storage/shared-preview', {});
    if (request !== storageState.previewRequest) return;
    if (!plan.fileCount) {
      storage$('#sharedCacheStatus').textContent = '정리할 공용 영상 캐시가 없습니다.' + ((plan.blocked || []).length ? ` 보호 항목 ${(plan.blocked || []).length}개는 유지합니다.` : '');
      return;
    }
    if (!activatePlan('sharedPlan', plan, request)) return;
    storage$('#storageConfirmTitle').textContent = '공용 영상 캐시를 정리할까요?';
    storage$('#confirmStorageCleanup').textContent = '공용 캐시 정리';
    storage$('#storageConfirmSummary').textContent = `${plan.fileCount || 0}개, ${storageBytes(plan.bytes)}를 정리할 계획입니다.`;
    storage$('#storageBlocked').textContent = [
      plan.cacheDir ? `캐시 경로: ${plan.cacheDir}` : '',
      ...(plan.files || []).map(item => `${item.path || item.name || '캐시 파일'} · ${storageBytes(item.bytes)}`),
      ...(plan.blocked || []).map(item => `보호: ${item.path || item.name || ''} · ${item.reason || '보호 항목'}`)
    ].filter(Boolean).join(' / ');
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = '현재 앱이 유휴 상태이고 같은 앱 프로세스의 계획이 유효할 때만 정리합니다.';
    storage$('#sharedCacheStatus').textContent = `공용 캐시 미리보기: ${plan.fileCount || 0}개 · ${storageBytes(plan.bytes)}`;
    openDialog(storage$('#storageConfirmDialog'), event.currentTarget);
  } catch (error) { storage$('#sharedCacheStatus').textContent = error.message; }
});
storage$('#loadMaintenance').addEventListener('click', loadMaintenance);
storage$('#maintenanceScope').addEventListener('change', () => { invalidatePlans(); renderMaintenance(); });
storage$('#selectMaintenanceCandidates').addEventListener('click', selectMaintenanceCandidates);
storage$('#previewMaintenance').addEventListener('click', async event => {
  const scope = maintenanceScope(); const candidateIds = maintenanceCandidateIds();
  const scanId = storageState.maintenance?.scan?.scanId;
  if (typeof scanId !== 'string' || !scanId) return storage$('#maintenanceStatus').textContent = '완료된 작업 폴더 전체 스캔이 필요합니다.';
  if (scope !== 'git' && !candidateIds.length) return storage$('#maintenanceStatus').textContent = '정리할 후보를 하나 이상 선택하세요.';
  setMaintenanceBusy(true); storage$('#maintenanceStatus').textContent = '선택한 후보의 정리 계획을 만드는 중…';
  try {
    const request = beginPreview();
    const plan = await storageRequest('/api/storage/maintenance-preview', scope === 'git' ? { scanId, scope } : { scanId, scope, candidateIds }, 180000);
    if (!activatePlan('maintenancePlan', plan, request)) return;
    storage$('#storageConfirmTitle').textContent = `${maintenanceKind(scope)} 정리 계획을 실행할까요?`;
    storage$('#confirmStorageCleanup').textContent = '선택한 후보 정리';
    storage$('#storageConfirmSummary').textContent = `${plan.fileCount || 0}개, ${storageBytes(plan.estimatedReclaimableBytes ?? plan.bytes)}를 정리할 계획입니다.`;
    storage$('#storageBlocked').textContent = [
      ...(plan.entries || []).map(item => `${item.path || item.source || ''} · ${storageBytes(item.bytes)}`),
      ...(plan.entries || []).filter(item => item.estimateIsUpperBound).map(item => `설치 ZIP 컨테이너 총량 ${storageBytes(item.grossAllocatedBytes)} · 공통 보관본 ${storageBytes(item.archiveRecovery?.uniqueMemberBytes)} · 순확보량은 상한 추정입니다.`),
      ...(plan.blocked || []).map(item => `보호: ${item.path || item.relativePath || ''} · ${item.reason || '보호 항목'}`),
      scope === 'git' ? 'Git 객체의 논리 크기와 실제 디스크 회수량은 다를 수 있습니다.' : ''
    ].filter(Boolean).join(' / ');
    storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent = scope === 'retirement' ? '선택한 이전 버전·중간 자료를 제거합니다. 최종본·원음·현재 모델·프로그램·최소 이력은 유지하며 일부 제작 캐시는 다시 만들어야 합니다.' : '계획을 만든 뒤 파일·Git 상태·보호 상태가 바뀐 항목은 정리하지 않습니다.';
    storage$('#maintenanceStatus').textContent = `${maintenanceKind(scope)} 미리보기를 확인한 뒤 정리를 확정하세요.`;
    openDialog(storage$('#storageConfirmDialog'), event.currentTarget);
  } catch (error) { storage$('#maintenanceStatus').textContent = error.message; }
  finally { setMaintenanceBusy(false); }
});
storage$('#confirmStorageCleanup').addEventListener('click', async () => {
  const activePlan = storageState.activePlan;
  if (!activePlan?.plan?.planId || storageState.confirming) return;
  setConfirming(true); setBusy(true);
  try {
    if (activePlan.type === 'entityPlan') {
      const plan = storageState.entityPlan; setBusy(true);
      storage$('#storageConfirmSummary').textContent = '격리·SQLite·완성 파일 상태를 다시 확인한 뒤 전체 제거를 실행하는 중…';
      const result = await storageRequest('/api/storage/entity-remove', { planId: plan.planId, confirm: true }, 950000);
      closeDialog(storage$('#storageConfirmDialog'), true); resetEntity();
      await refreshStorage(`프로젝트 ${result.removedProjects || 0}개 · 음악 그룹 ${result.removedGroups || 0}개 · 파일 ${result.removedFiles || 0}개를 제거했습니다. 파일 할당량 감소 ${storageBytes(result.freedAllocatedBytes)} · 남은 관리 이력 ${Number(result.remaining?.events || 0).toLocaleString('ko-KR')}개.`); return;
    }
    if (activePlan.type === 'trackingPlan') {
      const plan = storageState.trackingPlan; setBusy(true);
      const result = await storageRequest('/api/storage/reconcile-cleanup', { planId: plan.planId, confirm: true });
      closeDialog(storage$('#storageConfirmDialog'), true); storageState.trackingPlan = null;
      await refreshStorage(`${result.removedFiles || 0}개 Finder 표시 설정을 정리했습니다 · ${storageBytes(result.freedAllocatedBytes)} 확보.`); return;
    }
    if (activePlan.type === 'projectFinishPlan') {
      const plan = storageState.projectFinishPlan; setBusy(true);
      storage$('#storagePreviewStatus').textContent = '완성본·최소 이력을 다시 확인한 뒤 작업 자료를 정리하는 중…';
      const result = await storageRequest('/api/storage/project-finish', { planId: plan.planId, confirm: true }, 950000);
      closeDialog(storage$('#storageConfirmDialog'), true); resetProjectFinish();
      await refreshStorage(`${result.removedFiles || 0}개 작업 파일을 정리했습니다 · 파일 할당량 감소 ${storageBytes(result.freedAllocatedBytes)} · canonical 완성본 ${result.canonicalFiles || 0}개와 최소 이력을 유지했습니다.`);
      return;
    }
    if (activePlan.type === 'fileRemovePlan') {
      const plan = storageState.fileRemovePlan; setBusy(true);
      const result = await storageRequest('/api/storage/file-remove', { planId: plan.planId, confirm: true });
      closeDialog(storage$('#storageConfirmDialog'), true); storageState.fileRemovePlan = null;
      await refreshStorage(`${result.removedFiles || 0}개 등록 파일을 정리하고 ${storageBytes(result.freedBytes)}를 확보했습니다.`);
      return;
    }
    if (activePlan.type === 'restructurePlan') {
      const plan = storageState.restructurePlan; setBusy(true);
      storage$('#restructureStatus').textContent = '모델·완성본을 새 위치에서 검증한 뒤 기존 테스트 폴더를 정리하는 중…';
      const result = await storageRequest('/api/storage/restructure-cleanup', { planId: plan.planId, confirm: true }, 950000);
      closeDialog(storage$('#storageConfirmDialog'), true); storageState.restructurePlan = null;
      const disk = Number.isFinite(result.diskFreeDeltaBytes) ? ` · 디스크 여유 +${storageBytes(Math.abs(result.diskFreeDeltaBytes))}` : '';
      const summary = `${result.removedFiles || 0}개 파일을 정리했습니다 · 파일 할당량 감소 ${storageBytes(result.freedAllocatedBytes)}${disk} · 완성본 버전 ${Number(result.deliveryVersions || 0).toLocaleString('ko-KR')}개 보존 · 사라진 임시 등록 ${result.prunedRegistrations || 0}개 정리`;
      await refreshStorage(summary); return;
    }
    if (activePlan.type === 'sweepPlan') {
      const plan = storageState.sweepPlan; setBusy(true);
      const result = await storageRequest('/api/storage/sweep-cleanup', { planId: plan.planId, confirm: true }, 950000);
      closeDialog(storage$('#storageConfirmDialog'), true); resetSweep();
      const skipped = (result.skipped || []).length + (result.errors || []).length;
      const allocated = Number.isFinite(result.freedAllocatedBytes) ? storageBytes(result.freedAllocatedBytes) : '미측정';
      const disk = Number.isFinite(result.diskFreeDeltaBytes) ? ` · 디스크 여유 변화 ${result.diskFreeDeltaBytes < 0 ? '-' : '+'}${storageBytes(Math.abs(result.diskFreeDeltaBytes))}` : '';
      const summary = `${result.removedFiles || 0}개를 정리했습니다. 파일 할당량 감소 ${allocated}${disk}` + (skipped ? ` · ${skipped}건은 보호·변경 또는 오류로 유지했습니다.` : '') + ((result.warnings || []).length ? ` · 알림: ${result.warnings.join(' · ')}` : '');
      await refreshStorage(summary);
      await loadMaintenanceHistory();
      return;
    }
    if (activePlan.type === 'maintenancePlan') {
      const plan = storageState.maintenancePlan; setMaintenanceBusy(true);
      storage$('#maintenanceStatus').textContent = '검증된 정리 계획을 실행 중입니다. 완료 후 전체 폴더를 다시 스캔합니다.';
      const result = await storageRequest('/api/storage/maintenance-cleanup', { planId: plan.planId, confirm: true }, 950000);
      closeDialog(storage$('#storageConfirmDialog'), true); storageState.maintenancePlan = null;
      const logical = result.freedBytes ?? result.estimatedReclaimableBytes ?? 0;
      const allocated = result.allocationDeltaBytes ?? result.freedAllocatedBytes;
      const diskDelta = result.diskFreeDeltaBytes;
      const parts = [plan.scope === 'git' ? `${result.removedObjects || 0}개 Git 객체를 정리했습니다.` : `${result.removedFiles || 0}개 파일을 정리했습니다.`, `논리 정리량 ${storageBytes(logical)}`];
      const deltaBytes = value => `${value < 0 ? '-' : '+'}${storageBytes(Math.abs(value))}`;
      if (Number.isFinite(allocated)) parts.push(`파일 할당량 감소 ${deltaBytes(allocated)}`);
      if (Number.isFinite(result.retainedHistoryAllocatedBytes)) parts.push(`보존 이력 할당량 ${storageBytes(result.retainedHistoryAllocatedBytes)}`);
      if (Number.isFinite(result.grossAllocatedBytes)) parts.push(`설치 ZIP 컨테이너 총량 ${storageBytes(result.grossAllocatedBytes)}`);
      if (Number.isFinite(diskDelta)) parts.push(`디스크 여유 변화 ${deltaBytes(diskDelta)}`);
      if (result.auditPath) parts.push(`감사 기록: ${result.auditPath}`);
      if ((result.skipped || []).length) parts.push(`${result.skipped.length}건은 보호·변경되어 건너뛰었습니다.`);
      if ((result.warnings || []).length) parts.push(`알림: ${result.warnings.join(' · ')}`);
      await refreshStorage(parts.join(' · '));
      await loadMaintenanceHistory();
      storage$('#maintenanceStatus').textContent = parts.join(' · ');
      return;
    }
    if (activePlan.type === 'sharedPlan') {
      const result = await storageRequest('/api/storage/shared-cleanup', { planId: storageState.sharedPlan.planId, confirm: true });
      closeDialog(storage$('#storageConfirmDialog'), true); storageState.sharedPlan = null;
      const skipped = (result.skipped || []).length;
      storage$('#sharedCacheStatus').textContent = `${result.removedFiles || 0}개를 정리하고 ${storageBytes(result.freedBytes)}를 확보했습니다.` + (skipped ? ` ${skipped}건은 보호·변경되어 건너뛰었습니다.` : '') + ((result.warnings || []).length ? ' 감사 기록 경고가 있습니다.' : '');
      return;
    }
    if (activePlan.type === 'legacyPlan') {
      const result = await storageRequest('/api/storage/adopt', { planId: storageState.legacyPlan.planId, confirm: true });
      closeDialog(storage$('#storageConfirmDialog'), true); storageState.legacyPlan = null;
      await refreshStorage(`${result.movedFiles || 0}개를 관리 캐시로 옮겼습니다.` + ((result.skipped || []).length || (result.warnings || []).length ? ' 일부 항목은 건너뛰었습니다.' : ''));
      return;
    }
    if (activePlan.type !== 'plan') return;
    const result = await storageRequest('/api/storage/cleanup', { planId: activePlan.plan.planId, confirm: true });
    closeDialog(storage$('#storageConfirmDialog'), true); storageState.plan = null;
    const skipped = (result.skipped || []).length + (result.errors || []).length;
    const warnings = (result.warnings || []).length;
    const summary = `${result.removedFiles || 0}개를 정리하고 ${storageBytes(result.freedBytes)}를 확보했습니다.` + (skipped ? ` 일부 ${skipped}건은 보호·변경 또는 오류로 건너뛰었습니다. 새 미리 보기가 필요합니다.` : '') + (warnings ? ` 감사 기록 ${warnings}건은 저장하지 못했습니다.` : '');
    await refreshStorage(summary);
  } catch (error) {
    if (activePlan.type === 'entityPlan') {
      const recoverable = /중단|격리|복구|recovery/i.test(error.message);
      storage$('#recoverStorageEntity').hidden = !recoverable;
      storage$('#storageConfirmSummary').textContent = recoverable ? '제거가 중단되어 파일을 격리 보존했습니다. 아래 복구 버튼으로 원래 상태를 점검·복구할 수 있습니다.' : `${error.message} 제거를 실행하지 않았습니다. 새 계획이 필요할 수 있습니다.`;
      storage$('#storageBlocked').textContent = recoverable ? '격리된 자료는 자동으로 삭제하지 않았습니다. 복구에 실패하면 파일·SQLite 상태를 보존한 채 원인을 표시합니다.' : error.message;
    } else if (activePlan.type === 'projectFinishPlan') {
      resetProjectFinish();
      closeDialog(storage$('#storageConfirmDialog'), true);
      storage$('#storagePreviewStatus').textContent = `${error.message} 새 미리 보기가 필요합니다.`;
    } else if (activePlan.type === 'fileRemovePlan') {
      storageState.fileRemovePlan = null;
      closeDialog(storage$('#storageConfirmDialog'), true);
      status(`${error.message} 새 미리 보기가 필요합니다.`, true);
    } else if (activePlan.type === 'restructurePlan') {
      storageState.restructurePlan = null;
      closeDialog(storage$('#storageConfirmDialog'), true);
      storage$('#restructureStatus').textContent = `${error.message} 새 미리 보기가 필요합니다.`;
      status(error.message, true);
    } else if (activePlan.type === 'maintenancePlan') storage$('#maintenanceStatus').textContent = error.message;
    else status(error.message, true);
  } finally { setConfirming(false); setMaintenanceBusy(false); setBusy(false); }
});
storage$('#recoverStorageEntity').addEventListener('click', async () => {
  const plan = storageState.entityPlan; if (!plan?.planId) return;
  try {
    setBusy(true); storage$('#storageConfirmSummary').textContent = '격리된 파일·SQLite 등록·납품 이력을 점검해 원래 상태로 복구하는 중…';
    const result = await storageRequest('/api/storage/entity-recover', { planId: plan.planId, confirm: true }, 950000);
    closeDialog(storage$('#storageConfirmDialog'), true); resetEntity();
    await refreshStorage(`중단된 전체 제거를 복구했습니다. 복구 파일 ${result.restoredFiles || result.removedFiles || 0}개를 확인했고 프로젝트·음악 그룹·이력은 유지했습니다.`);
  } catch (error) {
    storage$('#storageConfirmSummary').textContent = `복구하지 못했습니다: ${error.message}`;
    storage$('#storageBlocked').textContent = '격리 자료와 복구 계획은 보존했습니다. 파일을 직접 삭제하지 마세요.';
  } finally { setBusy(false); }
});
storage$('#storageTrack').addEventListener('submit', async event => {
  event.preventDefault(); const project = selectedProject(); if (!project) return;
  const form = event.currentTarget;
  try {
    await storageRequest('/api/storage/track', { projectId: project.id, path: form.elements.path.value, kind: form.elements.kind.value, description: form.elements.description.value, reproducible: form.elements.kind.value === 'cache' });
    form.reset(); await refreshStorage('재생성 파일을 등록했습니다.');
  } catch (error) { status(error.message, true); }
});
for (const [dialog, close] of [['#storageHelpDialog', '#closeStorageHelp'], ['#storageConfirmDialog', '#closeStorageConfirm'], ['#storageTrackingHelpDialog', '#closeTrackingHelp'], ['#storageEventHelpDialog', '#closeEventHelp']]) {
  storage$(close).addEventListener('click', () => closeDialog(storage$(dialog)));
  storage$(dialog).addEventListener('click', event => { if (event.target === storage$(dialog)) closeDialog(storage$(dialog)); });
}
storage$('#storageConfirmDialog').addEventListener('cancel', blockConfirmClose);
storage$('#storageConfirmDialog').addEventListener('close', resetAllPlans);
storage$('#openStorageHelp').addEventListener('click', event => openDialog(storage$('#storageHelpDialog'), event.currentTarget));
storage$('#openTrackingHelp').addEventListener('click', event => openDialog(storage$('#storageTrackingHelpDialog'), event.currentTarget));
storage$('#openEventHelp').addEventListener('click', event => openDialog(storage$('#storageEventHelpDialog'), event.currentTarget));
bindInlineHelp(storage$('#maintenanceGitHelp'));
storage$('#storageGuide').href = storageUrl('/guide/storage/');
storage$('#storageHelpGuide').href = storageUrl('/guide/storage/');
async function findLegacy() {
  const project = selectedProject(); if (!project) return;
  const node = storage$('#legacyCandidates'); node.replaceChildren();
  try {
    const result = await storageRequest('/api/storage/legacy?projectId=' + encodeURIComponent(project.id));
    for (const item of result.candidates || []) { const row = storageNode('label', undefined, 'work-file'); const box = storageNode('input'); box.type='checkbox'; box.dataset.legacyCandidate=item.id; const text=storageNode('span'); const proof=item.evidence?.final ? ` · 완료본 ${item.evidence.final}${Number.isFinite(item.evidence.duration)?` · ${item.evidence.duration.toFixed(1)}초`:''}` : item.evidence?.classification === 'local-verification' ? ' · 로컬 검증 전용 · checksum·배포 기록 대조 완료' : ''; text.append(storageNode('strong',item.relativePath),storageNode('span',`${storageBytes(item.bytes)} · ${item.fileCount}개 · ${item.description}${proof}`,'hint')); row.append(box,text);node.append(row); }
    for (const item of result.blocked || []) node.append(storageNode('p',`${item.relativePath} · ${item.reason}`,'hint'));
    storage$('#previewLegacy').disabled = !(result.candidates || []).length;
    storage$('#legacyStatus').textContent = result.candidates?.length ? '후보를 선택해 관리 캐시로 옮기기 미리 보기를 만드세요.' : '옮길 수 있는 과거 렌더·검증 캐시가 없습니다.';
  } catch (error) { storage$('#legacyStatus').textContent = error.message; }
}
storage$('#findLegacy').addEventListener('click', findLegacy);
storage$('#previewLegacy').addEventListener('click', async event => {
  const project = selectedProject(); const candidateIds=[...document.querySelectorAll('[data-legacy-candidate]:checked')].map(node=>node.dataset.legacyCandidate); if (!project || !candidateIds.length) return storage$('#legacyStatus').textContent='옮길 후보를 선택하세요.';
  try {
    const request = beginPreview();
    const plan = await storageRequest('/api/storage/adopt-preview',{projectId:project.id,candidateIds});
    if (!activatePlan('legacyPlan', plan, request)) return;
    storage$('#storageConfirmTitle').textContent='관리 캐시로 옮길까요?'; storage$('#confirmStorageCleanup').textContent='관리 캐시로 옮기기'; storage$('#storageConfirmSummary').textContent=`${plan.fileCount}개, ${storageBytes(plan.bytes)}를 관리 캐시로 옮길 계획입니다.`; storage$('#storageBlocked').textContent=[...(plan.entries||[]).map(item=>`${item.source} → ${item.target} · ${storageBytes(item.bytes)}`),...(plan.blocked||[]).map(item=>item.reason)].join(' · '); storage$('#storageConfirmDialog').querySelector('.decision-guide-body p').textContent='계획 뒤 파일·보호 상태·작업 잠금이 바뀐 항목은 옮기지 않습니다.'; openDialog(storage$('#storageConfirmDialog'),event.currentTarget);
  } catch(error){storage$('#legacyStatus').textContent=error.message;}
});
refreshStorage('저장공간 정보를 불러왔습니다.', false);
loadMaintenanceHistory();
