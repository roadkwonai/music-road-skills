---
name: road-music-showreel-playlist
description: 음악·장르·가사를 해석해 분위기와 실제 비트·강약이 살아 있는 Showreel 플레이리스트 모션그래픽을 제작·수정한다. image_gen 이미지·0.5초 썸네일과 구간별 타이포·기하 모션, 가사 싱크·여러 곡 연결을 지원한다. 서사형 MV와 음악 생성은 별도다.
---

# 음악에 맞춘 Showreel 플레이리스트

음악의 정서와 가사 의미를 색·형태·모티프로 해석하고, 실제 타격음과 강약에 반응하는 모션그래픽을 원곡 전체 길이로 만든다. 음악 해석은 Codex, 신호 분석·시간 기반 합성·렌더는 Showreel이 맡는다. 가사 원문과 가창 시각을 보존하고, 큰 움직임과 읽기 정지의 대비로 리듬을 표현한다.

시작 시에는 현재 읽은 이 `SKILL.md`의 실제 절대 부모 경로를 `PLAYLIST_SKILL`에 넣어 [사용 시 업데이트 확인](../road-music-skills-update/references/use-time-check.md)을 한 번만 적용한다.

스타일 선택을 맡긴 일반 모션그래픽 요청은 **리듬 캔버스**의 비 CD 구간 연출로 시작한다. 사용자가 고른 형식·색·이미지·기존 프리셋은 우선한다. 음악만 받았다고 CD·가수 사진을 강제하지 않는다. CD 5종(가을 아카이브·누아르 필름·네온 애프터아워·로파이 노트북·크롬 프리즘)과 리듬 CD 그루브 다이얼도 계속 선택할 수 있다. 실제 명칭/지원값은 `assets/presets/*/preset.json`, 미리보기 검수 상태는 `preview.status`가 기준이다.

개인 스킬로 제작한다. Road Music 정식 기능 통합이나 모델 설치를 이 요청으로 추정하지 않는다. 모션은 Showreel 네이티브 엔진으로 만들고 LTX·새 음악 생성·나레이션을 선행시키지 않는다.

이전 `$road-music-showreel-cd` 호출은 호환 경로로 이 스킬에 연결된다. 새 요청과 문서는 `$road-music-showreel-playlist`를 사용한다.

**ChatGPT/Codex 기본 이미지 제작 도구는 내장 `image_gen`이다. Antigravity는 아래 호스트별 이미지 계약을 따른다.** 새 음악 모션그래픽은 곡에 맞는 장면 이미지들과 전용 썸네일을 이 도구로 생성해 Showreel에 합성한다. 사용자가 순수 기하 표현을 지정하거나 제공 이미지 재사용을 요청하면 그 선택이 우선한다. 추상·풍경·절차형 템플릿은 가수를 억지로 만들지 않는다. Python helper는 계획/프로젝트/렌더를 관리하며 독립 실행만으로 Codex 도구를 호출하지 않는다. 사용자가 직접 제공한 이미지나 명시한 데모 재사용은 존중한다. 도구가 없으면 필요한 이미지 생성 단계를 미완료로 보고하고 유료 API·기존 데모로 몰래 대체하지 않는다.

## 호스트별 이미지 도구

ChatGPT/Codex에서는 내장 `image_gen`, Antigravity에서는 현재 세션의 네이티브 이미지 생성 기능 또는 내장 `image-generator` 경로를 사용한다. [공통 이미지 계약](../road-music-video-studio/references/image-providers.md)을 따른다. 아래 문서의 `image_gen` 전용 인자는 ChatGPT 경로이며 Antigravity에 같은 도구명·모델 옵션을 강제하지 않는다. 실제 파일·도구·반환 모델을 기록하고 동일한 자산 검수/렌더 계약으로 전달한다. 이미지가 필요 없는 절차형 연출은 그대로 유지한다.

## HTML 제작·검수 화면

실제 영상 제작은 [공통 HTML 영상 제작실](../road-music-video-studio/SKILL.md)을 함께 사용한다. 스타일과 음악을 보고·들으며 고르고, 기획/이미지·부분 영상·최종 결과·수정 의견을 같은 프로젝트 화면에 게시한다. `publish`는 검수 등록 전체를 manifest로 교체하므로, 후속 게시에서도 유지할 기존 스토리보드·음원·영상·자막을 모두 manifest에 다시 넣는다. 이미 받은 선택은 유지하고 저장된 selection.json/feedback.json을 실제로 읽어 이 스킬의 입력에 반영한다. 표시용 페이지 생성이나 버튼 저장을 렌더 완료로 보고하지 않는다. HTML은 제작·검수 인터페이스이며, 엔진별 실제 생성·편집·렌더와 원곡/가사 시계는 아래 절차가 맡는다.

## 음악 중심 제작

곡에 맞는 역동적인 모션그래픽은 [음악 해석·구간 연출](references/music-direction.md)을 읽는다. 원곡/원문 출처 → 음악 신호와 가사 해석 → 실제 구간별 디자인 → 미리보기 수정 → 전체곡 렌더로 진행한다. 장르를 넣은 계획만 만들고 제작 완료라고 하지 않는다.

- **리듬 캔버스**: 궤도·리본·그리드·타일의 실제 템플릿. 별/비/꽃잎 모티프, 구간별 팔레트·강도, 선별된 타격음의 링·레이·스윕·펀치와 읽을 수 있는 가창 타이포를 쓴다. 음악에 맞춘 생성 이미지 위에 합성하며 순수 기하 모드도 유지한다. 생성 이미지·썸네일은 [음악 해석·구간 연출](references/music-direction.md)의 media 계약으로 전달한다.
- **사진/CD**: 사용자가 선택하거나 곡의 연출에 필요한 경우 아래 장르 계획과 image_gen을 쓴다.
- **기존 프로젝트 수정**: 저장된 원곡/시계/표시를 유지하고 요청한 연출만 새 프로젝트에서 고친다.

장르명이나 BPM만으로 화면을 결정하지 않는다. 가사의 화자·대상·핵심 이미지·감정 변화와 편곡 밀도를 읽고, 벌스의 여백과 후렴의 확대·브리지의 감쇠를 실제 시각에 반영한다. 네이티브 BPM/4박 다운비트는 추정값이다. 큰 효과는 실제 hits와 선택한 가사 구절에 배치하며, 모든 박에 같은 점멸·줌을 반복하지 않는다. 분석·청취·추론의 근거와 한계를 방향 JSON에 남긴다.

## 리듬 캔버스의 생성 이미지와 0.5초 썸네일

음악·가사에 실제로 등장하는 장소·물건·정서를 바탕으로 필요한 장면 이미지를 내장 `image_gen`으로 생성한다. 장르명만으로 가수 얼굴이나 특정 문화 이미지를 강제하지 않는다. 이미지 제작 후 실제 결과를 보고 글자·사물·화면비·자막 여백을 검수한다. 생성 프롬프트·도구·원본/저장 경로·해시를 프로젝트에 남긴다.

리듬 캔버스의 기본 썸네일은 곡명과 확인된 아티스트명, 사용자가 선택한 채널명으로 만들고 첫 **[0,0.5)초**에 고정 이미지로 표시한다. 음악은 0초부터 재생하며 가사/비트/곡 길이를 밀지 않는다. 별도 0.5초 무음 프리롤이나 다른 길이를 요청하면 그 요청을 명시적으로 반영한다. 후렴 구간 검수에는 썸네일을 다시 붙이지 않는다. 자산을 만들지 않은 상태나 예전 데모 재사용을 새 생성 완료라고 하지 않는다.

## 새 제작의 표시 선택

CLI에서 HTML을 보고 고르려는 요청은 먼저 [스타일 선택 화면](references/selection.md)의 `choose`를 실행해 URL을 패널/브라우저에 보여준다. 화면에서 받은 스타일·4개 표시 응답은 `--selection`으로 계획과 제작에 넘기며 다시 질문하지 않는다. 이미 명시한 스타일/옵션은 유지한다. HTML에 접근할 수 없으면 카탈로그와 아래 대화 입력으로 이어간다.

새 영상/플레이리스트 제작을 시작할 때 다음 **4개 항목 중 아직 답을 받지 않은 것**을 묻는다. 이미 요청에 적혀 있으면 반복 질문하지 않는다. 가능하면 `request_user_input_async`로 한 번에 묶고, 입력 도구가 없으면 짧은 한 메시지로 묻는다.

1. 음악에 반응하는 **선형 스펙트럼** 표시 여부.
2. **재생 대기 중인 다음 곡 목록** 표시 여부.
3. **현재 재생 중인 곡 이름** 표시 여부.
4. 템플릿의 브랜드 영역에 넣을 **운영 채널명** 입력.

각 표시 항목은 `표시 / 표시 안 함 / SKIP`, 채널명은 자유 입력 또는 `SKIP`을 허용한다. 항목별 SKIP은 해당 표시 끄기/채널명 빈 값이다. “전부 SKIP”이면 네 항목 모두 건너뛴다. 채널명을 프로젝트명·Road Music·파일명에서 추측하거나 임의 문구로 채우지 않는다. 빈 채널명은 CD 명판 또는 커스텀 템플릿의 브랜드 영역에 만들지 않는다.

답은 [표시 옵션·플레이리스트](references/playlist.md)의 display-options.json으로 저장한다. 선택은 서로 독립이며 가창 자막과 별개다. 기존 프로젝트 수정은 저장한 값을 유지하고 바꾸라는 항목만 갱신한다. 미응답을 시간 경과나 기본 선택으로 SKIP 처리하지 않는다. 답을 기다리는 동안 음원/가사/장르 분석은 진행할 수 있지만 미확정 표시 설정으로 렌더를 시작하지 않는다.

## 목록·선택

```bash
PLAYLIST_SKILL="/absolute/skills/road-music-showreel-playlist" # 현재 읽은 이 SKILL.md의 실제 부모
PLAYLIST_PY="${SHOWREEL_PYTHON:-python3}"
SKILLS_PARENT="$(dirname "$PLAYLIST_SKILL")"
UPDATE_SKILL="$SKILLS_PARENT/road-music-skills-update"
node "$UPDATE_SKILL/scripts/manage.cjs" check --target "$SKILLS_PARENT"
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" list
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" show '네온'
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" catalog
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" genres
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" choose --out '/절대/새-선택세션'
```

미리보기 요청이면 반환된 `assets/catalog.html`을 링크/패널로 보여준다. 실제 영상 카드에서 인트로/CD 구간 탐색과 장르 검색을 할 수 있다. 추천 장르는 연출 적합도이며 기존 4개 CD 미리보기는 같은 록 발라드, 크롬 프리즘 미리보기는 18초 무음 모션 검수본이다. 미렌더 프리셋을 재생 가능하다고 하지 않는다.

이름이 지정되면 해당 프리셋을 선택한다. 보고 고르려는 요청은 HTML 선택을 먼저 받는다. 제작 선택을 위임했다면 곡의 장르·명시된 보컬 구성·무드로 고르고 이유를 기록한다. **주황색 단어/어절 진행 추적**이 명시된 필수 요구면 검증된 `cues[].words`가 있는 그루브 다이얼을 추천하고, 계획에 그 필수 추적 요구를 기록한다. 사용자가 다른 프리셋을 명시 선택했다면 임의로 바꾸거나 줄 밑줄을 동등한 대체로 취급하지 말고 차이와 선택지를 알린다. 보컬 성별·인원은 장르나 음역으로 추정하지 않는다. 제작을 위임한 요청을 목록 안내만으로 끝내지 않는다.

## CD 계열 장르 계획

`plan --host codex|antigravity|antigravity-cli --genre ...`는 기존 CD와 `genrePlanner:"cd-assets"`를 선언한 그루브 다이얼의 장르별 인물/공간/촬영/자막/회전 계획과 5개 `image_gen` 프롬프트만 만든다. 데이터 원천은 `assets/genre-profiles.json`이며 음악 장르 지원의 화이트리스트가 아니다. 혼합 장르는 모두 보존하고 목록 밖 장르도 곡 브리프로 새 방향을 설계한다. 사용자가 고른 CD 화면 프리셋은 장르 기본값보다 우선한다. 일반 커스텀 프리셋에는 이 planner를 적용하거나 CD로 자동 대체하지 않는다. 그루브 다이얼의 장르별 재질·모션·이미지 계획은 [그루브 다이얼](references/groove-dial.md)을 따른다.

장르명만으로 가수의 나이·성별·국적, 보컬 수, 종교/문화 복장을 확정하지 않는다. 보컬 캐스팅은 사용자 설명, Road Music의 확인 가능한 생성 메타데이터, 확인 가능한 음원 정보 순으로 정한다. 음원만으로 불명확하면 `unknown`으로 남기거나 짧게 확인한다. 계획 helper는 자동 장르 인식기나 이미지 생성 완료 증거가 아니다.

`plan --vocal female|male|mixed|unknown|none --act auto|solo|duo|band|ensemble|artwork`으로 보컬과 편성을 명시한다. 여성 보컬 밴드는 여성 리드 보컬과 곡 편성에 맞는 멤버를 뜻하며, 전원 여성 밴드는 별도 요청이 있을 때만 쓴다. 남성·혼성·연주곡도 같은 규칙으로 계획한다. `none` 또는 `--instrumental`은 가수 없는 연주 이미지로 만들며, 알려진 보컬과 연주곡 지정의 충돌은 거부한다.

구체적인 색·재질 요청은 `--brief`만으로 끝내지 말고 [look 설정](references/genres.md)의 팔레트·재질 JSON을 만들어 `plan --look`으로 적용한다. 프롬프트와 실제 영상의 색/자막/회전 설정이 같은 사용자 의도를 따르게 한다.

## 그루브 다이얼

어절 추적이 필수이면 `plan --require-word-timing`으로 요구를 기록한다. 이 계획을 넘긴 `create`는 요구를 상속하며, 계획 없이 제작할 때는 `create --require-word-timing`을 명시한다. 화면에 보이는 가창 큐의 `words`가 없으면 출력 전에 중단한다. 가창 큐가 없는 인트로 미리보기는 허용하고 실제 가창 싱크 검수 완료로 보고하지 않는다. 입력·검증 범위는 [가창 자막](references/captions.md)을 따른다.

분절 사진 CD → 사진 셔터 → 케이스 조립 인트로와 회전 CD, 후반 카드 뒤집기·재배치를 제공한다. 선택한 음악의 실제 타격음에 반응하며 `soft / balanced / drive` 세 강도를 쓴다. 36개 장르의 기본 미술·모션을 지원하고 혼합·목록 밖 장르는 브리프로 보완한다. K-POP·현대 팝의 깨끗한 크롬부터 빈티지·레트로 질감까지 [전용 제작 지침](references/groove-dial.md)의 `plan --style '그루브 다이얼' --look ...`으로 계획한다. “최신 트렌드”라는 주장에는 해당 요청 시점의 실제 조사 근거가 필요하다.

스펙트럼·대기곡·현재 곡명·채널명은 위 공통 표시 질문과 SKIP을 그대로 사용한다. 채널명은 CD 케이스 명판에 합성한다. 카탈로그 사진·가수·30초 음악·DEMO CHANNEL을 새 제작의 기본값으로 복제하지 않는다.

## 커스텀 템플릿 제작

CD가 아닌 프리셋은 `--style <이름> --assets <manifest> --playlist <목록>`으로 만든다. Codex가 음악·편성·표현 목적을 읽어 그 프리셋의 prompts와 자산 계획을 먼저 작성하고, 해당 preset의 `assetSchema`에 맞는 이미지 또는 절차형 자산을 준비한다. `requiresArtist:true`일 때만 [이미지 제작](references/images.md)의 인물 캐스팅·검수를 적용한다. 리듬 캔버스는 [음악 해석·구간 연출](references/music-direction.md)의 direction을 적용한다. 이 흐름은 CD 케이스·디스크·photoA/B/C를 요구하지 않는다. `assetSchema:{}`인 절차형 프리셋은 `--assets`와 `--demo-assets`를 생략한다.

커스텀 템플릿의 공통 런타임 계약은 `PLAYLIST_CONFIG(duration/fps/audio/preset/assets/display/playlist)`, `PLAYLIST_LYRICS(cues)`, `PLAYLIST_SPECTRUM(FFT|null)`이며, 시간 `t`에 대한 순수 함수 `__seek(t)`와 로딩 완료 boolean `window.__ready=true`를 제공해야 한다. CD 레거시 템플릿은 기존 `CD_CONFIG` 등 전역을 유지한다. 외부 실행 hook이나 별도 엔진 명령은 프리셋 설정에 넣지 않는다.

## 새 음악으로 제작

1. 원곡 파일과 가사/타이밍 출처를 확인한다. 여러 곡이면 [플레이리스트](references/playlist.md)에 따라 순서·제목·각 원곡 시계를 보존한 tracks 입력을 만든다. MP3만 있으면 [가창 자막](references/captions.md)의 기존 로컬 도구로 초안을 만든다. 원곡과 제공 가사를 보존한다.
2. CD 계열과 그루브 다이얼은 장르 `plan`의 프롬프트를 곡의 실제 편성/무드와 캐스팅에 맞춘다. [이미지 제작](references/images.md)에 따라 내장 `image_gen`으로 성인 가상 가수/밴드를 설계한다. 같은 곡의 photoA/B/C·케이스·CD 인쇄면에는 같은 인물을 유지하고, 다음 곡은 새 아티스트 자산을 만든다. 커스텀 계열은 선택한 assetSchema와 requiresArtist만 따른다. 유료 API로 임의 전환하지 않는다.
3. [제작 절차](references/production.md)의 `create --style <프리셋>`으로 새 출력 폴더를 만든다. 기존 CD와 그루브 다이얼은 `--plan <계획.json>`을 지원한다. 표시 답변은 `--display`, 여러 곡은 `--playlist`로 전달한다. 기존 CD와 그루브 다이얼의 곡별 `plan`/`assets`/`vocal`/`act`/`artist`는 경계에서 해당 곡의 커버와 인물로 전환한다. 커스텀은 선택한 템플릿 자산을 그대로 쓰고, 리듬 캔버스는 렌더 전 `motion_direction.py apply`로 구간별 방향을 적용한다. `--demo-assets`는 카탈로그 재현/검증의 명시적 선택이며 캐스팅 일치 증거가 아니다.
4. 스타일 프레임과 짧은 미리보기로 음악/가사 의미의 반영, 강약 대비·리듬, 자막 대비·시각과 전환 경계를 확인한다. 주황 어절 추적을 요구했다면 렌더 전 `create` 응답과 `production.json`의 `wordTiming`으로 현재 가창 큐에 실제 words가 있는지 확인하고, 없으면 흰 문장·밑줄로 대체하지 않는다. 가창 큐가 0개인 인트로 검수는 그 범위를 구분한다. 사진/CD는 피부·종이·유리 질감과 얼굴 잘림/광학 이중상도 고친다. 요청하지 않은 제목·장르명·기술 라벨을 영상에 넣지 않는다.
5. 본편은 네이티브 `render.mjs`/`finish.py`를 호출하는 `render`로 1920×1080/30fps 제작한다. 여러 곡은 각 원곡 전체를 실제 샘플 수로 이어 긴 본편을 만들며, 구간 미리보기는 최종 본편을 대체하지 않는다. 영상·SRT·타이밍 JSON·설정·편집 프로젝트·이미지 생성 근거를 납품한다. 초안/최종 및 실제 규격을 구분해 보고한다.

렌더러는 한 번에 하나만 실행한다. 스킬 선택과 이미지 생성/렌더는 제작 범위에 포함되지만 외부 게시/전송이나 음악·모델 교체 권한으로 확대하지 않는다.

## 자막

문장 전체가 `[startSeconds,endSeconds)`에서 즉시 읽혀야 한다. 리듬 캔버스는 중앙 또는 하단 안전 영역에 최대 두 줄로 맞추고, 본문이 잘리지 않게 크기를 줄인다. 그루브 다이얼은 Paperlogy·반투명 차콜 판을 사용하고 검증된 `cues[].words`가 있을 때만 현재 어절을 호박색으로 강조해 비트에 맞춰 작게 확대·기울인다. 줄 자막만 있으면 어절 시간을 만들어 넣지 않는다. 밑줄/브래킷/글로/마커는 장식이며 글자를 늦게 나타나게 하지 않는다. CD/그루브 템플릿은 한 줄 자막이다. 공통 입력에는 개행 없는 문장을 쓰며 리듬 캔버스의 자동 줄바꿈은 원문을 바꾸지 않는다. 긴 문장은 원문을 보존하고 실제 가창 경계로 큐를 나눈다.

`create`는 원곡·자막·WAV 해시와 cut offset을 저장하고 원곡 불일치를 거부한다. 인트로가 10.17초여도 음악·자막을 그만큼 밀지 않는다. `draft`/미검수 상태를 보고와 카탈로그에 보존한다. 변환/표시 경계 검증을 가사 정답이나 가창 청취 검수 완료로 확대하지 않는다.

가사 없는 곡은 `plan --instrumental` 또는 `create --instrumental`로 지정한다. 가수·가창 동작·가짜 가사를 만들어 넣지 않는다. 자막 없이도 제작하며 무가사 상태를 기록한다. 클래식/재즈라는 장르명만으로 무가사라고 추정하지 않는다.

## 스타일 추가

“이 스타일 저장”, “OO 프리셋 추가” 요청은 [프리셋 등록](references/presets.md)을 따른다. 알아보기 쉬운 이름과 고유 id/별칭을 정하고, 설정·이미지 프롬프트·참고 자산·**실제 미리보기 영상**을 검증해 `add`로 저장한다. 카탈로그에 반영되면 다음 요청에서 이름으로 선택할 수 있다.

기존 프리셋/출력은 덮어쓰지 않는다. 새 배치·전환이 필요하면 템플릿과 검증을 함께 확장한다. 구현하지 않은 variant를 JSON에만 추가하지 않는다.

## 검증

스크립트 변경은 `scripts/test_presets.py`, `test_playlists.py`, `test_playlist_tools.py`, `test_vocal_cast.py`, `test_custom_presets.py`, `test_playlist_chooser.py`, 템플릿 변경은 `scripts/check-template.mjs`, `check-playlist-ui.mjs`, `check-track-art.mjs`를 실행한다. 그루브 다이얼은 `test_presets.py`·`test_playlists.py`와 `check-groove-template.mjs`도 실행한다. 실제 제작은 출력 프레임을 열어보고 자막 시작 전후·곡 전환 경계와 선택한 템플릿의 자산/브랜드 영역을 확인한다. CD 계열은 CD 한 바퀴와 곡별 인물·커버 일치도 확인한다. 리듬 캔버스는 `scripts/test_motion_direction.py`와 `check-motion-template.mjs`로 원곡 시계·구간·무음·시크·가사·효과를 확인한다. 자세한 의존성·렌더·검수는 [제작 절차](references/production.md)에 있다.
