---
name: road-music-showreel-cd
description: 이전 Showreel CD 프리셋 호출의 호환 경로. 새 이름 road-music-showreel-playlist로 연결한다.
---

# 새 스킬로 연결

이전 이름으로 요청하면 [Showreel 플레이리스트 프리셋](../road-music-showreel-playlist/SKILL.md)을 읽고 그 절차를 실행한다. 새 제작·프리셋 추가는 `$road-music-showreel-playlist`를 사용한다. 기존 이름 호출은 유지하며 실제 스크립트·자산은 `road-music-showreel-playlist`의 경로를 사용한다. 공통 HTML에서 CD 스타일을 골라 진행할 수 있다.

시작 시에는 [사용 시 업데이트 확인](../road-music-skills-update/references/use-time-check.md)을 한 번만 적용한다.

새 CD 제작은 공통 HTML 제작실을 `showreel-cd` 모드로 열어 CD 계열 미리보기부터 보여준다. 다른 제작 방식/스타일을 사용자가 명시한 경우 그 선택이 우선한다. 실제 엔진·스크립트는 유지보수되는 playlist 구현을 사용한다.
