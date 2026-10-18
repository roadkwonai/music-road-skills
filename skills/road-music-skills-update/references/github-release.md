# 로컬 GitHub 인증과 배포

묶음의 커밋·푸시·Release 게시를 요청받은 경우에만 적용한다. 저장소의 AGENTS.md·버전·기존 Release·배포 워크플로를 먼저 확인하고 이미 승인된 게시 범위 안에서 진행한다.

1. 저장소 또는 가장 가까운 신뢰할 수 있는 상위 경로의 `.envrc`를 찾는다. 셸 추적을 끄고 현재 명령의 셸에서 적용한다. `GH_TOKEN`과 Git 작성자·커미터 등 정의된 환경값을 사용한다. 명령마다 새 셸이면 다시 적용한다.
2. `.envrc` 원문, 토큰 값, 인증 헤더를 출력하지 않는다. `.envrc`를 커밋·배포하거나 토큰을 remote URL·명령 인자·전역 Git 설정에 넣지 않는다.
3. `gh api user`와 `gh repo view OWNER/REPO --json viewerPermission`으로 계정과 권한을 확인한다. 값이 없거나 권한이 부족하면 실제 차단 상태를 보고하며 다른 계정의 캐시 인증으로 계속하지 않는다.
4. PR·Release는 `gh`로 처리한다. HTTPS Git push/fetch는 아래처럼 GitHub CLI 인증을 연결해 같은 `GH_TOKEN`을 사용한다. GitHub Actions는 워크플로에서 제공하는 인증을 그대로 사용한다.

```bash
set +x
set -a
source /absolute/path/to/.envrc >/dev/null 2>&1
set +a
test -n "$GH_TOKEN" || exit 1
gh api user --jq .login
gh repo view OWNER/REPO --json viewerPermission
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push origin BRANCH
```

설치·업데이트 확인만으로 커밋·푸시·게시 권한을 추정하지 않는다. 기존 공개 태그나 Release 자산은 덮어쓰지 않으며, 새 버전의 태그·원격 커밋·ZIP·체크섬·공개 설치 결과를 확인한 뒤 게시 완료로 보고한다.
