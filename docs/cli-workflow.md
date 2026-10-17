# Road Music CLI에서 모션그래픽까지

Road Music CLI는 음악 생성·라이브러리 관리와 스킬 전달을 연결합니다. 스킬은 음악 엔진을 대체하지 않으며, 모션그래픽 렌더는 선택한 Showreel/JIZURA 환경에서 수행합니다.

## AI 작업 순서

```bash
# 현재 설치 버전의 공개 계약을 먼저 확인
node cli/road-music.js schema

# 음악 생성 뒤 완료 대기
node cli/road-music.js song:generate --json '{"caption":"...","lyrics":"..."}'
node cli/road-music.js job:wait --json '{"jobId":"<반환된 jobId>"}'

# 곡 목록에서 반환한 절대 경로를 다음 단계에 사용
node cli/road-music.js songs:list
node cli/road-music.js motion:handoff --json '{"music":"/absolute/path/from/songs-list.wav"}'
```

`song:generate`의 입력 형식과 `job:wait`의 정확한 인수는 설치된 CLI의 `schema`를 따릅니다. 생성 응답의 `jobId`를 먼저 기다리고, `songs:list`가 반환한 절대 `path`를 그대로 전달합니다.

## 스킬 관리 명령

| 명령 | 역할 |
| --- | --- |
| `skills:status` | 설치 위치·현재 상태 조회 |
| `skills:check` | 새 묶음 버전의 읽기 전용 확인 |
| `skills:install` | 번들 스킬을 설치 |
| `skills:update` | 명시적으로 새 버전 설치 |
| `skills:watch` | 새 Release 알림을 감시, 자동 설치하지 않음 |
| `motion:studio` | HTML 제작실 열기 |
| `motion:handoff` | 음원의 절대 경로를 제작실/스킬 입력으로 전달 |

일반 결과는 stdout JSON 한 줄이며, `--events` 진행 정보는 stderr JSONL로 읽습니다. 연결 오류가 `uncertain:true`이면 같은 생성 요청을 자동 재제출하지 말고 서비스·대기열·곡 목록으로 실제 실행 여부를 확인합니다.

## 자동화 경계

AI는 HTML에서 실제 선택을 받고 그 값을 제작에 반영할 수 있습니다. 반면 `image_gen`은 호스트 도구이고 CLI 내장 모델이 아닙니다. 모델 설치, 음원 생성 재시도, 외부 업로드, 기존 프로젝트 덮어쓰기는 별도 요청 범위입니다.

`motion:studio`와 `motion:handoff`의 host 입력은 Codex, Antigravity App/IDE, Antigravity CLI 중 현재 실행 환경을 기록합니다. 스킬 설치 대상은 각각 `CODEX_HOME/skills`, `~/.gemini/config/skills`, `~/.gemini/antigravity-cli/skills`이고, 프로젝트에는 `.agents/skills`를 쓸 수 있습니다. 최종 입력명은 CLI `schema`가 기준입니다.

완성본을 검수할 때는 `motion:studio`가 여는 제작실을 검수 모드로 유지합니다. 제작자는 새 MP4·자막·스토리보드를 `publish`로 등록하고, 검수자는 HTML의 **새 결과 확인**으로 같은 프로젝트의 목록을 갱신한 뒤 **검수 마치기**로 끝냅니다. 이 과정은 외부 게시를 수행하지 않습니다.

Codex 작업은 내장 `image_gen`을 사용할 수 있고, Antigravity 작업은 해당 환경에서 이용 가능한 네이티브 이미지 도구만 사용합니다. 어떤 호스트이든 CLI·스킬 경계에서는 이미지 경로, SHA-256, 실제 프롬프트, 생성 도구 기록을 같은 manifest로 넘깁니다. 특정 모델명·API 키·유료 권한은 입력으로 명시되지 않으면 가정하지 않습니다. [Antigravity 호스트 안내](antigravity.md)
