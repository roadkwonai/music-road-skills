# 호스트별 이미지 생성

곡별 프롬프트·자산 역할·참조 계보·원곡 시계를 유지하고 현재 작업 호스트의 생성 경로로 실제 이미지 파일을 만든다.

| 실행 환경 | 기본 생성 경로 | `--host` | 계획 `requiredTool` / `mode` |
| --- | --- | --- | --- |
| ChatGPT / Codex | 세션의 내장 `image_gen` | `codex` | `image_gen` / `built-in` |
| 로컬 Claude Code CLI / IDE | 외부 `gpt-image` 스킬 → ChatGPT 로그인 Codex CLI → 내장 `image_gen` | `claude` | `gpt-image` / `codex-cli-bridge` |
| Antigravity App / IDE | 해당 환경의 Nano Banana 네이티브 이미지 기능 | `antigravity` | `antigravity-native` / `host-native` |
| Antigravity CLI | 해당 버전의 Nano Banana 도구 또는 내장 `image-generator` 경로 | `antigravity-cli` | `antigravity-native` / `host-native` |

`requiredTool`은 생성 경로를 선택하는 계획 값이며 세션 도구의 실제 함수명이나 생성 완료 증거가 아니다. HTML과 Road Music CLI는 이미지 모델 자체를 내장하지 않는다. 이미지가 해당 제작 방식의 기본인 경우 완료 전 실제 도구 호출→workspace 파일→source/prompt/SHA ledger→decode→장면/렌더 사용 증거를 확인한다. 도구 누락·rate limit은 그 이미지 단계를 미완료로 남기며 유료 API·코드 자산으로 대체하지 않는다. 절차형 JIZURA처럼 이미지가 필요 없는 작업은 생성 경로를 실행하지 않는다.

## Claude의 GPT Image 연결

Claude에서는 설치된 **`gpt-image` 스킬의 `SKILL.md`를 먼저 읽고 그 runner를 사용한다.** Road Music이 별도 이미지 API나 중복 브리지를 만들지 않는다. 실제 로드한 `gpt-image/SKILL.md`의 부모를 `GPT_IMAGE_SKILL`로 정한다. `${CLAUDE_SKILL_DIR}`는 현재 읽은 Road Music 스킬 자신의 폴더일 수 있으므로 다른 스킬의 경로로 복사하지 않는다.

필수 구성은 Node.js 22+, Codex CLI, 같은 OS 환경의 **Sign in with ChatGPT**, 실제로 로드한 `gpt-image` 스킬이다. Road Music 업데이터는 `${CLAUDE_CONFIG_DIR:-~/.claude}/skills`를 Claude 개인 대상으로 해석하지만, 외부 `gpt-image`의 설치 위치·진단 지원 경로는 그 runner의 계약을 따로 확인한다. Road Music 스킬은 [설치·업데이트 스킬](../../road-music-skills-update/SKILL.md)을 따르고, 외부 `gpt-image`가 없으면 그 의존성 누락을 보고한다. 이미지 생성 위임만으로 새 로그인·계정 교체·모델 설치를 시작하지 않는다. 누락된 이미지 단계만 미완료로 남긴다.

`CLAUDE_CONFIG_DIR`를 쓸 때에는 그 실제 스킬 폴더에서 `gpt-image`가 발견되는지도 확인한다. 외부 runner의 설치/진단이 사용자 지정 경로를 따르는지는 설치 버전의 동작이 기준이며, Road Music의 경로 지원만으로 그 외부 스킬이 복사되지는 않는다.

```bash
GPT_IMAGE_SKILL="/absolute/installed/gpt-image" # 실제 읽은 gpt-image SKILL.md 부모
node "$GPT_IMAGE_SKILL/scripts/gpt_image.mjs" generate \
  --prompt '곡별로 확정한 이미지 프롬프트' \
  --out '/absolute/workspace/project/assets/photo-a.png'

# 통과한 A를 실제 파일 참조로 전달
node "$GPT_IMAGE_SKILL/scripts/gpt_image.mjs" generate \
  --prompt '같은 인물의 다음 장면을 위한 확정 프롬프트' \
  --reference '/absolute/workspace/project/assets/photo-a.png' \
  --out '/absolute/workspace/project/assets/photo-b.png'

# 기존 이미지를 수정할 때는 현재 수정 대상을 첨부
node "$GPT_IMAGE_SKILL/scripts/gpt_image.mjs" generate --mode edit \
  --prompt '요청받은 수정 내용' \
  --edit-target '/absolute/workspace/project/assets/photo-b.png' \
  --out '/absolute/workspace/project/assets/photo-b-v2.png'
```

- Road Music에서 곡·장르·가사에 맞는 이미지 기획을 위임받았다면 역할별 프롬프트를 먼저 확정하고 runner에 그대로 전달한다. 별도로 준 사용자 원문 프롬프트를 임의로 개사·번역·확장하지 않는다.
- CD의 photoA를 먼저 만들고, 반환된 실제 PNG를 B/C/케이스의 참조로 첨부한다. 수정은 가장 최근 결과를 `--edit-target`으로 재첨부한다. 참조 경로가 없으면 텍스트 설명이나 캐시 추측으로 대체하지 않는다.
- 투명 CD 케이스 요청은 `--background transparent`를 쓴다. 실제 PNG alpha 검수도 유지한다. 여러 독립 자산은 설치된 `gpt-image`의 batch 계약을 따르되 A에 의존하는 자산은 A가 만들어진 다음 실행한다.
- 최초 설치·연결 확인에는 해당 스킬의 `doctor --target claude --json`을 사용한다. 일반 생성마다 진단·모델 목록 탐색·별도 계획 호출을 반복하지 않는다. 로그인이나 이미지 이용 한도 오류에 자동 재시도·유료 API 전환을 하지 않는다.
- 인증 파일이나 API 키를 읽거나 전달하지 않는다. 브리지는 ChatGPT 인증을 확인하고 API 관련 환경을 자식 Codex에서 제거한다. API 인증만 확인되면 이미지 생성을 중단하고 필요한 인증 상태를 안내한다.

이는 로컬 실행 도구가 있는 Claude Code 경로다. Claude 웹/Cowork가 이 컴퓨터의 Codex CLI와 파일을 직접 실행한다고 설명하지 않는다.

## 공통 자산 계약

1. 실제 사용할 도구·참조 파일 입력을 확인한다. 추론용 모델 선택을 이미지 모델 선택으로 해석하지 않고, 없는 명령·모델 ID를 만들지 않는다.
2. 결과 파일을 열어 화면비·인물 일관성·문구·자막 여백·필요한 투명도를 확인한다. 지원하지 않는 형식/편집은 누락으로 기록한다.
3. 프로젝트 `assets/`에 저장하고 실제 도구, 반환 모델(없으면 `null`), 확정 프롬프트, 참조 파일·해시를 남긴다. `images.json` 또는 direction media 입력으로 같은 엔진에 전달한다.
4. 생성 경로가 달라도 캐스팅·구도·비율·가사·표시 선택·원곡 시계를 바꾸지 않는다. HTML 검수에는 실제 파일만 등록한다.

```json
{
  "host": "claude",
  "generator": "gpt-image/codex-cli/image_gen",
  "model": null,
  "promptId": "photoA",
  "file": "assets/photo-a.png",
  "sha256": "실제 파일에서 계산",
  "referenceFiles": [],
  "status": "generated-and-visually-reviewed"
}
```

위 기록은 실제 생성 뒤 작성하며 계획만으로 생성 완료라고 하지 않는다. Antigravity 기본은 Nano Banana를 유지한다. 사용자가 별도로 `gpt-image`를 명시 호출한 작업은 그 스킬 자체의 Codex 브리지 계약을 따른다.

## 유료 모델과 설치 경계

기본 `allowPaidModels:false`를 유지한다. `gpt-image`는 별도 과금 Images API를 사용하지 않는 ChatGPT 로그인 경로이며 API 키를 요청하지 않는다. `gpt-image-2.5` 같은 API로 품질·오류·한도 때문에 자동 전환하지 않는다. 사용자가 해당 작업의 유료 API 사용을 긍정적으로 명시한 경우에만 **별도 경로**로 검토하며 `gpt-image` 브리지의 대안으로 몰래 호출하지 않는다. Road Music 업데이터는 외부 `gpt-image` 스킬·계정·Codex 런타임을 덮어쓰거나 자동 갱신하지 않는다.

## 근거

Claude 설치·호출·현재 스킬 경로는 [공식 Skills](https://code.claude.com/docs/en/skills), 개인 설정 위치는 [공식 .claude 디렉터리](https://code.claude.com/docs/en/claude-directory)를 따른다. GPT Image의 실제 옵션·인증·batch 방식은 **현재 설치된 `gpt-image/SKILL.md`와 references**가 기준이다. Antigravity 네이티브 경로는 [Models](https://www.antigravity.google/docs/models/#additional-models) · [CLI 변경 기록](https://www.antigravity.google/docs/changelog?tab=cli) · [도구 목록](https://www.antigravity.google/docs/hooks/)을 참고하고 실행 버전에서 확인한다.
