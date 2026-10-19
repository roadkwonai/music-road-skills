# SQLite 소유권 원장

## 무엇을 SQLite로 관리하는가

프로필 데이터 폴더의 `storage.sqlite3`는 Road Music 저장공간 관리의 소유권 원장이다. 프로젝트·음악 그룹·등록 경로, 작은 파일 통계, 경로 소유 근거, 생성/수정/게시/정리 최소 이벤트와 재사용 가능한 스캔 메타데이터를 관리한다. workspace `.roadmusic/history.sqlite3`는 기존 납품 버전·파일 해시·변경 사유·diff 원장을 유지한다.

실제 음원·영상·원가사·자막·엔진 JSON·승인 자산은 계속 파일로 둔다. 프레임 이미지, 미디어 BLOB, 렌더 로그 덤프, 매 화면 진입의 전체 스캔 결과는 SQLite에 넣지 않는다. SQLite는 파일 삭제 권한을 만드는 도구가 아니라 소유권과 보호 근거를 빠르게 읽기 위한 메타데이터다.

## 조회·색인·성능

`storage:status`는 검사 항목의 활성 여부와 이유를 읽고, `storage:tracking`은 보관된 원장 색인을 읽는다. 둘 다 Electron 시작, Git 심층 검사, 전체 트리 재탐색, 파일 전체 해시, `VACUUM`을 실행하지 않는다.

실제 경로 변화가 의심될 때만 `storage:tracking`의 `refreshWorkspace:true`로 trusted workspace를 색인한다. 색인은 경로·크기·수정 시각과 확인 가능한 소유 근거를 일괄 기록한다. 삭제·게시 직전에는 해당 대상만 다시 검사한다. Git은 capability가 활성이고 사용자가 Git 범위를 명시한 경우에만 별도 검사한다.

## 관리 영역과 소유권 미확인 자료

`.roadmusic`, `.harness`, `.omx`, `_workspace` 같은 관리·검수·실행 영역은 음악별 제작물과 구분해 **보호된 관리 영역**으로 표시한다. 음악 그룹에 연결되지 않았다는 이유만으로 cache 또는 미연결 제작물로 분류하지 않는다.

어느 프로젝트·음악·관리 영역에도 확인 가능한 소유 근거가 없는 폴더는 **소유권 미확인·보호**로 남긴다. 용량과 경로는 보이지만 자동 일괄 정리나 reconcile 계획에는 넣지 않는다. 검증된 관리 잔재만 `storage:reconcile-preview`에서 계획을 만들고 `storage:reconcile-cleanup --confirm`으로 처리한다. 현재 기본 후보는 `.DS_Store`뿐이다.

## 프로젝트·그룹 제거

프로젝트/음악 그룹 제거는 캐시 정리와 별도다. `storage:project-remove-preview` 또는 `storage:group-remove-preview`가 실제 파일 범위, canonical 완성 파일 포함 여부, 공유 원음·활성 lease·핀·외부 경로 보호 상태를 먼저 반환한다. 받은 일회용 계획만 `storage:entity-remove --confirm`으로 실행한다.

파일 처리가 성공한 경우에만 ManagementDB의 live 프로젝트/그룹 경로·소유권 claim·관련 이벤트를 제거한다. 공유 자산, 활성 작업, 핀한 항목, 프로그램·모델, 외부 원음은 차단한다. 제거가 적용 중 중단되면 같은 계획 ID로 `storage:entity-recover --confirm`을 실행한다. 격리 자료의 지문·원래 경로·SQLite 상태가 모두 맞을 때만 원래 상태를 복구하고, 불일치나 변조가 있으면 격리를 유지한다. 납품 원장과 최소 감사 기록의 보존은 별도 제품 계약을 따르며, DB 행만 먼저 삭제해 파일을 고아로 만들지 않는다.
