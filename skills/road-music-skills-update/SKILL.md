---
name: road-music-skills-update
description: Road Music 모션그래픽 스킬 묶음의 설치 상태를 확인하고, 검증된 GitHub Release를 안전하게 설치·업데이트할 때 사용한다.
---

# Road Music 스킬 업데이트

## 버전 기록

설치 상태와 명시적 업데이트 확인 결과는 [제작 기록 스킬](../road-music-production-records/SKILL.md)의 SQLite component 원장에 남길 수 있다. 이 기록은 알림용이며, 오래된 기록만으로 설치 성공을 판단하거나 자동 설치하지 않는다.

`scripts/manage.cjs`는 manifest에 등록한 Road Music 스킬만 관리한다. 여기에는 `road-music-storage`, `road-music-production-records`와 지원 host용 agent 정의가 포함된다. `status`와 `check`은 프로그램·스킬 설치를 바꾸지 않으며, `check`는 확인 결과와 버전 관찰만 SQLite에 기록한다. `watch`는 변경을 알릴 뿐 자동 설치하지 않는다.

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
- Release 설치는 `roadkwonai/music-road-skills`의 `vX.Y.Z`, `MusicRoad-Skills-X.Y.Z.zip`, `SHA256SUMS.txt`가 모두 일치할 때만 진행한다. `check`의 최신 버전 정보는 설치 완료가 아니며, install/update 뒤에는 반환된 설치 결과와 managed 상태를 다시 확인한다. 체크섬·압축 검증·교체·상태 확인 중 하나라도 실패하면 설치 성공이나 준비 완료로 보고하지 않는다.
- 기존 관리 파일이 바뀌었거나 같은 이름의 미관리 스킬이 다르면 중단한다. 완전히 동일한 기존 스킬만 최초 설치에서 안전하게 채택한다.
- 설치 전 파일은 대상의 `.music-road-skills/backups/`에 보관하며 실패하면 롤백한다. 다른 스킬, 음악, 모델, 제작 결과는 건드리지 않는다.
- macOS와 Linux의 `unzip`/`zipinfo`가 필요하다. Windows 자동 설치는 지원하지 않는다.

설치 프로세스가 강제 종료된 뒤 `TARGET_BUSY`가 남으면, 표시된 PID가 실행 중인지 먼저 확인한다. 실행 중인 작업이 없을 때에만 오류 메시지에 표시된 대상의 `.music-road-skills/.lock` 파일 하나를 지운 뒤 다시 실행한다. 백업이나 스킬 폴더를 삭제하지 않는다.

프로그래밍 연동에는 현재 읽은 updater의 실제 절대 경로를 넣은 `require('/absolute/skills/road-music-skills-update/scripts/manage.cjs').execute(action, params)`를 사용한다. CLI 출력은 stdout JSON 한 줄이며, 진행 이벤트는 stderr JSONL이다.

스킬 묶음의 커밋·푸시·Release 게시까지 요청받은 유지보수 작업에서는 [로컬 GitHub 인증과 배포](references/github-release.md)를 따른다. 일반 `status`·`check`·설치 작업에 게시 절차를 추가하지 않는다.

제작 분석 HTML에서도 같은 updater의 check/update를 사용한다. 사용자의 업데이트 실행 클릭은 표시한 관리 설치 묶음에 대한 실행 요청이며, 단순 화면 열기는 설치 요청이 아니다. 진행량 미확인은 불확정으로 표시하고 확인된 설치 버전만 완료로 안내한다. 소스 체크아웃은 자동 교체하지 않으며, 응답 유실·중단 시 새 설치를 재제출하기 전에 기존 작업·관리 상태를 확인한다.

HTML의 개별 스킬 카드도 실제 설치는 관리 스킬 전체 묶음 단위다. 버튼·확인창에서 이 범위를 명시하고 한 스킬만 교체한 것처럼 안내하지 않는다. 확인 중 최신 버전과 실제 설치 검증 결과를 구분한다.
