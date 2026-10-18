---
name: 라인
design_system_name: LINE Design System for Global Family Service (LDSG)
slug: line-design-system
category: messenger
last_updated: "2026-08-02"
created_at: 2026-05-25
lang: ko
logo: https://getdesign.kr/logos/line-design-system.png
colors:
  # Messenger Primary Palette
  primary: "{colors.ldsg-color-linegreen}"   # 명세의 대표색 역할 — 서비스가 재정의하는 ldsg-color-brand-primary·검정 본문색 ldsg-color-role-primarytext 와 다른 축
  ldsg-color-linegreen: oklch(0.72 0.205 149)   # #06C755 · 공식 공개값. LDSG 기본 Primary
  ldsg-color-black: oklch(0 0 0)   # #000000 · 공식 공개값. 본문 텍스트·아이콘 스트로크
  ldsg-color-disabled-gray: oklch(0.92 0 0)   # #E4E4E4 · 공식 공개값. 비활성 컨텐츠/라벨
  # Gray Scale — LDSG는 White/Black 포함 18단을 이름과 hex로 발행하고, 아래는 그중
  # 본 문서가 다루는 11단이다. gray-800 하나만 발행값(#2A2A2A)과 다르며, 재구성
  # 잔차이므로 값은 그대로 둔다. 발행값을 이 주석 줄에 두는 이유는 토큰 줄의
  # 트레일링 주석에 hex가 둘이면 audit:oklch가 짝짓기 모호로 그 줄을 통째로
  # 스킵하기 때문이다 — 차이를 적으려다 그 줄만 기계 검증에서 빠질 뻔했다.
  ldsg-color-gray-100: oklch(0.99 0 0)   # #FCFCFC
  ldsg-color-gray-150: oklch(0.97 0 0)   # #F5F5F5 · 흰색 외 기본 표면 배경(가장 빈번)
  ldsg-color-gray-200: oklch(0.95 0 0)   # #EFEFEF
  ldsg-color-gray-300: oklch(0.90 0 0)   # #DFDFDF · 기본 보더 컬러 / 슬라이더 트랙(enabled)
  ldsg-color-gray-350: oklch(0.83 0 0)   # #C8C8C8 · placeholder / text-input placeholder
  ldsg-color-gray-400: oklch(0.77 0 0)   # #B7B7B7
  ldsg-color-gray-500: oklch(0.67 0 0)   # #949494 · help text, 보조 텍스트, footer items
  ldsg-color-gray-600: oklch(0.57 0 0)   # #777777 · bottom-nav enabled 아이콘/텍스트, pulldown-menu 우측 항목
  ldsg-color-gray-700: oklch(0.45 0 0)   # #555555
  ldsg-color-gray-800: oklch(0.30 0 0)   # #303030 · page-indicator active dot. 발행값과 다름(위 주석)
  ldsg-color-gray-900: oklch(0.18 0 0)   # #111111 · popup 닫기 버튼, side-drawer 메뉴 텍스트
  # Theme Color — Brand Color (기본값은 Rainbow 토큰 참조; 서비스가 재정의 가능)
  ldsg-color-brand-onsurface: oklch(1 0 0)   # #FFFFFF · 공식 기본 매핑(= white)
  ldsg-color-brand-onsurface-alt: oklch(0 0 0)   # #000000 · 공식 기본 매핑(= black)
  ldsg-color-brand-primary: oklch(0.72 0.205 149)   # #06C755 · 공식 매핑(= linegreen)
  ldsg-color-brand-primary-alt: oklch(0.63 0.178 149)   # #04A647 · = lightgreen-700 (매핑 공식 / hex 재구성)
  ldsg-color-brand-secondary: oklch(0.28 0.052 269)   # #1E2742 · = linenavy (매핑 공식 / hex 재구성)
  # ldsg-color-brand-secondary-alt:  TBD                    # 공식 "TBD" 표기 — 다운스트림이 임의 값을 발명하지 않는다
  # Theme Color — Role Color (의미 토큰)
  ldsg-color-role-positive: oklch(0.72 0.205 149)   # #06C755 · = lime-600. LINE-green 패밀리와 동일값(아래 정정 참고)
  ldsg-color-role-negative: oklch(0.61 0.217 28)   # #E8332E · = red-600 (매핑 공식 / hex 재구성)
  ldsg-color-role-link: oklch(0.61 0.197 258)   # #2C7DFA · = blue-600 (매핑 공식 / hex 재구성)
  ldsg-color-role-primarytext: oklch(0 0 0)   # #000000 · 공식 공개값(= black)
  ldsg-color-role-disabled: oklch(0.92 0 0)   # #E4E4E4 · 공식 공개값(= disabled-gray)
typography:
  # Title 계열 (타이트 line-height ~1.25–1.40) — RECONSTRUCTED px
  ldsg-typography-title-xxl:   # Headings
    fontFamily: Paperlogy
    fontSize: 38px
    lineHeight: 1.25
  ldsg-typography-title-xl:   # Headings
    fontFamily: Paperlogy
    fontSize: 28px
    lineHeight: 1.28
  ldsg-typography-title-l:   # Headings, List Item Title, Sub Title
    fontFamily: Paperlogy
    fontSize: 22px
    lineHeight: 1.30
  ldsg-typography-title-m:   # Headings, List Item Title, Sub Title
    fontFamily: Paperlogy
    fontSize: 18px
    lineHeight: 1.33
  ldsg-typography-title-s:   # Headings, List Item Title, Sub Title
    fontFamily: Paperlogy
    fontSize: 16px
    lineHeight: 1.35
  ldsg-typography-title-xs:   # Headings, List Item Title, Sub Title
    fontFamily: Paperlogy
    fontSize: 14px
    lineHeight: 1.40
  # Text 계열 (가독성 line-height 1.50) — RECONSTRUCTED px
  ldsg-typography-text-l:   # Body, Button Label
    fontFamily: Paperlogy
    fontSize: 18px
    lineHeight: 1.50
  ldsg-typography-text-m:   # Body baseline, Button Label, Sub Text, Caption, Overline, Badge
    fontFamily: Paperlogy
    fontSize: 16px
    lineHeight: 1.50
  ldsg-typography-text-s:   # Body, Button Label, Sub Text, Caption, Overline, Badge
    fontFamily: Paperlogy
    fontSize: 14px
    lineHeight: 1.50
  ldsg-typography-text-xs:   # Body, Button Label, Sub Text, Caption, Overline, Badge
    fontFamily: Paperlogy
    fontSize: 12px
    lineHeight: 1.50
spacing:
  ldsg-spacing-50: 2px
  ldsg-spacing-100: 4px
  ldsg-spacing-200: 8px
  ldsg-spacing-300: 12px
  ldsg-spacing-400: 16px   # 메신저 표면의 지배적 사이드 마진
  ldsg-spacing-500: 20px   # modal/popup 본문 인셋
  ldsg-spacing-600: 24px
  ldsg-spacing-800: 32px
  ldsg-spacing-1000: 40px
rounded:
  ldsg-radius-100: 3px   # 가장 작은 컴포넌트(예: Badge)
  ldsg-radius-200: 5px   # 가장 빈번. 버튼류 등 중간 사이즈
  ldsg-radius-300: 7px   # 화면 50% 정도 사이즈(예: 카드)
  ldsg-radius-400: 12px   # 화면 50%를 넘는 컴포넌트(Modal Sheet, Popup)
  ldsg-radius-circle: 50%   # 원형(지름 = 높이/너비의 50%) · 명세 Dimension 밖(%)이라 공식 린터 에러, 값은 유지
  ldsg-border-50: 0.5px   # 특수 케이스 한정. 일부 디바이스/브라우저에서 미렌더 위험
  ldsg-border-100: 1px   # 기본값(가장 널리 사용)
  ldsg-border-200: 2px   # 요소 강조가 필요할 때
elevation:
  # On White 배경
  ldsg-shadow-on-white-100: 0px 0px 2px oklch(0 0 0 / 0.07), 0px 1px 2px oklch(0 0 0 / 0.07)   # 소형 버튼, Chip, Badge
  ldsg-shadow-on-white-200: 0px 1px 6px oklch(0 0 0 / 0.12)   # 중/대 버튼
  ldsg-shadow-on-white-300: 0px 1px 20px oklch(0 0 0 / 0.07)   # Large Card, Bottom Sheet
  # On Light Gray 배경
  ldsg-shadow-on-gray-100: 0px 0px 1px oklch(0 0 0 / 0.05), 0px 1px 1px oklch(0 0 0 / 0.05)
  ldsg-shadow-on-gray-200: 0px 1px 4px oklch(0 0 0 / 0.06)
  ldsg-shadow-on-gray-300: 0px 1px 15px oklch(0 0 0 / 0.04)
---

# Design

## Source of truth

- **상태:** Active
- **갱신일:** 2026-10-18
- **우선순위:** 이 `# Design` 아래의 Road Music 계약이 제품 HTML의 정전이다. 뒤의 `# LDSG 원출처 참고`는 토큰의 출처와 범용 컴포넌트 참고 자료이며, 충돌하면 Road Music 계약을 따른다.
- **제품 표면:** 영상 제작실, Showreel 스타일 카탈로그·선택기, JIZURA 음악 스튜디오, 가사 가독성 검수 페이지, 완성 음원·원가사·영상의 재생과 다운로드, 생성되는 영상 장면 HTML.
- **검토한 근거:** [HTML 템플릿 검수 기록](../../references/studio-api.md), [영상 제작실](../studio.html), [공통 디자인 CSS](design.css), [JIZURA 음악 스튜디오](../../../road-music-jizura-playlist/assets/studio/index.html), [JIZURA CSS](../../../road-music-jizura-playlist/assets/studio/studio.css), [Showreel 카탈로그](../../../road-music-showreel-playlist/assets/catalog.html), [스타일 선택기](../../../road-music-showreel-playlist/scripts/playlist_chooser.py).
- **관측:** 공통 메뉴, Paperlogy, 밝은 중립 표면, 초록 주요 행동, 카드형 미리보기, 완성 파일 재생·다운로드가 구현돼 있다. 390px 화면에서는 메뉴의 마지막 항목이 홀로 다음 줄로 내려가고, 긴 결과 화면에서는 현재 상태와 다음 행동의 우선순위가 약해진다.
- **추론:** 주 사용자는 디자인 도구보다 음악 제작 흐름에 익숙한 한국어 사용자다. 따라서 선택 용어, 샘플과 완성본의 구분, 저장·완료 상태가 시각 장식보다 우선한다. 이 추론이 달라지는 사용자 조사 근거가 생기면 이 절을 갱신한다.

## Road Music HTML 적용

Road Music에서 생성·수정하는 HTML은 이 문서의 디자인 토큰과 적용 원칙을 따른다. 프로젝트 지정 글꼴은 **Paperlogy(페이퍼로지) 1.000**이며, 아래 원출처 설명의 system-native·언어별 폴백보다 우선한다. 제목·본문·버튼·폼·선택 목록·툴팁과 검수 페이지에 로컬 글꼴을 실제 로딩한다. 첨부한 `Paperlogy-1.000.zip`의 원본 TTF와 해시는 공통 HTML 디자인 자산에 보관한다.

공통 구현은 `skills/road-music-video-studio/assets/design/`이며 Python·Node 생성기에서 같은 토큰과 글꼴 자산을 사용한다. 기본 표면은 흰색·gray-150, 본문은 검정, 설명문은 가독성을 확보한 gray-700, 주요 행동은 LINE Green과 검정 글자를 사용한다. 이는 한국어 웹 화면을 위한 프로젝트 적용이며 LINE 공식 언어 팩을 새로 정의하는 것은 아니다. 영상 자체의 미술·색상·명시된 가사 연출과 HTML 제작·선택·검수 UI를 구분한다.

공식 [design.md 명세](https://github.com/google-labs-code/design.md/blob/main/docs/spec.md)를 문서 형식의 기준으로 참고한다. 문서만 연결했다고 적용 완료로 판단하지 않으며, 실제 CSS·템플릿 반영, 로컬 폰트 요청, 저장 동작과 좁은 화면 표시를 확인한다.

## Brand

- **성격:** 차분하고 정확한 로컬 음악 제작 데스크. 창작물은 화려할 수 있지만 제작 UI는 결과를 방해하지 않는 중립적 편집 환경이어야 한다.
- **신뢰 신호:** 실제 파일명·용량·상태, 샘플과 완성본의 명시적 구분, 저장 결과, 확정·추정 싱크의 구분, 원본과 일치하는 다운로드.
- **피할 것:** 보라색 그라데이션, 과도한 글로우·유리 효과, 카드마다 다른 장식, 의미 없는 영문 레이블, 성공하지 않은 작업을 완료처럼 보이게 하는 표현.

## Product goals

- 음악을 듣고 여러 영상 스타일을 비교한 뒤 제작 설정을 저장할 수 있어야 한다.
- 제작이 끝나면 음원·원가사·최종 영상을 같은 프로젝트에서 재생하고 한글 파일명으로 다운로드할 수 있어야 한다.
- 제작실, 카탈로그, 선택기, JIZURA, 검수 화면을 공통 메뉴로 이동하고 작성 중인 선택과 의견을 보존해야 한다.
- 샘플, 입력 파일, 중간 결과와 실제 완성 파일을 혼동하지 않게 해야 한다.
- **비목표:** HTML UI가 음악·영상 렌더 엔진을 대체하는 것, 영상 장면의 곡별 미술을 공통 UI 팔레트로 덮는 것, 외부 공식 편집기 내부를 재설계하는 것.
- **성공 신호:** 주요 작업이 키보드와 모바일에서 완료되고, 사용자가 현재 단계·저장 여부·완성 파일 유무를 설명 없이 식별하며, 모든 다운로드가 화면에 표시된 파일과 일치한다.

## Personas and jobs

- **1차 사용자 — 비기술 음악 제작자:** 곡을 들어 보고 어울리는 스타일을 고르며, 가사·채널 표시를 설정하고, 완성 파일을 재생·다운로드한다.
- **2차 사용자 — 검수자:** 원가사와 영상 결과를 비교하고, 자막·전환·음량 피드백과 승인 상태를 남긴다.
- **운영 사용자 — Road Music CLI·에이전트 사용자:** 스킬 실행 직후 필요한 로컬 페이지가 열렸는지 확인하고, 저장된 선택과 납품 파일을 다음 제작 단계에 전달한다.
- **사용 맥락:** 한국어, 로컬호스트, 데스크톱 중심이되 320–390px 좁은 창과 터치 입력도 지원한다. 이 사용자 구분은 현재 화면과 작업 흐름에서 도출한 추론이다.

## Information architecture

- 전역 메뉴 순서는 **영상 제작실 → 스타일 둘러보기 → 음악 → 제작 설정 → 완성 파일**로 고정한다. 현재 페이지는 `aria-current="page"`와 테두리·배경으로 구분한다.
- 영상 제작실의 기본 흐름은 **제작 방식 → 음악과 스타일 → 화면 표시 → 제작 설정 전달 → 완성 파일·재생과 다운로드**다.
- ‘완성 파일 바로 보기’는 상단에서 납품 영역으로 바로 이동시키고, 이동 뒤 제목 또는 영역에 키보드 초점을 둘 수 있어야 한다.
- JIZURA는 **추천·빠른 설정 → 전체 편집기 → 기능 안내**를 내부 탭으로 제공한다. Showreel 선택기는 **스타일 선택 → 표시 설정 → 저장** 순서다.
- 스토리보드·자막·수정 의견은 완성 파일보다 낮은 우선순위의 펼침 영역에 둔다.
- 영상으로 렌더되는 장면 HTML과 공식 외부 엔진 iframe에는 제작 UI 메뉴를 넣지 않는다.

## Design principles

1. **실제 결과를 먼저 보여 준다.** 완성 파일이 있으면 재생과 다운로드를 최우선 행동으로 제공한다.
2. **상태를 숨기지 않는다.** 준비 중, 저장 중, 완료, 오류, 미등록, 추정 싱크를 서로 다른 문구와 의미로 표시한다.
3. **선택은 돌아와도 남는다.** 페이지 이동·새 결과 확인·방식 변경 뒤에도 유효한 임시 선택과 피드백을 보존한다.
4. **창작물과 도구를 분리한다.** 미리보기와 영상은 곡의 색을 유지하고, 이를 둘러싼 제작 UI만 공통 토큰을 따른다.
5. **한국어를 기준으로 설계한다.** 긴 조사·파일명·줄바꿈을 견디고, 짧고 구체적인 한국어 동사를 사용한다.
6. **필요할 때만 펼친다.** 고급 설정과 검수 세부 항목은 기본 흐름을 막지 않는 탭·details·도움말에 둔다.

## Visual language

- **색:** 배경 `gray-150`, 표면 흰색, 본문 검정, 설명 `gray-700`, 구분선 `gray-300`, 주요 행동 LINE Green, 링크·포커스 blue-600, 오류 표식은 red-600을 쓴다. 작은 글자는 검정·gray-700으로 대비를 확보하고 LINE Green·blue-600·red-600은 버튼 배경·밑줄·포커스·경계 표식에 사용한다. 색만으로 상태를 전달하지 않는다.
- **타이포그래피:** 모든 한국어 UI는 로컬 **Paperlogy 1.000**을 실제 로딩한다. H1은 28–38px/700, H2는 22px/600, H3은 18px, 본문·버튼·입력은 16px, 보조문은 14px 이상을 기본으로 한다. 긴 본문은 1.5, 원가사 미리보기는 1.8 행간을 사용한다.
- **간격:** 4px 계열 토큰을 사용하고, 기본 컴포넌트 간격은 12–16px, 패널 안쪽은 16–24px, 주요 절 사이는 32px를 기준으로 한다.
- **형태와 깊이:** 입력·버튼 5px, 카드 7px, 큰 패널 12px 반경을 쓴다. 그림자는 보조 수단이며 1px 구분선으로 구조를 먼저 보여 준다.
- **모션:** 상태 전환은 짧고 절제한다. `prefers-reduced-motion`에서는 애니메이션·전환·부드러운 스크롤을 제거한다.
- **이미지와 아이콘:** 실제 미리보기·포스터를 우선하며, 준비되지 않은 자산은 명시적 빈 상태로 대체한다. 텍스트 없는 아이콘 버튼에는 접근 가능한 이름을 제공한다.

## Components

- **공통 페이지 메뉴:** 현재 위치, 로컬 제작실 복귀, 페이지 내부 앵커를 제공한다. 760px 이하에서는 3열 그리드로 모든 항목을 표시한다. 긴 메뉴명은 단어 단위로 줄바꿈하며 한 항목만 고립되는 임의 flex 줄바꿈을 피한다.
- **음악·스타일 영역:** 음원 연결 패널과 스타일 카드를 세로로 분리해 긴 스타일 목록 옆의 빈 열을 없앤다. 스타일 카드는 1100px 이상 3열, 중간 화면 2열, 760px 이하 1열로 표시한다.
- **모드·스타일 카드:** 16:9 미리보기, 이름, 용도, 실제 샘플 여부, 선택 상태를 포함한다. 선택은 색 외에 테두리·표식·라디오 상태로 드러낸다.
- **폼 컨트롤:** 최소 높이 44px, 항상 보이는 라벨, 설명과 오류 연결, SKIP의 의미를 제공한다.
- **상태 메시지:** 저장·새로고침·오류를 가까운 `role="status"` 또는 적절한 경고 영역에 표시하며 이전 성공 문구를 새 작업 중 그대로 두지 않는다.
- **완성 파일 카드:** 파일 종류, 이름, 크기·원본 일치 상태, 재생기 또는 원문, 다운로드를 같은 카드 안에 둔다. 실제 등록 파일만 노출한다.
- **검수 영역:** 스토리보드·자막·피드백·승인 상태를 완성 파일 아래의 펼침 영역으로 제공한다.
- **도움말과 툴팁:** 버튼은 44×44px 터치 영역과 접근 가능한 이름을 갖고, 키보드·포인터·터치에서 닫을 수 있어야 한다.
- **토큰 소유권:** 공통 CSS와 Paperlogy 자산은 `skills/road-music-video-studio/assets/design/`이 소유한다. 뒤의 LDSG `## Components` 절은 원출처 참고이며 Road Music 컴포넌트 계약을 재정의하지 않는다.

## Accessibility

- 목표는 **WCAG 2.2 AA**다. 본문·컨트롤·포커스의 대비를 확인하고, 초록색 자체를 성공이나 선택의 유일한 표식으로 쓰지 않는다.
- 모든 기능을 키보드로 사용할 수 있어야 하며 시각 순서와 DOM 순서를 맞춘다. `:focus-visible`은 3px 링크색 외곽선으로 유지한다.
- 버튼·입력·탭·도움말의 터치 목표는 최소 44×44px다. 라디오·체크박스는 그룹 제목과 연결한다.
- 동적 저장·로딩 결과는 과도한 반복 없이 스크린리더에 전달한다. 오류는 원인과 다음 행동을 함께 말한다.
- 영상·음원에는 고유한 접근 가능한 이름을 제공한다. 자동 재생하지 않으며 한 미디어를 재생하면 다른 미디어를 일시정지한다.
- 한국어 긴 파일명, 조사, 원가사 줄바꿈을 자르지 않는다. 다운로드 링크의 목적은 파일 종류와 이름만으로 구분되어야 한다.
- 동작을 줄인 사용자에게 장식 모션을 강제하지 않는다. 캔버스 미리보기에서 의미 있는 정보가 있을 때는 텍스트 요약을 함께 제공한다.

## Responsive behavior

- 기본 최대 폭은 표면에 따라 1280–1480px이며, 넓은 화면에서는 2열 비교와 고정 미리보기를 허용한다.
- 960px 이하에서는 JIZURA 편집·미리보기를 1열로 바꾸고 고정 미리보기를 해제한다.
- 760px 이하에서는 제작 카드·완성 파일·액션을 1열로 바꾸고 좌우 여백을 14–16px로 줄인다.
- 공통 메뉴는 760px 이하에서 3열 그리드로 고르게 배치해 화면 밖의 항목을 찾기 위한 가로 스크롤을 요구하지 않는다. 앵커 이동 시 고정 메뉴가 제목을 가리지 않게 여유를 둔다.
- 630px 이하에서는 JIZURA의 보조 브랜드 문구·프로젝트 상태를 줄이고 탭을 가로 스크롤로 제공한다.
- 최소 검수 폭은 320px다. 문서 전체에 가로 스크롤이 생기지 않아야 하며, 긴 파일명·가사는 컴포넌트 내부에서 줄바꿈한다.
- 호버 효과는 보조 피드백이며, 터치에서는 선택·활성 상태만으로 기능을 이해할 수 있어야 한다.

## Interaction states

- **로딩:** ‘준비 중’, ‘저장 중’, ‘새 결과 확인 중’처럼 현재 작업을 구체적으로 표시하고 중복 제출을 막는다.
- **빈 상태:** 미리보기·원가사·완성 파일이 없으면 이유와 다음 제작 단계를 말한다. 빈 카드를 완성 결과처럼 보이지 않게 한다.
- **성공:** 저장된 대상과 완료된 파일 수를 짧게 알리고 관련 영역으로 이동할 수 있게 한다.
- **오류:** 네트워크, 파일 누락, 토큰 만료, 저장 실패를 구분하고 재시도 또는 제작실 복귀 행동을 제공한다.
- **비활성:** 비활성 이유를 주변 설명으로 제공하며 색과 커서만으로 끝내지 않는다.
- **느린 연결:** 미디어 메타데이터를 우선 로딩하고 포스터를 유지한다. 다운로드와 재생은 독립적으로 실패·재시도할 수 있어야 한다.
- **초안·추정:** 자동 정렬·추정 싱크와 확정 검수는 라벨과 기록에서 분리한다.

## Content voice

- 한국어 존댓말을 기본으로 하되 버튼은 ‘선택 저장’, ‘새 결과 확인’, ‘음악 다운로드’처럼 짧은 행동형을 사용한다.
- ‘샘플’, ‘입력 음원’, ‘중간 결과’, ‘완성 파일’을 정확히 구분한다. 완료되지 않은 작업에 ‘완성’, ‘확정’, ‘원본 일치’를 쓰지 않는다.
- 기술 용어는 사용자의 결정에 필요할 때만 쓰고 바로 옆에서 설명한다. `SKIP`처럼 유지해야 하는 고정 용어는 첫 노출에서 의미를 설명한다.
- 상태 문구는 대상과 결과를 포함한다. 예: ‘선택이 저장되었습니다’, ‘등록된 영상이 없습니다’.
- 오류는 비난하거나 외치지 않고 사실과 복구 행동을 함께 제시한다.

## Implementation constraints

- 사용자 화면은 정적 HTML·CSS·JavaScript와 Python·Node 생성기로 구성한다. 현재 요구만을 위해 새 UI 프레임워크나 의존성을 추가하지 않는다.
- 공통 토큰·Paperlogy·메뉴는 기존 `html_design.py`와 `html-design.mjs`를 재사용한다. 독립 산출물에는 상대 경로 자산을 함께 복사한다.
- 인증된 로컬 서버는 세션 토큰, Host 검사, CSP, 허용된 파일 경로를 유지한다. 토큰을 배포 템플릿이나 문서에 기록하지 않는다.
- 미디어는 범위 요청과 한글 `Content-Disposition` 다운로드를 지원하고, 화면에 등록된 원본만 제공한다.
- UI 변경으로 기존 영상의 미술·가사·싱크를 재렌더하지 않는다. 영상 장면 템플릿은 Paperlogy만 공통 적용하고 곡별 연출은 보존한다.
- 변경 검증은 관련 단위·계약 검사, `npm test`, 변경 JavaScript의 `node --check`, 실제 브라우저의 데스크톱·390px·320px 확인을 포함한다. 폰트는 CSS 선언뿐 아니라 실제 사용 글꼴을 확인한다.

## Open questions

- [ ] 완성 파일이 여러 곡·버전으로 늘어날 때 최신본·승인본·이전본을 어떤 기준으로 묶을지 결정한다. — **담당:** Road Music 제품 소유자 · **영향:** 납품 목록의 정보 구조와 기본 정렬
- [ ] 지원 브라우저·OS의 최소 버전을 확정한다. — **담당:** Road Music 운영 · **영향:** `:has()`, OKLCH, 로컬 폰트와 미디어 Range 동작의 호환 범위
- [ ] 캔버스 기반 JIZURA 미리보기의 텍스트 대체 설명 수준을 정의한다. — **담당:** JIZURA 제작·검수 담당 · **영향:** 비시각 사용자에게 전달되는 효과·리듬 정보

# LDSG 원출처 참고

아래 절은 LINE Design System for Global Family Service의 토큰·컴포넌트 조사 기록이다. Road Music HTML에는 위 `# Design` 계약을 먼저 적용하고, 여기서는 출처 확인과 세부 패턴 참고만 한다.

## Brand & Style

라인의 디자인 시스템은 두 갈래로 나뉜다. **LDSM(LINE Design System for Messenger)**은 라인 메신저 본체의 시스템이고, **LDSG(LINE Design System for Global Family Service)**는 LY Corporation 산하 **글로벌 패밀리 서비스**가 동일한 UX 표준을 공유하도록 설계된 공용 시스템이다 [src:2]. 여기서 "패밀리 서비스"는 단일 메신저 스킨이 아니라 Messenger·LINE Pay·LINE Music·LINE Manga·LINE Shopping 등 라인 계열 앱 전반을 가로지르는 **크로스-프로덕트 레이어**를 가리킨다 [src:2]. 목표는 모든 패밀리 서비스가 "같은 가족의 일부처럼" 느껴지게 하면서도, 각 제품이 자기만의 Primary 컬러·브랜드 이미지·카피 톤을 재정의할 수 있게 하는 것이다 [src:2]. 본 카탈로그 항목은 LDSG에 한정한다 — LDSM의 "LINE Semantic Colors" 명명 체계나 다크모드 자동 매핑은 이 문서의 토큰 정의에 포함하지 않는다 [src:2][src:17].

LDSG의 컬러 구조는 세 층으로 나뉜다 — **Rainbow Colors(불변)**, **Theme Colors(서비스별 교체 가능)**, **Language Packs(언어별 폰트 세트)**다 [src:1][src:2][src:3]. Rainbow Colors는 모든 컴포넌트를 만드는 불변 팔레트이고, Theme Colors는 각 패밀리 서비스가 자기 색으로 바꿀 수 있는 Brand·Role 토큰이며, 그 변경조차 Rainbow Colors 범위 안에 머물러야 한다 [src:1]. 이 "공통 골격은 고정, 색·언어는 교체"라는 분업이 LDSG가 한 시스템으로 여러 제품을 묶는 방식이다 [src:1][src:2].

타깃 사용자는 일본·대만·태국을 중심으로 한 동아시아·동남아 메신저 및 패밀리 서비스 사용자다 [src:4]. 라인은 일본에서 압도적 1위, 대만 보급률이 높은 국민 메신저 포지션을 갖고 있고 [src:4], LDSG는 이들 시장의 라인 패밀리 서비스 UI 일관성을 책임진다 [src:2]. 한국(KR)은 LDSG의 1차 시장이 아니며 공식 Language Pack에서도 의도적으로 빠져 있지만(EN/JP/TC/TH만 1급), 라인 본사의 모태가 한국 NHN(Naver) 자회사이고 한국 디자인 팀이 라인 시스템에 직접 기여하는 구조라 연결은 사용자 노출보다 조직 차원에서 깊다 [src:4].

감성 톤은 절제된 친근함이다 — 채팅 제품치고 "유난히 조용한" 시스템으로, 차분하고 중립적이며 "은행 창구의 예의 바른 직원" 같은 인상을 노린다 [src:2]. 그라데이션·네온·보라-파랑 워시·장식 액센트가 없고, LINE Green·Black·11단 그레이 세 색이 거의 모든 일을 한다 [src:2]. 호버/프레스를 색상 변화가 아닌 단순 opacity 조정(Hover 70%, Pressed 50%)으로 일관 처리해, 컬러 체계가 작아도 시각 피드백이 명료하게 작동하도록 설계되어 있다 — 이 opacity 기반 상태 모델이 LDSG의 가장 특징적인 시스템 트레이트다 [src:1][src:2]. 카카오톡 같은 강한 채도의 노랑이나 큐트한 라운드와 달리, 차분한 LINE Green과 보수적인 5/12px 라운드로 톤이 기운다 [src:2]. 일러스트도 검정 라인아트(흰 배경 위 검정, 폰을 든 친근한 캐릭터)로 통일되어 있고, 모션은 시트/드로어/팝업이 ~200–300ms ease-out으로 슬라이드-페이드하는 절제된 수준이다 [src:2].

콘텐츠·보이스 기조도 같은 절제 위에 있다 — 중간 정도의 격식, 사실 전달 위주, 슬랭·마케팅 톤 없음 [src:2]. UI 크롬에는 이모지를 쓰지 않고(이모지는 사용자 메시지에만 존재), 정보 카피에 느낌표를 쓰지 않으며("오류는 외치지 않고 진술한다"), 라벨은 Confirm / Cancel / Next / Save / Remove 같은 짧은 명령형을 쓴다 [src:2]. 제목·본문·버튼은 sentence case이되 브랜드·기능명(LINE Pay, OpenChat)은 고유명사로 둔다 [src:2].

## Colors

> **프로비넌스 정정(2026-07-29).** 이 절은 원래 "LINE이 공식 공개한 정확값은 단 3개뿐이고 나머지는 스와치 **이미지**에서 측정·재구성했다"고 적고 있었다. **틀린 서술이라 철회한다** — LDSG는 이름이 붙은 정확 hex를 **텍스트 데이터로 194개** 발행한다(`LINE Green`·`LINE Gray`·`LINE Blue` 등 18개 팔레트 그룹, 각 스와치가 `code`/`name`/`usage` 필드를 갖는다) [src:1][src:33].
>
> 오해가 생긴 이유가 이 항목의 교훈이다 — 인용한 docs URL을 그냥 GET 하면 **텍스트가 10자**만 돌아온다. 사이트가 Gatsby 클라이언트 렌더라 색표가 브라우저에서만 그려지기 때문이고, 값 자체는 같은 경로의 `page-data.json`에 평문으로 들어 있다 [src:33]. 렌더되지 않은 페이지를 보고 "이미지로만 공개"라고 결론 내린 것이다. **부재 주장은 코퍼스가 아니라 렌더된 원본으로 확인해야 한다.**
>
> 대조 결과 이 절의 색 토큰 24개 중 22개가 발행값과 ΔE ≤ 0.02, 2개가 ≤ 0.05로 일치했다 — 재구성은 정확했고, 틀린 것은 값이 아니라 "공개되지 않았다"는 서술이었다. 본 문서는 OKLCH를 유일 정전(canonical)으로 두고 출처 hex는 프로비넌스 주석으로 남긴다.

LDSG의 공식 컬러 체계는 **Rainbow Color**로 부른다 — 모든 컴포넌트를 만드는 불변 팔레트이며, 교체 가능한 컴포넌트라도 색 변경은 Rainbow Colors *안에서만* 허용된다 [src:1]. 구조는 **Messenger Primary Palette** + **Theme Color(Brand Color + Role Color)**이고, Theme Color는 서비스별 교체 가능, Rainbow Color는 불변이다 [src:1][src:2].

- **{colors.ldsg-color-linegreen}** = `#06C755` ≈ `oklch(0.72 0.205 149)`: LDSG의 모든 패밀리 서비스가 공유하는 기본 Primary. LINE이 컬러 페이지에 "LINE Green (#06C755)"으로 명문화한 **공식 공개값**이다 [src:1].
- **정정 — positive == LINE Green**: 이전 카탈로그 항목은 `positive`/`lime-600`을 LINE Green과 다른 초록 색상(`≈ oklch(0.7 0.2 145)`)으로 추정했으나, `lime-600`은 `#06C755` — LINE-green 패밀리와 **동일값**이다(공식 컬러 페이지가 positive를 "lime-600, 브랜드에 가까운 초록"으로 규정) [src:1]. 다운스트림은 별도 초록을 발명하지 말고 LINE Green 값으로 합친다.
- **Gray scale 표기**: 스톱 번호가 비균일하다 — …300, **350**, 400, 500…에서 150·350은 half-stop이다 [src:1]. `{colors.ldsg-color-gray-150}`(#F5F5F5 ≈ `oklch(0.97 0 0)`)이 흰색 다음으로 가장 빈번한 표면 배경이다 [src:2].
- **{colors.ldsg-color-role-positive}** / **{colors.ldsg-color-role-negative}** / **{colors.ldsg-color-role-link}**: 의미 단위로 분리된 Role 토큰. 의미를 위한 색이지 장식이 아니며, Role 색은 브랜드 색과 유사·동일할 때만 변경한다 [src:1][src:2]. (참고: 컬러 페이지 본문은 link를 "shades of red"로 서술하나 기본 토큰은 `blue-600`이다 — 토큰을 정전으로 본다 [src:1].)
- **`ldsg-color-brand-secondary-alt`**: 공식 문서가 "TBD"로 둔 미정의 토큰이다. 다운스트림은 임의 값을 발명하지 않는다 [src:1].
- **On Surface 대비**: Primary·Secondary 컬러 위 텍스트/아이콘은 명도 대비 **3:1 이상**을 요구한다 [src:1].
- **State 처리**: Normal 100% / Hover 70% / Pressed 50% / Disabled = `{colors.ldsg-color-role-disabled}`(#E4E4E4 ≈ `oklch(0.92 0 0)`). 컬러 토큰을 늘리지 않고 opacity로 상태를 표현하는 것이 LDSG의 일관 원칙이며, Disabled 라벨은 enabled 상태 색과 무관하게 항상 #E4E4E4를 쓴다 [src:1].
- **Opacity 동반 토큰(재구성)**: 일부 컴포넌트 spec이 별도의 알파-온-블랙/화이트 토큰을 참조한다 — `ldsg-opacity-black-80`(toast 컨테이너), `ldsg-opacity-black-40`(dimmer / number page-indicator 배경), `ldsg-opacity-black-5`(footer divider), `ldsg-opacity-white-10`(number-indicator 보더), `ldsg-opacity-white-50`(비활성 page number). 별도 색상이 아니라 검정/흰색 위 알파다 [src:13][src:14][src:10].

## Typography

LDSG는 자체 폰트가 아닌 **Typography 토큰 + 언어별 Language Pack**으로 타이포를 운영한다 — 동일 토큰을 쓰면 언어를 바꿔도 시각 인상이 유지된다 [src:3]. 폰트는 언어별 **system-native**이며 커스텀 웹폰트가 없다 [src:8][src:2]. Language Pack은 **EN / JP / TC / TH 4개 언어**를 지원하고 English가 기본/베이스이며, 언어 팩 파일이 베이스 라이브러리 위에 연결된다 [src:3]. **한국어(KR)는 LDSG Language Pack이 아니다** — 아래 KR 폴백 항목은 다운스트림 권장일 뿐 LDSG의 일부가 아니다 [src:3][src:5].

### 언어별 system-native 폰트 스택 (재구성값 — 공식은 system-native 원칙만 명시)

"system-native"라는 원칙은 공식이고 [src:8][src:2], 아래 리터럴 스택은 본 문서가 system-native 원칙에 맞춰 구성한 값이다 [src:3]:

```css
--ldsg-font-en: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial,
                "Segoe UI", Roboto, "Noto Sans", sans-serif;
--ldsg-font-jp: "Hiragino Kaku Gothic ProN", "Hiragino Sans", "Yu Gothic", Meiryo,
                "Noto Sans JP", sans-serif;
--ldsg-font-tc: "PingFang TC", "Heiti TC", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
--ldsg-font-th: "Sukhumvit Set", "Helvetica Neue", "Noto Sans Thai", sans-serif;
```

Text-input·pulldown의 본문 텍스트는 공식 spec에서 "system-native, 16px, line-height 1.4"로 고정되어 있고, 슬라이더 값 라벨은 "SF Pro Text Bold 13"(Hover 20), min/max 숫자는 "SF Pro Text Regular 13" 같은 iOS-native 세부값이 관찰된다 [src:7].

### 토큰 네이밍 구조

토큰명은 5요소 조합 `Language - Type - Size - FontSize - Weight`이며, 실무 형식은 `$ldsg-{lang}-{type}-{size}-{weight}`(예: `ldsg-typography-en-title-m-200` / `$ldsg-en-title-xxl-200`)다 [src:3][src:2]. 컴포넌트 spec에서는 언어 세그먼트를 생략한 약식(`ldsg-typography-title-m-200`, `ldsg-typography-text-s-100`)을 쓰기도 한다 [src:7][src:13].

- **Type**: `title`(헤딩·리스트 타이틀·서브타이틀, 작은/타이트 line-height) / `text`(본문·버튼 라벨, 가독성 우선 넉넉한 line-height) [src:3]
- **Size**: XS · S · M · L · XL · XXL [src:3]
- **Weight**: `100` / `200` / `300` 숫자 토큰(다국어/폰트별 width 체계가 달라 추상화) [src:3]. **Weight 매핑(재구성 — 공개 소스에 수치 없음)**: `100 → 400 Regular`, `200 → 500 Medium`, `300 → 700 Bold`

### Size → px 스케일 (RECONSTRUCTED — 캐노니컬 아님, 강조 플래그)

> **주의:** LDSG는 타입 사이즈를 **이미지로만** 공개해 px 값이 HTML에서 추출되지 않는다 [src:3]. 아래 px는 본 문서가 공식 이미지에서 재구성한 **근사값**이며, 캐노니컬이 아닌 충실한 근사로 취급해야 한다 [src:3]. 정확값은 LDSG Figma 직접 측정이 필요하다.

Title 스케일 = 38/28/22/18/16/14, Text 스케일 = 18/16/14/12이다 [src:3]. Line-height 토큰은 `ldsg-lineheight-tight 1.25` / `ldsg-lineheight-normal 1.5`(재구성값)이고 접두사 `ldsg-lineheight`는 공식이다 [src:8]. 용도 매핑(Title/Text → Headings·Body·Button Label·Caption 등)은 공식 확정값이다 [src:3].

### 컴포넌트별 기본 토큰 적용 예 [src:18][src:7]

- Popup Title: `ldsg-typography-title-m-200`(Medium) / `ldsg-typography-title-l-200`(Large)
- Popup Description: `ldsg-typography-text-s-100`(Medium 기본, 색 `{colors.ldsg-color-gray-500}`)
- Stepper Text Field: `ldsg-typography-title-s-100`
- Floating Pill Button 라벨: `ldsg-typography-text-s-100`
- Toast 텍스트: `ldsg-typography-text-m-100`(색 `{colors.ldsg-color-gray-100}`)
- text-input Title: `ldsg-typography-text-m-200` / Help Text: `ldsg-typography-text-s-100`

### 한국어(KR) 폴백 (LDSG가 아님, 다운스트림 권장만)

KR은 LDSG Language Pack에 없다 [src:3][src:5]. 한국어 환경에서 LDSG의 시각 인상을 따르려면 **LINE Seed KR**을 우선 후보로, 폴백으로 **Pretendard Variable**을 두는 구성이 자연스럽다 — LINE Seed는 기하학 기반 산세리프로 "convenience and friendliness"를 키워드 삼고 EN/JP/KR/TH/TW를 지원하며 다국가 파운드리와 공동 개발됐다 [src:9][src:22]. 다만 이는 **다운스트림 폴백 권장일 뿐 LDSG 자체가 아니다**.

## Spacing

LDSG는 별도의 **글로벌 spacing 스케일 페이지를 공개하지 않는다** — 패딩·간격은 컴포넌트별 spec 표에 케이스로만 정의된다 [src:5][src:8]. Overview는 `ldsg-spacing` 접두사와 "100 단위 기준, 50을 half-step"이라는 규칙만 명시할 뿐 값 표가 없다 [src:8]. 아래 사다리는 본 문서가 컴포넌트 spec 실측에서 재구성한 값이다(재구성 — 공개 소스에 값 표 없음, 아래 컴포넌트 실측으로 교차검증):

사다리 = 2 / 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 [src:8]. 컴포넌트 spec의 실측값이 이 사다리를 뒷받침한다 — text-input·pulldown 2열 필드 간격 **12px** [src:7], pulldown-menu 화면 가장자리에서 **≥ 8px**·앵커에서 **2–8px**·min-width **112px**·기본 인셋 16 [src:11], toast 하단 마진 **≥ 16px**(기본 16) [src:13], page-indicator 마진 이미지 바깥 **16px**·안쪽 **12px** [src:14], footer end-margin 최대 **24px** [src:10]. 16px이 지배적 인셋이고 modal/popup 본문은 20px이다 [src:2].

## Rounded

라운드는 5단으로 정리된 **공식 공개값**이다. 가장 빈번한 값은 5px(버튼류)로, 카카오톡 같은 큐트한 라운드보다 절제된 모서리 처리가 LDSG의 특징이다 [src:5].

- Action Button의 라운드 커스터마이징은 `{rounded.ldsg-radius-100}` / `{rounded.ldsg-radius-200}` / `{rounded.ldsg-radius-300}` 3개 중 하나로 제한된다 [src:7].
- Full-bleed(하단 고정) 버튼은 설계상 **라운드 0**이다 [src:7][src:2].
- Chip의 기본 라운드는 "Pill"(완전 둥근 모서리)이다 [src:8].

`{rounded.ldsg-radius-circle}`(`50%`)는 공식 DESIGN.md 린터가 에러로 보고한다 — 명세(`alpha`)의 Dimension 은 px·em·rem 만 받는다. 비율 곡률은 요소 크기를 따라가므로 고정 길이로 옮기면 모양이 달라져, 값 그대로 두고 알려진 한계로 기록한다.

### Border Width

라운드와 같은 Object Styles 페이지에 정의된 **공식 공개값** [src:5]:

`0.5px`는 허용되나 일부 디바이스 미렌더 위험이 플래그되어 작은 객체 한정이다 [src:5][src:2].

## Elevation & Depth

그림자는 **배경별로 분리된 6종**의 **공식 공개값**으로 운영된다. On White 배경 3단, On Light Gray 배경 3단을 각각 정의해, 어두운 그림자가 회색 배경에서 뭉개져 보이는 정합성 문제를 막는다 [src:5][src:2]. 알파는 모두 0.04~0.12 사이의 매우 옅은 값으로 통일되어 있어 "정돈된 친근함" 쪽으로 톤이 기운다 — 드롭섀도 드라마, inner shadow, glow가 없다 [src:2].

운용 원칙은 단순하다 — 컴포넌트가 놓이는 배경색을 먼저 확정한 뒤 그에 맞는 그림자 그룹을 고르고, 컴포넌트 크기(소·중·대)에 따라 100/200/300 단계를 결정한다 [src:5][src:2].

## Shapes

기하학 기반의 절제된 도형 언어가 LDSG의 시각 정체성이다. 모회사 LY Corporation DESIGN HUB의 비주얼 콘셉트는 "그리드, 도형, 아웃라인, 앵커 포인트 등 최소한의 시각 요소를 활용해 디자인의 기반과 과정을 시각화"로 명시되어 있다 [src:26]. LINE Seed 자체가 "geometry-based, convenience and friendliness"를 디자인 키워드로 삼은 기하학적 산세리프이며, 로고의 직선적 형태를 유지하면서 명확한 곡선을 강조해 가독성과 친근함을 동시에 추구한다 [src:5][src:22].

표면 처리도 같은 기조다 — "카드"는 흰 블록 + 7px 라운드(`{rounded.ldsg-radius-300}`) + 보더 없음 + `{elevation.ldsg-shadow-on-white-300}` 그림자로, 컬러 보더·호버 리프트·컬러 좌측 액센트 스트라이프가 없다 [src:2]. 카카오톡의 큐트한 라운드보다 절제된 5px(`{rounded.ldsg-radius-200}`)를 기본으로 두고, 가장 큰 화면 단위인 Modal/Popup에서도 12px(`{rounded.ldsg-radius-400}`)를 넘기지 않는 점이 이 도형 언어의 실제 적용이다 [src:5][src:2].

원형은 별도로 `{rounded.ldsg-radius-circle}`(50%)로 명시되어 있어 아바타·FAB·Circle Badge 같은 완전 원형 요소에만 한정해서 쓴다 [src:5]. 투명도 사용도 절제되어 있어 modal scrim(dimmer)과 선택적 disabled 오버레이에만 쓰고, 표준 컴포넌트에는 frosted glass·backdrop blur가 없다 [src:2].

## Components

LDSG의 컴포넌트는 모두 LINE 자체 아이콘 라이브러리 **LAICON**을 사용하도록 명시되어 있다 [src:5][src:6][src:11]. LAICON은 공개 다운로드가 불가능해(추출 가능한 iconography 페이지 부재) 본 프리뷰는 **Lucide**(MIT, CDN)로 대체하고 Lucide에 없는 solid 변형은 직접 깎은 SVG로 채웠다 — 프로덕션에서는 LAICON 익스포트로 교체한다 [src:6]. 아이콘 스타일은 주 내비에 solid-fill 검정(둥근 내부 형태), 입력 필드에 stroke/outline(search, close-x, chevron)을 쓰고, 한 컴포넌트 안에 두 weight가 공존하기도 한다(bottom-nav selected = solid, unselected = outline) [src:2]. 사이즈는 16/20/24px이며 24px이 내비·버튼 아이콘의 주력이다 [src:2].

상태 처리는 색상 변경이 아닌 **opacity 변화(Normal 100 / Hover 70 / Pressed 50 / Disabled = `{colors.ldsg-color-role-disabled}`)**로 일관 적용된다. 단, **Hover는 PC·웹 환경 전용**이라 모바일에서는 opacity-70% Hover 상태가 존재하지 않는다 [src:1][src:7]. 일부 컴포넌트는 라이브러리에서 Hover/Pressed를 제공하지 않고 개발 단계에서 적용한다 [src:6][src:8].

### action-button

기본 액션 버튼. 구조는 Icon(옵션) + Text Label + Container. Icon+Text / Text Only / Icon Only 3패턴, XL·L·M·S·XS 5사이즈, Flexible(좌우 패딩 고정, 텍스트에 따라 너비 자동) vs Fixed(너비 자유)로 폭 동작을 선택한다 [src:7].

커스터마이징은 배경색을 foundation 컬러 범위 안에서, 라운드는 `{rounded.ldsg-radius-100}`/`{rounded.ldsg-radius-200}`/`{rounded.ldsg-radius-300}` 중 하나로, 타이포는 LDSG 토큰 안에서(폰트 크기는 바꾸지 않음) 조정한다 [src:7]. 가로 배치 시 우선순위 높은 버튼을 우측에 두며, 동일 행 3개 이상은 주의가 권장된다 [src:7]. Disabled는 enabled 색과 무관하게 `{colors.ldsg-color-role-disabled}`를 쓴다 [src:1][src:7].

```tsx
<ActionButton
  type="contained"            // 'contained' | 'outlined' | 'ghost'
  size="m"                    // 'xl' | 'l' | 'm' | 's' | 'xs'
  pattern="iconText"          // 'iconText' | 'textOnly' | 'iconOnly'
  width="flexible"            // 'flexible' | 'fixed'
  radius="ldsg-radius-200"    // 'ldsg-radius-100' | 'ldsg-radius-200' | 'ldsg-radius-300'
>
  확인
</ActionButton>
```

### action-button-full-bleed

iPhone X+ 디바이스(375×812 이상) 전용 변형. 라운드 0, 전체 너비, 화면 하단 고정(비스크롤), Home indicator 영역도 같은 색으로 칠한다. 화면 최하단 1차 액션 한정으로 사용한다 [src:7][src:2].

```tsx
<ActionButton
  type="contained"
  variant="fullBleed"         // 라운드 0, 전체 너비, 하단 고정
  size="l"
>
  결제하기
</ActionButton>
```

### icon-button

아이콘 단독 버튼. 구조는 Container + Icon + Text. Contained / Outlined / Slot(slot은 임의 이미지/그래픽 수용) 3타입, **S(32px) / L(52px)** 2사이즈. 라이브러리는 Enabled/Disabled만 지원하며 Hover/Pressed는 개발 단계에서 적용한다 [src:23]. Badge 옵션은 None / Dot / Number(1–999, 초과 시 "999+", 너비 자동)다 [src:23].

```tsx
<IconButton
  type="contained"            // 'contained' | 'outlined' | 'slot'
  size="l"                    // 's' (32px) | 'l' (52px)
  icon="search"               // LAICON 아이콘 키
  badge="dot"                 // 'none' | 'dot' | 'number'
  badgeCount={5}              // number 모드 전용, 1~999 (초과 시 "999+")
/>
```

### icon-button-group

아이콘 버튼 묶음. 권장 개수는 3~5개이며 6개 이상은 expanded 옵션으로 펼친다. 그룹 내 단일 컬러·스타일 유지, 등간격, icon-only 혼용 금지, 라벨 줄바꿈·축약 금지가 권장된다 [src:23].

### floating-action-button-circle

원형 FAB. Single Action vs Expandable 2종으로, Expand 상태에서는 dimmer가 깔리고 자식 버튼이 펼쳐지며 메인 아이콘이 close로 자동 전환된다 [src:27]. 메인 컨테이너 채움 `{colors.ldsg-color-brand-primary}`, 그림자 `{elevation.ldsg-shadow-on-white-200}`, 메인 아이콘 흰색, 자식 컨테이너 흰색 + 동일 그림자, 자식 아이콘 검정. 자식 버튼 최대 5개 [src:27].

```tsx
<FabCircle
  variant="expandable"        // 'single' | 'expandable'
  icon="plus"
>
  <FabChild icon="camera" label="카메라" />
  <FabChild icon="image" label="갤러리" />
</FabCircle>
```

### floating-action-button-pill

알약 형태 FAB. auto-width·고정 높이, 보더 `{colors.ldsg-color-gray-300}`, 라운드 `{rounded.ldsg-radius-circle}`, 그림자 `{elevation.ldsg-shadow-on-white-200}`, 라벨 `ldsg-typography-text-s-100` 검정. Refresh 같은 보조 액션 유도용으로 화면 상/중/하단 어디에도 배치할 수 있고 즉시 액션을 실행한다 [src:27].

### switch

On/Off 토글. 구조는 Text Label + Description(옵션) + Container + Thumb. 상태 Enabled/Disabled/Error, On/Off. Hover/Pressed는 라이브러리 미제공(개발 단계 적용)이며, 토글이 대상 요소에 **즉시** 영향을 주는 컨텍스트에만 쓴다(저장 버튼이 따로 있는 폼에는 부적합) [src:12].

```tsx
<Switch
  label="알림 받기"
  description="중요 메시지만"   // 옵션
  checked={true}
  onChange={handleChange}
/>
```

### chip

선택 가능한 작은 라벨. 구조는 Left Icon(옵션) + Text + Right Icon(옵션) + Container. Text Only / Side Icons / Left Icon / Right Icon 4패턴, Contained·Outlined(Outlined가 낮은 우선순위) 2타입, Small·Medium·Large 3사이즈, Selected/Unselected/Disabled 상태(+ 인터랙션 Hover/Pressed). auto-width, 기본 채움 `{colors.ldsg-color-brand-primary}`, 기본 텍스트/아이콘 흰색, 기본 라운드 **Pill** [src:28].

**단일 선택만 가능한 경우 사용 금지** — 2개 이상의 선택지가 있을 때만 쓴다 [src:28].

```tsx
<Chip
  type="contained"            // 'contained' | 'outlined'
  size="m"                    // 's' | 'm' | 'l'
  pattern="leftIcon"          // 'textOnly' | 'sideIcons' | 'leftIcon' | 'rightIcon'
  selected={false}
  icon="filter"
>
  카페
</Chip>
```

### stepper

수량 증감 입력. 구조는 Left Button + Text Field + Right Button. Contained/Outlined 타입, **S(32px) / M(46px)** 2사이즈. 최솟값 도달 시 Minus 버튼이 자동 Disabled로 전환되고 Text Field는 직접 입력도 지원한다. Text Field 타이포 `ldsg-typography-title-s-100`, enabled 아이콘/텍스트 검정, disabled `{colors.ldsg-color-role-disabled}` [src:29]. 소수점·넓은 범위에는 부적합하며 그 경우 슬라이더 사용이 권장된다 [src:29].

```tsx
<Stepper
  size="m"                    // 's' (32px) | 'm' (46px)
  value={1}
  min={1}
  max={99}
  onChange={handleChange}
/>
```

### radio-button

상호 배타 선택. 구조는 Container + Text Label + Description(옵션). 상태 Enabled/Disabled/Error, Selected/Unselected. Hover/Pressed는 라이브러리 미제공. 한 번 선택된 후에는 미선택 상태로 되돌릴 수 없는 점이 핵심 — 그룹의 mutual exclusion을 보장하며 그룹당 하나만 선택된다 [src:30].

### badge

상태/카운트 표시. 구조는 Container + Digit Text + Icon. Dot / Number / Icon 3타입, **S·M·L·XL·XXL 5사이즈(기본값만 사용)**. Number는 2-digit+ 옵션을 지원한다. 단독 사용 불가 — 항상 다른 컴포넌트(아이콘/아바타)와 함께 쓴다. 색상 변경 가능하나 기본 권장은 서비스 Primary 또는 빨강 계열이다 [src:31].

```tsx
<Badge
  type="number"               // 'dot' | 'number' | 'icon'
  size="m"                    // 's' | 'm' | 'l' | 'xl' | 'xxl'
  count={12}
  twoDigit={true}             // 두 자리 이상 표시
/>
```

### text-input

텍스트 입력 필드. 구조는 Title(옵션) / Input Container / Help Text Area(옵션) / Input Area(Prefix·Text·Suffix·Tailing Icon). **컨테이너 타입 Contained / Outlined / Underlined** — Contained는 배경 `{colors.ldsg-color-gray-150}`·보더 없음, Outlined는 보더 `{rounded.ldsg-border-100}`·`{colors.ldsg-color-gray-300}`, Underlined는 하단 보더만 동일 [src:16]. 상태 Enabled/Disabled/Error, 타이핑 상태 Placeholder / On Focus(erase 아이콘 추가) / On Typing / Typed [src:16].

Title은 옵션이나 권장이며 Required는 `*`를 `{colors.ldsg-color-role-negative}`로 붙인다. Help Text는 Help-only / Help+Counter / Counter-only 옵션이다. Title 타이포 `ldsg-typography-text-m-200` 검정, help `ldsg-typography-text-s-100` `{colors.ldsg-color-gray-500}`, 본문 텍스트 **system-native 16px / line-height 1.4**, placeholder `{colors.ldsg-color-gray-350}`, typed 검정, prefix/tailing 아이콘 검정(LAICON) [src:16]. 고정 높이·가변 너비(기본 = 화면 − 마진), 2열 간격 12px. 최대치 초과 시 Error + help text로 알린다 [src:16].

화면당 컨테이너 타입은 하나로 통일하고, 타이틀을 쓰며, placeholder는 라벨이 아닌 예시값으로, 오류는 제출 후가 아니라 실시간으로 보여주고, 키보드를 입력 형식에 맞춘다 [src:16].

```tsx
<TextInput
  type="outlined"             // 'contained' | 'outlined' | 'underlined'
  title="제목"                // 옵션(권장)
  required                    // '*'를 role-negative로 표기
  placeholder="예: 회의 안건"  // 예시값(라벨 아님)
  helpText="안내 문구를 입력하세요."
  helpVariant="helpCounter"   // 'help' | 'helpCounter' | 'counter'
  maxLength={40}
  state="error"               // 'enabled' | 'disabled' | 'error'
/>
```

### checkbox

다중 선택 체크박스. 구조는 Container + Text Label + Description(옵션). 일반 상태 Enabled / Disabled / Error / Hover(PC) / Pressed, 선택 상태 Selected / Unselected(기본) / **Indeterminate**. Hover/Pressed는 개발 단계 자동 적용 [src:32]. **중첩**: 부모가 자식 전체를 토글하고, 자식이 섞이면 부모가 Indeterminate, Indeterminate 부모를 선택하면 자식 전체가 Selected가 된다. 라벨은 한 줄만, 긴 텍스트는 핵심을 라벨에·상세를 description에 둔다 [src:32].

```tsx
<Checkbox
  label="이용약관에 동의합니다"
  description="자세한 안내"      // 옵션
  state="indeterminate"        // 'selected' | 'unselected' | 'indeterminate'
/>
```

### slider

연속 값 입력. 구조는 Min Value Icon(옵션) / Track / Value Label(옵션) / Max Value Icon(옵션) / Min Numeric(옵션) / Thumb / Fill / Max Numeric(옵션). 패턴 Basic / Side Icons / Numeric Value, Thumb는 **Single**(단일 값) 또는 **Double**(범위) [src:20]. 상태 Enabled/Disabled(Hover/Pressed는 thumb·라벨이 확대). Fill `{colors.ldsg-color-brand-primary}`(disabled `{colors.ldsg-color-role-disabled}`), Track `{colors.ldsg-color-gray-300}`(enabled) / `{colors.ldsg-color-gray-150}`(disabled), Thumb **18×18**(Hover 24×24), 패딩 8px(Hover 10px), 값 라벨 폰트 SF Pro Text Bold 13(Hover 20)·흰색·라벨 라운드 5px, side icon 24×24 검정 [src:20]. 드래그/플릭, 클릭/탭-점프 인터랙션. Double 값이 같을 때 thumb와 라벨을 겹치지 않게 한다 [src:20].

```tsx
<Slider
  pattern="numericValue"      // 'basic' | 'sideIcons' | 'numericValue'
  thumb="double"              // 'single' | 'double'
  min={0}
  max={100}
  value={[20, 80]}
/>
```

### pulldown

선택(select) 입력. anatomy·타입·상태는 text-input과 동일하되 Input Area에 **Chevron-Down 아이콘**이 붙는다 — Title(옵션) / Input Container / Help Text(옵션) / Input Area. 타입 Contained(`{colors.ldsg-color-gray-150}`) / Outlined(`{rounded.ldsg-border-100}`·`{colors.ldsg-color-gray-300}`) / Underlined, 상태 Enabled/Disabled/Error [src:21]. 본문 텍스트 system-native 16px / 1.4, placeholder `{colors.ldsg-color-gray-350}`, chevron·입력 아이콘 검정(변경 가능). 고정 높이·가변 너비(기본 화면 − 마진), 2열 그리드 간격 12px. "여러 옵션 중 선택, 공간 효율적으로." do/don't는 text-input과 동일하다 [src:21].

```tsx
<Pulldown
  type="outlined"             // 'contained' | 'outlined' | 'underlined'
  title="카테고리"            // 옵션
  placeholder="선택하세요"
  options={['카페', '식당', '편의점']}
/>
```

### popup

오버레이 다이얼로그. 구조는 Image Area(옵션) / Close(옵션) / Title / Description / Additional Items(옵션) / Button Area. 4가지 패턴 — Text Popup(기본 alert) / Avatar Popup(OA 계정 추가용) / Image Popup(4:3·16:9) / Promotion Popup(4:3·16:9·1:1·세로 4:3, 광고용) [src:18].

- **너비 고정 288px**, 자동 높이(최대 504px) — 초과 시 상단이 스크롤되고, 더 큰 컨텐츠는 `{component.bottom-sheet}`로 옮긴다 [src:18].
- LIFF 환경에서 높이 472px+면 iPhone SE의 LIFF 닫기 버튼과 겹칠 수 있어 주의 [src:18].
- Button Area는 세로(가시성 높음, 컨텐츠 많을 때) / 가로(간단한 confirm) 중 선택 — 세로: Primary Only / Primary+Outlined / Primary+Ghost / 3버튼(비권장), 가로: Primary Only / Ghost Primary+Secondary / Contained Primary+Secondary [src:18].
- Title 기본 타이포 `ldsg-typography-title-m-200`(Medium) / `ldsg-typography-title-l-200`(Large), Description `ldsg-typography-text-s-100`(Medium 기본) 색 `{colors.ldsg-color-gray-500}`, 닫기 버튼 `{colors.ldsg-color-gray-900}` [src:18].
- 화면 중앙 정렬, 좌우 마진 고정·상하 마진 조정 가능 [src:18].

```tsx
<Popup
  pattern="text"              // 'text' | 'avatar' | 'image' | 'promotion'
  size="medium"               // Title 토큰 'ldsg-typography-title-m-200'
  title="삭제하시겠어요?"
  description="이 작업은 되돌릴 수 없어요."
  buttonLayout="vertical"     // 'vertical' | 'horizontal'
  buttons={[
    { type: 'contained', label: '삭제', role: 'primary' },
    { type: 'ghost', label: '취소' },
  ]}
/>
```

### pulldown-menu

앵커에 붙는 오버레이 리스트. 구조는 Container / Title(옵션, 기본 True) / Pulldown List Item(Left Item·Text·Divider·Right Item). 패턴 Text Only / Side Items / Left Item / Right Item. **Left Item: Avatar / Icon / Slot**, **Right Item: Arrow / Arrow+Text / Text / Icon / Slot** [src:11]. 상태 Enabled/Disabled(Hover는 PC 전용). **min-width 112px**, 고정 너비·auto-height, 기본 인셋 16. 컨테이너 배경 흰색·보더 `{colors.ldsg-color-gray-150}`, divider `{colors.ldsg-color-gray-150}`, title `{colors.ldsg-color-gray-500}`, 텍스트 검정(disabled `{colors.ldsg-color-role-disabled}`), arrow·우측 텍스트 `{colors.ldsg-color-gray-600}` [src:11]. 앵커 기준 상/하/좌/우 배치, 가장자리에서 ≥ 8px·앵커에서 2–8px. **6개 이하에 적합**(초과 시 bottom sheet), divider는 항목 *타입*을 나눌 때만 쓰고 모든 항목 사이나 마지막 아래에는 두지 않는다 [src:11].

### bottom-sheet

하단에서 올라오는 시트. 구조는 Dimmer / Header Area(옵션) / Handlebar(옵션) / Contents Area / Button Area(옵션). **요소 패턴 7종: Text(기본) / Avatar / Grid / List / Image / Full Image / Custom** [src:15]. Dimmer는 **Modal(기본, 인터랙션 차단)** vs **Interactive(dimmer 없음, 페이지 사용 가능)**. Handlebar 옵션(드래그로 full-height 확장, scroll-top에서 아래로 드래그하면 닫힘). **Header: Normal(top-nav) / Close Only(기본) / Tab Only / Search Only / None**, **Button Area: Vertical(기본) / Horizontal / Full Bleed / None**(Home-Indicator 옵션) [src:15]. 너비 100% 가변·하단 고정(좌우 간격 변경 불가)·auto height(0–100% minus safe area, 초과 시 스크롤). 컨테이너 흰색, title 검정, grid 배경 `{colors.ldsg-color-gray-150}`·grid 아이콘/텍스트 검정, description `{colors.ldsg-color-gray-500}`(강조 `{colors.ldsg-color-gray-800}`), link `{colors.ldsg-color-role-link}` [src:15]. 키보드가 시트를 밀어 올리며 가로 방향도 지원한다. **태블릿/PC에서는 사용 불가**(드로어/풀다운으로 대체), 좌우 마진이 필요하면 popup을 쓴다 [src:15].

```tsx
<BottomSheet
  pattern="list"              // 'text' | 'avatar' | 'grid' | 'list' | 'image' | 'fullImage' | 'custom'
  dimmer="modal"              // 'modal' | 'interactive'
  header="closeOnly"          // 'normal' | 'closeOnly' | 'tabOnly' | 'searchOnly' | 'none'
  buttonArea="vertical"       // 'vertical' | 'horizontal' | 'fullBleed' | 'none'
  handlebar
/>
```

### toast-overlay

짧게 떴다 사라지는 알림. 구조는 Container / Text / Icon. **Icon Toast**(아이콘 타입 Check Mark / Loading / Exclamation Mark / Custom, 주목도 높음) vs **Text Toast**(텍스트 전용, Position Center / Bottom, Lines Single / Multiple) [src:13]. **약 4초 후 자동 소멸하며 사용자가 강제로 닫을 수 없다**. Loading 변형은 로드 후 결과를 보여주고, text-toast loading은 "Loading"을 표시한다. Bottom 배치는 하단에서 ≥ 16px(기본 16) [src:13]. 컨테이너 채움 **`ldsg-opacity-black-80`**(변경 불가), 텍스트 **`ldsg-typography-text-m-100`** 색 `{colors.ldsg-color-gray-100}`(변경 불가), 아이콘 흰색(Custom = LAICON). 낮은 중요도 정보 전용이며, 주목이 더 필요하면 popup/snackbar를 쓴다 [src:13].

```tsx
<ToastOverlay
  variant="icon"              // 'icon' | 'text'
  icon="check"                // 'check' | 'loading' | 'exclamation' | 'custom'
  position="bottom"           // 'center' | 'bottom' (text 변형)
>
  저장되었습니다
</ToastOverlay>
```

### footer

애플리케이션 footer(모바일 전용). 구조는 Divider(옵션) / Social Media Links(옵션) / Items / Copyright / Container. Social Icon True/False, **타입 Circle Solid / Ghost, 사이즈 M(30px) / L(36px)**, 가로 최대 5개(M)·6개(L), 총개수 무제한 [src:10]. 레이아웃 2종: Footer-for-Side-Drawer vs Footer-for-Full-Width. 고정 너비 375px·end-margin 최대 24px·auto height. Items/copyright `ldsg-typography-en-title-xs-100`, items `{colors.ldsg-color-gray-500}`, copyright `{colors.ldsg-color-gray-400}`, social 기본 Circle Solid L `{colors.ldsg-color-gray-500}`, divider 1px `ldsg-opacity-black-5`, 컨테이너 배경 `{colors.ldsg-color-gray-150}`(max-height 667px) [src:10]. 저작권·약관·개인정보·보안 같은 애플리케이션 용도 전용이며 콘텐츠 구분용이 아니다 [src:10].

### tab

탭 내비. 구조는 Tab Item(Container / Label / Selected Indicator / Notification Badge) / Tab Container / Expand Button(옵션) / Divider. **Flexible Tab**(마진 M=12/S=8, underline M=2/S=1, Expand 버튼 옵션, 항목이 너비 초과 시 horizontal-scroll + 선택 항목 auto-center, 항목 수 무제한) vs **Fixed Tab**(2–4개, 사이드 마진 Default 16 / None 0 → 100% width) [src:24]. 기본 flexible 패딩 S(8), 기본 underline M(2), underline None도 가능. 상태 Selected/Unselected에 opacity Normal 100 / Hover 70 / Pressed 50, 하나만 Selected. Badge True/False, 콘텐츠 스와이프 옵션, Expanded Tab List는 dimmed 오버레이로 열린다 [src:24].

```tsx
<Tab
  variant="flexible"          // 'flexible' | 'fixed'
  underline="m"               // 'm' | 's' | 'none'
  items={['전체', '받은', '보낸']}
  selectedIndex={0}
/>
```

### side-drawer

좌측에서 열리는 드로어. 구조는 Header(옵션) / Container / Dimmer / Divider(옵션) / Active Area(옵션) / Inactive Area / Footer(옵션). Avatar True/False. 메뉴 항목은 가시성을 위해 **Icon + Text**여야 하며, 한 리스트 레벨에서 Icon+Text와 Text-only를 섞지 않는다 [src:25]. **컨테이너 너비 기본 280px(최대 300px, 화면의 최대 80%)**·배경 흰색. **Dimmer 너비 240px·`ldsg-opacity-black-40`**(버거 아이콘으로 열고 dimmer 탭/스와이프로 닫음). Divider `{colors.ldsg-color-gray-150}`. Active Area: solid 아이콘 검정·폰트 `ldsg-typography-text-m-100` `{colors.ldsg-color-gray-900}`·컨테이너 배경 `{colors.ldsg-color-gray-150}`. Inactive: solid 아이콘 검정·`ldsg-typography-title-m-100` `{colors.ldsg-color-gray-900}` [src:25]. Header title `ldsg-typography-title-m-200`·sub-text `ldsg-typography-text-xs-100`, Footer `ldsg-typography-title-xs-100` `{colors.ldsg-color-gray-500}`. 항목 초과 시 세로 스크롤, 메뉴 중첩은 최대 2단(3단 이상 금지) [src:25].

### bottom-navigation

하단 탭바. 구조는 Container / Icon Button / Icon / Text(옵션). 패턴 Icon+Text / Icon Only / Slot+Text / Slot(Icon+Text 권장, Icon-Only는 직관적 아이콘에만). **3 / 4 / 5 컬럼**(기본값 사용, 최대 5, 가로 스크롤 없음) [src:19]. **상태 Selected / Enabled / Disabled** — **selected 아이콘 = solid, enabled = regular/outline**, disabled `{colors.ldsg-color-role-disabled}`. selected 아이콘/텍스트 검정, enabled `{colors.ldsg-color-gray-600}`, disabled `{colors.ldsg-color-role-disabled}`. Home-Indicator 옵션(375×812+), Badge 옵션 None / Dot / Number(1–999, "999+") [src:19]. 컨테이너 흰색·100% width·auto height·하단 고정(스크롤에도 유지), 버튼 간 등간격 [src:19].

```tsx
<BottomNavigation
  pattern="iconText"          // 'iconText' | 'iconOnly' | 'slotText' | 'slot'
  columns={4}                 // 3 | 4 | 5
  items={[
    { icon: 'home', label: '홈', state: 'selected' },     // selected = solid icon
    { icon: 'chat', label: '채팅', state: 'enabled' },     // enabled = outline icon
  ]}
/>
```

### page-indicator

페이지 위치 표시. 구조는 Activated Dot / Inactive Dot / Container / Current Page / Total Page. 두 타입 **Dot**과 **Number**(규칙에 따라 함께 사용 가능) [src:14]. Dot: **5페이지 미만 → dot 수 = 페이지 수, 6페이지 초과 → dot이 페이지보다 적고 이동 시 active dot이 리사이즈**. Dot 사이즈 S(기본) 5px / L 7px, active `{colors.ldsg-color-gray-800}`·inactive `{colors.ldsg-color-gray-300}` [src:14]. Number: current/total, 컨테이너 배경 `ldsg-opacity-black-40`·보더 `ldsg-opacity-white-10`, page-number 높이 S 18px / L 22px, active 흰색·inactive `ldsg-opacity-white-50`. 배치는 dot 이미지 바깥 16px·안쪽 12px, number 상단 12px. auto width·고정 높이 [src:14].

### skeleton

로딩 플레이스홀더. 단일 anatomy(Skeleton Item). **그라데이션 shimmer 애니메이션이 좌상 → 우하로 흐른다**. 서비스 진입·페이지 전환에서 체감 로드를 줄이는 용도이며, **progress indicator와 동시 사용 금지** [src:6]. 너비/높이는 변경 가능하나 **배경 `{colors.ldsg-color-gray-150}`은 변경 불가**. LIFF에서는 네이티브 우상단 닫기 버튼을 skeleton으로 덮을 수 없다 [src:6].

## Do's and Don'ts

### Do

- Primary가 필요한 모든 자리에는 `{colors.ldsg-color-brand-primary}` = LINE Green(`#06C755` ≈ `oklch(0.72 0.205 149)`)을 기본으로 둔다 — 다른 색을 임의로 Primary로 승격시키지 않는다 [src:1].
- 상태 변화(Hover/Pressed)는 컬러 토큰을 새로 만들지 말고 opacity(70%/50%) 조정으로 표현한다 — 단 Hover는 PC·웹 전용임을 전제한다 [src:1][src:7].
- 그림자는 컴포넌트가 놓이는 배경색(흰색 vs 라이트 그레이)에 맞춰 `{elevation.ldsg-shadow-on-white-100}`~`300` 또는 `{elevation.ldsg-shadow-on-gray-100}`~`300` 중 옳은 그룹을 골라 쓴다 [src:5].
- 가로 배치된 버튼은 우선순위 높은 쪽을 **오른쪽**에 둔다 [src:7].
- 라운드는 컴포넌트 크기에 따라 `{rounded.ldsg-radius-100}` / `{rounded.ldsg-radius-200}`(기본) / `{rounded.ldsg-radius-300}` / `{rounded.ldsg-radius-400}` 중에서 고르며, 기본값 5px 외 값은 정당화가 필요하다 [src:5].
- Disabled는 enabled 색과 무관하게 `{colors.ldsg-color-role-disabled}`(#E4E4E4 ≈ `oklch(0.92 0 0)`)로 통일한다 [src:1].
- 카피는 sentence case·짧은 명령형(Confirm/Cancel/Next/Save)으로 쓰고, 폼 필드 placeholder는 라벨이 아닌 예시값으로 둔다 [src:6].
- 한국어 환경에서 LDSG 시각 인상을 따르려면 본문 폰트를 LINE Seed KR로, 폴백을 Pretendard Variable로 둔다(LDSG 자체 기능이 아닌 다운스트림 권장) [src:5][src:22].

### Don't

- hex나 rgba로 새 컬러를 정의하지 않는다 — LDSG의 재구성값(`red-600` 등)도 토큰명으로 참조하고, 다운스트림에서 임의 hex를 박지 않는다 [src:1].
- `positive`/`lime-600`을 LINE Green과 다른 별도 초록으로 취급하지 않는다 — 동일값(`#06C755` ≈ `oklch(0.72 0.205 149)`)이다 [src:1].
- `ldsg-color-brand-secondary-alt` 같은 공식 "TBD" 토큰에 임의 값을 발명하지 않는다 [src:1].
- 단일 선택만 가능한 컨텍스트에 `{component.chip}`을 쓰지 않는다(2개 이상 선택지 전용) [src:8].
- 한 행에 `{component.action-button}` 3개 이상을 두는 구성은 피한다 [src:7].
- `{component.stepper}`를 소수점이나 넓은 범위 입력에 쓰지 않는다 — 그 경우 슬라이더로 교체한다 [src:7].
- `{component.popup}` 높이를 504px 초과로 설계하지 않는다 — 더 큰 컨텐츠는 `{component.bottom-sheet}`로 옮긴다. LIFF에서는 472px 이상도 피한다(iPhone SE의 LIFF 닫기 버튼과 겹침) [src:18].
- `{component.bottom-sheet}`를 태블릿/PC에 쓰지 않는다 — 드로어/풀다운으로 대체하고, 좌우 마진이 필요하면 popup을 쓴다 [src:15].
- `{component.toast-overlay}`를 강제 확인이 필요한 중요 정보에 쓰지 않는다 — 자동 소멸하고 사용자가 닫을 수 없으므로 그 경우 popup을 쓴다 [src:13].
- `{component.skeleton}`을 progress indicator와 동시에 쓰지 않는다 [src:6].
- 라이브러리 미제공 상태(Switch·Stepper·Icon Button·Radio·Checkbox의 Hover/Pressed)를 디자인 단계에서 임의 색상으로 지정하지 않는다 — 개발 단계 적용 약속을 따른다 [src:6][src:12][src:7].
- UI 크롬에 이모지나 느낌표를 쓰지 않는다 — 오류는 외치지 않고 진술한다 [src:6].
- LDSM의 "LINE Semantic Colors" 토큰명·다크모드 자동 매핑을 LDSG 토큰과 혼용하지 않는다 — 두 시스템은 별개의 명명 체계를 갖는다 [src:17].
- LDSG를 라인이 아닌 제품에 채용할 때 라인의 메신저 패밀리 서비스 도메인(메신저 본체 컬러 테마를 잇는 LINE Green 브랜드 상속, 메신저·결제·뮤직·만화·쇼핑 같은 패밀리 프로덕트 맥락과 그 카피·플로우)을 그대로 이식하지 않는다 — LDSG는 패밀리 서비스용 공용 시스템이므로 차용할 것은 시각 언어(절제된 LINE Green primary·opacity 기반 Hover/Pressed 상태·배경별 분리 그림자·보수적 5/12px 라운드·기하학 미니멀 도형·이모지 없는 절제된 보이스)이고, 브랜드 색·제품 도메인은 자기 서비스에 맞게 재정의한다 [src:1][src:2].
- 디자인시스템 이름 자체(`LDSG`·"LINE Design System" 워드마크)를 생성하는 제품 UI의 헤더·타이틀·버튼·라벨에 넣지 않는다 — 차용할 것은 시각 언어이지 시스템 이름이 아니다. UI 텍스트·네이밍은 자기 서비스 브랜드로 재정의하고, 출처 표기가 필요하면 footer attribution에만 둔다.

## Responsive Behavior

LDSG는 공식 breakpoint 값 표를 공개하지 않는다 — Overview에 `ldsg-breakpoint` 접두사만 있고 값이 없다 [src:8]. LIFF(LINE 내장 웹뷰)와 패밀리 모바일 앱 웹뷰가 주된 실행 환경이라 디자인 결정 자체가 **모바일 우선·웹뷰 가정**에 잠겨 있으며, 실무적으로 단일 뷰포트(모바일)에 가깝다 [src:8][src:2]. 데스크톱과 모바일의 차이는 사실상 **Hover 존재 여부**와 **Home-indicator/full-bleed 게이팅** 둘뿐이다 [src:2].

| Breakpoint | 환경 | Key Changes |
| --- | --- | --- |
| sm 360px (재구성) | 폰 (360/375/414 1급) | 모바일 기본 레이아웃; Hover 상태 없음 [src:1] |
| md 768px (재구성) | 태블릿 | `{component.bottom-sheet}`·`{component.footer}` 사용 불가 → 드로어/풀다운 대체 [src:15][src:10] |
| lg 1024px (재구성) | PC 웹 | Hover(opacity 70%) 활성; 버튼·탭·체크박스/라디오/스위치 Hover는 PC 전용 [src:7][src:24] |
| iPhone X+ (375×812+) | Home indicator 보유 | `{component.action-button-full-bleed}`·bottom-navigation Home-Indicator 옵션 사용 가능 [src:7][src:19] |

> breakpoint 값(sm 360 / md 768 / lg 1024)은 본 문서 재구성값이며 LINE 공식 발표값이 아니다(공개 소스에 값 없음 — Overview는 접두사만 명시).

- **터치 타깃**: `{component.icon-button}` S 32px / L 52px, `{component.stepper}` S 32px / M 46px, slider thumb 18×18(Hover 24×24). S 사이즈는 일반 가이드(44×44px)에 못 미쳐 마진 확보가 필요하다 [src:8][src:7].
- **Popup 사이징**: 폭 288px 고정 × 최대 504px, 그 이상은 `{component.bottom-sheet}`로 옮긴다. LIFF에서 472px 이상은 닫기 버튼과 겹침 [src:18].
- **레이아웃 collapse**: `{component.bottom-sheet}` 너비 100%·하단 고정·태블릿/PC 불가 [src:15]; `{component.bottom-navigation}` 최대 5개·가로 스크롤 없음 [src:19]; `{component.tab}` Flexible(초과 시 가로 스크롤) vs Fixed(2–4개) [src:24]; `{component.footer}` 모바일 전용·375px 고정 [src:10]; `{component.pulldown-menu}` 6개 이하 권장(초과 시 bottom sheet) [src:11]; `{component.icon-button-group}` 3~5개 권장, 6개 이상 expanded [src:6].
- **이미지 비율**: Image Popup 16:9·4:3 / Promotion Popup +1:1·세로 4:3 [src:18]; `{component.bottom-sheet}` 375px 너비 기준 16:9=210h, 4:3=281h, 1:1=375h, 3:4=500h [src:15].

## Known Gaps

LDSG 공식 문서가 공개하지 않거나 이미지로만 제공해 다운스트림이 직접 채워야 하는 항목이다. **컬러는 여기서 빠졌다** — 애초에 공백이 아니었고, 그 경위는 아래 첫 항목에 적었다. 타입 px·spacing 스케일은 본 문서가 재구성해 값을 채웠지만 **LINE 공식 발표값이 아니므로 목록에 남긴다** — "값이 없음"은 해소됐어도 "공식이 아님"은 그대로다.

- **컬러는 여기서 빠진다(2026-07-29 정정)**: 이 항목은 원래 "파생 컬러도 이미지로만 공개돼 재구성했다"고 적고 있었으나 사실이 아니다 — LDSG는 팔레트 194색을 이름·hex 텍스트로 발행하며, 본 문서 색 토큰 24개 중 22개가 그 발행값과 ΔE ≤ 0.02로 일치한다(자세한 경위는 Colors 절) [src:33]. 컬러 정확값을 Figma에서 따로 검증할 필요는 없다.
- **공식 미발표 vs 재구성**: 본 문서의 타입 px·**weight 매핑**·spacing 스케일·breakpoint 값은 LINE이 **공식 발표한 값이 아니다**. 타입 px는 공식 페이지가 이미지로만 공개한 것을 측정·재구성했고(이미지 출처 인용 가능), **weight 매핑·spacing 사다리·breakpoint 값은 공식 페이지에 수치 자체가 없어 인용 가능한 공개 소스가 없다**(컴포넌트 spec 실측·관행으로 재구성). 이 값들은 LDSG Figma 라이브러리에서 끌어와 검증해야 한다 [src:1][src:3].
- **타입 px의 RECONSTRUCTED 성격**: 타입 사이즈는 공식 페이지가 이미지로만 노출해 px가 추출 불가다 — Typography 섹션의 px는 재구성 근사값이며 캐노니컬이 아니다 [src:3].
- **다크 모드**: LDSG 공식 페이지에 다크 모드 카운터파트 토큰이 없다 — 다운스트림이 직접 설계해야 한다 [src:1].
- **한국어(KR) Language Pack 부재**: LDSG Language Pack은 EN/JP/TC/TH로 한정이며 KR은 1급이 아니다 — 한국어 적용 시 LINE Seed KR / Pretendard Variable 폴백 매핑을 다운스트림이 정의해야 한다 [src:3][src:5].
- **LAICON 미공개**: 모든 컴포넌트 슬롯이 LAICON을 지정하나 공개 다운로드가 불가하다 — 본 프리뷰는 Lucide로 대체했고, 프로덕션은 LAICON 익스포트로 교체해야 한다 [src:6].
- **LDSM(LINE Messenger 본체) 미포함**: 본 항목은 LDSG(글로벌 패밀리)에 한정한다. LDSM은 "LINE Semantic Colors" 명명 + 다크모드 자동 매핑 + case-studies/UX guidelines를 포함하는 독립 시스템이며, 향후 별도 카탈로그 항목으로 추가될 수 있다 [src:17].

## References

1. https://designsystem.line.me/LDSG/foundation/color-en
2. https://designsystem.line.me/LDSG (LDSG 공식 사이트 — 시스템·브랜드 개요)
3. https://designsystem.line.me/LDSG/foundation/typography-en
4. https://en.wikipedia.org/wiki/Line_(software)
5. https://designsystem.line.me/LDSG/foundation/object-styles-en
6. https://designsystem.line.me/LDSG/components (LDSG 컴포넌트 문서 — 보이스·아이코노그래피·상태·skeleton 등)
7. https://designsystem.line.me/LDSG/components/buttons/action-button-en/
8. https://designsystem.line.me/LDSG/foundation/overview-en
9. https://github.com/line/seed
10. https://designsystem.line.me/LDSG/components/navigations/footer-en
11. https://designsystem.line.me/LDSG/components/overlays/pulldown-menu-en
12. https://designsystem.line.me/LDSG/components/inputs/switch-en/
13. https://designsystem.line.me/LDSG/components/overlays/toast-overlay-en
14. https://designsystem.line.me/LDSG/components/indicators/page-indicator-en
15. https://designsystem.line.me/LDSG/components/overlays/bottom-sheet-en
16. https://designsystem.line.me/LDSG/components/inputs/text-input-en
17. https://designsystem.line.me/LDSM/foundation/color/line-semantic-colors-ex-en/
18. https://designsystem.line.me/LDSG/components/overlays/popup-en/
19. https://designsystem.line.me/LDSG/components/navigations/bottom-navigation-en
20. https://designsystem.line.me/LDSG/components/inputs/slider-en
21. https://designsystem.line.me/LDSG/components/inputs/pulldown-en
22. https://seed.line.me/ — LINE Seed 공식 사이트. 서체 철학·배포 진입점(공식 저장소 line/seed가 이 URL을 안내한다). 클라이언트 렌더 페이지라 정적 fetch로는 본문이 잡히지 않는다.
23. https://designsystem.line.me/LDSG/components/buttons/icon-button-en/
24. https://designsystem.line.me/LDSG/components/navigations/tab-en
25. https://designsystem.line.me/LDSG/components/navigations/side-drawer-en
26. https://design.lycorp.co.jp/ — LY Corporation DESIGN(구 creative.line.me 브랜드 가이드라인의 현행 이전지). 모회사 디자인 포털.
27. https://designsystem.line.me/LDSG/components/buttons/floating-action-button-en/
28. https://designsystem.line.me/LDSG/components/inputs/chip-en/
29. https://designsystem.line.me/LDSG/components/inputs/stepper-en
30. https://designsystem.line.me/LDSG/components/inputs/radio-button-en/
31. https://designsystem.line.me/LDSG/components/indicators/badge-en/
32. https://designsystem.line.me/LDSG/components/inputs/checkbox-en
33. https://designsystem.line.me/page-data/LDSG/foundation/color-en/page-data.json — [src:1]과 같은 페이지의 Gatsby 데이터 파일. docs URL을 그냥 GET 하면 텍스트가 10자뿐이라 색표를 읽을 수 없지만, 이 경로는 18개 팔레트 그룹 194색을 `code`/`name`/`usage` 평문으로 반환해 값 검증이 가능하다.
