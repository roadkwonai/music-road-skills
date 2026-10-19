# 음악 장르별 제작

음악 장르와 화면 프리셋은 별개다. 같은 트로트도 크림 종이 아카이브나 흑백 누아르로, K-POP도 사용자가 원하면 빈티지 스타일로 만들 수 있다. 이 문서의 `plan --genre`는 기존 CD와 `genrePlanner:"cd-assets"`를 선언한 그루브 다이얼에 적용한다. 일반 custom은 거부된다. CD 계열 프리셋은 화면 형식 참고이며 36개 장르의 전용 이미지/영상이 이미 만들어졌다는 의미가 아니다.

## 범위

`assets/genre-profiles.json`의 창작 기본값 36개: 정통/세미/댄스 트로트, 발라드, 록발라드, R&B, 재즈, 팝, **K-POP**, 인디팝, 시티팝, 신스팝, 댄스팝, 힙합·랩, 소울, funk, 디스코, 록, 하드록, 메탈, 펑크록, 블루스, 포크·어쿠스틱, 컨트리, 로파이, 앰비언트, 일렉트로닉·EDM, 라틴, 보사노바, 레게, 클래식, 시네마틱·OST, 국악/퓨전, 월드/지역, 가스펠·CCM·워십, 뉴에이지. `K-POP`/`케이팝`/`kpop`/`K-pop`은 같은 K-POP 프로필로 정규화한다. 이 목록은 음악학적 분류나 지원 제한이 아니다.

다른 장르는 중단하지 않고 원래 이름과 곡 브리프로 인물/공간/촬영 매체/물성을 새로 설계한다. 복합 장르는 `R&B + 재즈`, `트로트 / EDM`처럼 병기한다. 먼저 적은 장르를 기초로 쓰되 두 장르의 방향과 사용자 무드를 모두 프롬프트에 남긴다. 더 중요한 장르/세부 편성은 Codex가 곡 정보로 결정하고 브리프에 명시한다. 문자열 매칭은 오디오 장르 인식이나 자연어 의도 해석의 대체물이 아니다.

`customDirectionNeedsAdaptation=true`이면 Codex가 목록 밖 요소를 해석해 구체적인 장면/인물/물성을 보완한다. 미등록 장르에 화면을 지정하지 않은 helper의 가을 아카이브는 임시 기본값이다. “최신곡”·“신곡”은 장르 분류나 실시간 유행 확인의 증거가 아니다. 사용자가 새 제품·현대적인 CD를 원하면 `--style '크롬 프리즘'`을 우선하고, 빈티지 스타일을 명시하면 그 선택을 유지한다.

## 계획

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" genres
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" plan \
  --genre '트로트' --brief '차분한 이별곡, 소극장, 청록빛 무대' \
  --vocal female --act solo \
  --artist '짙은 단발과 바랜 재킷' \
  --out '/절대/새작업/genre-plan.json'
```

사용자가 고른 화면을 유지하려면 `--style '누아르'`를 더한다. 이 경우 장르별 인물·촬영 방향은 쓰고 지정 스타일의 색감/자막/회전은 보존한다. 미지정이면 장르 기본 스타일과 visual 설정을 고른다. `--brief`는 곡의 정서/편성/시대/소품/선호를, `--artist`는 가상 인물 설정을 받으며 사용자 문구를 보존한다. `--vocal female|male|mixed|unknown|none`, `--act auto|solo|duo|band|ensemble|artwork`은 이미지 캐스팅을 명시한다. 장르나 음역으로 나이·성별·국적·종교·지역 의상을 추정하지 않는다. 무드/사용자 지시가 장르 예시보다 우선이다.

여성 보컬+band는 여성 리드 보컬과 곡에 맞는 밴드 편성이다. 밴드 전원을 여성으로 만들려면 사용자가 따로 요청한다. `mixed`는 여성·남성 보컬이 함께 있는 편성이고, `none`/`--instrumental`은 가수·가창 동작 없는 연주 장면이다. 사용자 설명, 생성 메타데이터, 확인 가능한 음원 정보에 근거가 없으면 `unknown`으로 계획하고 확인한다.

명시한 화면 스타일이 있으면 장르의 sceneDirection(공간·행동)만 가져오고 촬영 매체/고유 색은 선택한 화면을 따른다. 혼합 장르도 기본 촬영 매체는 첫 장르 하나에서만 가져와 컬러/흑백 지시가 동시에 섞이지 않게 한다.

K-POP·댄스 팝·일렉트로닉·EDM은 기본적으로 크롬 프리즘을 사용할 수 있다. 이 스타일은 새 진주 아크릴·크롬·유리 반사, 자연스러운 피부, 깨끗한 현대 패션을 쓴다. `paperDirection`이라는 필드명에도 실제 종이나 테이프·스크래치·필름 그레인을 넣지 않는다. `sceneDirection`은 장소·행동·포즈만 다루므로 사용자가 빈티지 프리셋을 고르면 그 매체·색과 충돌하지 않는다.

“은빛 종이”, “청록색 무대”처럼 구체적인 요청은 brief에만 남기지 않는다. Codex가 요청을 해석해 다음처럼 **실제 팔레트·재질을 look JSON으로 작성**하고 `plan --look '/절대/look.json'`으로 적용한다. helper는 자연어를 임의 RGB로 번역하는 모델이 아니며, Codex가 정한 수치와 재질을 프롬프트/영상 설정에 함께 반영한다.

```json
{"palette":{"paper":"#E5E6E8","ink":"#25303A","accent":"#8A949C"},"paperDirection":"구겨진 은빛 종이와 무광 은박, 조용한 하단 여백"}
```

look은 palette/자막 caption/회전 discPeriodSeconds의 지원 설정과 photoDirection/paperDirection 문자열을 받는다. 그루브 다이얼에만 `variant`와 `motionMode`도 지원하며, 장르 기본 팔레트·재질·리듬 강도보다 명시 look이 우선한다. 자세한 장르별 그루브 연출은 [groove-dial.md](groove-dial.md)를 따른다. 지정한 항목은 스타일/장르 기본값보다 우선하며 누락한 팔레트/자막 항목은 선택한 기본값을 유지한다. 사용자 취향을 임의로 바꾼 값이 아니라 요청에 맞춘 제작 선택으로 기록한다. 고친 look으로 계획을 다시 만들면 5개 이미지 프롬프트와 실제 합성 팔레트도 같이 갱신된다.

계획 결과:

- genre.input/matched/unlisted/mode: 원래 장르와 인식/혼합/목록 밖 상태.
- effectivePreset: 실제 적용할 팔레트/서체/자막 장식/회전 주기와 이미지 방향.
- imageGeneration: 현재 호스트의 공급자 계약과 `status=prompts-ready-not-generated`. Codex는 **requiredTool=image_gen, mode=built-in**, Claude는 **requiredTool=gpt-image, mode=codex-cli-bridge**다. photoA/B/C/case/paper의 프롬프트·투명 배경·참조 역할이며 실제 이미지는 아니다.
- motionGuidance: 장르별 연출 제안. 새 전환을 자동 구현했다는 뜻이 아니다. 기본 native variant의 5구간은 공유하며 추가 움직임은 실제 프로젝트에서 구현·검수한다.
- casting: 보컬/편성/연주곡 여부와 확인 필요 상태. 장르나 음역을 추정 근거로 쓰지 않는다.
- captions/instrumental: 가사 유무와 실제 가창 시각 보존 기준.

파일 출력은 기존 계획을 덮어쓰지 않는다. 새 경로나 새 버전 파일로 저장한다.

## 이미지에서 영상까지

1. AI가 계획의 casting과 곡에 맞는 아티스트 설정을 확정한다. 현재 호스트의 공급자 계약으로 5개 자산을 실제 생성하고 원본/참조/저장 경로를 기록한다. Claude는 `gpt-image` 브리지의 실제 결과를 쓴다. 제공 이미지가 있으면 해당 범위는 재사용한다.
2. [이미지 제작](images.md)대로 A의 일관성을 유지해 B/C/케이스를 만든다. 사용자가 동의하지 않은 데모/유료 API/다른 이미지 도구로 대체하지 않는다.
3. 생성한 5개 PNG의 images.json과 실제 자막을 제공한다.

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" create \
  --plan '/절대/새작업/genre-plan.json' --music '/절대/원곡.mp3' \
  --captions '/절대/타이밍.json' --assets '/절대/images.json' \
  --out '/절대/새프로젝트'
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" render --project '/절대/새프로젝트' --preview
```

프로젝트 preset.json과 reel/config.js에 계획의 visual 설정이 적용된다. genre-plan.json을 복사하고 production.json에 계획 해시·원곡 해시·자막 시계·이미지 해시를 보존한다. SRT/원문/가창 onset은 장르 효과 때문에 바꾸지 않는다. 프롬프트만 작성한 상태로 제작 완료라고 하지 않는다.

## 무가사 곡

`plan --genre '클래식' --instrumental`처럼 명시한다. create에는 --captions를 생략한다. 계획 없이도 `create --style ... --instrumental`을 쓸 수 있다. 실제 편성에 맞는 가상 성인 연주자/악기 정물/공간으로 제작하며 가수·가창 동작·가짜 가사를 만들지 않는다. captions 상태는 instrumental-no-lyrics, cues/SRT는 비어 있다. 보컬 곡은 기존 자막 입력을 요구하므로 실수로 자막을 빼는 흐름과 구분된다.

## 확장

목록 밖 장르도 바로 계획할 수 있다. 반복 사용할 음악 가족이면 genre-profiles.json에 새 고유 id/name/aliases, baseStyle, artistDirection/sceneDirection/photoDirection/paperDirection/motionDirection, 지원되는 visual 설정을 추가하고 `genres`/시험으로 검증한다. sceneDirection은 색·필름 매체를 넣지 않는 공간/행동/구도다. 기존 별칭을 다른 장르로 덮지 않는다.

새 화면 스타일 자체를 저장할 때는 [프리셋 등록](presets.md)을 따른다. CD는 최종 설정/이미지/실제 미리보기를 새 이름으로 add에 등록한다. CD가 아닌 스타일은 자체 template·assetSchema·실제 미리보기까지 만들어 등록한다. 장르 계획을 만든 것과 새 이름의 완성 프리셋을 등록한 것을 구분한다.
