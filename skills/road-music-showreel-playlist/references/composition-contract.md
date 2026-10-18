# 개방형 장면·이미지 계약

`native_project.py apply`는 입력/시계/파일 연결을 검증한다. 의미를 해석하거나 임의 모션명을 렌더하는 엔진이 아니다. `concept.md`의 후보 선택과 스타일 프레임을 바탕으로 Codex가 아래 계획과 실제 `REEL.scene`을 작성한다.

## composition.json

```json
{
  "schemaVersion": 1,
  "concept": "이 곡의 한 문장 생각과 전개",
  "tracks": [{
    "id": "track-001",
    "sourceSha256": "playlist.json의 원곡 SHA256",
    "scenes": [{
      "id": "s01",
      "startSeconds": 0,
      "endSeconds": 8,
      "lyricCueIds": ["1"],
      "meaning": "이 구절/음악 사건을 이 화면으로 해석한 이유",
      "subject": "화면의 주체",
      "action": "어떤 상태에서 무엇을 하여 어떻게 변하는가",
      "medium": "사진 조각 + Canvas 표면 등 자유로운 매체",
      "composition": "주체·시점·거리·깊이와 읽기 영역",
      "transition": "마지막 형태/시선을 다음 장면으로 잇는 방법",
      "assets": ["surface"]
    }]
  }]
}
```

- 시간은 **각 원곡 기준**이다. track id/hash는 준비 프로젝트의 playlist.json과 일치해야 한다. 장면은 선택한 원곡 범위를 빈틈·겹침 없이 덮고 id는 트랙 안에서 고유하다. 시각 예를 실제 음악에 복제하지 않는다.
- lyricCueIds는 해당 원곡 입력에 실제 존재하는 cue id다. 무가사/음악 해석 장면은 빈 배열과 실제 음악/사용자 근거를 meaning에 기록한다. 가사를 확보하지 못한 보컬 곡을 instrumental로 위장하지 않는다.
- medium/action/transition은 닫힌 enum이 아니다. ‘별·리본·타일’ 중 하나를 고르는 입력도 아니다. 이 필드를 작성한 사실이 실제 구현이나 의미 적합성의 증거가 되지는 않는다.
- apply는 선택 컷과 교집합을 만들고 실제 PCM 트랙 offset으로 출력 시계에 옮긴다. resolved id는 `track-001.s01`, 출력 start/end와 원곡 sourceStart/sourceEnd, 잘리기 전 originStart/originEnd를 보존한다. 마지막 한 프레임 미만 패딩만 마지막 장면에 포함한다.

## media.json

```json
{
  "schemaVersion": 1,
  "assets": [{
    "id": "surface",
    "path": "images/surface.png",
    "roles": ["scene-object", "fold-surface"],
    "requireAlpha": true,
    "source": {"kind":"image_gen", "tool":"image_gen", "prompt":"실제로 사용한 프롬프트"}
  }]
}
```

path는 manifest 상대 또는 절대 로컬 PNG/JPEG/WebP다. apply가 실제 decode/치수/해시, 요청한 alpha와 참조 id를 확인하고 assets/media/로 복사한다. 역할 이름은 자유롭고 source.kind는 image_gen/provided/reuse를 구분한다. 이미지 생성에는 실제 프롬프트와 도구를 남기며, 제출 기록의 복사를 도구 호출의 독립 인증으로 부르지 않는다. 더 자세한 실제 생성 근거/참조/수정 내역은 별도 ledger로 함께 보관한다.

씬의 assets에 사용 id를 적는다. 선언되지 않은 이미지 참조와 누락 파일은 실패다. roles나 REEL.img 호출만으로 mask/texture가 구현됐다고 하지 말고 실제 프레임으로 확인한다. [이미지 역할 설계](image-direction.md)를 따른다.

첫 카드를 선택한 계획은 최상위 `"opening":{"thumbnailId":"cover","seconds":0.5}`를 추가한다. media의 실제 id를 참조하고 새 음악/무음 프리롤을 만들지 않는다. 원곡 중간 컷에서는 다시 표시하지 않는다. 독립 썸네일 파일의 생성/납품과 영상 첫 카드 삽입을 구분한다.

## 저자 코드와 기본 Showreel

입력은 `FILM_INPUT`, 정규화된 계획/미디어는 `FILM_PLAN`, 디코드된 이미지는 `FILM_IMAGES`에 있다. 실제 화면은 `reel/scenes.js`에서 native API로 작성한다. helper가 빈 씬을 완성된 템플릿으로 채우지 않는다.

```js
const scene = FILM_PLAN.scenes.find(s => s.id === 'track-001.s01');
REEL.scene({
  id: scene.id,
  start: REEL.cue('scene.' + scene.id) - 0.5 / REEL.fps,
  end: REEL.cue('scene.' + scene.id + '.end') - 0.5 / REEL.fps,
  async setup(el) {
    await FILM_MEDIA_READY;
    this.image = FILM_IMAGES.surface;
    // 이 장면의 DOM/Canvas/마스크/기하/물리 자료를 준비한다.
  },
  render(lt, ctx) {
    const sourceTime = scene.sourceStartSeconds + ctx.t - scene.startSeconds;
    const progress = (sourceTime - scene.originStartSeconds) /
      (scene.originEndSeconds - scene.originStartSeconds);
    // 콘셉트에 맞는 실제 draw/transform을 작성한다. progress만 계산하고 끝내지 않는다.
  }
});
```

이 코드는 연결 형식이며 완성 장면 예제가 아니다. scene 경계·하드 컷 반프레임과 원곡 절대 시계를 구분하고, UI/본문 가사를 scene마다 다시 만들지 않는다. 새 이미지/폰트의 픽셀을 setup에서 쓰기 전 decode를 기다린다. 여러 모듈/셰이더/3D를 쓰면 로컬 파일로 index에 연결하고 실제 등록 id와 계획 범위를 맞춘다.

## 기술·미술 증거

브라우저 검사 `qa/native-runtime.json`은 현재 렌더 입력의 파일 해시 맵과 실제 씬/자막/미디어/시크 검사다. 최종 전곡 전에는 같은 files 맵을 가진 `qa/creative-review.json`에 장면별 실제 판정과 proof 경로를 남긴다.

```json
{"schemaVersion":1,"files":{"reel/scenes.js":"현재 SHA256 등 전체 fingerprint"},
 "scenes":[{"id":"track-001.s01","decision":"keep","note":"직접 본 변화/의미/가독성 판단","evidence":["qa/실제-proof.png"]}],
 "limitations":["직접 청취 여부와 표본 검수 범위"]}
```

files는 `native_project.py fingerprint --project ...`의 `files` 또는 현재 runtime 보고서에서 가져온 **전체 맵**이다. 자동으로 all-keep를 만들어 통과시키지 않는다. fix/rebuild가 있거나 입력/코드/자산/폰트가 바뀌었으면 실제 수정·재검토한다. 이 맵은 신선도 검사이며 미적 판단·권한의 증거를 대신하지 않는다. `check`는 이와 별도로 동결 원곡·가사·PCM·mix·저장 미디어의 SHA/치수/alpha, captions JSON/SRT/FILM_INPUT 전문과 composition·FILM_PLAN·timeline binding을 다시 대조한다. runtime 보고서의 실제 등록 scene id/시각도 creative review와 정확히 같아야 한다.

check는 FILM_INPUT의 playlist/display/오디오/길이/규격/FFT를 저장 선택·실제 분석과 대조한다. FFT는 준비 mix 해시와 연결된다. FILM_PLAN의 실제 media/src/해시/alpha와 전체 장면·opening은 저장 media/composition과 같아야 한다. 새 fingerprint 기록으로 이 연결 검사를 대신하지 않는다.

저운동 경고만 있는 곡은 숫자나 보고서를 수정하지 않는다. 실제 final을 확인한 뒤 다음 선택 필드를 creative-review에 추가한다. issues는 현재 `qa/<name>-motion.json`의 전문 목록, 두 SHA는 해당 최종 보고서와 실제 master의 해시다.

```json
{"motionReview":{"issues":["현재 실제 저운동 경고 전문"],"reason":"이 음악에서 의도한 정착/여백과 검토 근거","evidence":["qa/실제-final-strip.png"],"motionReportSha256":"실제 final motion JSON SHA","finalOutputSha256":"실제 final master SHA"}}
```

render는 입력·출력·QA 서명을 `qa/<name>-render.json`에 저장하고 검토 필요 상태를 반환한다. 실제 최종 시트/원음 proof를 본 뒤 `native_project.py finalize --project ... --name ...`로 같은 산출물을 재검증한다. 기존 final을 덮거나 렌더를 반복할 필요는 없다. 섬광과 미분류 기술 결함은 motionReview로 우회할 수 없다. 검토된 경고도 최종 응답에 그대로 공개된다.

원곡/가사/PCM과정규화scene시계는전체정밀도로보존한다. 설치된upstream timeline.py가scene/cue를소수3자리밀리초형식으로내보내는경우,그저장형식의예상round값과엄격히대조한다. 한프레임미만끝패딩을타임라인비교때문에늘리거나원음시계를반올림하지않는다.
