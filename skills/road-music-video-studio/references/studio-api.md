# 제작실 명령과 파일 계약

## 명령

| 명령 | 역할 | 표준 출력 |
| --- | --- | --- |
| `init --out ABS [--music ABS] [--mode MODE] [--host codex\|claude\|antigravity\|antigravity-cli]` | 새 프로젝트와 선택적 외부 음악 등록 | 초기화 JSON 한 줄 |
| `serve --project ABS [--music ABS] [--host codex\|claude\|antigravity\|antigravity-cli] [--review] [--open] [--timeout SEC] [--session-file ABS]` | 토큰 보호 루프백 제작실 | stderr 준비 JSONL, 선택 뒤 stdout 완료 JSON 한 줄 |
| `publish --project ABS --manifest ABS` | 완성 미디어를 검수 화면에 등록 | 등록 JSON 한 줄 |

`serve`의 기본 제한 시간은 900초다. `--open`은 로컬 기본 브라우저를 여는 명시적 요청일 때만 쓴다. 서버는 `127.0.0.1`에만 바인딩하고, 토큰·정확한 Host·같은 Origin이 모두 맞는 요청만 저장한다.

기본 세션은 선택 저장 뒤 완료되어 다음 제작 단계가 즉시 `selection.json`과 `production-request.json`을 읽는다. 결과 검수에는 `--review`를 사용한다. 이 모드에서는 선택·피드백을 여러 번 저장할 수 있고, 화면의 **검수 마치기**가 완료 신호다. 진행 중 새 결과는 자동 새로고침하지 않으며 **새 결과 확인**으로만 읽는다.

## 저장 파일

- `studio-project.json`: 프로젝트 이름·등록 미디어 목록과 읽기 전용 `imagePolicy`를 기록한다. 외부 음악은 파일 경로·SHA-256·크기로 고정한다. 음악 없이 시작하면 `media`는 빈 배열이며, 브라우저에서 고른 파일만 프로젝트 `inputs/music/`에 등록된다.
- `selection.json`: 호스트, 모드, 실제 스타일 id, 화면 표시 값. `null`은 SKIP/미지정이다. `host`는 `codex`, `claude`, `antigravity`, `antigravity-cli`이며 실제 이미지 생성은 해당 호스트 공급자가 실행한다.
- `production-request.json`: 선택을 저장한 시점의 입력 스냅샷이다. 제작 스킬은 이 파일을 읽어 이어서 작업한다.
- `showreel-request.json`: CD·등록 프리셋 모션그래픽에서만 만드는 기존 `plan/create --selection` 호환 입력이다. `schemaVersion`, `styleId`, `display`, `music`만 포함한다. SKIP은 기존 도움말과 같은 false/빈 채널명으로 정규화한다.
- `feedback.json`: `draft`, `needs-revision`, `approved`와 피드백 본문.

`imagePolicy`는 Codex일 때 `{ "provider": "image_gen", "mode": "built-in", "allowPaidModels": false }`, Claude일 때 `{ "provider": "gpt-image", "mode": "codex-cli-bridge", "allowPaidModels": false }`, Antigravity일 때 `{ "provider": "antigravity-native", "allowPaidModels": false }`로 기록한다. Claude의 `gpt-image` 누락은 의존성 누락이며 브라우저 입력으로 로그인·설치·유료 모델을 허용할 수 없다. 추가 유료 API는 별도의 명시적 요청에서만 판단한다.

## 제작 방식 샘플

`assets/examples.json`은 네 제작 방식의 실제 형식 샘플만 등록한다. 각 항목은 `mode`, 제목·설명·태그, `SKILLS_ROOT` 상대 `video`·`poster`, 오디오 메모와 출처를 가져야 한다. 서버는 이 manifest에서 검증된 파일만 `/media/sample-*`으로 제공한다. 샘플은 다른 곡의 형식 예시이며 현재 선택한 음악의 새 제작 결과가 아니다.

선택을 저장한 뒤 서버 연결이 끊기면 `selection.json`과 `production-request.json`의 값을 사용한다. 이전에 고른 표시·채널값은 SKIP으로 덮어쓰지 않는다.

## 결과 등록 manifest

`title`, `sourceMusicSha256`, `video`, `audio`, `lyrics`, `captions`, `storyboard`만 허용한다. `title`은 제어문자 없는 1~180자 문자열이며 검수 화면의 프로젝트 이름을 바꾼다. `sourceMusicSha256`은 렌더에 사용한 원음의 64자리 SHA-256이다. 각 미디어 값은 절대 파일 경로 하나 또는 최대 24개 경로 배열이다. 지원 형식은 MP4/MOV/WebM, WAV/MP3/FLAC/M4A 등 오디오, UTF-8 TXT/Markdown 원가사, SRT/VTT/ASS/LRC 자막, PNG/JPEG/WebP/AVIF/GIF다. 원가사는 최대 256 KiB이며 UTF-8 BOM을 허용한다. 원가사 파일은 HTML이나 Markdown으로 실행하지 않고 일반 텍스트로 미리 본다.

`publish`는 이전 검수 등록을 누적하지 않고 manifest의 허용 미디어 전체로 교체한다. 따라서 후속 `publish`에서도 유지할 기존 스토리보드·음원·영상·자막을 모두 manifest에 다시 포함한다. 등록 결과는 현재 음악의 SHA-256과 대조해 **현재 원음과 일치**, **다른 원음의 결과**, **원음 확인 필요**로 표시한다. `sourceMusicSha256`을 넣지 않은 이전 결과는 현재 곡의 완료 결과처럼 표시하지 않는다.

제작실은 등록된 id로만 미디어를 제공한다. URL 또는 브라우저 입력으로 임의 경로를 읽거나, 브라우저에서 명령을 실행하지 않는다. 브라우저 업로드는 프로젝트 안 `inputs/music/`에만 쓴다.


## 완성 파일 표시와 다운로드

상태 응답의 `media.review`는 `audios`, `lyrics`, `videos`, `captions`, `storyboard`를 구분한다. 등록된 완성 파일에는 재생용 `url`, 첨부 다운로드용 `downloadUrl`, `size`와 원음 대조 상태 `sourceStatus`를 제공한다. `lyrics`에는 원문 미리보기 `text`도 포함한다. 최초 입력 `media.music`은 제작에 사용한 원음이며 완료 음원 목록으로 자동 승격하지 않는다.

완성 파일 화면은 음원 재생·다운로드, 원가사 읽기·다운로드, 전곡 영상 재생·다운로드를 먼저 표시한다. 파일 개수는 등록 현황이며 파일 검사·청취·가사 싱크 검수 완료의 의미로 쓰지 않는다. 스토리보드·자막·수정 의견은 펼침 영역에 남긴다.

다운로드는 등록된 `/media/ID?token=TOKEN&download=1`만 제공하며 `Content-Disposition: attachment`의 UTF-8 파일명으로 저장한다. 임의 경로를 받는 다운로드 API는 만들지 않는다. 기존 토큰·Host·바이트 범위 재생 검증은 그대로 적용한다. `publish`는 결과 목록을 교체하므로 후속 영상 등록 시 보존할 음원·가사·기존 결과 경로를 함께 포함한다.


## 공통 메뉴와 CLI 시작

- 명시적인 `service:start` 연결 성공 후 제작실을 열며, 상태 API의 `application: "road-music-video-studio"`와 절대 `project`를 대조해 기존 서버를 재사용한다. 조회·스키마·배치 호출에는 자동 열기를 적용하지 않는다.
- `serve`는 기본 앱 데이터 폴더의 `video-studio-session.json`에 `{schemaVersion:1,url,project,pid,expiresAt}`를 원자적으로 기록한다. `expiresAt`는 Unix **초**이며, `--session-file`은 별도 프로필·격리 실행용이다. 종료 시 자신의 URL과 일치하는 레코드만 해제한다.
- 메뉴는 `/`, `/catalog/`, 음악·표시 설정·완성 파일의 앵커를 연결한다. 카탈로그의 영상·설정 파일도 동일한 토큰으로 제공하고 등록된 스타일 id만 받는다.
- 공통 제작실은 페이지를 떠날 때 브라우저 세션에 미저장 선택·의견을 임시 보관하고 복귀할 때 형식을 검증해 복원한다. 제작 설정·피드백의 실제 저장은 기존 저장 버튼으로만 수행한다.
- 현재 소스 CLI에서 `.agents/skills` 또는 `skills`의 제작실을 사용한다. 해당 자산이 없는 구형 배포본에는 새 스킬을 자동 설치하지 않으며, 서버 시작은 유지하고 제작실 준비 경고를 남긴다.

Showreel 모션그래픽의 `styleId:null`은 곡별 새 native 연출을 뜻한다. 이 경우 실제 음원은 필요하지만 기존 프리셋을 강제하지 않으며 `production-request.json`을 읽어 native 제작으로 이어간다. 등록 프리셋용 `showreel-request.json`은 새로 만들거나 반환하지 않는다. CD 모드는 계속 실제 프리셋 id가 필요하다.

## 역할별 페이지와 문서

- `GET /?token=…`: 제작 설정 전용. 기존 선택과 입력 음원을 유지한다.
- `GET /results/?token=…&view=list|large`: 완성 파일 목록/큰 보기. 각 미디어와 별도 원가사·자막을 제공한다.
- `GET /review/?token=…`: 스토리보드·영상·원문·자막·의견 검수 전용. 미저장 의견은 같은 세션의 페이지 왕복에서 보존한다.
- `GET /guide/?token=…`, `/guide/<slug>/?token=…`: `start/studio/results/review/styles/jizura/cli/troubleshooting`의 Markdown 원문에서 HTML을 렌더한다.
- `GET /guide/<slug>.md?token=…`: 해당 원문의 UTF-8 Markdown을 내려받는다. 임의 파일 경로는 받지 않는다.
- `GET /downloads/complete.zip?token=…`: 현재 프로젝트에 publish된 영상·음원·원가사·자막을 원본 그대로 묶는다. 입력 음원(id=music)·예시·스토리보드는 제외한다. 빈 목록은 404, 동명 파일은 ZIP 내부에서만 번호 접미사로 구분한다.

모든 경로는 기존 Host·세션 토큰 인증을 사용한다. 미디어의 Range·개별 다운로드도 유지한다. `media.review.captions[].text`는 크기 제한 안의 UTF-8 원문 미리보기이며, 읽지 못하면 `previewError`만 제공하고 원본 다운로드는 유지한다. 원가사를 ASR로 바꾸거나 LRC를 SRT로 이름만 바꾸지 않는다.

`guide_content.py --out ABS_DESIGN_ASSETS`는 `guides/*.md`와 `guides/*.html`을 생성한다. Python `apply_design`과 Node `applyDesign`이 이 렌더러를 재사용해 Markdown 복사 원문과 HTML이 갈라지지 않게 한다. 새 패키지 설치는 필요 없고 기존 Python 실행 환경을 사용한다.

## 음악별 작업 보관함

- `GET /works/`: 음악별 목록. `GET /works/<64hex>/`: 해당 음악의 작업 상세와 내부 메뉴.
- `GET /api/works`: 파일 시각 기준 정렬된 그룹 요약·KST 날짜 배열·음원·대표 영상·가용성.
- `GET /api/works/<64hex>`: source·전체 files·스토리보드·원음 연결 상태·다운로드 주소.
- `GET /works/<group>/files/<file>`: 등록된 파일만 Range 재생, `&download=1`이면 원본 다운로드. `.../text`는 UTF-8 가사·자막만 최대 256KiB JSON 미리보기.
- `GET /works/<group>/download.zip`: 사용한 원음과 완료 파일·스토리보드 포함. 중복 SHA 제거, 누락/변경 시 409로 중단하며 부분 ZIP을 성공으로 보내지 않는다.
- `GET /api/works/<group>/records`: 그룹 파일에 실제 연결된 프로젝트별 설정·검수 기록. 원음이 바뀌거나 없어진 프로젝트는 사용할 수 없다고 표시한다.
- `POST /api/works/<group>/records/<project-id>/feedback`: 기존 Origin·세션 토큰·JSON 검증을 거쳐 해당 프로젝트 의견만 저장한다. 브라우저에서 임의 프로젝트 경로나 명령을 받지 않는다.

라이브러리는 데이터 폴더 `video-studio-library.json`이며 원음 해시별 누적 스냅샷이다. `publish`, 완성 프로젝트 `serve`, `library-register --project ABS`에서 등록한다. 입력 음원의 내용이 달라졌으면 이전 결과를 새 곡에 붙이지 않고 제작 당시 SHA가 일치하는 보존 원음을 확인한다. 프로세스 간 잠금·원자 저장을 사용하며 등록/ZIP 작성 중 파일 변경을 검증한다. 영상·가사·원음 파일은 이동·수정하지 않는다. 기존 프로젝트 기록의 경로 교정은 검증된 실제 보존 파일을 확인한 경우에만 명시적으로 한다.

### 가이드 예시 이미지

`GET /guide-media/<name>?token=...`은 공통 가이드에 등록된 SVG/WebP 이미지 이름만 제공한다. Host와 세션 토큰을 확인하며 비등록·경로 이탈·누락 파일은 거부한다. 외부 URL이나 사용자가 지정한 임의 경로를 이미지로 불러오지 않는다. 가이드의 각 fenced 예시는 텍스트만 클립보드로 복사하며 실제 명령 실행 API와 연결되지 않는다.
