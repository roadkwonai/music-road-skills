# 프로젝트 저장공간 운영 계약

## 경로와 보존

| 위치 | 용도 | 정리 조건 |
| --- | --- | --- |
| `Output/<음악--SHA12>/<프로젝트--ID12>/<시각>/` | 게시 검증된 최종 음원·영상·가사·자막·최종 스토리보드 | 게시 이력과 최종 납품만 보존 |
| `.roadmusic/work/<음악SHA12>/<프로젝트--ID>/` | 새 제작의 입력·편집 설정·렌더·재개 자료 | 완료 검증 뒤 producer 소유 캐시만 자동 정리 |
| 원본 음악/가사·inputs·완성 납품·편집 소스·승인 자산 | 실제 작품과 재편집 근거 | 영구 보호 |
| `.roadmusic/cache/` | 렌더 조각·합성 전 무음 영상·재생성 분석 데이터 | 명시 등록, 무잠금·무핀, 완료 후 보존 기간 적용 |
| `.roadmusic/intermediate/` | 수정 비교용 초안·미채택 중간본 | 기본 보존, 프로젝트 정책 변경 + 정확한 항목 선택 |
| `.roadmusic/history/` | 큰 상세 작업 흔적 | 기본 보존, 프로젝트 정책 변경 + 정확한 항목 선택 |
| `.roadmusic/history.jsonl` | 작업/정리별 최소 감사 요약 | 항상 보존 |
| `.roadmusic` 밖의 과거 폴더 | 레거시 결과·캐시가 섞인 자료 | 읽기 전용으로 먼저 점검, 임의 일괄 삭제 금지 |
| `<앱 데이터>/video-cache/` | 과거 앱의 공용 영상 분석 자료 | 프로젝트 정리에서 제외. 안전 재시작을 요청한 경우 SKILL.md의 전용 `video:cache`·`video:cache-clear` 경로로만 정리 |

프로젝트 목록의 총 파일 용량과 삭제 시 실제 회수 가능 용량은 다를 수 있다. 하드링크 공유·핀·외부 참조·활성 작업·권한 오류가 있는 항목은 근거를 보고한다. 같은 파일의 경로를 두 번 세어 디스크 회수량으로 안내하지 않는다.

## 공개 CLI 사용 순서

명령은 프로젝트 루트에서 실행하며 다른 폴더에서는 실제 CLI 절대 경로를 쓴다. `schema`가 현재 설치본의 최종 계약이다. 아래 절대 경로는 사용자가 관리할 실제 프로젝트 경로로 바꾼다.

```bash
node cli/road-music.js storage:register --json '{"project":"/absolute/output/my-video"}'
node cli/road-music.js storage:list
```

등록 결과의 `id`를 이후 `projectId`에 넣는다. 등록은 원본/완성파일을 이동하거나 삭제하지 않는다. 기본 폴더·정책·프로젝트 기록을 준비한다. 현재 trusted Road Music workspace가 등록되면 `usageScope`는 `managed-cache`이며, 목록은 `.roadmusic` 아래만 세어 workspace 원본과 채택 뒤 관리 사본을 이중 집계하지 않는다.

```json
{"projectId":"등록 결과 ID","path":".roadmusic/cache/render-proof","kind":"cache","description":"보존한 composition과 원음으로 재생성 가능한 렌더 조각","reproducible":true}
```

이 JSON을 실제 파일로 저장해 `storage:track --file /absolute/track.json`에 전달한다. 작업 폴더에 모델·원본·최종본을 함께 넣지 않는다. 중요한 미채택 중간본은 kind `intermediate`로 등록하며 `storage:pin`으로 별도 보존할 수 있다.

```json
{"projectId":"등록 결과 ID","state":"editing","preserveHistory":true,"autoCleanup":false,"retainDays":7,"maxCacheBytes":2147483648,"maxCacheFiles":20000}
```

`storage:policy --file /absolute/policy.json`은 수정 작업의 보존 정책이다. 예산 초과는 경고이지 원음이나 히스토리를 자동 삭제하는 권한이 아니다. 다시 완료할 때에는 실제 납품·검수가 끝난 것을 확인하고 `state:completed`로 갱신한다.

```json
{"projectId":"등록 결과 ID","entryIds":["직접 선택한 항목 ID"]}
```

이 JSON으로 `storage:preview --file /absolute/preview.json`을 실행한다. 반환 계획을 확인한 뒤 실행한다.

```bash
node cli/road-music.js storage:cleanup --json '{"planId":"미리보기에서 반환된 ID"}' --confirm
```

`projectId` 없는 미리보기는 등록된 모든 프로젝트의 재생성 캐시만 다룬다. `storage:history`는 해당 프로젝트의 요약 이력을 읽는다. 누락·오프라인 프로젝트는 보호 상태로 남고, 전체 정리는 사용할 수 있는 프로젝트만 계획하며 건너뛴 사유를 보여 준다. 잠긴 프로젝트는 제작 프로세스가 자기 토큰으로 끝내기 전까지 정리하지 않는다. `storage:lease`의 acquire에는 실제 제작 작업을 감싸는 프로세스 PID가 필요하다. PID를 가진 제작 프로세스가 잠금 획득 후 엔진을 시작하고 `finally`에서 반환된 토큰을 해제한다. 짧은 CLI 조회 프로세스 PID로 제작 중 보호를 주장하지 않는다.

## 레거시 프로젝트

프로젝트 등록 뒤 목록이 비었다면 관리 대상으로 검증된 캐시가 아직 없다는 뜻이다. 기존 `qa`, `runtime`, `draft`, 오래된 스토리보드 폴더를 통째로 등록하지 않는다. 무엇인지 모르는 파일, 프로그램·모델·공유 실행 환경과 사용자 라이브러리 바깥 자료는 그대로 둔다.

일반 `production+playlist`, preset 해시가 일치하는 CD, 완료·납품 검수가 끝난 native 프로젝트는 서로 다른 picture/parts 후보 조건을 사용한다. 현재 trusted Road Music workspace에서는 코드에 고정된 역사적 로컬 검증 ZIP 2개만 후보가 될 수 있다. 모두 공개 `storage:legacy` → `storage:adopt-preview` → `storage:adopt --confirm` → `storage:preview` → `storage:cleanup --confirm` 흐름을 사용한다. 프로필별 증거와 핀·후속 정리는 [레거시 캐시 채택](legacy-cache-adoption.md)을 따른다. 이 절차 밖의 파일을 임의로 `.roadmusic/cache`로 옮기거나 `storage:track`으로 우회 등록하지 않는다.

## 소스 복사와 완료 기록

새 실험은 필요한 소스만 복사하거나 기존 실행 환경을 사용한다. 앱 번들·node_modules·모델·Output·영상 캐시·.harness/work를 함께 복사하지 않는다. 동일 입력 fingerprint의 분석과 렌더 청크는 재사용하고, 성공 뒤 재개 조각을 불필요하게 남기지 않는다. 원본·현재 편집 코드·최종 납품 및 검수 기록은 기존 제작 계약을 따른다.

작업별 이력에는 입력/결과의 식별자와 해시·단계·시각·변경 이유·검수 결과를 짧게 남긴다. 전부 복제한 프로젝트 스냅샷으로 이력을 대신하지 않는다. 이미지 생성 프롬프트·seed·모델 출처처럼 재현에 필요한 근거는 승인 자산 manifest에 남기며 캐시로 분류하지 않는다. 새 작업을 `Output/`에 직접 만들지 않고, 게시 단계가 검증된 파일을 시간 버전으로 복사·등록한다.


## 제작 중·완료 시 용량 관리

작업 폴더 전체 유지보수는 `storage:maintenance-list`의 선행 전체 스캔으로 시작한다. 새 제작의 원음·원가사·모델은 복제하지 않고 검증된 원본 경로/지문으로 인계한다. 수정마다 앱·의존성·전체 프로젝트를 새로 복사하지 않는다. 자산의 독립 사본이 필요한 동결 입력/독립 HTML은 지원하는 Python/파일시스템에서 copy-on-write 복사를 사용하고, 지원하지 않으면 기존 독립 복사를 유지한다. 서로 수정이 전파되는 hardlink로 편집 사본을 합치지 않는다.

Showreel/앱 영상 producer는 작업 잠금과 프로젝트 cache 등록을 연결한다. MV/harness도 `input.json`의 `schema_version:1`·`source_audio` 절대 경로/지문과 `production-plan.json`의 `objective`/`tasks`가 있는 실행 폴더를 공개 `storage:register`로 등록할 수 있다. 단계 제작의 중간 PNG·concat·분석 결과는 `.roadmusic/cache/<단계>/`에 분리해 재생성 조건을 기록하고 명시 등록한다. 제작 동안 살아 있는 producer PID lease를 유지하며 성공/실패/취소에 자기 토큰만 해제한다. 원음·승인 이미지·`preproduction/animatic.mov`·최종 master·검수 기록은 cache로 넣지 않는다.

단계 종료 때 파일 수/용량/예산을 확인한다. 편집 중 필요한 재개 cache와 실패 근거는 유지하고, 더 이상 필요 없는 것으로 검증된 캐시만 공개 미리보기/정리로 처리한다. 프로젝트 완료와 납품/필수검수가 끝난 뒤 completed/보존기간 정책을 적용하면 lease 해제와 완료 이벤트에서 재생성 캐시가 정리된다. Git/설치복제본 정리를 매 렌더마다 자동 실행하지 않는다.

애니매틱은 원본 PNG·타이밍·원음 PCM 검수를 보존하면서 검수 영상에 매 프레임 PNG 코덱을 기본 강제하지 않는다. 기존 MV 지침의 지원 코덱·무손실 원음·실제 재생/PCM 지문 검증을 따른다. 필요한 전 프레임 분석 증거는 삭제하지 말고 원본·추출 설정·인덱스·주석·contact sheet와 함께 보관한다. 옛 애니매틱/완성본을 작은 프록시로 바꿔 치우지 않는다.
