# 명시한 프리셋으로 제작

사용자가 CD·그루브 다이얼·리듬 캔버스 또는 등록된 스타일을 지정했을 때 읽는다. 새 자유 연출 요청의 기본 경로는 [native 제작](production.md)이다. 일반적인 ‘음악 모션그래픽’이라는 표현을 기존 preset alias에 자동 매칭하지 않는다. 이미 선택한 형식을 자유 연출로 강제 변환하지 않는다.

- CD/그루브: [장르 계획](genres.md), [그루브 다이얼](groove-dial.md), [가상 아티스트 자산](images.md).
- 리듬 캔버스: [지원된 direction 스키마](rhythm-canvas.md). orbit/ribbons/grid/tiles는 이 경로의 구현값이며 Showreel의 표현 한계가 아니다.
- 사용자 등록 프리셋: [등록/자산 계약](presets.md).
- 보고 선택하는 요청: [선택 화면](selection.md). 기존 선택을 받았다면 다시 묻지 않는다.
- 실제 legacy plan/create/render 명령과 검증: [프리셋 제작 절차](preset-production.md).

기존 playlist_presets.py/cd_presets.py/motion_direction.py와 프리셋 자산/카탈로그를 그대로 유지한다. 새 native 명령을 도입했다는 이유로 과거 프로젝트·곡·프리셋을 자동 마이그레이션하지 않는다. 여러 곡의 기존 CD 화면·자막 스타일·캐스팅·이미지 선택은 원래 경로로 보존한다.
