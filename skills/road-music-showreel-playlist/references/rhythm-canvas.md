> 사용자가 **리듬 캔버스**를 명시한 경우에만 쓰는 기존 direction 계약이다. 일반 음악 요청은 [새 연출 흐름](production.md)을 사용한다.

# 음악을 해석해 만드는 모션그래픽

현재 음원·구간별 비트 반응·가사 재정렬·모션 결정성·섬광 보완은 [공통 품질 절차](production-quality.md)를 적용한다. 콘셉트가 기존 템플릿을 넘으면 [네이티브 모션 구현](showreel-motion.md)으로 이어가며, 분석 파일을 만드는 것과 실제 장면에 연결하는 것을 구분한다.

이미지 공급자는 [호스트별 이미지 생성](../../road-music-video-studio/references/image-providers.md)을 따른다. `image_gen` 인자 설명은 ChatGPT에 해당하며 Antigravity에서는 해당 세션의 이미지 기능/참조 입력으로 연결한다.


`리듬 캔버스`는 생성 이미지와 기하 모션을 함께 합성하는 Showreel 템플릿이며, 이미지 없는 절차형 모드도 지원한다. 음악을 넣었다는 이유만으로 CD·가수 사진·장르 라벨을 붙이지 않는다. 네 가지 화면 방식은 출발점이며, 곡이 요구하면 복사된 프로젝트의 장면을 직접 수정한다. 별도의 신규 스킬이나 음악 생성 모델은 필요 없다.

## 해석과 분석

먼저 원곡 경로·해시·실제 길이, 가사 원문/시각의 출처, 사용자가 정한 장르·색·표현을 확보한다. 같은 해시의 Road Music 제작 자료가 있으면 원문·의도 장르를 연결한다. 생성 요청의 목표 BPM/길이는 결과 오디오의 실측값과 구분한다. 음역으로 보컬 성별·국적·인원이나 장르를 확정하지 않는다.

기존 Showreel의 `scripts/music_tools.py analyze <음악> --out <새 분석.json>`으로 beats/downbeats/hits/energy를 얻는다. `hits`는 광대역 spectral flux 피크이며 킥·스네어 분리 결과가 아니다. BPM은 고정 템포 휴리스틱, downbeats는 4박 가정이다. 하프타임·변박·긴 곡의 드리프트를 확인하지 못했으면 큰 움직임을 고정 격자 전체에 깔지 말고 실제 hits를 골라 쓴다. 무음에서 추정된 BPM/히트는 근거로 삼지 않는다.

`analysis.json.energy`는 약 0.5초 간격 `[시각,dB]`; `reel/timeline.js`의 `TL.music.energy`는 0.05초 정규화 envelope다. 주파수 스펙트럼은 공통 표시 설정을 켰을 때만 만드는 실제 FFT이며 이 두 곡선과 다르다.

Codex가 다음을 해석해 `direction.json`에 기록한다. helper는 의미를 이해하는 모델이나 자동 장르 분류기가 아니다.

- 장르·편성·밀도: 사용자 설명, 확인 가능한 메타데이터, 실제 오디오 분석을 구분한다. 청취하지 않았으면 그렇게 쓴다.
- 가사: 화자와 대상, 감정의 변화, 반복되는 구절, 핵심 이미지와 절정을 읽는다. 원문을 바꾸지 않는다. 가사 미확보/불확실은 그대로 표시하며 연주곡으로 위장하지 않는다.
- 구조: 실제 도입·벌스·프리·후렴·브리지·끝을 가사 시각과 에너지 변화로 나눈다. 에너지 피크 하나를 자동으로 후렴이라 단정하지 않는다.
- 연출: 장르명보다 곡의 구체적인 정서가 우선이다. “발라드=항상 느림”, “K-POP=항상 네온”처럼 고정하지 않는다. 팔레트·모티프·화면 방식·강약이 해석한 의미를 어떻게 나타내는지 적는다.

## 실제 구현된 화면 방식

| style | 표현 | 곡에 맞춘 출발점 |
|---|---|---|
| `orbit` | 궤도·깊이감 있는 점과 확장 링 | 밤·동행·여운이 있는 발라드/R&B/앰비언트. 후렴에서 공간과 궤도 크기를 넓힌다 |
| `ribbons` | 음악 에너지를 따라 흐르는 곡선·리본 | 재즈·소울·어쿠스틱의 호흡, 밝은 팝의 유연한 그루브 |
| `grid` | 원근 그리드와 타격음에 반응하는 기하 패턴 | 댄스·일렉트로닉·힙합의 명확한 리듬과 도시적인 긴장 |
| `tiles` | 분절된 색면·타일의 재배치와 깊이 변화 | 록·펑크·경쾌한 팝의 타격감, 절정의 화면 확장 |

모티프 `stars / rain / petals / none`은 실제 그리는 절차형 요소다. 조용한 밤의 별, 이별/빗소리의 낙하, 회복/봄의 꽃잎 등 가사 맥락에 맞을 때만 선택한다. 새로운 모티프는 JSON에 이름만 쓰지 않고 템플릿 구현·프레임 검수까지 한다.

작은 움직임은 에너지 곡선, 큰 링·레이·스윕·펀치는 선별된 실제 hits 또는 명시한 가사 구절에서 일어난다. `intensity`는 곡 해석에 따른 **연출 강도**이며 오디오 측정치가 아니다. 긴 곡은 가사의 정착·여백과 후렴의 확대, 브리지의 감쇠를 대비시킨다. 반복 후렴은 알아볼 수 있는 모티프를 유지하고 마지막 후렴만 필요한 만큼 확장한다. 강도 0.2~0.45는 잔잔한 호흡, 0.45~0.65는 중간 강도의 출발점이다. 그리드·타일의 0.65 초과는 선명한 색면과 빠른 원근/패럴랙스를 더하는 드라이브 범위이므로 편곡과 정서에 맞게 선택한다.

## 방향 JSON과 원곡 시계

### 생성 이미지와 첫 0.5초 카드

새 제작에서는 가사·장르·정서에서 장면을 정해 내장 `image_gen`으로 실제 이미지를 만든다. 예를 들어 심야 메시지 노래는 젖은 도시·불 켜진 창·휴대전화·새벽처럼 가사의 물건과 감정 변화를 연결한다. 이미지 수와 인물 사용은 곡에 맞게 정하며 고정 가수 사진을 강제하지 않는다. 제공 이미지나 순수 기하 표현을 지정한 요청은 그대로 따른다.

썸네일은 별도 이미지로 만들고 곡명·확인된 아티스트·사용자가 선택한 채널명만 넣는다. 실제 결과를 열어 한글·사물·구도와 16:9 크롭을 확인하고, 오자나 원치 않은 인물/소품은 `image_gen` 편집으로 고친다. 새 자산을 이전 곡의 데모로 대체하지 않는다. 선택한 생성 파일은 작업 폴더에 복사하고 도구=`image_gen`, built-in 모드, 프롬프트/편집 프롬프트·원본/저장 경로·해시를 `assets/generation.json`에 보존한다. 승인된 이미지를 재사용할 때도 원래 생성 ledger가 있으면 함께 복사하고 재사용으로 표시한다. 원래 프롬프트/도구 근거가 없으면 사용자 제공·출처 미확인으로 기록하며 새 image_gen 실행 근거를 꾸미지 않는다. helper의 픽셀/해시 복사만으로 생성 ledger가 자동 전승되지는 않는다. 별도 유료 API는 필수 작업이 아니다.

기존 direction 최상위에 다음 `media`를 추가하고 각 구간에 `imageId`와 선택 `imageOpacity`(0..1, 기본 .8)를 넣는다. 이 이미지는 CD용 `--assets`가 아니다.

```json
"media": {
  "thumbnail": {"path":"/절대/thumbnail.png","durationSeconds":0.5},
  "images": [
    {"id":"city","path":"/절대/city.png"},
    {"id":"signal","path":"/절대/signal.png"}
  ]
}
```

구간 예: `"imageId":"city","imageOpacity":0.9`. 입력은 실제 PNG/JPEG/WebP의 절대 로컬 경로, 최소 960×540이며 가로 16:9·1920×1080 이상을 권장한다. `apply`가 프로젝트 `assets/motion/`으로 복사하고 상대 src·SHA256·크기를 기록하므로 생성 캐시나 외부 원본 경로에 의존해 재생하지 않는다. 이미지가 없는 기존 direction도 그대로 동작한다.

음악·가사는 원곡 0초를 유지한다. 원곡 시작 프로젝트만 첫 [0,0.5)초에 썸네일이 UI·효과 위에 고정되며, 후렴 컷의 원곡 시작이 0보다 크면 카드를 다시 붙이지 않는다. 현재 helper가 지원하는 카드 길이는 0.5초다. 다른 길이/별도 프리롤 요청은 실제 구현과 검수도 함께 바꾼다. 카드와 첫 가창이 겹치면 카드가 우선하며 가사 시각은 밀지 않는다.

이미지는 시간 함수의 팬·줌과 선택 타격음에 반응하고 기하 레이어의 투명도를 낮춰 사진을 살린다. 새 이미지를 디코드하지 못하면 렌더 준비 완료로 표시하지 않는다. `render=1`에서는 카드의 표시 여부만 목표 프레임 시각으로 정렬해 sub=4 모션 블러가 16번째 프레임에 썸네일 잔상을 섞지 않게 한다. 음악·가사·분석 시각은 이 양자화를 적용하지 않는다. 30fps의 첫 15프레임과 0.5초 직후를 실제 렌더에서 확인한다.

공통 `create`를 먼저 실행하면 `playlist.json`에 `track-001` 등의 id, 원곡 SHA256, 실제 PCM 샘플 경계가 나온다. `--style '리듬 캔버스'`에는 이미지 manifest나 CD용 `--plan`을 넣지 않는다. 표시 설정은 기존 선택을 유지한다.

```json
{
  "schemaVersion": 1,
  "type": "showreel-music-direction",
  "tracks": [{
    "id": "track-001",
    "sourceSha256": "playlist.json에 기록된 해당 원곡의 SHA256",
    "interpretation": {
      "genre": "사용자 제공 장르와 확인 범위",
      "mood": "초반의 망설임에서 후렴의 해방감으로",
      "lyricTheme": "밤을 지나 서로를 격려하는 가사. 원문 출처와 검수 범위 기록",
      "rationale": "밤의 궤도를 유지하고 후렴에서 별과 공간을 넓힘. 청취 여부와 추론 근거 기록"
    },
    "sections": [{
      "startSeconds": 0, "endSeconds": 40,
      "label": "도입과 벌스",
      "style": "orbit", "motif": "stars", "intensity": 0.3,
      "palette": {"background":"#111E36","foreground":"#FFF5DF","accent":"#F3B774","secondary":"#83BFD6"}
    }, {
      "startSeconds": 40, "endSeconds": 80,
      "label": "후렴",
      "style": "ribbons", "motif": "stars", "intensity": 0.7,
      "palette": {"background":"#20233E","foreground":"#FFF5DF","accent":"#F3B774","secondary":"#83BFD6"}
    }],
    "accents": [{"timeSeconds":42.5,"kind":"sweep","strength":0.65}]
  }]
}
```

위 시각은 형식 예다. 실제 곡의 길이와 가창/편곡 경계를 쓴다. `sections`와 수동 `accents`의 시각은 **각 원곡의 0초 기준**이며 영상 offset이 아니다. 구간은 순서대로 겹침 없이 선택한 원곡 범위를 덮어야 한다. 전체곡 계획을 별도 구간 미리보기에 적용하면 helper가 교집합을 잘라 매핑한다. 여러 곡은 각각의 id/원곡 해시/해석/구간을 작성하며 앞 곡의 전역 시각을 복사하지 않는다.

`palette` 네 색은 #RRGGBB, style/motif는 위 지원값, intensity/strength는 0..1이다. `label`과 interpretation은 제작 메타데이터이며 화면에 자동 출력하지 않는다. 수동 accents는 선택 사항이고 `ring / rays / sweep / punch`를 지원한다. helper가 원곡 시각을 변환하고, 자동 효과와 같은 순간이면 수동 효과를 우선한다. 수동 효과의 origin은 `manual-choice`이며 가사 또는 실제 음향 히트에서 왔다고 자동 추정하지 않는다. 기존 저장 프로젝트의 `lyric-phrase`는 호환해서 읽는다.

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" create \
  --style '리듬 캔버스' --music '/절대/원곡.mp3' \
  --captions '/절대/원곡-가사.json' --display '/절대/display-options.json' \
  --out '/절대/새-프로젝트'
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/motion_direction.py" apply \
  --project '/절대/새-프로젝트' --direction '/절대/direction.json'
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" render \
  --project '/절대/새-프로젝트' --preview
```

연주곡은 `--instrumental`로 captions를 생략한다. 여러 곡은 공통 [플레이리스트](playlist.md)의 `--playlist`를 사용한다. 짧은 미리보기는 `--start`/`--duration`으로 **별도 프로젝트**를 만들고, 같은 원곡 시계의 direction을 적용한다. create의 최소 길이는 12초이며 본편은 길이/시작 옵션을 생략해 모든 원곡 전체를 사용한다.

적용 helper는 원곡·프로젝트 WAV 해시와 구간/색/지원 효과를 검사한 뒤 `motion-direction.json`, `reel/direction.js`, `production.json.motionDirection`을 저장한다. 자동 accents는 네이티브 히트에서 구간 강도별 최소 간격으로 선별하며 -70dB 이하에서는 생략한다. BPM 격자를 강제로 재생성하지 않는다. 이미 적용/렌더한 프로젝트에는 재적용하지 않고 새 create 프로젝트에 수정 계획을 적용한다. 렌더러는 기존 네이티브 경로를 그대로 쓴다.

공통 경로는 원본 파일을 보존하고, 영상용 WAV를 48k stereo로 준비해 native mix의 음량 조정·짧은 fade-in을 적용한다. 비트/가사 시각·재생속도는 바꾸지 않지만 비트 단위로 동일한 오디오 복사는 아니다. 사용자가 오디오 처리를 금지하면 기존 파일을 고치지 말고 새 프로젝트에서 원곡 WAV 패딩만 준비하고 FFT도 그 실제 믹스를 기준으로 다시 만든다.

## 검수와 납품

`scripts/test_motion_direction.py`로 해시·원곡 컷·곡 경계·무음·효과 간격·잘못된 설정을 검증한다. `scripts/check-motion-template.mjs <프로젝트> <새 QA 폴더>`로 실제 Chrome의 역순 시크 동일성, 모드/구간 경계, 자막 onset/end, 글자 영역, 무음, 표시 옵션을 확인한다. 스타일 변경 시 템플릿 소스와 새 미리보기를 함께 검수한다. 캔버스 장면의 `resetFrame(ctx)`를 보존한다. `clearRect`만 호출하면 이전 효과의 선 굵기·경로 같은 그리기 상태가 다음 프레임에 남아 역순 시크가 달라질 수 있다.

실제 음악의 도입·가장 조용한 구간·후렴·브리지·끝과 선택 effects 전후를 프레임으로 연다. 다음을 고친다: 가사/정보 겹침, 한글 잘림, 과도한 발광, 리듬 없는 등속 운동, 반복 효과의 피로감, 의도하지 않은 빈 프레임. motion_check는 섬광/멈춤을 보조하며 감정 적합성이나 가창 정답을 보증하지 않는다. 실제 파일·화면으로 확인한 범위와 청취/ASR 초안을 구분한다.

납품은 전체 길이 MP4·짧은 미리보기·편집 가능한 reel·원문/SRT/타이밍·방향 JSON·출처와 QA다. 스킬 제작 검증용 짧은 영상은 전곡 납품으로 안내하지 않는다. 네 가지 화면을 시험했다고 모든 장르의 전곡 품질이 검증됐다고 하지 않는다.

## 확인한 Showreel 근거

설치된 실제 검수 영상은 [24초 네 방식 비교](../assets/presets/rhythm-canvas/preview.mp4)와 [12초 고강도 설정](../assets/presets/rhythm-canvas/drive-preview.mp4)이다. 둘 다 같은 원곡을 사용한 기능 검수이며 장르별 전곡 납품본은 아니다. [검증 기록](../assets/presets/rhythm-canvas/verification.json)에 실제 규격·움직임·섬광·가사 초안 상태와 검수 한계를 보존했다.

2026-10-17 설치/공식 upstream은 commit `64521220a2f8e91cb9894400c48c15b7f45205d6`로 같았다. [음악 분석 구현](https://github.com/revfactory/showreel/blob/64521220a2f8e91cb9894400c48c15b7f45205d6/scripts/music_tools.py#L163-L237), [네이티브 시간 함수·음악 동기](https://github.com/revfactory/showreel/blob/64521220a2f8e91cb9894400c48c15b7f45205d6/references/engine.md), [리듬·아트 디렉션](https://github.com/revfactory/showreel/blob/64521220a2f8e91cb9894400c48c15b7f45205d6/references/design.md), [검수](https://github.com/revfactory/showreel/blob/64521220a2f8e91cb9894400c48c15b7f45205d6/references/qa.md), [MIT 허가](https://github.com/revfactory/showreel/blob/64521220a2f8e91cb9894400c48c15b7f45205d6/LICENSE)를 기준으로 작성했다. 설치 업데이트·새 음악·TTS·유료 이미지 생성은 이 흐름의 필수 작업이 아니다.
