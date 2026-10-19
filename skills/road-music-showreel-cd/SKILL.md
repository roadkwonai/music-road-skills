---
name: road-music-showreel-cd
description: 이전 Showreel CD 프리셋 호출의 호환 경로. 새 이름 road-music-showreel-playlist로 연결한다.
---

# 새 스킬로 연결

실제 CD Showreel 제작·수정 기록은 대상 [Showreel 스킬](../road-music-showreel-playlist/SKILL.md)과 [제작 기록 스킬](../road-music-production-records/SKILL.md)을 함께 따른다.

이 호환 경로도 Codex·로컬 Claude Code CLI/IDE·Antigravity에서 `road-music-showreel-playlist`의 설치·호스트 이미지·HTML 검수 계약을 그대로 따른다. 새 CD 제작은 대상 스킬의 실제 이미지 도구·workspace 자산·렌더 사용·전용 썸네일 완료 조건을 그대로 적용하며, 선택 화면이나 프리셋 미리보기만으로 완료라 하지 않는다. 사람이 이미지 미사용 또는 제공·승인 자산 재사용을 명시한 경우만 대상 스킬의 예외를 따른다. Claude에서 이미지가 필요하면 로드된 `gpt-image` 스킬의 ChatGPT 로그인 Codex CLI 브리지를 쓰며, 자세한 공급자 계약은 [공통 이미지 공급자 안내](../road-music-video-studio/references/image-providers.md)를 따른다.

이전 이름으로 요청하면 [Showreel 플레이리스트 프리셋](../road-music-showreel-playlist/SKILL.md)을 읽고 그 절차를 실행한다. 새 제작·프리셋 추가는 `$road-music-showreel-playlist`를 사용한다. 기존 이름 호출은 유지하며 실제 스크립트·자산은 `road-music-showreel-playlist`의 경로를 사용한다. 공통 HTML에서 CD 스타일을 골라 진행할 수 있다.

시작 시에는 [사용 시 업데이트 확인](../road-music-skills-update/references/use-time-check.md)을 한 번만 적용한다.

새 CD 제작은 공통 HTML 제작실을 `showreel-cd` 모드로 열어 CD 계열 미리보기부터 보여준다. 다른 제작 방식/스타일을 사용자가 명시한 경우 그 선택이 우선한다. 실제 엔진·스크립트는 유지보수되는 playlist 구현을 사용한다.

새 CD/플레이리스트 작업은 `Output`이 아닌 `.roadmusic/work/<원음SHA12 또는 unassigned>/<프로젝트--ID>/`에서 생성한다. 새 `Output/...` 요청은 실제 작업 경로로 변환되며, 게시 검증을 마친 최종 납품만 `Output`의 시간 버전에 둔다. 기존 프로젝트 경로는 바꾸지 않는다.

호환 카탈로그와 제작 HTML은 유지보수 구현의 `DESIGN.md` 토큰과 번들 Paperlogy를 따른다.

HTML 제작·선택·검수 화면에는 [공통 DESIGN.md](../road-music-video-studio/assets/design/DESIGN.md)와 번들 Paperlogy를 적용한다. 현재 프로젝트의 DESIGN.md가 있으면 이를 먼저 대조한다. 화면 열기는 [단계별 페이지 이동](../road-music-video-studio/references/page-flow.md)의 같은 Ego 페이지를 재사용하며, 이미 열린 화면에 새 탭을 추가하지 않는다.

완성 결과는 [공통 보관함 계약](../road-music-video-studio/SKILL.md#음악별-내-작업물과-상세)에 따라 원음 기준으로 등록한다. 음악별 상세의 내부 메뉴에서 스타일 영상·음원·가사/자막·스토리보드·검수 기록을 함께 확인하고, 실제 확인된 스타일 이름을 manifest에 기록한다. 전역 메뉴에 결과·검수 페이지를 추가로 분산시키지 않는다.
