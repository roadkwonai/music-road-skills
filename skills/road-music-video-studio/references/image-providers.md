# 호스트별 이미지 생성

같은 프롬프트·역할·참조 계보를 유지하면서 **현재 작업 중인 호스트의 실제 이미지 기능**을 사용한다. 이 문서는 다른 제작 문서에 나오는 `image_gen`이라는 ChatGPT 경로를 Antigravity에서 어떻게 연결할지 정한다.

| 실행 환경 | 생성 경로 | 계획 helper의 `--host` |
| --- | --- | --- |
| ChatGPT / Codex | 세션에 제공된 내장 `image_gen` | `codex` |
| Antigravity App / IDE | 현재 세션의 Nano Banana 네이티브 이미지 기능 | `antigravity` |
| Antigravity CLI | 해당 버전의 Nano Banana 이미지 도구 또는 내장 `image-generator` 경로 | `antigravity-cli` |

## 실행 계약

1. 먼저 호스트에서 이미지 생성 기능과 참조 이미지 입력을 실제 사용할 수 있는지 확인한다. 추론용 모델 선택을 이미지 모델 선택으로 해석하지 않는다.
2. ChatGPT에서는 `image_gen`으로 생성한다. Antigravity에서는 현재 제공되는 이미지 생성 도구/내장 경로를 사용한다. 세션이 제공하지 않은 명령·모델 ID·파라미터를 만들지 않는다.
3. 같은 아티스트/공간을 유지해야 하면 통과한 이미지를 해당 도구의 참조 인자로 넣는다. 역할별 prompt와 참조 파일 SHA를 기록한다.
4. 반환된 **실제 파일**을 열어 화면비·인물 일관성·글자·배경·자막 여백을 확인하고 프로젝트 `assets/`에 저장한다. 케이스가 필요한 프리셋은 실제 alpha 투명도 요구도 그대로 검사한다. 호스트가 필요한 형식/편집을 지원하지 않으면 누락을 보고하고 지원하는 방향을 제안한다.
5. 기존 `images.json`/direction media 계약에 파일 경로를 전달하고 HTML에 게시한다. 생성 도구 차이 때문에 곡의 시계·캐스팅·구도·비율·가사·표시 선택을 바꾸지 않는다.

`imageGeneration.requiredTool=antigravity-native`는 **호스트 기능을 사용하라는 계획 값**이다. 실제 도구명이 아니다. 실제 생성 도구·모델명은 결과의 metadata로 확인하며, 모델명이 반환되지 않으면 `null`로 남긴다.

```json
{
  "host": "antigravity",
  "generator": "actual-host-tool-or-image-generator",
  "model": null,
  "promptId": "photoA",
  "file": "assets/photo-a.png",
  "sha256": "실제 파일에서 계산",
  "referenceFiles": [],
  "status": "generated-and-visually-reviewed"
}
```

위 JSON은 생성 기록 예시다. 별도의 렌더 입력 스키마를 대체하지 않는다. 도구가 없으면 이미지 단계의 미완료 상태를 유지하며 유료 API·다른 계정·과거 데모로 자동 전환하지 않는다. 명시적인 API 모델 사용 요청은 그 요청 범위에서 별도 처리한다. HTML이나 CLI가 호스트 이미지 생성 기능 자체를 내장한 것으로 설명하지 않는다.

## 공식 근거

2026-10-18 확인. Antigravity는 추가 이미지 모델을 추론 모델과 구분한다. CLI 이미지 경로는 버전과 표면에 따라 다를 수 있으므로 현재 기능을 확인한다. [Models](https://www.antigravity.google/docs/models/#additional-models) · [CLI 변경 기록](https://www.antigravity.google/docs/changelog?tab=cli) · [도구 목록](https://www.antigravity.google/docs/hooks/)

## 유료 모델 기본 차단

Showreel MV의 기본은 `allowPaidModels:false`다. image_gen/Nano Banana 기본 경로에서 실패하거나 더 높은 품질을 원한다는 이유로 `gpt-image-2.5` 같은 별도 과금 API로 전환하지 않는다. 사용자가 해당 작업에 별도 유료 사용을 긍정적으로 명시한 경우에만 예외를 기록한다. 모델명 비교·인용·금지 문구는 승인이 아니다.
