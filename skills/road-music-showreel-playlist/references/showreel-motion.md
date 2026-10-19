# 기본 Showreel의 표현력을 직접 쓰기

이 문서는 enum 효과표가 아니라 콘셉트를 실제 장면으로 구현할 때 읽는다. 자유 연출은 [native 제작](production.md)이 기본이며 [composition 계약](composition-contract.md)으로 장면·이미지·원곡 시계를 연결한다. 리듬 캔버스를 먼저 만든 뒤 부트를 수동 교체하는 우회 경로가 아니다.

## 문서와 도구의 역할

`SHOWREEL_HOME` 또는 기존 `~/.local/share/roadmusic-video-tools/showreel`에서 현재 설치본을 읽는다. 이 문서 대조만으로 설치본을 업데이트하지 않는다.

| 기본 문서 | 실제 제작 판단 |
|---|---|
| SKILL.md / brief.md | 콘셉트 후보·선택·기술 과제·첫5초 |
| design.md | 매체·구도·서체·재질·운동의 성격과 읽기 |
| story.md | 음악 기반 구성·장면 경계·script.json |
| engine.md | REEL.scene/config/overlay/preload/큐·DOM/SVG/Canvas/WebGL/3D/물리 |
| techniques.md | 필요한 T01–T22 코드 조각의 정확한 사용 |
| images.md | 소재/마스크/누끼/시트의 실무. Codex 생성 도구는 내장 image_gen 우선 |
| audio.md | 분석·원음 믹스·명시한 사운드 디자인 |
| qa.md | 실제 프레임/동작 띠의 미술 비평·기술 검사·마감 |

[공식 Showreel](https://github.com/revfactory/showreel)은 콘셉트에서 화면을 코드로 만든다. 22기법은 자동 컴포넌트 목록이 아니며, 모두 넣거나 음악 프롬프트를 다시 생성할 필요도 없다. 기존 곡에 새 음악/나레이션/효과음을 기본으로 추가하지 않는다. 원곡에 맞는 기능을 선택하고 이번 작품의 실제 구현/검수와 도구의 일반 지원을 구분한다.

## 장면 구현

- `REEL.scene`을 직접 쓴다. 새 파일/모듈을 index에 연결하고 실제 id/범위를 FILM_PLAN과 맞춘다. FILM_INPUT은 음악/가사/표시 자료, FILM_PLAN은 의미·시간·자산 계획이며 미술 엔진이 아니다.
- 시간은 t의 순수 함수. 누적 위치/실시간 clock/무작위/CSS animation 대신 native cue/prog/kf/spring/rand/noise 또는 고정 단계로 미리 계산한 물리를 쓴다.
- 이미지·폰트·glyph/mask/입자는 setup에서 준비한다. `await FILM_MEDIA_READY` 뒤 자연 크기/픽셀을 사용한다. 필수 이미지 실패를 검은 사각형으로 조용히 대체하지 않는다.
- Canvas 상태/경로를 매 프레임 초기화하고 save/restore를 맞춘다. 같은 변위를 좌표와 transform에 중복 적용하지 않는다. glyph의 clip과 본체를 함께 이동해 정착된 원형이 복귀하는지 본다.
- 입자/자모/재질/3D/깊이/마스크는 실제 구현대로 부른다. 단순 음절 이동을 자모 조립, 반복 선을 악기 분리, 큰 단어만 바꾼 것을 새 장면이라고 확대하지 않는다.
- WebGL2는 preserveDrawingBuffer와 render마다 draw/오류검사. three.js 라이브러리는 기존 로컬 파일만 연결하고 mixer.setTime(t)를 사용한다. 없는 의존성을 설치된 것처럼 안내하지 않는다.
- FX의 실제 인자와 layer를 설치본 fx.js에서 확인한다. 모든 장면에 HUD/그레인/비네트/레터박스·흔들림을 덮지 않는다. 카메라/플래시와 안정된 본문/표시를 분리한다.
- 하드 컷/상태 변화의 반프레임 보정은 native shutter에 적용한다. 가창 전문의 gate나 원곡 시계 전체를 함께 이동하지 않는다. 연속 공간/아이리스/물리 진행은 scene별 local progress로 초기화하지 말고 원래 구간 시계로 계산한다.

대표 프레임·동작 띠·경계와 원음 proof에서 의미·상태·재질·무게를 확인한다. 새 `check-native-project.mjs`는 runtime/원문/표시/시크를 확인하며 미술/음악 적합성은 [비평](native-qa.md)으로 별도 판정한다. 기존 check-motion-template.mjs 통과를 새 native 장면 검사로 전용하지 않는다.

## 원음 proof에서 발견한 구현 오류를 막기

- Canvas `fillText`는 현재 path에 글자 윤곽을 추가하지 않는다. 글자 속 이미지에는 실제 offscreen alpha mask와 source-in/destination-in 또는 검증한 글리프 path를 쓰고, 최종 픽셀에 이미지 질감이 보이는지 확인한다.
- 합성 오브젝트의 줄·손·피크·마스크는 실제 자산의 자연 크기에서 anchor를 잡고 본체와 같은 fit/회전/스케일 변환을 공유한다. 생성 자산의 방향을 보지 않고 임의 좌표에 선을 얹지 않는다.
- 박별 누적 사건은 장면 시작의 실제 비트와 원곡/출력 원점을 기준으로 한다. 곡 전체의 비트 번호를 고정 숫자에서 빼지 말고, 구간 시작/중간/끝에서 실제로 단계가 전개되는지 본다. 정수 i에 %1을 적용해 모든 요소를 한 좌표에 쌓는 오류도 확인한다.
- 프로젝트 helper가 native 함수명과 다른 인자 뜻을 갖지 않게 한다. 특히 native prog(t,start,duration)와 구간 종료 시각 보간을 같은 이름으로 혼동하지 않는다. 실제 렌더에서 초기/중간/정착을 확인한다.
- 파열/던짐은 대상이 사라지는 시점뿐 아니라 방향·힘의 출처·비행·착지/해방의 결과가 읽혀야 한다. 반주가 이어지는데 빈 배경과 화면 밖 파편만 남으면 사건을 재기획한다.

- 하나의 고해상도 alpha 이미지를 여러 장면에서 서로 다른 크기로 반복 그리면 Chromium의 재샘플링 캐시 때문에 같은 시각의 픽셀이 달라질 수 있다. 실제 역순 검사가 이미지 영역에서만 실패하면 smoothingQuality를 바꾸는 것만으로 해결됐다고 가정하지 않는다. 영향받은 자산은 decode 직후 자연 크기의 픽셀을 canvas에 한 번 고정하고, 필요하면 장면 setup에서 출력 크기의 sprite를 만들어 변환한다. 한 장면만 고쳐 다른 재사용 장면의 실패가 뒤늦게 나타날 수 있으므로 preview/render 양쪽과 전체 역순 검사를 다시 통과시킨다. 허용 오차를 넓혀 숨기지 않는다.
