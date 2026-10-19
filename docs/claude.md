# Claude Code에서 음악부터 영상까지

[처음으로](../README.md) · [설치](install.md) · [CLI 연계](cli-workflow.md) · [HTML 제작실](html-studio.md)

이 안내는 로컬 파일과 Node.js를 실행할 수 있는 **Claude Code CLI/IDE 세션**용이다. Claude 웹, Cowork, cloud 세션은 이 컴퓨터의 `node`·Codex CLI·로컬 HTML 서버를 직접 실행하는 경로가 아니므로, 이 스킬 묶음의 로컬 렌더와 `gpt-image` 브리지를 실행했다고 설명하지 않는다.

## 설치와 호출

Claude Code의 개인 스킬 기본 경로는 `~/.claude/skills`, 프로젝트 스킬 경로는 `.claude/skills`다. `CLAUDE_CONFIG_DIR`를 설정한 환경에서는 Road Music updater가 개인 경로를 그 디렉터리 아래로 해석한다. 설치 대상은 현재 실행한 저장소가 아니라 명시한 호스트 경로다.

```bash
# 로컬 Claude Code의 개인 스킬 경로
node skills/road-music-skills-update/scripts/manage.cjs install \
  --source "$PWD" --host claude

# 이 프로젝트에만 설치
node skills/road-music-skills-update/scripts/manage.cjs install \
  --source "$PWD" --target "$PWD/.claude/skills"
```

새 세션에서 각 디렉터리 이름을 `/road-music-showreel-playlist`처럼 호출하거나, 설명과 일치하는 요청으로 자동 선택하게 할 수 있다. 다음 여섯 스킬의 제작 범위와 원곡·가사·타이밍·HTML 검수 계약은 Codex와 같다.

| 스킬 | Claude Code에서 하는 일 |
| --- | --- |
| `road-music-showreel-playlist` | Showreel CD·리듬 캔버스·여러 곡 모션그래픽 |
| `road-music-showreel-cd` | 이전 CD 호출을 playlist 스킬로 호환 연결 |
| `road-music-showreel-mv` | 이미지·스토리보드·리듬 편집형 전곡 M/V |
| `road-music-jizura-playlist` | JIZURA 네이티브 키네틱 타이포·프로젝트·MP4 |
| `road-music-video-studio` | 로컬 HTML 선택·재생·피드백·검수 |
| `road-music-skills-update` | 버전 확인·보존형 설치·업데이트 |

LTX 2.5 기반 `road-music-mv` 감독 스킬과 모델은 이 묶음에 포함하지 않는다.

## Claude 이미지 경로

Claude Code에는 Codex의 내장 `image_gen` 도구가 없다. 새 이미지를 요구하는 Showreel 작업은 실제로 로드된 외부 `gpt-image` 스킬에 위임한다. 그 스킬은 같은 OS의 ChatGPT 로그인 Codex CLI를 통해 내장 `image_gen`을 사용한다. `gpt-image`가 설치·로드되지 않았으면 이미지 의존성 누락으로 보고하고, 로그인·Codex 설치·모델 설치·별도 유료 API로 대체하지 않는다.

`CLAUDE_SKILL_DIR`은 **현재 로드된 Road Music 스킬**의 경로이므로 `gpt-image` 경로로 쓰지 않는다. `gpt-image/SKILL.md`를 실제로 읽은 뒤 그 부모를 별도로 정한다. `CLAUDE_CONFIG_DIR`를 사용자 지정했다면 그 실제 Claude 스킬 폴더에서 `gpt-image`가 발견·로드됐는지 확인한다. 현재 `gpt-image` runner의 설치/진단 경로 지원까지 Road Music updater가 대신 제공한다고 가정하지 않으며, 외부 스킬을 수정·재설치하지 않는다.

```bash
GPT_IMAGE_SKILL="/absolute/path/to/loaded/gpt-image" # 실제 읽은 gpt-image/SKILL.md의 부모
node "$GPT_IMAGE_SKILL/scripts/gpt_image.mjs" generate \
  --prompt '...' --out /absolute/project/assets/photo-a.png
```

참조 이미지는 `--reference /absolute/path/to/reference.png`, 수정 대상은 `--edit-target /absolute/path/to/current.png`, 실제 알파 배경 요청은 `--background transparent`를 사용한다. 참조·수정·투명 배경의 입력 검증과 출력 계약은 `gpt-image` 스킬 및 [공통 이미지 공급자 계약](../skills/road-music-video-studio/references/image-providers.md)이 기준이다. Claude 결과 기록은 `provider: "gpt-image"`, `mode: "codex-cli-bridge"`를 사용하며 실제 생성 파일·프롬프트·참조 경로·SHA-256을 프로젝트에 남긴다.

JIZURA의 이미지 없는 절차형 연출에는 `gpt-image`가 필요 없다. 이미지가 필요한 Showreel 작업도 기존 가사, 원곡 시간축, 캐스팅 근거, 자막 검수와 HTML 선택을 바꾸지 않는다.

## 제작실과 업데이트

제작실에는 `--host claude`를 기록해 같은 로컬 HTML 선택·검수 흐름을 사용한다. 화면 저장은 렌더나 이미지 생성의 증거가 아니며, 실제 결과 manifest만 검수 화면에 등록한다.

```bash
python3 skills/road-music-video-studio/scripts/studio.py init \
  --out /absolute/path/to/project --music /absolute/path/to/song.wav --host claude
python3 skills/road-music-video-studio/scripts/studio.py serve \
  --project /absolute/path/to/project --host claude --open
```

`check`은 새 Release를 읽기 전용으로 확인한다. `install`과 `update`만이 명시한 대상에 백업을 만든 뒤 설치하며, 기존 로컬 수정·다른 스킬·음원·모델을 자동으로 바꾸지 않는다. `CLAUDE_CONFIG_DIR`를 쓸 때에도 updater가 반환한 실제 대상 경로를 기준으로 확인한다.

공식 Claude Code 스킬 경로·호출·`CLAUDE_SKILL_DIR` 치환은 [Skills 문서](https://code.claude.com/docs/en/skills), `CLAUDE_CONFIG_DIR`과 로컬 구성 경로는 [`.claude` 디렉터리 문서](https://code.claude.com/docs/en/claude-directory)를 따른다.
