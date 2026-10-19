# 결과·제작자료 등록 계약

이 문서는 제작 스킬과 영상 제작실이 같은 결과를 등록·검수할 때 지켜야 할 경계다. 선택 저장, 실제 렌더, 등록, 검수 승인, 외부 게시를 서로 같은 완료 상태로 취급하지 않는다.

## 등록 전 확인

- 실제 원음의 SHA-256, 실제 파일 경로와 실제 제작 시각 `producedAt`을 구분한다. 파일 생성·수정 시각은 legacy 근거일 수 있으나 렌더 완료 증거로 바꾸지 않는다.
- `publish --dry-run` 또는 `/api/publish-preview`의 추가·유지·제거·경고를 먼저 확인한다. 실제 `publish`는 현재 프로젝트 등록 목록을 manifest로 교체한다.
- 입력 음원·형식 샘플·중간 렌더·생성되지 않은 파일을 완성 결과로 등록하지 않는다.

## media와 artifact

media는 `audio`, `lyrics`, `captions`, `video`, `storyboard`다. 캡션에는 명시적으로 확인된 경우에만 `forVideoSha256`으로 대응 영상을 기록한다.

artifact는 native project, direction, analysis, plan, validation, cues, compose, report, source archive처럼 제작을 재현·검수하는 자료다. 허용된 파일 형식은 `.json`, `.txt`, `.md`, `.zip`, `.jizura`이며 폴더·HTML·실행 파일은 등록하지 않는다. JSON·텍스트 자료는 읽기 전용 원문 표시만 제공한다.

## 감상용과 제작자료 ZIP

- 감상용 음악 그룹 ZIP은 사용한 원음과 등록된 media만 담는다.
- 제작자료 ZIP은 감상용 ZIP과 분리하며, 등록된 artifact와 `syncChecks` 근거를 함께 담는다.

누락·변경된 파일이 있으면 부분 ZIP을 완성본처럼 만들지 않는다. 사용자가 실제로 내려받아야 할 범위가 어느 쪽인지 명확히 표시한다.

## 싱크 검수 기록

`syncChecks[]`의 각 행은 원가사 줄 번호, 시작·끝 시각, `confirmed` 또는 `estimated`, 근거 문장, 가능한 경우 영상·자막·가사 SHA와 검수 시각을 보관한다. 자동 정렬·ASR·반복 발음처럼 근거가 부족한 시각은 추정으로 남기며 원가사를 바꾸지 않는다.

역사 기록은 읽기 전용으로 보존한다. 현재 프로젝트의 피드백만 수정할 수 있고, 과거 기록을 새 결과의 근거로 덮어쓰지 않는다.

## 제작 스킬의 책임

JIZURA, Showreel MV, Showreel 음악 모션그래픽은 실제 결과와 함께 재현·검수 자료를 남긴다. 제작실은 그 자료를 임의 생성하거나 렌더 성공으로 추정하지 않으며, 실제 등록·검증된 자료만 음악 상세와 제작자료 ZIP에 제공한다.

`syncChecks[].reviewedAt`은 선택 사항이며 시간대가 있는 ISO 시각 또는 Unix 초를 보존한다. 저장 시각을 실제 청취·가창 검수 시각으로 자동 승격하지 않는다.
