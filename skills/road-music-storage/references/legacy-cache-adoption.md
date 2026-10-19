# 검증된 제작·패키지 레거시 캐시 채택

관리 밖의 알려진 producer 캐시나 역사적 로컬 패키지 검증 ZIP을 새 저장공간 흐름으로 옮길 때만 이 문서를 읽는다. 채택은 정리가 아니다. 검증된 후보를 관리 cache로 옮겨 등록한 뒤 별도의 정리 계획을 만든다.

## 공통 경계

- 먼저 실제 프로젝트 또는 현재 trusted Road Music workspace root를 `storage:register`로 등록한다. 경로나 후보 ID를 추측하지 않고 `storage:legacy`가 반환한 `candidates[].id`만 사용한다.
- 후보와 하위 파일은 일반 비실행 파일이고 symlink를 포함하지 않아야 하며 열려 있지 않아야 한다. 후보·증거·파일 snapshot이나 해시가 계획 뒤 달라지면 채택하지 않는다.
- Showreel 프로젝트의 JSON·텍스트·concat·코드·HTML·CSS·Markdown·셸·YAML에서 후보의 상대·절대 경로를 streaming 방식으로 찾는다. 파일당 16 MiB, 프로젝트 합계 64 MiB, 파일 수 안전 한도 중 하나를 넘거나 읽는 동안 실제 바이트가 증가하면 참조 여부를 추측하지 않고 보호한다. 청크 경계에 걸친 참조도 찾는다.
- 일반 draft·tmp·qa·스토리보드, 임의 package-check·확장 kit·source ZIP은 후보가 아니다. 공용 `<앱 데이터>/video-cache/`도 이 흐름으로 이전하거나 삭제하지 않는다.

## Showreel producer 프로필

### 일반 production + playlist

`production.json`과 `playlist.json`이 모두 `schemaVersion:1`이면 `out/<이름>-picture.mp4`와 대응 `out/<이름>-picture.parts`를 각각 검증할 수 있다. 대응 완성본 `out/<이름>.mp4`는 오디오·영상 스트림과 양수 길이를 가져야 한다. aggregate picture는 영상만 있고 길이가 양수이며 완성본과 길이 차이가 1초 이하여야 한다.

parts에는 정확한 `settings.json`, `concat.txt`, `seg_000000_000060.mp4` 형식의 숫자 세그먼트만 허용한다. `settings.json`은 `scale`, `sub`, `shutter`, `format`, `crf`, `fps`, `W`, `H`, `code` 키와 정해진 숫자·문자열 형식을 모두 가져야 한다. `concat.txt`는 중복 없이 모든 세그먼트와 정확히 일치해야 하며, 단순 파일명·`file '파일명'`·같은 parts 폴더로 확인되는 절대 경로만 허용한다. 세그먼트는 개별 디코딩하지 않고 aggregate와 완성본을 미디어 증거로 사용한다.

### CD production + preset

유효한 playlist 대신 `preset.json`을 쓰는 CD 프로필은 `production.json.presetId`와 `preset.json.id`가 같고, `production.json.presetSha256`이 실제 preset SHA-256과 일치해야 한다. 이 프로필은 검증된 picture MP4만 후보로 반환하며 parts는 채택하지 않는다. 대응 완성본과 picture의 스트림·길이 조건은 일반 프로필과 같다.

### native complete + delivery QA

native 프로필은 `project.json`의 `width`, `height`, `fps`, `duration`이 양수이고, `production-state.json`이 `status:complete`, `finalQa:pass`, `delivery:pass`, `pending:[]`여야 한다. 이 프로필은 parts만 후보로 반환하고 aggregate picture와 납품 원본은 보존한다.

`qa/delivery-check.json`은 `pass:true`, `sourceUnchanged:true`, `lyricsUnchanged:true`, `decodeXerror:pass`와 2~16개 납품 파일 기록을 가져야 한다. 각 기록은 `out` 바로 아래 MP4의 실제 bytes·SHA-256과 일치하고 검사 전후 snapshot이 같아야 하며, 오디오·영상 스트림과 `project.json.duration` ±1초 길이를 가져야 한다. 중복 납품 경로는 거부한다. aggregate picture도 영상만 있고 길이가 양수이며 첫 납품 영상과 길이 차이가 1초 이하여야 한다. 프로젝트·상태·delivery proof와 납품 snapshot이 후보 ID에 포함되어 계획 뒤 변경을 차단한다.

## trusted workspace의 역사적 패키지 ZIP

workspace 등록은 저장공간 도구가 포함된 현재 repository root와 정확히 같고, `package.json`의 이름이 `road-music`, `bin.road-music`이 `cli/road-music.js`이며 실제 CLI·`AGENTS.md`·비-symlink `.git`이 존재할 때만 허용한다. 반환된 `usageScope:managed-cache`에 따라 `.roadmusic` 아래만 목록·용량에 포함하며 workspace 원본은 다시 세지 않는다.

지원 후보는 아래 두 역사적 local verification ZIP뿐이다.

| ZIP 상대 경로 | 고정 SHA-256 | 요구 receipt |
| --- | --- | --- |
| `Output/showreel-playlist-rebuild-20261018/package-check/MusicRoad-Skills-0.1.1.zip` | `95094e36f66ebb9e8e7392ce2af4fcb301faf12f1293d9f2feccd6c705dda80b` | `Output/showreel-playlist-rebuild-20261018/{package-audit.json,validation.json}`, ZIP 폴더 `SHA256SUMS.txt` |
| `Output/showreel-tomorrow-full-rebuild-20261018/package-check-v2/MusicRoad-Skills-0.1.1.zip` | `fa473c28dbe747194b48d8d0e3921b580af49ff9449d96f3fba39051d3787ff8` | `Output/showreel-tomorrow-full-rebuild-20261018/qa/{package-audit.json,delivery-audit.json}`, ZIP 폴더 `SHA256SUMS.txt` |

receipt의 절대 archive 경로·선언 SHA가 위 ZIP과 일치해야 한다. playlist 기록은 `local verification only; not published`와 `complete-local-not-published`, tomorrow 기록은 `pass:true`, `finalized:true`, 양쪽 `published:false`를 요구한다. 비-symlink `Output/skills-release-review-20261018/{published-release.json,github-releases.json}` 두 파일과 그 공개 digest가 모두 필요하며, 공개된 digest의 ZIP은 후보가 아니다. ZIP은 닫혀 있고 손상되지 않았으며 비실행 일반 파일이어야 하고, 실제 SHA·checksum·receipt·공개 기록과 검사 전후 snapshot이 모두 일치해야 한다. 경로 또는 부모 alias·symlink도 거부한다.

미래의 임의 package-check, draft, expanded kit, source ZIP은 지원하지 않는다. 새 패키지 producer를 일반 규칙으로 추론하지 말고 코드에 검증 프로필이 추가되기 전까지 보존한다.

## 공개 CLI 흐름

현재 설치본의 `schema`가 최종 계약이다. 별도 명령 없이 기존 12개 `storage:*`를 사용한다.

```bash
node cli/road-music.js storage:register --json '{"project":"/검증된/프로젝트/또는/workspace/root"}'
node cli/road-music.js storage:legacy --json '{"projectId":"등록 결과 ID"}'
node cli/road-music.js storage:adopt-preview --json '{"projectId":"등록 결과 ID","candidateIds":["목록에서 받은 후보 ID"]}'
node cli/road-music.js storage:adopt --json '{"planId":"이전 미리보기 ID"}' --confirm
node cli/road-music.js storage:preview --json '{"projectId":"등록 결과 ID","kinds":["cache"]}'
node cli/road-music.js storage:cleanup --json '{"planId":"정리 미리보기 ID"}' --confirm
```

`storage:legacy`의 Showreel 후보는 `evidence.final`, `duration`, `producer`를, 패키지 후보는 receipt·publisher 해시, ZIP SHA-256, `classification:local-verification`, profile kind를 제공한다. `storage:adopt-preview`의 source·target·용량·파일 수와 차단 사유를 확인한다. 계획은 15분 동안 유효하며 `--confirm`은 JSON 필드가 아니다.

채택은 후보 루트를 관리 cache로 원자 이동한 뒤 등록하고, 등록 실패 시 해당 이동을 되돌린다. 일반 프로필에서 parts와 aggregate를 함께 선택하면 parts를 먼저 옮겨 aggregate 증거를 유지한다. 보존할 채택 항목은 반환된 `entries[].id`를 `storage:pin`의 `entryId`로 고정한다. 실제 삭제까지 요청받은 경우에만 새 `storage:preview`·`storage:cleanup --confirm` 계획을 실행한다. 원본·완성본·aggregate·납품 파일·producer·검수 기록과 workspace 프로그램은 정리하지 않는다.
