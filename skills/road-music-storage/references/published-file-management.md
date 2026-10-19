# 게시 파일과 프로젝트 마무리

## 등록 완성 파일 하나 제거

`storage:file-remove-preview`에는 음악 그룹의 `groupId`와 등록 파일의 `fileId`만 넣는다. 반환한 일회용 `planId`는 `storage:file-remove --confirm`에 한 번만 쓴다. 임의 경로 삭제나 이전 계획 재사용으로 대체하지 않는다.

제거 대상은 Output 안의 canonical 완성 파일 하나여야 하며, 원음·현재 프로젝트 입력·외부 파일·symlink·활성 lease 참조는 보호한다. 계획과 실행 사이에 파일 해시·등록·참조가 바뀌면 중단한다. 성공하면 연결된 `studio-project.json`의 해당 media, WorkLibrary 목록과 SQLite 납품 이력을 함께 갱신하고 tombstone을 남긴다.

음악 그룹의 마지막 완성 파일도 명시 선택이면 계획을 만들 수 있다. 이때 재생·다운로드가 불가능해진다는 경고를 표시할 뿐 자동으로 차단하지 않는다. 자동 일괄 정리에는 이 경로를 넣지 않는다. HTML은 선택한 파일 가까이에 진행 상태를 표시하고, 파일이 없어진 그룹·보호 사유·실패 사유를 빈 목록이나 오류로 설명한다.

## 완료 프로젝트의 private work 정리

`storage:project-finish-preview`에는 정확한 `projectId`를 넣고, 반환한 계획만 `storage:project-finish --confirm`으로 실행한다. 대상은 `.roadmusic/work/` 안의 `completed` 또는 `archived` 프로젝트 중 idle·무핀 상태여야 한다.

실행 전 프로젝트 media와 SQLite 납품 이력의 canonical Output 파일 해시·크기를 다시 확인한다. 검증되면 비최종 work 자료만 지우고 `studio-project.json`, `selection.json`, `feedback.json`, SQLite 이력과 작은 완료 요약은 남긴다. canonical Output과 원음은 지우지 않는다. symlink·외부 media·변경된 파일·누락된 납품 이력이 있으면 정리하지 않는다.

editing 상태에서는 성공한 렌더의 producer 소유 picture cache만 예산 초과 시 자동 정리한다. 완료 뒤에는 검증된 파생 stems만 자동 정리할 수 있다. 전체 private work 정리는 사용자가 완료 프로젝트의 명시적 마무리를 요청했을 때만 사용하며, 수정 중인 작업은 계속 보존한다.

기존 모델로 생성 검증이 필요하면 [완성본 전용 구조 전환](final-output-structure.md)의 `setup:test-profile` 절차로 새 격리 프로필을 만든다. 기존 모델·라이브러리·앱을 바꾸지 않으며, 생성 성공 자체가 전체 프로젝트 마무리나 파일 제거 권한을 뜻하지 않는다.
