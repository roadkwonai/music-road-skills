# 스킬 업데이트

업데이트 스킬은 스킬 사용·유지관리 요청에서 한 번만 GitHub Release를 읽기 전용으로 확인하고, 설치된 스킬의 로컬 변경을 보존하면서 명시된 설치만 수행합니다. 정기 자동 확인·자동 설치는 기본값이 아닙니다.

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

```bash
node skills/road-music-skills-update/scripts/manage.cjs install --source "$PWD"
```

기본 설치 대상은 `CODEX_HOME/skills` 또는 `~/.codex/skills`입니다. 프로그래밍 연동은 `require('./scripts/manage.cjs').execute(action, params)`를 쓰며, CLI는 stdout에 결과 JSON 한 줄, stderr에 진행 JSONL을 기록합니다. 지원 action과 매개변수는 스킬의 `SKILL.md`와 `manage.cjs`의 `execute(action, params)`가 기준입니다.

이 업데이터의 기본 대상은 Codex 스킬 경로입니다. Antigravity App/IDE는 `--host antigravity`와 `~/.gemini/config/skills`, Antigravity CLI는 `--host antigravity-cli`와 `~/.gemini/antigravity-cli/skills`, 프로젝트 설치는 `--target /absolute/project/.agents/skills`를 사용합니다. 명시한 `--target`이 우선합니다. 어느 호스트에서도 `check`는 알림용이며 자동 설치·모델 설치를 하지 않습니다. [Antigravity 안내](antigravity.md)

> [!WARNING]
> 업데이트 확인만으로 동작 중 렌더나 브라우저 세션을 종료하지 않습니다. 설치 전에 진행 중인 프로젝트와 사용자 수정본을 확인하세요.
