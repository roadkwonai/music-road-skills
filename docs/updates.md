# 스킬 업데이트

업데이트 스킬은 스킬 사용·유지관리 요청에서 한 번만 GitHub Release를 읽기 전용으로 확인하고, 설치된 스킬의 로컬 변경을 보존하면서 명시된 설치만 수행합니다. 정기 자동 확인·자동 설치는 기본값이 아닙니다.

아래 상대 경로와 `$PWD`는 저장소 루트에서 실행할 때만 쓴다. 설치본을 다른 작업 디렉터리에서 관리할 때는 현재 읽은 `SKILL.md`의 실제 절대 경로와 그 부모 target을 쓴다.

```bash
# 현재 설치와 원격 Release 비교: 읽기 전용
node skills/road-music-skills-update/scripts/manage.cjs check

# 설치 대상의 최신 Release를 명시적으로 반영
node skills/road-music-skills-update/scripts/manage.cjs update

# 명시적으로 요청한 경우에만 주기적 알림; 자동 설치하지 않음
node skills/road-music-skills-update/scripts/manage.cjs watch
```

## 동작 원칙

1. `check`는 해당 요청에서 한 번만 실행한다. 변화가 없으면 조용히 계속하고 새 버전만 알립니다.
2. `install`/`update`는 대상과 체크섬을 검증하고 기존 파일을 백업합니다.
3. 로컬 수정 또는 충돌은 보존하고, 무단 덮어쓰기를 하지 않습니다.
4. `watch`는 새 Release를 알릴 뿐 설치·재시작·모델 다운로드를 하지 않습니다.
5. 묶음 manifest는 등록된 스킬을 모두 포함해야 합니다. 제작 스킬의 공용 HTML·디자인·Paperlogy 자산은 해당 스킬 폴더 안에 넣어 함께 설치하며, 프로젝트 루트의 별도 파일은 자동으로 복사하지 않습니다.
6. 대상에 설치된 묶음이 없으면 `check`는 `not-installed`를 기록하고 `update`는 설치를 대신 실행하지 않습니다. 공개된 정식 Release가 없으면 `check`는 `no-release`를 기록합니다. 두 상태 모두 최신 설치나 설치 완료가 아니며, 설치할 Release가 생길 때까지 `update`를 실행하지 않습니다.

> [!NOTE]
> 2026-10-20 버전 초기화 뒤의 첫 묶음은 `0.1.0`입니다. 이전 `0.1.1` 설치본은 `check`에서 `release-reset-required`로 표시하며, `update`는 이를 최신으로 표시하거나 자동 교체하지 않습니다. 현재 작업과 로컬 수정본을 보존하고 새 빈 설치 대상을 지정해 설치하세요. 기존 대상의 버전을 낮추는 설치는 계속 차단합니다.

> [!IMPORTANT]
> 사용자 승인에 따라 2026-10-20의 현재 `0.1.0` 수정본을 같은 버전으로 다시 배포합니다. 이는 이번 버전 초기화에만 적용하는 예외입니다. 같은 버전 번호만으로 이전 다운로드와 같은 파일이라고 판단하지 말고, Release의 `SHA256SUMS.txt`와 설치 전 파일 검증 결과를 확인하세요. 이후 정식 릴리스는 다시 새 버전·새 태그만 사용합니다.

## SQLite 버전 기록

`ROADMUSIC_DATA_DIR`가 현재 Road Music 프로필을 가리키고 제작 기록 도구가 설치된 경우, 명시적 `check`와 성공한 `install`/`update`는 SQLite component 원장에 스킬 묶음과 실제 설치된 개별 스킬의 버전·마지막 확인 결과를 남깁니다. 개별 `version`이 manifest에 없으면 묶음 `VERSION` 기준임을 함께 표시합니다. 관리 설치가 아닌 소스 checkout을 확인한 경우에는 이름과 상태에 **소스 checkout·미설치 관찰**로 표시하여 설치 완료와 구분합니다. 이 기록은 대시보드 알림과 비교용입니다. 설치 성공은 계속 설치 대상의 manifest·VERSION·파일 해시·체크섬 검증으로만 판정하며, SQLite에 남은 오래된 버전만으로 설치 성공이나 업데이트 완료로 판단하지 않습니다.

독립 CLI의 제작실은 프로필 `settings.deliveryRoot`가 가리키는 검증된 완료본 작업 경로를 우선 사용합니다. 설정이 없으면 설치 키트 경로를 사용하며, 이 경우 이전 작업 이력이 연결됐다고 간주하지 않습니다. 해당 작업의 WorkLibrary 이력 DB를 실제로 읽었을 때만 오래된 연결 표시를 해제하며, 확인하지 못하면 기존 상태를 유지합니다. 설치·업데이트 과정에서 기존 `Output` 폴더나 SQLite 이력을 이동·복제하지 않습니다.

```bash
node skills/road-music-skills-update/scripts/manage.cjs install --source "$PWD"
```

기본 설치 대상은 `CODEX_HOME/skills` 또는 `~/.codex/skills`입니다. 프로그래밍 연동은 실제 절대 경로를 넣은 `require('/absolute/skills/road-music-skills-update/scripts/manage.cjs').execute(action, params)`를 쓰며, CLI는 stdout에 결과 JSON 한 줄, stderr에 진행 JSONL을 기록합니다. 지원 action과 매개변수는 스킬의 `SKILL.md`와 `manage.cjs`의 `execute(action, params)`가 기준입니다.

이 업데이터의 기본 대상은 Codex 스킬 경로입니다. Claude Code는 `--host claude`와 `~/.claude/skills`(또는 `CLAUDE_CONFIG_DIR` 아래의 동등 경로), 프로젝트 설치는 `--target /absolute/project/.claude/skills`를 사용합니다. Antigravity App/IDE는 `--host antigravity`와 `~/.gemini/config/skills`, Antigravity CLI는 `--host antigravity-cli`와 `~/.gemini/antigravity-cli/skills`, 공통 프로젝트 설치는 `--target /absolute/project/.agents/skills`를 사용합니다. 명시한 `--target`이 우선합니다. 어느 호스트에서도 `check`는 알림용이며 자동 설치·모델 설치를 하지 않습니다. [Claude Code 안내](claude.md) · [Antigravity 안내](antigravity.md)

> [!WARNING]
> 업데이트 확인만으로 동작 중 렌더나 브라우저 세션을 종료하지 않습니다. 설치 전에 진행 중인 프로젝트와 사용자 수정본을 확인하세요.
