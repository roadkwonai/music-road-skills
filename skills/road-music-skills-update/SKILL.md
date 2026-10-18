---
name: road-music-skills-update
description: Road Music 모션그래픽 스킬 묶음의 설치 상태를 확인하고, 검증된 GitHub Release를 안전하게 설치·업데이트할 때 사용한다.
---

# Road Music 스킬 업데이트

`scripts/manage.cjs`는 여섯 개의 manifest 등록 스킬만 관리한다. `status`와 `check`은 읽기 전용이며, `watch`는 변경을 알릴 뿐 자동 설치하지 않는다.

스킬 사용 요청에서는 [사용 시 업데이트 확인](references/use-time-check.md)을 한 번만 따른다. `check` 요청 자체에서는 다시 확인하지 않으며, 새 버전이 없으면 제작을 계속한다.

```bash
UPDATE_SKILL="/absolute/skills/road-music-skills-update" # 현재 읽은 이 SKILL.md의 실제 부모
SKILLS_PARENT="$(dirname "$UPDATE_SKILL")"
node "$UPDATE_SKILL/scripts/manage.cjs" status --target "$SKILLS_PARENT"
node "$UPDATE_SKILL/scripts/manage.cjs" check --target "$SKILLS_PARENT"
node "$UPDATE_SKILL/scripts/manage.cjs" install --target "$SKILLS_PARENT"
node "$UPDATE_SKILL/scripts/manage.cjs" update --target "$SKILLS_PARENT"
```

- 위 명령의 `SKILLS_PARENT`는 현재 설치 대상이며, updater 실행 파일의 형제 스킬들이 있는 경로다. 일반 Release 설치는 `--source`를 생략한다. 설치 대상은 기본적으로 `${CODEX_HOME:-~/.codex}/skills`이며 `--target`과 `--source`에는 절대 경로만 쓴다.
- 위 예시는 이미 설치된 스킬을 관리하는 경우다. 새 설치나 다른 호스트·대상을 요청받으면 사용자가 지정한 목적지를 우선한다. 체크아웃에서 이 문서를 읽었다는 이유로 저장소의 `skills/`를 설치 대상으로 삼지 않는다.
- 로컬 묶음으로 설치할 때만 `manifest.json`·`VERSION`·`skills/`를 모두 담은 체크아웃 또는 Release 루트를 `BUNDLE_ROOT`로 사용한다. 실행 파일 경로, 설치 대상, 배포 source를 서로 바꾸지 않는다.

```bash
BUNDLE_ROOT="/absolute/path/to/music-road-skills"
node "$UPDATE_SKILL/scripts/manage.cjs" install \
  --target "$SKILLS_PARENT" --source "$BUNDLE_ROOT"
```
- `--host claude`의 기본 대상은 `~/.claude/skills`이며 `CLAUDE_CONFIG_DIR`가 있으면 그 아래 경로다. `--host antigravity`의 기본 대상은 `~/.gemini/config/skills`, `--host antigravity-cli`는 `~/.gemini/antigravity-cli/skills`다. 프로젝트별 Claude는 `.claude/skills`, 공통 프로젝트는 `.agents/skills`를 항상 `--target` 절대 경로로 지정한다. 기존 `~/.gemini/antigravity/skills`는 자동 이전하지 않는다.
- Release 설치는 `roadkwonai/music-road-skills`의 `vX.Y.Z`, `MusicRoad-Skills-X.Y.Z.zip`, `SHA256SUMS.txt`가 모두 일치할 때만 진행한다.
- 기존 관리 파일이 바뀌었거나 같은 이름의 미관리 스킬이 다르면 중단한다. 완전히 동일한 기존 스킬만 최초 설치에서 안전하게 채택한다.
- 설치 전 파일은 대상의 `.music-road-skills/backups/`에 보관하며 실패하면 롤백한다. 다른 스킬, 음악, 모델, 제작 결과는 건드리지 않는다.
- macOS와 Linux의 `unzip`/`zipinfo`가 필요하다. Windows 자동 설치는 지원하지 않는다.

설치 프로세스가 강제 종료된 뒤 `TARGET_BUSY`가 남으면, 표시된 PID가 실행 중인지 먼저 확인한다. 실행 중인 작업이 없을 때에만 오류 메시지에 표시된 대상의 `.music-road-skills/.lock` 파일 하나를 지운 뒤 다시 실행한다. 백업이나 스킬 폴더를 삭제하지 않는다.

프로그래밍 연동에는 현재 읽은 updater의 실제 절대 경로를 넣은 `require('/absolute/skills/road-music-skills-update/scripts/manage.cjs').execute(action, params)`를 사용한다. CLI 출력은 stdout JSON 한 줄이며, 진행 이벤트는 stderr JSONL이다.

스킬 묶음의 커밋·푸시·Release 게시까지 요청받은 유지보수 작업에서는 [로컬 GitHub 인증과 배포](references/github-release.md)를 따른다. 일반 `status`·`check`·설치 작업에 게시 절차를 추가하지 않는다.
