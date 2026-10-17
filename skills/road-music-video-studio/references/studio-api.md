# 제작실 명령과 파일 계약

## 명령

| 명령 | 역할 | 표준 출력 |
| --- | --- | --- |
| `init --out ABS [--music ABS] [--mode MODE] [--host codex\|antigravity\|antigravity-cli]` | 새 프로젝트와 선택적 외부 음악 등록 | 초기화 JSON 한 줄 |
| `serve --project ABS [--music ABS] [--host codex\|antigravity\|antigravity-cli] [--review] [--open] [--timeout SEC]` | 토큰 보호 루프백 제작실 | stderr 준비 JSONL, 선택 뒤 stdout 완료 JSON 한 줄 |
| `publish --project ABS --manifest ABS` | 완성 미디어를 검수 화면에 등록 | 등록 JSON 한 줄 |

`serve`의 기본 제한 시간은 900초다. `--open`은 로컬 기본 브라우저를 여는 명시적 요청일 때만 쓴다. 서버는 `127.0.0.1`에만 바인딩하고, 토큰·정확한 Host·같은 Origin이 모두 맞는 요청만 저장한다.

기본 세션은 선택 저장 뒤 완료되어 다음 제작 단계가 즉시 `selection.json`과 `production-request.json`을 읽는다. 결과 검수에는 `--review`를 사용한다. 이 모드에서는 선택·피드백을 여러 번 저장할 수 있고, 화면의 **검수 마치기**가 완료 신호다. 진행 중 새 결과는 자동 새로고침하지 않으며 **새 결과 확인**으로만 읽는다.

## 저장 파일

- `studio-project.json`: 프로젝트 이름·등록 미디어 목록과 읽기 전용 `imagePolicy`를 기록한다. 외부 음악은 파일 경로·SHA-256·크기로 고정한다. 음악 없이 시작하면 `media`는 빈 배열이며, 브라우저에서 고른 파일만 프로젝트 `inputs/music/`에 등록된다.
- `selection.json`: 호스트, 모드, 실제 스타일 id, 화면 표시 값. `null`은 SKIP/미지정이다. `host`는 `codex`, `antigravity`, `antigravity-cli`이며 실제 이미지 생성은 해당 호스트 도구가 실행한다.
- `production-request.json`: 선택을 저장한 시점의 입력 스냅샷이다. 제작 스킬은 이 파일을 읽어 이어서 작업한다.
- `showreel-request.json`: CD·Showreel 모션그래픽에서만 만드는 기존 `plan/create --selection` 호환 입력이다. `schemaVersion`, `styleId`, `display`, `music`만 포함한다. SKIP은 기존 도움말과 같은 false/빈 채널명으로 정규화한다.
- `feedback.json`: `draft`, `needs-revision`, `approved`와 피드백 본문.

`imagePolicy`는 Codex일 때 `{ "provider": "image_gen", "allowPaidModels": false }`, Antigravity일 때 `{ "provider": "antigravity-native", "allowPaidModels": false }`로만 기록한다. 브라우저 입력으로 유료 모델을 허용할 수 없으며, 추가 유료 API는 별도의 명시적 요청에서만 판단한다.

## 제작 방식 샘플

`assets/examples.json`은 네 제작 방식의 실제 형식 샘플만 등록한다. 각 항목은 `mode`, 제목·설명·태그, `SKILLS_ROOT` 상대 `video`·`poster`, 오디오 메모와 출처를 가져야 한다. 서버는 이 manifest에서 검증된 파일만 `/media/sample-*`으로 제공한다. 샘플은 다른 곡의 형식 예시이며 현재 선택한 음악의 새 제작 결과가 아니다.

선택을 저장한 뒤 서버 연결이 끊기면 `selection.json`과 `production-request.json`의 값을 사용한다. 이전에 고른 표시·채널값은 SKIP으로 덮어쓰지 않는다.

## 결과 등록 manifest

`title`, `sourceMusicSha256`, `video`, `audio`, `captions`, `storyboard`만 허용한다. `title`은 제어문자 없는 1~180자 문자열이며 검수 화면의 프로젝트 이름을 바꾼다. `sourceMusicSha256`은 렌더에 사용한 원음의 64자리 SHA-256이다. 각 미디어 값은 절대 파일 경로 하나 또는 최대 24개 경로 배열이다. 지원 형식은 MP4/MOV/WebM, WAV/MP3/FLAC/M4A 등 오디오, SRT/VTT/ASS/LRC, PNG/JPEG/WebP/AVIF/GIF다.

등록 결과는 현재 음악의 SHA-256과 대조해 **현재 원음과 일치**, **다른 원음의 결과**, **원음 확인 필요**로 표시한다. `sourceMusicSha256`을 넣지 않은 이전 결과는 현재 곡의 완료 결과처럼 표시하지 않는다.

제작실은 등록된 id로만 미디어를 제공한다. URL 또는 브라우저 입력으로 임의 경로를 읽거나, 브라우저에서 명령을 실행하지 않는다. 브라우저 업로드는 프로젝트 안 `inputs/music/`에만 쓴다.
