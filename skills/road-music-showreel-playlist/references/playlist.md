# 표시 선택과 여러 곡 플레이리스트

자유 연출은 네 응답을 완성한 display JSON과 곡 목록을 `native_project.py prepare --display ... --playlist ...`에 전달한다. 아래 CD용 plan/assets 예시는 명시한 프리셋에서만 사용한다. 새 음악의 기본 경로가 스타일 선택 화면을 요구하는 것은 아니다.

## 입력 질문

HTML 선택을 요청한 CLI 흐름은 [selection.md](selection.md)의 화면에서 먼저 답을 받는다. 이미 저장한 선택은 `--selection`으로 전달하고 대화로 다시 묻지 않는다.

새 제작에서 미확정 항목만 한 번에 묻는다. 표시 설정을 묻는 것은 제작 승인 요청이 아니다. 이미 답한 항목/수정하지 않는 기존 값은 다시 묻지 않는다.

`request_user_input_async`가 있으면 다음 네 질문을 함께 전달할 수 있다. 이미 아는 항목은 배열에서 뺀다.

```json
{"questions":[
 {"title":"음악에 반응하는 선형 스펙트럼을 표시할까요? SKIP하면 표시하지 않습니다.","options":["SKIP","표시","표시 안 함"]},
 {"title":"다음에 재생할 대기 곡 목록을 표시할까요? SKIP하면 표시하지 않습니다.","options":["SKIP","표시","표시 안 함"]},
 {"title":"현재 재생 중인 곡 이름을 표시할까요? SKIP하면 표시하지 않습니다.","options":["SKIP","표시","표시 안 함"]},
 {"title":"템플릿 브랜드 영역에 넣을 운영 채널명을 입력해 주세요. 넣지 않으려면 SKIP을 선택하세요.","options":["SKIP"]}
]}
```

마지막 질문은 UI의 자유 입력으로 실제 채널명을 받는다. 입력 도구가 없으면 네 항목을 간결한 텍스트 질문으로 묻고 답을 기다린다. 기본 선택/무응답/시간 경과는 답이 아니다. “전부 SKIP”, “스펙트럼만 켜고 나머지는 SKIP”처럼 분명한 묶음 답변도 그대로 해석한다. 부분 응답이면 남은 것만 묻는다.

## 저장과 적용

display-options.json:

```json
{"showSpectrum":true,"showQueue":true,"showNowPlaying":true,"channelName":"사용자가 입력한 채널명"}
```

표시 bool은 true/false. 각 값에 `"SKIP"` 또는 null을 주면 false로, 채널명은 빈 값으로 정규화한다. 채널명은 원문을 보존하되 바깥 공백만 제거하며 120자 이내·제어문자 없는 문자열이어야 한다. 실제 그리기에서 긴 이름은 공간에 맞춰 말줄임한다. “채널명이 없을 때”의 자리표시자나 자동 브랜드명은 없다.

`plan --display <옵션.json>`으로 계획에 저장하거나 `create --display <옵션.json>`으로 최종 적용한다. create의 명시 파일이 계획보다 우선한다. 옵션 파일은 네 답을 모두 반영한 완성본으로 만든다. 기존 프로젝트 수정에서는 저장한 값을 읽어 필요한 항목만 바꾼 완성 파일을 쓴다.

기존 preset CLI 호출은 질문 도구를 실행하지 않고 all-off 기본을 유지한다. 새 native prepare는 네 표시 키가 모두 적힌 완성 파일을 요구한다. **Codex 스킬을 사용하는 새 제작에서는 위 네 답을 먼저 받는다.** 이 두 경로를 혼동하지 않는다. create는 최종 display-options.json과 production.display/displaySource를 저장한다.

SKIP한 표시 옵션을 프리셋 기본값이나 다음 곡 전환에서 다시 켜지 않는다. 현재 곡명 표시를 꺼도 가창 자막은 기존 설정대로 유지한다. 대기 목록은 현재/이미 끝난 곡을 제외한 다음 곡만 보여주며, 마지막에는 다음 곡 없음으로 표시한다. 현재 곡명은 `[startSeconds,endSeconds)`의 곡만 표시한다.

채널명은 image_gen 사진에 구워 넣지 않고 Showreel 템플릿의 브랜드 영역에 합성한다. CD는 케이스 명판을 쓰며 사진 인쇄면만 회전한다. custom은 자체 레이아웃의 브랜드 영역을 쓴다. 스펙트럼/목록/곡명을 켜면 템플릿이 정보·가사 안전 영역을 확보한다.

## 여러 곡 입력

playlist-input.json은 순서 있는 실제 음원 목록이다. 파일 기준 상대 경로 또는 절대 경로를 쓴다.

```json
{"schemaVersion":1,"tracks":[
 {"path":"songs/song-a.mp3","title":"첫 번째 곡","captions":"lyrics/a.json","plan":"plans/a.json","assets":"images/a.json","vocal":"female","act":"band","artist":"여성 리드 보컬과 드럼·베이스·기타"},
 {"path":"songs/song-b.mp3","title":"두 번째 곡","captions":"lyrics/b.srt","captionOriginSeconds":0,"plan":"plans/b.json","assets":"images/b.json","vocal":"male","act":"solo"},
 {"path":"songs/instrumental.wav","title":"연주곡","instrumental":true,"plan":"plans/c.json","assets":"images/c.json","vocal":"none","act":"ensemble"}
]}
```

지원 필드: path, title, startSeconds, durationSeconds, captions, captionOriginSeconds, instrumental, vocal, act, artist, assets, plan. 보컬 곡은 원곡에 맞는 JSON/SRT를 준비한다. 각 곡에 [가창 자막](captions.md)의 해시·시계 검증을 적용한다. 연주곡만 instrumental=true로 하고 가사를 생략한다. `vocal`/`act`/`artist`/`plan`은 기존 CD와 그루브 다이얼 requiresArtist 흐름의 이미지 캐스팅·계획이다. `assets`는 CD 또는 custom의 선택한 assetSchema manifest이며, custom에 CD 사진 키를 강제하지 않는다. 곡의 제목은 사용자 목록→오디오 title 태그→파일 stem 순으로 읽고 출처를 남긴다. ID3이 없고 stem에 장르 접두사가 붙었더라도 사용자 또는 곡 메타데이터의 표시 제목이 있으면 단일 곡은 `--title`, 플레이리스트는 track `title`로 그대로 넘긴다. 이는 파일명을 바꾸거나 제목을 임의로 고치는 일이 아니다. 제목 표시가 필요한데 정확한 제목이 없으면 파일명 사용 여부를 명확히 한다. 모든 표시를 SKIP했으면 표시를 위한 새 제목 입력을 요구하지 않는다.

최상위 `casting`은 사용자가 모든 곡에 같은 보컬/편성을 명시할 때만 둔다. 상위 main plan의 casting은 트랙마다 자동 복제하지 않는다. 캐스팅 근거가 없으면 곡별 `vocal:"unknown"`으로 남기며, 장르·음역으로 여성/남성을 결정하지 않는다.

각 곡의 start/duration은 **그 원곡의 초 단위**다. 둘을 생략하면 원곡 전체를 쓴다. 자막 입력의 원점은 JSON source.cutStartSeconds 또는 captionOriginSeconds이며 원곡 시작과 구분한다. 트랙을 바꿀 때 앞 곡 자막/전역 offset을 다음 곡에 재사용하지 않는다. PCM48k stereo로 준비한 실제 샘플 수를 누적해 전역 경계/목록/곡명/가사를 만든다. 자동 크로스페이드·속도 변경·곡 사이 임의 공백을 넣지 않는다. 렌더 길이는 실제 총길이에만 1프레임 미만 패딩을 더한다. 인트로는 플레이리스트 시작에 한 번만 적용하며, 첫 곡이 인트로보다 짧으면 다음 곡부터 본문 아트를 쓴다.

CD는 공통 style/look의 variant·palette·caption·discPeriodSeconds를 앨범 전체에서 유지한다. 곡별 `assets`가 있으면 곡 경계에서 CD 인쇄면·케이스 사진을 해당 곡의 가상 아티스트로 바꾼다. custom은 선택한 template·assetSchema를 앨범 전체에서 유지한다. 그루브 다이얼은 곡별 plan의 `motionMode`가 다를 수 있으므로 트랙 경계에서 모션 강도도 바뀌고, 공통 variant/palette/caption/discPeriodSeconds는 앨범 전체에서 유지한다. 어느 경우나 곡명·대기 목록·가사·실제 오디오 스펙트럼은 같은 전역 시계로 갱신하며, 마지막 프레임 패딩은 마지막 곡 자산/상태를 유지한다.

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" create \
  --plan '/절대/genre-plan.json' --playlist '/절대/playlist-input.json' \
  --display '/절대/display-options.json' --assets '/절대/images.json' \
  --out '/절대/새플레이리스트'
```

--music와 --playlist는 하나만 고른다. playlist 모드에서는 각 곡의 제목/컷/가사를 tracks에 넣고 단일 곡용 --start/--duration/--title/--captions/--caption-origin을 함께 쓰지 않는다. 단일 곡도 --display를 지원하며 --title로 곡명을 정할 수 있다. 총 영상은 기존 인트로를 위해 12초 이상이다.

## 실제 스펙트럼과 검증

스펙트럼을 켠 경우 최종 audio/mix.wav의 **실제 FFT**를 분석한다. 24k mono, Hann 창 4096, 약20fps, 40~12000Hz의 48밴드이며 0~255 값으로 저장한다. 선형은 가로 일렬 배치이며 주파수 밴드는 로그 간격이다. t=index*dt 중심의 창을 사용하고 dt는 실제 hop/sampleRate다. 창 길이에 따른 시간 해상도가 있으며, 임의 막대·RMS 복제·비트 난수로 대체하지 않는다. 전처리 값만 시간으로 보간하므로 시크/병렬 렌더 결과가 일정하다. 꺼진 경우 분석을 생략하고 spectrum.js는 null이다.

프로젝트의 playlist.json에 트랙별 원곡 해시·입력 자막 시계·PCM 샘플 경계, display-options.json에 최종 선택, production.json에 두 파일/스펙트럼 분석 오디오의 해시가 남는다. 렌더/마감은 기존 render 명령을 사용한다.

검수 시 각 곡 경계 직전/직후의 음원·곡명·대기 목록·가사·선택한 템플릿 자산을 함께 확인한다. 동일 제목 두 곡도 별개 id로 처리한다. SKIP한 DOM/브랜드 영역이 없고, FFT가 무음/주파수 변화에 반응하며, 정보 영역이 가사나 템플릿 본문과 겹치지 않는지 확인한다. 긴 타임라인은 앞·각 경계·끝에서 seek한다. CD는 커버/인물도 확인한다. 시험은 `test_playlists.py`, `test_playlist_tools.py`, `test_vocal_cast.py`, `check-playlist-ui.mjs`, `check-track-art.mjs`를 사용한다.
