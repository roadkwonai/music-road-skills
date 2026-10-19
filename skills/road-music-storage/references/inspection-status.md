# 통합 저장공간 상태

시작은 읽기 전용 `storage:status` 또는 제작실 `GET /api/storage/status`다. 이 호출은 Electron·Git 심층 검사·정리·전체 작업 폴더 재스캔을 실행하지 않는다.

응답의 `capabilities`에는 `projectCache`, `projectFinish`, `sharedVideoCache`, `workspaceScan`, `retirement`, `verification`, `artifacts`, `git`이 있으며 각각 `enabled`와 `reason`을 제공한다. `git`은 기본 상태에서 `inspection:"not-requested"`다. `enabled:false`는 항목이 없거나 현재 환경에서 안전하게 검사할 수 없다는 뜻이다. `enabled:true`도 삭제 가능 판정은 아니며, 대상·잠금·핀·파일 변경을 별도 미리보기와 확인 실행에서 다시 검사한다. 빈 후보나 오류로 바꾸지 말고 UI에서 비활성 이유를 표시한다.

일반 `storage:maintenance-list`는 메타데이터와 비Git 후보만 확인한다. `scope:"retirement"`은 이전 제작 자료만, `scope:"git"`은 실제 Git 저장소가 있는 개발 환경에서 명시할 때만 Git 보호 상태를 검사한다. Git 검사는 자동 prune·fsck·반복 탐색을 하지 않는다.

`scanCache`는 압축 인벤토리 경로와 `writesOnStatus:false`를, `history`는 SQLite 메타데이터 경로와 `writesOnStatus:false`를 나타낸다. SQLite는 버전·감사·스캔 결과 재사용용 메타데이터이며, 상태 조회마다 전체 파일 해시·전체 재스캔·`VACUUM`을 실행하지 않는다. 정리 계획과 확인 실행에서는 필요한 파일만 다시 검증한다.

`storage:status`는 기존 capability와 스캔/이력 경로를 반환하고, `storage:tracking.status`는 검사 항목의 `id`, `label`, `enabled`, `reason`, `required`, `available`을 함께 제공한다. `storage:tracking`은 프로필 `storage.sqlite3`의 cached ownership, known ownership 요약과 소유권 미확인·보호 요약도 반환한다. 기본 조회는 DB만 읽으며, `refreshWorkspace:true`에서만 명시적으로 workspace 경로·크기·수정 시각을 색인한다. 관리·검수·실행 영역은 미연결 제작물로 바꾸지 않고 보호된 관리 영역으로 표시한다.
