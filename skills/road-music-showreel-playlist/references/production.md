# 제작과 검증

## 기존 설치

- Showreel: `~/.local/share/roadmusic-video-tools/showreel`; 원본 commit `64521220a2f8e91cb9894400c48c15b7f45205d6`.
- Python(NumPy/Pillow): `SHOWREEL_PYTHON 또는 현재 Python 3.11+ 환경`.
- Node.js 24, ffmpeg/ffprobe, Chrome, Showreel의 기존 playwright-core.

`SHOWREEL_HOME`, `SHOWREEL_PYTHON`으로 다른 기존 설치를 지정할 수 있다. 누락되면 의존성을 보고한다. 자동 모델 다운로드나 유료 API를 대안으로 쓰지 않는다.

실제 제작 시 설치된 Showreel `SKILL.md`와 `references/engine.md`, `design.md`, `techniques.md`, `qa.md`를 읽는다. 이미지는 이 스킬의 내장 image_gen 경로가 우선이다. 레거시 외부 이미지 CLI 부재를 내장 도구 부재로 판단하지 않는다. 영상은 시간 t의 순수 함수이며 누적 상태/무작위/CSS 애니메이션으로 시크 결과를 바꾸지 않는다.

## 입력과 생성

음악 해석을 구간별 실제 모션으로 만드는 리듬 캔버스는 [music-direction.md](music-direction.md)의 `create --style` → `motion_direction.py apply` → 네이티브 render 순서다. CD용 장르 plan과 이미지 manifest를 요구하지 않는다. 새 생성 이미지·썸네일은 direction.media로 검증·복사해 적용한다.

HTML에서 스타일·표시를 고르고 CLI 제작으로 넘기는 경우 [선택 화면](selection.md)의 `choose`와 `plan/create --selection`을 사용한다.

새 제작의 표시 질문/선택형 선형 스펙트럼/현재 곡명/대기곡/채널명/여러 곡 연결은 [플레이리스트](playlist.md)를 따른다. --display는 plan/create 모두 지원하고 --playlist는 create에서 --music 대신 쓴다. 선택을 SKIP하면 표시하지 않는다.

기존 CD와 그루브 다이얼은 [장르 계획](genres.md)을 먼저 만들고 `create --plan <genre-plan.json>`으로 적용한다. `plan --vocal`/`--act`의 캐스팅은 장르가 아니라 사용자 설명, 음악 생성 메타데이터, 확인 가능한 음원 정보에 근거한다. 일반 custom은 `--style`과 그 assetSchema로 만들며 `--plan`을 받지 않는다. 그루브 다이얼은 `genrePlanner:"cd-assets"` 계약으로 장르 계획을 받아 자체 템플릿을 사용한다. 가사 없는 곡은 --instrumental 또는 연주곡 CD 계획을 사용하고 --captions를 생략한다. 보컬 곡은 실제 자막 입력이 필요하다.

K-POP·댄스 팝·일렉트로닉·EDM의 현대적 새 제품 연출은 `--style '크롬 프리즘'`을 쓴다. 이 선택은 image_gen 프롬프트뿐 아니라 prism 합성의 투명 케이스·진주 아크릴 바탕·clean light-sweep/glass reveal에도 적용된다. 스타일의 `preview.status`가 pending이면 미리보기가 완성됐다고 보고하지 않고, 새 스틸과 렌더 검수 뒤에만 ready로 올린다.

CD의 `images.json`은 다음 5개 PNG 경로를 담는다. 파일 기준 상대 경로 또는 절대 경로, 최소 한 변 500px. case는 실제 투명 alpha다. custom은 선택한 preset의 assetSchema를 따르며 빈 객체 `{}`면 공통 `--assets` 입력을 요구하지 않는다. 리듬 캔버스의 선택 이미지·썸네일은 별도의 direction.media를 사용한다.

```json
{"photoA":"images/artist-a.png","photoB":"images/artist-b.png","photoC":"images/artist-c.png","case":"images/case.png","paper":"images/paper.png","casting":{"vocal":"female","act":"solo","reviewed":true,"artistId":"fictional-act-01","evidence":"visual review"}}
```

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" create \
  --style '가을 아카이브' --music '/절대/원곡.mp3' \
  --captions '/절대/가사.json' --assets '/절대/images.json' \
  --out '/절대/새-프로젝트'
```

- 전체곡은 start/duration 생략. 플레이리스트도 각 track의 start/duration을 생략하면 원곡 전체를 이어 붙인다. 미리보기는 별도 프로젝트/구간으로 `--start 79.76 --duration 18`처럼 원곡 기준으로 지정하며, 긴 최종본을 줄이거나 대체하지 않는다.
- 최소 12초다. CD는 기본 10.17초 인트로 뒤에 본문을 남긴다. custom은 자체 template의 타임라인을 따른다. 더 짧은 영상은 장면 큐/템플릿도 조정해 검증해야 한다.
- `--demo-assets`는 카탈로그 참고 사진을 재사용하는 명시적 옵션이며 `demo-only`다. 여성/남성/혼성 캐스팅 일치 증거로 쓰지 않는다.
- JSON 자막은 `source.cutStartSeconds`를 원곡 offset으로 읽는다. SRT 기본 원점=원곡 0초. 클립 상대 SRT는 `--caption-origin <원곡시작초>`를 명시한다.
- 음원은 48k stereo WAV로 자르고 네이티브 음악 분석/타임라인/믹서로 -14 LUFS 믹스를 만든다. 원본·가사 문구는 보존한다.
- `production.json`은 원곡/자막/WAV 해시, 설정 snapshot, 실제 사용 이미지 해시, 요청 길이와 `ceil(T*30)` 렌더 길이/프레임 패딩을 따로 저장한다. 플레이리스트에는 곡별 PCM 샘플 경계·캐스팅 검수·곡별 이미지 출처도 남긴다. 1프레임 미만 패딩 때문에 음악 재생속도를 바꾸지 않는다.

네이티브 timeline 로그의 `발화 0.0s`는 나레이션 합계다. 가창 자막의 유무·개수·시각은 `captions/lyrics.json`을 확인한다.

생성 파일: `preset.json`, `production.json`, `script.json`, `timeline.json`, `reel/`, `captions/lyrics.{json,srt}`, `audio/music/music.wav`, `audio/mix.wav`. custom reel은 선택한 template의 로컬 HTML/JS만 복사한다. 새 이미지의 프롬프트와 결과 경로/인물 설정은 필요한 경우에만 프로젝트 `assets/generation.json`에 기록한다. demo-assets는 기존 generation.json을 새 생성이 아님을 표시해 자동 복사한다. 컷 경계에 0.5초 미만만 남은 문장은 captionWarnings에 표시한다. 정확한 컷 요청을 임의로 바꾸거나 문구를 삭제하지 않고, 조정 가능한 컷이면 가창 경계를 기준으로 길이를 고른다.

## 렌더

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" render --project '/절대/프로젝트' --preview
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" render --project '/절대/프로젝트'
```

preview와 본편은 각각 그 프로젝트의 전체 길이를 1920×1080으로 렌더하며 preview는 sub=1, 본편은 sub=4 PNG 캡처다. 긴 영상의 빠른 검토는 별도 구간 프로젝트/스틸로 하며 최종 전체 렌더와 구분한다. 현재 Chrome 조합은 네이티브 --scale 로그와 실제 캡처 크기가 다를 수 있어, 이 스킬은 scale=1로 고정하고 실제 ffprobe 규격을 검증한다. 네이티브 `render.mjs`→`finish.py`, H264/yuv420p/BT709/tv/AAC48k/faststart/SRT. JSON 완료 응답은 stdout 한 줄, 진행은 stderr다. 기존 출력이 있으면 거부한다. 수정본은 새 프로젝트 경로로 만들며 코드 변경 뒤 이전 네이티브 캐시를 재사용하지 않는다. 렌더러는 한 번에 하나만 실행한다.

CD는 사진 인쇄면만 회전하고 케이스/허브/반사는 고정이다. 5개 기본 구간 `focus→print→memory→bokeh→cd`를 장르에 맞춰 조정할 수 있으나 원곡과 자막 시계는 보존한다. custom은 자체 template의 연출을 따르되 `PLAYLIST_CONFIG`, `PLAYLIST_LYRICS`, `PLAYLIST_SPECTRUM`, 순수 함수 `__seek(t)`, boolean `window.__ready=true`로 같은 시간 계약을 지킨다. 음악 히트가 장면 밖이면 유효 범위 내 이벤트/시각을 고른다.

스틸: Showreel `render.mjs --dir <reel> --stills 0,0.9,4.4,6.4,9.8,10.1,12.5 --outdir <새QA폴더> --workers 1`. 다른 렌더와 동시 실행하지 않는다.

## 확인

- helper의 실제 프레임 수/30fps/yuv420p/전체 디코드 결과와 `qa/*-media.json`을 읽는다. 해상도·색 범위·오디오 레이트/채널·음량도 확인한다.
- 실제 첫 프레임, 전환 전후, 본문을 열어본다. 선택 템플릿의 자산 잘림·저대비·빈 프레임을 고친다. CD는 얼굴 이중상/유리 바깥 검은 판·CD 회전 위상도 확인한다.
- `check-template.mjs`: CD 5 variant의 decode, 시크 동일성, 자막 onset/end gate, 글꼴, CD 회전 위상. 프리즘은 factory-new 케이스/바탕과 scratch·grain 부재도 스틸로 확인한다. custom은 해당 template의 `__seek(t)`/`window.__ready=true`와 assetSchema를 검수한다. 그루브 다이얼은 `test_presets.py`·`test_playlists.py`와 `check-groove-template.mjs <생성 프로젝트> <새 QA 폴더>`로 표시 8조합·3단계 모션·5개 variant 설정의 로딩·시크·가사 어절·곡 경계·장시간 시크를 검수한다. `test_custom_presets.py`는 custom의 template·자산 경로·등록 제약을 확인한다. `check-track-art.mjs`는 CD 곡별 아트의 첫 인트로/경계/짧은 첫 곡/긴 seek 동작을 확인한다. `test_vocal_cast.py`는 requiresArtist CD manifest의 캐스팅·검수 요구를 확인한다.
- JSON/SRT/번인 문구·시각 일치, 시작 직전 숨김/직후 전문 표시를 최종 서브프레임 렌더에서도 확인한다. 가창 정렬은 [자막](captions.md) 기준이다.
- 네이티브 `motion_check.py`로 섬광/빈 프레임을 확인한다. 템플릿의 읽기 정지는 의도라면 시각/이유를 기록한다. 섬광 실패는 의도로 무시하지 않는다.
- `contact_sheet.py`가 현재 ffmpeg에서 `-vsync vfr` 오류를 내면 프로젝트 QA용 복사본에서만 `-fps_mode vfr`로 바꾼다. 검사 기준은 유지한다.

납품: 재생 영상·카탈로그·설정/편집 프로젝트 경로, 선택 스타일, 이미지 도구, 자막 검증 범위를 짧게 적는다. 듣지 않은 가창 싱크를 청취 완료로 보고하지 않는다.
