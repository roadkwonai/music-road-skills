# 설치

## 요구 사항

- Node.js 24
- Git
- 선택: `ffmpeg`/`ffprobe` (렌더와 미디어 검사)
- 선택: 설치된 Showreel 또는 JIZURA 엔진 (각각의 실제 렌더 단계)

스킬 묶음 설치는 엔진·AI 모델·음원 라이브러리를 다운로드하거나 옮기지 않습니다.

## 저장소에서 설치

```bash
git clone https://github.com/roadkwonai/music-road-skills.git
cd music-road-skills
node skills/road-music-skills-update/scripts/manage.cjs install --source "$PWD"
```

위 상대 경로와 `$PWD`는 `cd music-road-skills` 뒤의 저장소 루트 기준입니다. 설치본을 다른 작업 디렉터리에서 관리할 때는 현재 읽은 `SKILL.md`의 실제 절대 경로를 씁니다.

기본 대상은 `CODEX_HOME/skills`이며 `CODEX_HOME`이 없으면 `~/.codex/skills`입니다. 이미 같은 이름의 스킬이 있으면 설치 도구가 원본을 먼저 보존합니다. 설치 뒤 새 Codex 세션에서 스킬 이름을 호출합니다.

## Claude Code에서 사용

Claude Code의 전역 스킬은 `~/.claude/skills`, 특정 프로젝트의 스킬은 `.claude/skills`에 둡니다. `CLAUDE_CONFIG_DIR`를 설정한 환경에서는 개인 경로가 그 디렉터리 아래로 바뀝니다. 업데이터의 Claude 호스트 지원 여부와 정확한 옵션은 설치한 `road-music-skills-update`의 `SKILL.md`가 기준이며, 프로젝트 대상은 항상 절대 경로로 명시합니다. [Claude Code 상세 안내](claude.md)

```bash
# Claude Code 전역 스킬 경로
node skills/road-music-skills-update/scripts/manage.cjs install \
  --source "$PWD" --host claude

# 이 프로젝트에서만 사용할 경로
node skills/road-music-skills-update/scripts/manage.cjs install \
  --source "$PWD" --target "$PWD/.claude/skills"
```

Claude에서 새 이미지를 만들어야 하면 별도 `gpt-image` 스킬이 필요합니다. Road Music 스킬은 이를 설치하거나 ChatGPT 로그인을 열지 않습니다. 실제 로드한 `gpt-image/SKILL.md`의 부모를 `GPT_IMAGE_SKILL`로 사용하며, 누락되면 이미지 의존성 누락으로 보고합니다. `CLAUDE_CONFIG_DIR`를 쓰더라도 외부 `gpt-image` runner가 그 사용자 지정 경로를 자동 지원한다고 가정하지 말고 실제 로드 경로와 해당 스킬의 설치·진단 계약을 확인합니다.

## Antigravity에서 사용

Antigravity는 Codex의 `CODEX_HOME` 경로를 추정하지 않습니다. 공식 설치 위치는 다음과 같습니다.

| 대상 | 전역 스킬 경로 |
| --- | --- |
| Antigravity App/IDE | `~/.gemini/config/skills` |
| Antigravity CLI | `~/.gemini/antigravity-cli/skills` |
| 프로젝트 공통 | `.agents/skills` |

업데이터는 `--host antigravity`, `--host antigravity-cli`, `--target ABS`를 지원하며 명시한 `--target`이 우선합니다. 전역 경로와 프로젝트 경로를 혼동하지 마세요. Antigravity는 작업 지침으로 `AGENTS.md`와 `GEMINI.md`를 함께 읽습니다. [공식 Skills 문서](https://www.antigravity.google/docs/skills/) · [공식 Rules 문서](https://www.antigravity.google/docs/rules/) · [상세 안내](antigravity.md)

```bash
# Antigravity App/IDE 전역 설치
node skills/road-music-skills-update/scripts/manage.cjs install --source "$PWD" --host antigravity

# Antigravity CLI 전역 설치
node skills/road-music-skills-update/scripts/manage.cjs install --source "$PWD" --host antigravity-cli

# 저장소에만 적용하는 공통 프로젝트 설치
node skills/road-music-skills-update/scripts/manage.cjs install --source "$PWD" \
  --target "$PWD/.agents/skills"
```

```bash
python3 skills/road-music-video-studio/scripts/studio.py init \
  --out /absolute/path/to/project --host antigravity
python3 skills/road-music-video-studio/scripts/studio.py serve \
  --project /absolute/path/to/project --host antigravity --open
```

`init` 뒤 HTML에서 음악 파일을 등록할 수 있고, 이미 확정한 음악은 `--music /absolute/path/to/song.wav`로 전달할 수 있습니다. Antigravity의 Nano Banana 네이티브 이미지 기능이 사용 가능한 경우에만 해당 도구로 새 이미지를 만듭니다. Showreel MV는 기본 경로에서 `gpt-image-2.5` 같은 별도 유료 API로 자동 전환하지 않으며, 사용자가 별도로 요청한 경우에만 사용합니다. 이미지 결과는 호스트와 관계없이 공통 프로젝트 manifest에 경로·해시·프롬프트를 남깁니다.

## Road Music CLI와 함께 설치

Road Music CLI 설치 과정은 런타임을 준비한 뒤 번들된 스킬 묶음을 설치합니다. 설치 상태는 다음 공개 명령으로 확인합니다.

```bash
node cli/road-music.js skills:status
node cli/road-music.js skills:check
```

CLI가 반환하는 정확한 JSON과 지원 옵션은 `node cli/road-music.js schema`에서 확인합니다. [CLI 워크플로](cli-workflow.md)를 이어서 읽으세요.

> [!WARNING]
> 설치는 기존 사용자 수정본을 자동으로 삭제하지 않습니다. 충돌이 있으면 백업 경로와 충돌 정보를 확인한 뒤, 의도적으로 설치 또는 복구를 선택하세요.
