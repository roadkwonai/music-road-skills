---
name: road-music-skills-update
description: Road Music 모션그래픽 스킬 묶음의 설치 상태를 확인하고, 검증된 GitHub Release를 안전하게 설치·업데이트할 때 사용한다.
---

# Road Music 스킬 업데이트

`scripts/manage.cjs`는 여섯 개의 manifest 등록 스킬만 관리한다. `status`와 `check`은 읽기 전용이며, `watch`는 변경을 알릴 뿐 자동 설치하지 않는다.

스킬 사용 요청에서는 [사용 시 업데이트 확인](references/use-time-check.md)을 한 번만 따른다. `check` 요청 자체에서는 다시 확인하지 않으며, 새 버전이 없으면 제작을 계속한다.

```bash
node scripts/manage.cjs status
node scripts/manage.cjs check
node scripts/manage.cjs install --source "$PWD"
node scripts/manage.cjs update
node scripts/manage.cjs install --host antigravity --source "$PWD"
```

- 설치 대상은 기본적으로 `${CODEX_HOME:-~/.codex}/skills`이며 `--target`과 `--source`에는 절대 경로만 쓴다. 현재 묶음 폴더에서는 `--source "$PWD"`가 절대 경로를 전달한다.
- `--host antigravity`의 기본 대상은 `~/.gemini/config/skills`, `--host antigravity-cli`는 `~/.gemini/antigravity-cli/skills`다. 프로젝트별 `.agents/skills`는 항상 `--target` 절대 경로로 지정한다. 기존 `~/.gemini/antigravity/skills`는 자동 이전하지 않는다.
- Release 설치는 `roadkwonai/music-road-skills`의 `vX.Y.Z`, `MusicRoad-Skills-X.Y.Z.zip`, `SHA256SUMS.txt`가 모두 일치할 때만 진행한다.
- 기존 관리 파일이 바뀌었거나 같은 이름의 미관리 스킬이 다르면 중단한다. 완전히 동일한 기존 스킬만 최초 설치에서 안전하게 채택한다.
- 설치 전 파일은 대상의 `.music-road-skills/backups/`에 보관하며 실패하면 롤백한다. 다른 스킬, 음악, 모델, 제작 결과는 건드리지 않는다.
- macOS와 Linux의 `unzip`/`zipinfo`가 필요하다. Windows 자동 설치는 지원하지 않는다.

설치 프로세스가 강제 종료된 뒤 `TARGET_BUSY`가 남으면, 표시된 PID가 실행 중인지 먼저 확인한다. 실행 중인 작업이 없을 때에만 오류 메시지에 표시된 대상의 `.music-road-skills/.lock` 파일 하나를 지운 뒤 다시 실행한다. 백업이나 스킬 폴더를 삭제하지 않는다.

프로그래밍 연동에는 `require('./scripts/manage.cjs').execute(action, params)`를 사용한다. CLI 출력은 stdout JSON 한 줄이며, 진행 이벤트는 stderr JSONL이다.
