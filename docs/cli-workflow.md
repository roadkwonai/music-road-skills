# Road Music CLI에서 제작실과 결과까지

CLI의 현재 공개 계약은 설치한 `node cli/road-music.js schema`가 기준입니다. `songs:list`의 절대 path·dir를 그대로 쓰고, 음악 생성의 jobId는 `job:wait`으로 완료를 확인합니다. 다른 버전의 `motion:*`·`skills:*` 예시가 schema에 없다면 실행하지 않습니다.

자세한 실제 명령·스킬 helper·원가사/SRT 준비·publish 예시는 [CLI 가이드 Markdown 원문](../skills/road-music-video-studio/assets/guides/cli.md)에서 관리합니다. HTML의 **사용 가이드 → CLI**는 같은 원문을 렌더링하며 우측 상단에서 Markdown으로 복사할 수 있습니다.

## 페이지의 역할

- **제작실:** 음악·스타일·표시 설정을 저장합니다. 저장은 렌더 완료가 아닙니다.
- **내 작업물:** 원음 SHA-256 기준으로 여러 프로젝트의 완성 음원·원가사·자막·영상·스토리보드와 검수·제작 기록을 모아 봅니다.
- **완성 결과·결과 검수:** 현재 프로젝트를 바로 확인하는 호환 경로입니다. 전역 메뉴에는 넣지 않으며, 모든 결과는 내 작업물에서 찾습니다.
- **사용 가이드:** 화면별 사용법·오류 복구를 읽고 Markdown 원문을 복사합니다.

스킬만 있는 환경은 실제 `road-music-video-studio/SKILL.md`의 부모를 기준으로 `scripts/studio.py init`, `serve --review --open`, `publish`를 사용합니다. 명시적인 서비스 시작 또는 `--open`만 필요한 화면을 열고, 조회·schema·배치는 새 창을 열지 않습니다. 기존 Ego 탭을 재사용하며 자동화에서는 `ROADMUSIC_STUDIO_AUTO_OPEN=0`을 사용합니다.

## 결과와 보존

manifest는 `audio`·`lyrics`·`captions`·`video`·`storyboard`를 분리합니다. `publish`는 현재 프로젝트의 목록 교체이므로 남길 파일도 다음 manifest에 넣습니다. 이후 내 작업물은 원음 SHA-256이 같은 결과를 이력으로 누적합니다. 원가사는 ASR로 교체하지 않고, SRT·LRC의 형식과 확정·추정 싱크 기록을 구분합니다. 음악 그룹 ZIP에는 사용한 원음과 등록된 완성 영상·음원·원가사·자막·스토리보드를 넣으며, 입력 외 샘플·중간 결과는 제외합니다. 등록 파일이 누락되거나 달라졌다면 ZIP을 만들지 않습니다.

기존 프로젝트는 `python3 "$STUDIO_SKILL/scripts/studio.py" library-register --project /absolute/existing-project`로 보관함에 추가할 수 있습니다. 이는 스킬 helper이며 설치된 Road Music CLI schema에 없는 `motion:*` 명령을 추측해 실행하지 않습니다.

이미지·영상 모델과 편집 엔진은 스킬의 실제 호스트 환경을 사용합니다. 선택 저장을 모델 실행으로 해석하거나 누락된 도구를 유료 API로 자동 대체하지 않습니다. [호스트와 이미지 계약](../skills/road-music-video-studio/references/image-providers.md)과 [문제 해결](../skills/road-music-video-studio/assets/guides/troubleshooting.md)을 따릅니다.
