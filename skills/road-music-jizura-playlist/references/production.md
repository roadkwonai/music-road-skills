# 실행과 입력

## 의존성

Python 3.11 이상 표준 라이브러리, Node.js 24(내장 WebSocket), ffmpeg/ffprobe, Chrome, JIZURA 브라우저판을 사용한다. 유료 키나 새 이미지/음악 모델은 필요 없다. 렌더는 한 번에 하나씩 실행한다.

확인한 런타임: `~/.local/share/roadmusic-video-tools/jizura`, **v0.10.1**, commit `fc16bfe43ea4a6c25a21f1caf04d17326de14f00`. 공개 `J.ui/J.uiApi`와 native 파일 입력/MP4 출력 경로를 사용한다. 실제 등록된 부품을 검사하고 새 버전으로 임의 업데이트하지 않는다.

```bash
JIZURA_SKILL="/absolute/skills/road-music-jizura-playlist" # 현재 읽은 이 SKILL.md의 실제 부모
JIZURA_PY="${SHOWREEL_PYTHON:-python3}"
SKILLS_PARENT="$(dirname "$JIZURA_SKILL")"
UPDATE_SKILL="$SKILLS_PARENT/road-music-skills-update"
node "$UPDATE_SKILL/scripts/manage.cjs" check --target "$SKILLS_PARENT"
node "$JIZURA_SKILL/scripts/render-jizura.mjs" --self-check
"$JIZURA_PY" "$JIZURA_SKILL/scripts/project.py" styles
```

다른 설치 경로는 `--jizura-root`/`--chrome`으로 지정한다. 런타임이 없으면 누락을 보고하고, 설치까지 맡긴 경우 새 전용 경로에 공식 저장소의 위 commit을 내려받는다. 다른 앱/모델을 바꾸거나 Road Music 비공개 IPC로 우회하지 않는다. [공식 저장소](https://github.com/852wa/JIZURA)의 MIT LICENSE/THIRD_PARTY_NOTICES를 보존한다. 처음 쓰는 글꼴은 Google Fonts를 읽을 수 있다. fallback/네트워크 실패는 실제 프레임으로 확인한다.

## 분석

입력은 실제 절대 경로를 쓴다. 아래 `/절대/...`는 사용자의 실제 경로로 바꾼다. `--out`은 아직 없는 디렉터리다.

```bash
node "$JIZURA_SKILL/scripts/render-jizura.mjs" \
  --project "$JIZURA_SKILL/assets/probe.jizura.json" \
  --audio "/절대/음악.wav" --out "/절대/새-분석폴더" --inspect
```

`analysis.json`의 `audio.path/sha256/duration/bpm/beats/energy/energyRate`를 읽는다. `registry.json`은 실제 스타일/부품, `plan.json`은 실제 계획된 컷을 담는다. raw audio beats와 수동 BPM 적용 뒤 plan beats를 혼동하지 않는다. 에너지 곡선은 장르/가사 의미/가창 시각이 아니다.

## 연출과 cue

`direction.json`의 예시다. `sections[].jizura`는 해당 시간대의 가사 override와 간주 배경/도형에 실제로 적용된다. cue별 jizura가 같은 항목을 덮어쓴다. 구간의 id/start/end/role을 원음 시계로 기록한다. 자유 서술 motifs/references/rationale는 해석 근거이며, 실행할 반복 모티프는 cue.motif와 아래 directing으로 연결한다.

```json
{
  "title":"실제 곡명", "artist":"", "genre":["시티팝"],
  "profile":"neon-city", "seed":20261017, "lang":"ko",
  "interpretation":"가사의 중심 이미지와 감정 변화를 곡에 맞게 기재",
  "sections":[{"start":0,"end":12,"role":"intro","evidence":"실제 편성 변화"}],
  "motifs":[{"music":"스네어","visual":"패널 전환","where":"후렴"}],
  "references":[], "rationale":"이 곡과 스타일 선택의 연결",
  "timingStatus":"provided-lrc-unreviewed", "listeningReviewed":false,
  "jizura":{"fx":{"motion":0.7,"glitch":0.1}}
}
```

무자막은 `instrumental:true`. 보컬 곡에서 자막 없이 제작하는 경우 그래픽 모드로 이 값을 쓰고 실제 보컬 유무는 별도로 기록한다. 수동 BPM을 생략하면 검출 비트를 쓴다. 수동 지정에는 실측 `bpm`과 `beatOffset`이 모두 필요하다.

`cues.json`은 원음 시작=0초인 배열이다. 원문/순서/시각을 보존한다. SRT/LRC에서 변환할 때 출처·오프셋·정렬 상태를 별도 기록한다. LRC의 다음 행 시작은 현재 행 가창 끝의 확정 근거가 아니다.

```json
[
  {"start":1.2,"end":3.8,"text":"사용자가 제공한 실제 가사","section":"verse",
   "jizura":{"cuts":1,"layout":"center","enter":"wipe","exit":"blur"}},
  {"start":4.2,"end":7.1,"text":"다음 실제 구절","section":"chorus","breakBefore":true,
   "jizura":{"cuts":1,"layout":"huge","enter":"pop","exit":"shrink"}}
]
```

- builder는 빈 구간에 `[interlude N]`을 명시한다. 무가사 구간은 `kind:"interlude",start,end,jizura:{bg,decor}`로 설계할 수 있다. 프로필별로 글자 없이 보이는 배경과 beatRing 등의 도형을 명시하고, 검출 비트 8개 단위로 배경을 바꾼다. 실제 마디/스윙은 확인하고 명시 구간으로 조정한다. spectrumRing은 에너지/비트로 움직이는 절차형 그래픽이며 주파수별 FFT 측정 결과가 아니다.
- 단어 시각이 있으면 `cuts:3,cutTime:{"1":0.6,"2":1.2}`처럼 행 시작 기준 상대 초를 쓴다. 균등 분할은 정렬 결과가 아니다. 엔진이 실제 나눈 문구는 `plan.json`으로 확인한다.
- 겹침·음원 초과·0.35초 미만 행/분절은 거부한다. 0.35초보다 짧은 쉼에는 별도 간주 행을 끼우지 않고 앞 문장의 읽기 시간을 다음 onset까지 유지한다. 원래 가창 end는 cueMap에 보존하며 이를 연장된 가창으로 부르지 않는다. 과밀한 가사는 실제 구절 단위로 묶거나 별도 자막 레이어로 처리한다.
- 엔진은 `/`, `*`, `|`, 행 끝 `!`, 시작 `[`/`#`를 구문으로 해석한다. builder는 원문 충돌을 거부한다. 원문 문자를 삭제하지 말고 해당 구절을 원문 레이어로 합성한다.
- ASR만 있으면 기존 설치된 로컬 도구로 초안을 만들고 검수 전 상태를 기록한다. 형제 스킬의 `"$SKILLS_PARENT/road-music-showreel-playlist/references/captions.md"`가 있으면 해시/시계/정렬 근거 규칙을 참고할 수 있다. 필수 의존성은 아니며 없어도 가용 도구로 진행한다. 유료 전송/새 모델 다운로드는 임의 대안이 아니다.

```bash
"$JIZURA_PY" "$JIZURA_SKILL/scripts/project.py" build \
  --analysis "/절대/새-분석폴더/analysis.json" \
  --direction "/절대/direction.json" --cues "/절대/cues.json" \
  --out "/절대/새-곡-프로젝트"
```

무자막이면 `--cues`를 생략한다. 자동 제목은 비워 긴 간주에서 제목이 반복 노출되지 않게 하고 곡명은 direction에 보존한다. 화면 제목은 요청한 cue로 넣는다.

## 렌더와 원음 마무리

여러 전역 스타일을 한 곡 안에 섞으려면 [스타일 조합 제작](style-composition.md)을 따른다. 단일 native 프로젝트의 `style`은 하나다. 같은 스타일 안의 구간별 기법 변화와 여러 스타일의 구간 렌더를 구분하고, 후자는 새 `project.py compose --manifest ... --out ...`으로 원음 시계를 보존해 합친다. 여러 곡을 이어 붙이는 아래 `assemble`과 용도가 다르다.

```bash
node "$JIZURA_SKILL/scripts/render-jizura.mjs" \
  --project "/절대/새-곡-프로젝트/project.jizura.json" \
  --audio "/절대/음악.wav" --out "/절대/새-네이티브-렌더" --render
```

래퍼는 격리 Chrome에서 JIZURA 자체의 프로젝트/음악 입력과 MP4 버튼을 쓴다. 실제 plan과 검수 프레임을 보존하고 자기 Chrome만 종료한다. stdout 한 줄 JSON을 읽는다. AAC 미지원으로 WAV가 따로 나온 경우 무음 MP4를 완료라고 하지 않는다. 원음으로 아래 assemble을 실행해 음성을 넣고 검증한다.

엔진은 마지막 가사 길이를 추정하므로 원음 끝에 짧은 terminal 간주를 둔다. raw 영상은 0.01초와 프레임 반올림만큼 길 수 있다. **한 곡도 assemble로 원음 길이에 맞춰 마무리한다.** 여러 곡은 원래 순서로 manifest에 넣는다. 규격이 같아야 하며 원음보다 짧은 영상은 거부한다.

```json
{"tracks":[
  {"title":"실제 곡명","audio":"/절대/음악.wav","project":"/절대/새-곡-프로젝트/project.jizura.json","video":"/절대/실제-native.mp4"}
]}
```

```bash
"$JIZURA_PY" "$JIZURA_SKILL/scripts/project.py" assemble \
  --manifest "/절대/tracks.json" --out "/절대/새-최종-플레이리스트.mp4"
```

원음 해시를 확인하고 분석된 음원 길이로 영상을 잘라 원음과 연결한다. 영상 프레임 수는 누적 오디오 시계에서 반올림하고 오디오는 별도로 연결해 곡 사이에 프레임 반올림 무음을 넣지 않는다. 영상 경계는 반 프레임 안에서 양자화되며 최종 AAC/컨테이너에는 끝 패딩이 있을 수 있다. 크로스페이드/리믹스는 자동 적용하지 않는다. `.mp4.json`의 실제 규격/길이/챕터를 읽는다. 스트림 검사를 청취/가사 정답 검수로 확대하지 않는다. 부분 미리보기를 전체 본편이라고 하지 않는다.

## 자체 확인

```bash
"$JIZURA_PY" "$JIZURA_SKILL/scripts/test_project.py"
node --check "$JIZURA_SKILL/scripts/render-jizura.mjs"
node "$JIZURA_SKILL/scripts/directing.test.mjs"
node "$JIZURA_SKILL/scripts/render-jizura.test.mjs"
```

래퍼 변경 후에는 격리된 짧은 음원으로 실제 inspect/MP4도 실행하고, directed 프로젝트를 새 브라우저에서 재로드해 이벤트 시각과 배치 파라미터가 같은지 확인한다. 자동 검사는 취향·가사 정답·청취까지 증명하지 않는다.


## 리듬 오검출 확인

자동 BPM은 후보값이다. 목표 프롬프트의 BPM도 실제 생성 음원의 BPM을 증명하지 않는다. 도입·중간·끝에서 드리프트가 보이면 기존 NumPy 런타임으로 음향 어택을 비교한다. 이 기기에서는 다음 Python에 NumPy가 이미 설치되어 있다. 없는 환경에서는 누락을 보고하며 임의로 패키지를 설치하지 않는다.

```bash
"$JIZURA_PY" "$JIZURA_SKILL/scripts/rhythm.py" \
  --audio "/절대/음악.mp3" --native-analysis "/절대/분석/analysis.json" \
  --out "/절대/새-리듬검증폴더"
```

`rhythm.json`의 분석 구간·hop 해상도·native/fitted 비교를 읽는다. strong onset recall과 grid tick precision은 다르다. 반박/배속 후보도 확인하고, 일치도가 높은 모든 grid tick에 강효과를 달지 않는다. 음악적 BPM·박자표·다운비트를 자동 확정하는 도구가 아니다. 후보 채택 시 실제 데이터 해상도보다 정밀한 숫자를 정확도로 주장하지 않는다. 수동 bpm/beatOffset을 넣으면 builder의 간주 전환도 같은 그리드를 사용한다.

## 효과 스코어와 후렴 모티프

가사 전문을 유지하는 cuts:1은 native unify의 일부 연출을 막는다. 그래서 “unify:true면 반복 후렴이 같을 것”이라고 가정하지 않는다. 같은 원문 구절에 같은 `cue.motif` 값을 주면 builder가 native line id 그룹을 만들고, 래퍼가 공개 `J.lineSnapshot`과 `overrides.lockedCuts`로 실제 배치/움직임을 고정한다. 복제한 appearance와 각 위치의 이벤트 시각은 분리한다.

```json
{
  "directing": {
    "schemaVersion":1,
    "sourceSha256":"분석 JSON의 실제 원음 SHA-256",
    "accents":[{"time":72.86,"type":"zoomPunch","amp":0.45,"dur":0.18}],
    "schemes":[{"start":0,"end":68,"index":0},{"start":68,"end":90,"index":1}]
  },
  "reviewTimes":[15.6,69.3,79.5,156.6,191,215.1]
}
```

이 값들은 direction.json의 최상위 필드다. effect id는 실행의 registry.fx, 색면 index는 선택한 실제 스타일의 schemes 범위에서 고른다. 유한한 time/amp/dur와 원음 해시를 검사한다. 전체 화면 효과는 가사 cut에 적용되며 간주에는 이 잠금 경로가 없다. 간주 효과는 beatRing 같은 반응형 배경/도형으로 만들고, 스코어의 미할당 항목을 보고에서 확인한다. 색면은 lyric cut의 시작 시각으로 선택하므로 구간 경계와 가사 행 경계를 맞추어 계획한다.

렌더/inspect 출력의 **directed.jizura.json**이 점수가 구워진 native 편집 프로젝트이며, `directing-report.json`과 실제 `plan.json`으로 적용을 확인한다. vanilla JIZURA에서도 같은 원음을 불러와 재현된다. 파라미터를 임시 monkeypatch하거나 별도 영상 엔진으로 바꾸지 않는다. 원래 unlocked 프로젝트도 보존한다. 가사·컷 수·전체 스타일을 바꾸면 잠금을 풀고 원래 입력에서 다시 bake한다. 잠긴 모습이 새 전역 스타일을 자동으로 따라간다고 가정하지 않는다.

`reviewTimes`는 원음 초 기준 검수 시각이다. 렌더 전 seek 프레임 외에 실제 완성 MP4에서도 해당 시각을 추출해 확인한다. preview의 `actualExportSpan.t0`는 원음 offset이며, 구간 출력의 영상을 원곡 전체 본편으로 소개하지 않는다.

리듬 분석기 변경은 NumPy가 있는 같은 Python으로 `scripts/test_rhythm.py`를 실행한다. 짧은 쉼의 가창 end와 실제 읽기 hold는 `timingNotes`에서 구분한다. directing의 일부 accent라도 할당되지 않거나 time/type/amp/dur가 실제 plan과 다르면 완료로 처리하지 않는다. 오디오를 불러올 때 UI가 바꾸는 snap 설정은 원래 명시값으로 복원한 뒤 bake한다.

<a id="html-studio"></a>
## HTML Studio: 여러 추천과 커스텀 제작

로컬 공식 편집기를 같은 origin에 연결해 27개 스타일·860개 부품을 그대로 사용한다. 원격 사이트 iframe에 명령을 보내는 방식이 아니다. 기획과 기능 대응은 [설계](studio-design.md), [공식 기능 분석](official-features.md)에 있다.

Codex가 음원/가사를 해석해 단일 스타일 후보는 `direction.recommendations`에 기록한다. 조합안은 `direction.compositionRecommendations`로 구간·강도·이유를 구분하고 [조합 비교](style-composition.md#recommend)로 보여 준다. profile/genre/interpretation/sections/motifs도 유지한다. 현재 HTML의 profile 카드는 단일 프로젝트를 바꾸며, 조합 배열을 자동 합성하거나 전곡 스타일 시퀀스를 재생하지 않는다. 조합 후보는 실제 비교 영상과 구간 프로젝트로 선택권을 제공한다.

```json
{"profile":"noir-groove","genre":["로파이 재즈"],
 "recommendations":[
   {"profile":"noir-groove","reason":"실제 곡의 편성과 어두운 여백을 연결한 이유"},
   {"profile":"paper-ballad","reason":"같은 음악을 종이·잉크·구절의 호흡으로 해석한 이유"},
   {"profile":"deep-space","reason":"잔향과 긴 프레이즈를 공간과 빛으로 해석한 이유"}
 ]}
```

실제 제작에서는 예시 이유를 그대로 쓰지 않고 해당 곡의 근거로 바꾼다. 장르가 모호하면 불확실성을 적고 음악적 차이가 있는 후보를 제안한다. 페이지 단독 업로드의 수치/검색 기반 후보는 보조 추천이다. 브라우저 안에 별도 LLM 장르/가사 분석기를 설치했다고 소개하지 않는다.

### 열기

```bash
"$JIZURA_PY" "$JIZURA_SKILL/scripts/studio.py" \
  --out "/절대/새-Studio-세션" \
  --audio "/절대/음악.wav" \
  --project "/절대/project.jizura.json" \
  --direction "/절대/direction.json" \
  --analysis "/절대/analysis.json"
```

`--out`만 필수다. 기존 프로젝트가 없으면 `--project`를 생략한다. 음원만 연결하면 가짜 가사 대신 무자막 그래픽에서 출발한다. 기존 프로젝트를 불러오면 먼저 기존 설정을 유지한다. 표준 출력의 준비 JSON에 있는 `url`을 브라우저/패널로 연다. 서버는 127.0.0.1 전용이고 랜덤 포트와 세션 토큰을 쓴다. 사용자 요청 없이 외부에 게시하거나 네트워크 전체에 열지 않는다.

`ego-browser` 요청이면 같은 TaskSpace에서 페이지를 열어 실제 프리뷰와 설정을 확인한다. 사용자에게 보여 줄 결과 페이지는 완료 때 keep하고 조사 페이지는 닫는다. 외부 JIZURA 사이트의 표시 버전과 고정 로컬 버전을 혼동하지 않는다.

### 선택과 편집

- **추천·빠른 설정**: 세 후보와 이유를 비교한다. 추천을 누르면 같은 음원의 실제 프레임이 바뀐다. 전체 스타일, 테마/분위기, 7개 효과 강도와 화면비·해상도·fps·음원 포함·합성 배경·가운데 비우기를 조절한다.
- **JIZURA 전체 편집기**: 공식 스타일·연출·기법·내보내기 탭을 그대로 사용한다. 가사/LRC와 탭 싱크(Space/Tab), 줄/컷 시각, 컷별 layout/enter/hold/exit/decor/treat/bg/cam/trans, 파트 ON/OFF와 잠금, 색·서체·업로드 폰트, 프레임 홀드·HUD·숫자 숨김, 범위 내보내기, PNG/투명 전후경/LRC/AE를 다룬다.
- 테마는 다음 자동 구성의 범위다. 테마만 선택하고 현재 영상에 적용됐다고 하지 않는다. 재구성 후 실제 plan과 컷을 확인한다. 추천 변경에서도 원문·고정 시각·컷 분절·사용자 잠금을 보존한다.
- 음악이 바뀌면 이전 곡의 가사 시각/연출을 검수 완료로 승계하지 않는다. 원음 SHA와 directing 스코어가 다르면 적용을 중단해 미적용 상태를 보존한다. 가사/타이밍 변경은 검수 전 상태로 기록한다.
- **설정 저장**은 현재 native 상태를 새 `revision-...`에 저장한다. 원본과 이전 revision은 덮어쓰지 않는다. 예전 directing 스코어로 사용자의 커스텀을 되돌리지 않는다. 성공적으로 bake된 스코어는 lockedCuts와 provenance로 남기고, 실패한 스코어를 조용히 버리지 않는다.

### 원음·폰트와 재열기

브라우저에서 새 음원을 고르면 서버가 자기 세션 `inputs`에 복사하고 해시를 연결한다. 원본은 수정하지 않는다. 네이티브 프로젝트 JSON 자체에는 음원·폰트 바이너리가 포함되지 않으므로 세션 폴더와 함께 보관한다.

업로드 폰트는 저장할 때 native IndexedDB에서 추출해 실제 폰트 자산으로 복사하고 `fontAssets`에 경로·해시·key를 기록한다. 새 포트/세션에서는 이 자산을 `J.saveFontData → J.restoreUserFonts`로 복원한다. 로컬 CLI 렌더도 같은 자산을 확인해 복원한다. 폰트 원본이 없거나 해시가 다르면 대체 글꼴로 완료됐다고 하지 않고 재업로드를 안내한다. 폰트 파일을 옮겼으면 fontAssets의 실제 경로를 맞춘다.

저장한 설정을 다시 열 때는 새 세션 폴더를 쓰고 `--project`에 실제 저장된 절대 경로를 지정한다. 원음도 `project.source.path`의 검증된 파일을 연결한다. 포트가 같아야 폰트가 유지된다고 가정하지 않는다.

### 제작과 검수

페이지의 MP4 버튼은 공식 브라우저 출력이다. PNG/투명 전후경/AE 및 대형 영상의 직접 파일 저장은 전체 편집기의 실제 버튼을 사용한다. 브라우저 파일 선택 권한이 필요한 버튼은 사용자가 직접 다룬다. After Effects용 JSON 출력과 실제 AE 애플리케이션 검증은 구분한다.

채팅에서 이어 제작할 때 `/api/status`의 `lastProject` 또는 저장 응답 경로를 읽어 해당 프로젝트를 `render-jizura.mjs --project`에 그대로 사용한다. 이전 direction으로 다시 build하여 사용자 커스텀을 덮어쓰지 않는다. 원음 전체/여러 곡의 최종 납품은 assemble로 마무리한다. 의도적 음원 제외나 부분 범위 출력은 원음 전체 본편으로 보고하지 않는다.

서버 종료는 실행 세션에서 Ctrl+C 또는 토큰으로 인증된 `/api/stop`을 사용한다. 서버가 멈추면 페이지의 저장/음원 불러오기도 중지되지만 저장 파일은 남는다. 사용자가 계속 설정할 결과 페이지를 남길 때는 서버를 함께 유지한다.

### 변경 후 검사

```bash
"$JIZURA_PY" -B "$JIZURA_SKILL/scripts/test_project.py"
"$JIZURA_PY" -B "$JIZURA_SKILL/scripts/test_studio.py"
node "$JIZURA_SKILL/assets/studio/studio.test.mjs"
node "$JIZURA_SKILL/scripts/directing.test.mjs"
node "$JIZURA_SKILL/scripts/render-jizura.test.mjs"
```

실제 브라우저에서도 음원 연결→여러 후보 선택→수동 스타일/효과 변경→공식 세부 편집→저장→새 세션 재열기→짧은 MP4를 확인한다. 업로드 폰트가 있으면 다른 포트와 깨끗한 렌더 프로필에서 복원되는지 검사한다. 결과를 실제 청취·정밀 가창 싱크 검수로 확대하지 않는다.

공식 편집기 안에서 세션 도중 다른 프로젝트를 직접 열면, 그 프로젝트의 폰트가 현재 세션에 등록되어 있지 않을 수 있다. 이때 누락 안내를 따르고 폰트를 다시 올리거나 `--project`로 새 Studio 세션을 열어 manifest 자산을 복원한다. 임의 파일 경로를 브라우저 API에 넣어 이 경계를 우회하지 않는다.
