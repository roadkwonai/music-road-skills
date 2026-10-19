# Music Road Skills 유지보수

한국어로 안내한다. 스킬의 사용자 선택·가사 원문·원곡 시계·기존 프로젝트를 보존한다.

## 로컬 Git·GitHub 인증

- 로컬 Git·GitHub 작업 전에 저장소 또는 가장 가까운 신뢰할 수 있는 상위 경로의 `.envrc`를 현재 셸에 로드한다. `GH_TOKEN`과 Git 작성자·커미터 등 정의된 환경값을 사용하며 기존의 다른 계정 인증이나 SSH를 먼저 사용하지 않는다. GitHub Actions의 워크플로 인증은 유지한다.
- 셸 추적을 끄고 `set -a; source /absolute/path/.envrc >/dev/null 2>&1; set +a`로 적용한다. 원문·토큰·인증 헤더는 출력하거나 Git·로그·산출물에 넣지 않는다. 파일 또는 `GH_TOKEN`이 없으면 인증 누락을 보고한다.
- `gh api user`와 `gh repo view OWNER/REPO --json viewerPermission`으로 계정·권한을 확인한다. PR·Release는 GitHub CLI(`gh`), HTTPS Git 작업은 `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' ...`를 사용한다. 전역 Git 인증이나 remote URL에 토큰을 저장하지 않는다.

## 유지보수 범위

- 이 저장소는 Showreel/JIZURA 스킬과 HTML·문서·업데이트 도구를 관리한다. LTX 기반 `road-music-mv`, 모델, 개인 음원·실제 제작 프로젝트·토큰은 배포하지 않는다.
- `manifest.json`이 묶음 버전·스킬 경로의 기준이다. 스킬별 핵심 계약을 유지하고 외부 엔진을 복제하지 않는다.
- 공통 HTML은 `skills/road-music-video-studio/`가 관리한다. 선택/피드백 저장과 실제 렌더 실행을 구분한다. 브라우저 입력으로 임의 명령을 실행하지 않는다.
- 업데이트는 GitHub Release와 체크섬을 검증하고 설치된 파일의 로컬 변경을 보존한다. 새 버전 확인만으로 기존 수정·다른 스킬·엔진을 덮어쓰지 않는다.
- `release/YYYY-MM-DD-title.md`에 변경·검증·제한을 쓰고 VERSION과 manifest의 버전을 맞춘다. 같은 정식 버전을 덮어쓰지 않는다.
- 변경에 맞는 단위·통합 검사를 실행한다. UI는 실제 선택·재생·저장을, 업데이트는 격리 경로와 변조/충돌을 검증한다.
- 여러 작업자가 파일을 나눠 수정할 수 있다. 담당 범위 밖의 변경을 되돌리지 않는다.

- HTML 제작·선택·검수 UI는 루트 DESIGN.md와 번들 Paperlogy를 적용한다. 설치에 필요한 공통 디자인 계약도 road-music-video-studio/assets/design/DESIGN.md에 포함한다.
- CLI/스킬은 기존 Ego 페이지 한 개에서 필요한 화면으로 이동한다. 같은 주소를 새 탭으로 반복 열지 않으며 사용자 생성 공간·제어 중단을 우회하지 않는다. 단계별 page-flow.md를 따른다.

음악·영상의 제작 이후 정보는 음악별 `/works/` 목록과 `/works/<원음 SHA-256>/` 상세의 내부 메뉴로 묶는다. 영상·음원·원가사·자막·스토리보드·프로젝트 검수 기록을 이 상세에서 확인하며, 제작 설정과 가이드는 별도 페이지로 유지한다. 전역 메뉴는 제작실·내 작업물·스타일·사용 가이드다. 현재 프로젝트의 옛 결과/검수 URL은 호환용으로 보존한다. UI는 Paperlogy·DESIGN.md와 사용자가 지정한 ProKit의 정보 구조·가독성 기준을 적용한다.
