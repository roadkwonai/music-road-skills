# 가사 가독성·싱크 근거 검수

가사가 있는 제작·수정에는 이 절차를 적용한다. 자동 후보 검사 → 실제 MP4 프레임 검수 → 문제 행 수정 → 새 출력 재검수를 기본 흐름으로 삼는다. 무자막 영상에는 가사 검사를 강제하지 않는다.

## 자동 검사와 실제 판정

`render-jizura.mjs --inspect`는 실제 native plan으로 `readability.json`을 만든다. `--render`는 cueMap이 있는 경우 내보낸 **실제 MP4**에서도 `readability-final/`의 프레임·후보 JSON·HTML을 자동 생성한다. `project.py compose`와 `assemble`도 최종 MP4 생성 뒤 같은 검수를 자동 호출한다. 조합본은 `<최종.mp4>.readability/`, 여러 곡은 그 아래 `track-N/`으로 곡별 원음과 최종 영상의 시작 시각을 구분한다. assemble 입력의 plan이 영상 폴더 밖에 있으면 track.plan에 실제 절대 경로를 준다. cueMap이 없는 공식 프로젝트는 원문 행·시계 대응을 먼저 복구하며, 검사가 생략된 상태를 통과로 표시하지 않는다.

자동 검사는 원문/표시 시계 불일치와 다음 **위험 후보**를 찾는다.

- 큰 단어 강조와 읽기 이동·줌의 조합: 화면 끝 잘림, 행간 간섭 가능성.
- 긴 영어 구절의 center/splitScreen 배치: 구절 중간 줄바꿈·반전 경계의 간섭 가능성.
- 짧은 행의 입구 잔상·색 분리·슬라이스·타이핑: 실제 읽을 시간 손실 가능성.
- 이전 가사를 합성하는 전환·모프: 이전 문구가 새 문구를 가릴 가능성. 전환 시작·중간·끝도 추출한다.
- 끝부분의 조기 소멸·간격: 가창 end, 화면 hold, 다음 행 진입을 혼동하지 않는다.

공식 renderer에 외부로 노출된 최종 글자 경계 측정 API가 없으므로 후보를 픽셀 기반 확정 오류라고 부르지 않는다. `riskFlags: []`도 가독성 통과가 아니다. 검사기는 항상 `needs-visual-review`, 이미지 자료는 `visualReview: pending`, 청취는 `listeningReviewed: false`에서 시작한다. 사진 생성만으로 이 상태를 승격하지 않는다.

각 표시 행의 등장 직후·중간·끝과 **표시 종료 뒤의 한 프레임·짧은 꼬리**를 자동 추출하고, 위험 효과의 시각도 추가한다. 종료 뒤에는 다음 가사/간주로 정상 전환됐는지, 이전 잔상이 새 문구를 가리는지 구분한다. 같은 sourceLine의 승인된 이어 표시는 잔상 오류로 단정하지 않는다. 짧은 행은 샘플을 표시 구간 안으로 제한한다. `sourceLine`이 같은 이어 표시 행도 각각 검사해 마지막 음에서 사라지지 않는지 확인한다. 프레임의 원음 시각과 영상 내부 시각을 구분한다.

## 합성한 최종 MP4 검사

native 구간 검사는 최종 합성 검사를 대신하지 않는다. 자동 생성된 자료가 있으면 먼저 재사용하며, 이전 제작본이나 검수 도구만 다시 실행할 때는 아래 명령을 쓴다. 단일 완성본은 원음 0초 기준 프로젝트·actual plan을, 조합본은 **실제 사용한** compose manifest를 전달한다. 원음 시작이 다른 부분 영상은 `--source-start`에 실제 offset을 준다.

```bash
node "$JIZURA_SKILL/scripts/readability.mjs" \
  --project "/절대/project.jizura.json" --plan "/절대/native-render/plan.json" \
  --video "/절대/최종.mp4" --out "/절대/새-가사검수"

node "$JIZURA_SKILL/scripts/readability.mjs" \
  --manifest "/절대/composition.json" --video "/절대/최종-조합.mp4" \
  --out "/절대/새-조합-가사검수"
```

`--video`가 없으면 `--out`은 새 JSON 파일이며 plan 후보만 출력한다. 영상이 있으면 `--out`은 새 디렉터리다. 기존 출력·원곡은 덮어쓰지 않는다. `review.json`은 실제 MP4 SHA·원음 SHA·각 프레임 SHA·원음/영상 시각을 묶는다. 여러 곡을 수동 재검수할 때는 원곡 기준 `--source-start`와 별개로 `--video-start`에 최종 플레이리스트에서 그 곡이 시작하는 시각을 준다. `review.html`은 이 자료를 보는 보조 시트이며 공통 HTML 제작실이나 렌더 엔진을 대체하지 않는다. 프레임을 공통 제작실에 올릴 때는 해당 완성본과 같은 원음 SHA로 게시한다.

Codex는 생성한 프레임을 실제로 열어 모든 원문 행의 누락·잘림·줄바꿈·대비·잔상을 판정한다. 위험 후보는 개별 큰 프레임과 효과 전후를 추가 확인한다. 프레임 사이 가림이 의심되면 해당 짧은 구간을 더 촘촘하게 추출한다. 표본 검수를 전 프레임 검수라고 하지 않는다.

재생 검수에는 시작·끝, 재생 배율, seek·buffering·error와 가능하면 dropped frame을 기록한다. 초기 로딩과 재생 도중 멈춤을 구분한다. 브라우저에서 소리가 재생됐다는 사실은 Codex가 들었다는 증거가 아니다. 직접 청취가 불가능하면 초기에 알리고, 로컬 ASR·파형·원문 근거와 시각 검수를 계속하되 청취·음절 싱크 확정은 미검수로 남긴다.

## 문제 행만 고치기

원문·가창 시각·sourceLine·승인 상태를 먼저 보존한다. 배치와 효과 문제를 가사 시각 이동으로 숨기지 않는다.

- **잘림/행간:** 해당 lockedCut의 강조 크기·이동 폭을 낮추거나 더 넓은 여백의 native 배치로 바꾼다. fitSize가 적용되면 sx 변경만으로 폭이 줄지 않을 수 있다. 최대 확대·pan·효과 시점에서 다시 본다.
- **영어 구절:** 원문 단어·쉼표를 유지하며 한 줄 또는 의미 단위로 읽히는 배치를 고른다. `Cross the / line, cross / the line`처럼 반복 구절 경계를 깨는 분절을 피한다. 공식 배치가 다시 자동 줄바꿈한다면 그 한계를 확인하고, 원문에 임의 개행을 넣거나 강제로 컷을 나누어 싱크를 만들지 않는다.
- **잔상:** 짧은 행의 입구 echo/chroma/slice 등 본문 판독을 방해하는 이벤트부터 줄인다. 스타일의 지연 색 분리 패스는 `enabled.fx.chroma:false`나 `echoFrames` 제거 뒤에도 `fx.chroma` 값으로 남을 수 있으므로 실제 입구 프레임을 확인해 필요한 프로젝트에서 낮춘다. 가창 끝까지 읽혀야 하는 짧은 행은 lockedCut의 `exit`·`outDur`도 확인한다. 배경·비트 움직임과 곡의 강약은 유지한다. 화려한 스타일의 모든 효과를 일괄 제거하지 않는다.
- **긴 후렴:** 실제로 반복된 동일 문장을 이어 표시할 때 sourceLine과 원문을 보존하고, 논리 가사 행과 렌더 표시 행 수를 따로 센다. 반복 근거 없이 새 문장을 추가하지 않는다.

잠금이 있는 프로젝트는 상위 override뿐 아니라 **실제 적용되는 lockedCuts와 재열기 후 plan**을 수정·확인한다. 연출 변경만 한 경우 `lyrics/timing/cutTime`과 cue 보호 필드가 같아야 한다. 실제 싱크를 고칠 때는 옛 시각·새 시각·새 근거를 기록하고, 원음과 연결된 검수 상태를 다시 평가한다.

문제가 있는 구간만 새 경로로 렌더하고 원음을 한 번 넣어 재합성한다. native actualExportSpan이 시간상 덮더라도 프레임 반올림으로 한 프레임이 부족할 수 있다. 필요한 sourceFrameEnd와 실제 프레임 수를 대조하고, 부족하면 다음 컷을 여유분으로 포함해 그 구간만 다시 내보낸 뒤 최종 trim 경계는 유지한다. 간주가 여러 native 행으로 나뉘므로 여유 범위를 마지막 가사 행 번호+1로 고정하지 말고 실제 plan에서 목표 end 뒤까지 덮는 행을 고른다. 첫 구간의 0초와 마지막 간주 끝도 포함한다. source 분석과 probe의 미세한 duration 반올림 차이는 manifest의 공통 end로 명시하며 가창 시계를 이동하지 않는다.

수정 후 새 최종 MP4로 다시 검사한다. 자동 생성된 `decision-template.json`을 복사해 `visual-review.json`을 작성한다. Codex가 실제 프레임을 보고 검수자·행별 발견/수정 근거와 각 프레임의 `pass/issue/pending`을 기록한다. 검수하지 않은 프레임을 일괄 pass로 채우지 않는다. 다음 명령은 현재 MP4·원음·모든 참조 프레임 SHA와 누락/미해결 판정을 확인한다.

```bash
node "$JIZURA_SKILL/scripts/readability.mjs" \
  --review "/절대/가사검수/review.json" --decision "/절대/visual-review.json" \
  --manifest "/절대/composition.json" --out "/절대/새-시각검수-판정.json"
```

단일 프로젝트는 `--manifest` 대신 원래 `--project`·`--plan`과 해당 시각 offset을 다시 전달한다. 판정기는 이 원래 입력에서 전체 기대 프레임을 재계산해 review 파일 자체의 일부 누락도 확인하며, `project.source.path` 또는 manifest.audio의 현재 원음 SHA도 대조한다. 원음 경로가 없어 다시 검증할 수 없으면 시각 준비 완료로 승격하지 않는다.

파일 생성의 `ok:true`와 가독성 판정은 별개다. native/compose/assemble은 검수 전 `visualReady:false`를 반환한다. 모든 대상 프레임을 확인하고 현재 해시와 일치하는 판정이 통과한 경우에만 시각 검수 `visualReady:true`를 근거로 쓴다. 이 값은 가창 싱크·청취 확정이 아니다. 추정 싱크 허용 여부와 미청취 상태는 따로 남기며 자동으로 승격하지 않는다. 다른 MP4나 이전 프레임의 판정을 새 결과에 승계하지 않는다. 최종 납품은 MP4 + 원문/cue/SRT + native/manifest + 자동 후보·프레임·시각 판정 + 싱크 근거를 묶는다.

## 확정·자동 정렬·추정 구분

정규화된 상태는 검수 JSON의 행별 `timing.status`에 둔다. 원래 `timingStatus`와 `timingEvidence`는 함께 보존한다.

새 cue에는 `aligned-draft` 또는 `estimated`처럼 상태를 명시하고 방법·실패 이유는 `timingEvidence`에 기록한다. `estimated-free-asr-assisted`·`estimated-forced-dtw-low-confidence`처럼 추정을 명시한 기존 이름도 추정으로 유지하며, 도구명이 포함됐다는 이유로 자동 정렬 초안으로 승격하지 않는다. 이전 제작의 `original-text-forced-dtw-estimated-unreviewed`는 자동 정렬 초안을 뜻했던 호환 이름으로만 처리한다.

| 상태 | 의미 |
| --- | --- |
| `confirmed` | 현재 원음·원문·시각에 묶인 직접 청취 또는 사용자의 확정 근거가 있는 행 |
| `aligned-draft` | ASR/forced-DTW 등 도구의 자동 정렬 초안. 원문 고정 성공·높은 확률·비트 일치도는 청취 확정이 아님 |
| `estimated` | 근거가 부족한 시각을 편집상 추정 배치. 사용자가 표시를 승인해도 가창 시각 확정과 다름 |
| `unreviewed` | 출처/검수 근거가 없거나 현재 원음·원문·시각과 맞지 않는 기존 확인 기록 |

확정 기록은 cue에 다음처럼 둔다. 이 필드는 개인 제작 계층의 메타데이터이며 공식 JIZURA의 정렬 기능이 아니다.

```json
{
  "start": 12.3, "end": 14.8, "text": "실제 원문", "sourceLine": 4,
  "timingStatus": "user-confirmed",
  "timingReview": {
    "status": "confirmed", "method": "user-confirmed", "reviewer": "실제 검수자",
    "evidence": "현재 구간을 확인한 기록이나 사용자 확정 근거",
    "sourceSha256": "현재 원음의 실제 64자리 SHA-256",
    "textSha256": "text UTF-8 원문 전체의 실제 SHA-256",
    "start": 12.3, "end": 14.8
  }
}
```

`method`는 `manual-listening` 또는 `user-confirmed`다. 상태 이름만 바꾸거나 ASR 재실행만으로 confirmed를 만들지 않는다. 원음 SHA·text SHA·start/end 중 하나라도 달라지면 이전 확정 기록은 유효하지 않다. 가창 끝이 아니라 읽기 꼬리를 계산했다면 그 end까지 확정한 것으로 기록하지 않는다. `displayHoldUntil`은 화면 유지 시각이고 가창 끝과 별개다.

추정 행은 실제 문구를 미리 주지 않은 ASR, 앞뒤 확인된 가사, 다른 동일 구절의 음향·시각 근거로 재확인한다. 토큰이 청크 경계·한 시점에 몰린 강제 정렬은 실패 신호다. 원문 프롬프트 ASR의 반복 환각을 독립 증거로 세지 않으며, ASR 미인식만으로 음원에서 가사가 없다고 단정하지 않는다. 새 근거가 없으면 기존 승인 추정 구간을 유지하고 불확실성을 남긴다. 원가사 표시 승인 없이 행을 삭제하거나 다른 후렴 길이를 복사하지 않는다.
