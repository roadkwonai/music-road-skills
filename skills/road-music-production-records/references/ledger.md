# 제작 기록 원장 계약

이 원장은 프로필 `storage.sqlite3`의 메타데이터 테이블이다. 음원·영상·프레임·엔진 로그는 기존 프로젝트 파일에 두며 SQLite BLOB로 복사하지 않는다.

## 기록 순서

1. `production:request`에 절대 `project`, `domain`(`music` 또는 `motion`), `prompt`, 선택 `title`·`groupId`·`intent`를 보낸다. 응답의 `requestId`를 보관한다.
2. 실제 producer가 시작될 때 `production:task-start`에 같은 `project`·`domain`, `taskType`, 선택 `engine`·`model`·`requestId`를 보낸다. 응답의 `taskId`를 보관한다.
3. 종료 뒤 `production:task-finish`에 같은 `taskId`, `succeeded`/`failed`/`cancelled`, 실제 `elapsedMs`와 확인된 요약·파일만 보낸다.

처음 기록된 사용자 제작 요청은 분야별 메인 프롬프트다. 제목·가사·음원 수정/검수 요청은 과거 최초 제작 원문을 대신하지 않는다. 이후 요청은 수정 이력으로 남고, 같은 요청을 엔진 단계마다 복제하지 않는다. `requestId`·`taskId` 재사용은 같은 내용을 재시도·복구할 때만 쓴다.

## 측정과 비교

- `elapsedMs`: 실제 작업 시작부터 종료까지의 벽시계 시간이다. 큐 대기·사용자 검토·다른 작업 시간은 포함하지 않는다.
- `mediaSeconds`: 생성·렌더 결과의 실제 재생 길이다. 없는 작업은 생략한다.
- `frameCount`: 실제 출력 프레임 수다. 정지 이미지·음악 생성에는 생략한다.
- 평균은 완료된 같은 `domain`·`taskType`·엔진/모델 조건의 작업만 비교한다. 조건이 다르거나 표본이 너무 적으면 “비교 기준 부족”으로 표시한다.
- 느린 작업은 같은 비교 집단의 평균보다 긴 실측 완료 작업이며, 실패·취소는 별도 상태로 표시한다. 평균은 품질·비용·성공을 보장하지 않는다.

## 개인정보와 정리

프롬프트는 프로젝트 안에서 재사용·복사할 수 있으므로 비밀번호, API 키, 인증 헤더, 개인 연락처를 넣지 않는다. AI 응답·결과 요약은 4,000자 이내의 간결한 설명으로 기록한다. 파일 경로는 실제 생성물을 찾기 위한 메타데이터이며 존재 여부·크기·수정 시각만 원장에 기록한다.

프로젝트/음악 그룹 제거는 `storage:project-remove-preview` 또는 `storage:group-remove-preview`로 범위를 확인한 뒤에만 실행한다. 성공한 제거는 연결된 프롬프트·작업·파일·경로 이력을 SQLite에서 함께 제거한다. 일반 캐시 정리는 원장이나 최종 결과물을 지우지 않는다.

긴 프롬프트와 파일 목록은 `--stdin` 또는 `--file` JSON을 사용한다. 생성 파일은 `production:files-record`로 정리 전에 200개씩 누적할 수 있다. 성공 평균·p95는 같은 조건의 표본을 사용하고, 총 소요에는 실패·취소 비용을 포함하며 하위 단계를 중복 합산하지 않는다.

## AI 응답과 결과 요약

내장 생성·렌더는 작업과 파일 메타데이터를 자동 기록한다. 에이전트가 실제 결과를 검수하고 완료 응답을 작성하는 단계는 같은 프로젝트·분야·`requestId`의 `review` task로 연결한다. `aiSummary`에 무엇을 요청받아 어떻게 처리했는지, `resultSummary`에 확인한 결과와 한계를 짧게 적는다. 생성·수정 task를 복제하거나 이미 종료된 task의 측정값·상태를 바꾸지 않는다. 검수에 실제 걸린 시간만 기록하며 모르면 `elapsedMs`를 생략한다.

## 실행 중 기록과 예상 시간 조회

`production:task-start`의 `expectedMediaSeconds`·`expectedFrameCount`는 시작 시 이미 알려진 목표값이며 완료 실측값을 대신하지 않는다. 실제 단계 경계에서 `production:task-progress`에 `taskId`와 `currentStage`·`summary`·확인된 `progress`(0~1) 중 하나 이상을 전달한다. 비율을 모르면 생략한다. 종료한 작업을 갱신하거나 같은 단계의 오래된 비율로 되돌리지 않는다. 내장 이벤트는 저빈도로 합치며 외부 제작도 매 프레임 기록하지 않는다.

`production:activity`는 읽기 전용 현재 현황이다. `projectId`·`groupId`·`domain` 필터와 `limit`(1~100)·`offset`(0~10000)을 받는다. `queue.nextOffset`으로 다음 페이지를 조회한다. `scope`는 현재 범위, `globalQueue`는 전체 작업량이며 `completionEtaMs`는 기간이 아닌 절대 epoch 밀리초다. `projects`의 현재 작업·다음 대기 작업·추정 단계와 `queue.items`의 시간 근거·표본 수·범위·대기/남은 시간을 구분한다. 모든 미확정 값은 null이고 0으로 바꾸지 않는다. 예상값은 완료 실측 이력을 덮어쓰지 않는다. 앱 실행 순서는 기존 대기열을 따르며 SQLite에 별도 스케줄러를 만들지 않는다.
