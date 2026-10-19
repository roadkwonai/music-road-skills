# YuE2 고급 활용 프롬프트

![요청·실제 제작 단계·결과 기록을 연결하는 운영 흐름 예시](media/production-flow.svg)


[YuE 제작 가이드](yue-prompt-guide.md) · [YuE CLI 워크플로](yue-cli-workflow.md) · [CCM 고급 활용](ccm-advanced.md) · [고정 공식·MLX 원문](vendor/yue2/README.md)

이 문서는 Road Music에서 YuE2를 주 엔진으로 쓸 때의 고급 요청문 모음이다. Apple Silicon의 기본 엔진 ID는 `yue-mlx`이며, Windows NVIDIA 경로는 `yue`다. 두 엔진의 설치·런타임을 섞지 않는다. `schema`와 `yue:capabilities`가 실제 지원 필드의 최종 기준이고, 예시는 설치·생성 권한을 뜻하지 않는다.

## 먼저 지킬 경계

- `mode:"plan"`은 **음원이 아니라 ABC 계획 작업 산출물**을 만들며, GPU 계획 추론을 수행한다. 입력만 무추론으로 검토할 때는 `song:prepare`를 쓴다.
- 새 가사·style·장르를 바꾸면 새 `song:prepare` 뒤 `song:generate`를 사용한다. 선율을 보존하려면 검증한 `abc`를 그 새 생성 입력에 넣는다.
- `song:render`는 기존 곡의 metadata 가사·style을 재사용하고, 실제 `dir`과 `abc`로 **악보만 바꾼 전체 새 녹음**을 만든다. 가사·style 변경 도구가 아니다.
- `targetSeconds`는 기록·비교용 목표이며 실제 길이를 제어하지 않는다. 결과 파일 길이, 자연 EOS, `truncated.abc`, `truncated.semantic`을 각각 확인한다.
- `instrumental:true`는 보컬 없는 의도다. Vocal 성부가 비거나 보컬 누출이 없다는 보증은 아니다.
- `cfgScale`은 semantic AR 조건 유도, `odeSteps`는 acoustic ODE 계산량에 관계한다. 높은 수치가 더 좋은 결과를 보장하지 않는다.

## 공통 명령 순서

새 곡은 `yue:capabilities → song:prepare → song:generate → job:wait → song:detail` 순서로 확인한다. 기존 작업 산출물의 단계 재실행은 상태 확인 후 `song:replay`를 쓰며, `plan`은 저장된 ABC 뒤 semantic부터, `synthesize`는 ODE 관련 값만, `decode`는 VAE 관련 값만 바꿀 수 있다. 실제 허용 목록은 매번 `yue:capabilities`를 우선한다.

| 사례 | 공개 명령 순서 | 예측 가능한 변화 | 보장하지 않는 것 |
| --- | --- | --- | --- |
| 1, 4, 5, 7, 8 | `yue:capabilities → song:prepare → song:generate → job:wait → song:detail` | 새 요청의 final 입력·실제 파일·길이 기록 | 특정 길이·가창·품질 |
| 2, 9 | `yue:capabilities → song:prepare → song:generate(mode:plan) → job:wait → score:inspect` | ABC 계획과 `truncated.abc` 기록 | semantic·audio 결과, 음원 품질 |
| 3 | `score:inspect → yue:capabilities → song:prepare → song:generate → job:wait` | 코드 없는 외부 ABC 조건 확인 | 자동 코드 제거·악기 분리 |
| 6 | `score:inspect → score:compare → song:detail → song:render → job:wait` | 기존 metadata를 유지한 새 전체 녹음 | 가사·style 변경, 부분 파형 수정 |
| 10 | `yue:capabilities → song:detail → song:replay(plan) → job:wait → production:tasks` | 저장 ABC 뒤 semantic CFG 한 요소 비교 | 새 ABC 작곡 |
| 11 | `yue:capabilities → song:detail → song:replay(synthesize) → job:wait → production:tasks` | acoustic ODE 한 요소의 비용 비교 | CFG 변경·품질 향상 |
| 12 | `song:detail → score:inspect → production:tasks → production:files → production:dashboard` | 확인 근거와 중단 사유 | 자동 청취 품질 판정 |

## 16개 고급 옵션의 단계·기본값·CCM 활용

다음은 2026-10-20에 대조한 고정판/MLX와 공개 capabilities의 기본값이다. 특정 CCM의 품질 최적값을 뜻하지 않는다. 값을 생략한 기준 설정을 먼저 확인한 뒤, 적용할 한 요소만 비교한다.

| 단계 | 공개 advanced 키 | 기본값 | 무엇을 바꾸고 무엇을 보장하지 않나 |
| --- | --- | --- | --- |
| semantic AR | temperature | 1.0 | 음악 토큰 선택의 무작위성. 0은 greedy이며 더 자연스러운 가창의 보장이 아님 |
| semantic AR | topP | 0.95 | 누적 확률 후보 범위. temperature와 동시에 바꾸면 원인 비교가 어려움 |
| semantic AR | topK | 100 | 후보 개수. 예를 들어80과100을 비교할 때 나머지는 기준선 유지 |
| semantic AR | repetitionPenalty | 1.2 | 최근 토큰 반복 억제. 가사에 의도한 후렴 반복을 정확히 조절하는 키가 아님 |
| semantic AR | penaltyWindow | 50 | 반복 억제의 참조 토큰 창. 초·마디·가사 줄 수가 아님 |
| semantic AR | minTokens | 200 | 종료 허용 전 최소 생성 예산. 최소 재생 초나 완창 보장이 아님 |
| semantic AR | maxTokens | 9000 | 최대 생성 예산. 한도 도달은 semantic 잘림이 될 수 있으며 목표 길이 제어가 아님 |
| ABC 계획 AR | abcTemperature | 0.7 | 새로 만드는 기호 계획의 무작위성. 외부 ABC를 제공하면 planner를 우회하므로 비교 효과 없음 |
| ABC 계획 AR | abcTopP | 0.9 | 새 ABC 후보의 누적 확률 범위. 제공 악보를 보정하는 값이 아님 |
| ABC 계획 AR | abcTopK | 30 | 새 ABC 계획 후보 수. 악보의 음표·성부 개수를 정하지 않음 |
| ABC 계획 AR | abcRepetitionPenalty | 1.005 | 기호 토큰 반복 억제. 회중 후렴의 적절한 재현 여부는 별도 검수 |
| ABC 계획 AR | abcPenaltyWindow | 100 | 기호 계획 반복 참조 창. semantic 창과 구분 |
| ABC 계획 AR | abcMinTokens | 32 | ABC 계획의 최소 예산. 최소 마디 수나 악보 완성 보장이 아님 |
| ABC 계획 AR | abcMaxTokens | 4096 | ABC 계획 최대 예산. 한도 도달/계획 잘림 확인 필요 |
| semantic 조건 유도 | cfgScale | full/melody1.0, off1.01 | semantic 조건부/무조건부 logits 결합. ABC계획·acoustic ODE 값이 아니며0은 무조건부 쪽 실험 |
| acoustic NAR ODE | odeSteps | 32 midpoint | 음원 합성 계산량. 32는 midpoint 평가64회이며 높은값의 품질 우위는 보장하지 않음 |

`parts.strong` 단독은 CFG를 바꾸지 않는다. 현재 호환 구현은 `parts.strict`와 `parts.strong`이 둘 다 true일 때1.5를 제안하고, 명시한 `advanced.cfgScale`가 최종 우선한다. 제한된 편성과 샘플링을 비교할 때 숨은 CFG 변경을 섞지 않도록 effective를 확인한다.

### 컨텍스트·입력 예산을 읽는 법

컨텍스트24,576은 가사 문자 수가 아니다. 각 단계의 입력 prefix와 생성 예산을 합쳐 초과 여부를 런타임 tokenizer로 검증한다. `song:prepare`의 `validation.context`가 requires-runtime-tokenizer이면 아직 토큰 길이를 실제로 검증한 것이 아니다. minTokens≤maxTokens, abcMinTokens≤abcMaxTokens를 만족시키고 최대 예산을 모두 크게 올리지 않는다. ABC/semantic truncation은 playable 파일이 있다는 이유로 무시하지 않는다.

### 저장 단계를 재사용할 때 바꿀 수 있는 것

| MLX replay stage | 재사용하는 것 | 바꿀 수 있는 공개 advanced | 필요한 판단 |
| --- | --- | --- | --- |
| plan | 무결성을 검증한 저장 plan과 원 ABC/prefix | semantic7개·cfgScale·odeSteps | 새 ABC 작곡이 아니며 가사/style/ABC는 변경 불가 |
| synthesize | 검증된 semantic/noise | odeSteps만 | cfgScale·semantic sampling을 넣지 않음 |
| decode | 검증된 acoustic latent | 없음 | 가사·편곡 수정이 아니며 허용된 VAE runtime만 capabilities로 확인 |

plan에는 온전한 plan_manifest.json, 뒤 단계에는 필요한 result.json과 실제 semantic/noise/latent·해시가 있어야 한다. 파일 일부만 남은 실패 결과를 재사용 가능하다고 추정하지 않는다. 필요한 단계 캐시는 편집 중에만 보관하고, 더 재사용하지 않는 완성 프로젝트는 공개 저장공간 미리보기로 최종본·최소 이력만 남길 수 있다.

### 계획 승인과 악보 수정의 서로 다른 음원화

같은 가사/style의 검증한 MLX plan을 이어 만들 때는 stage:plan 재사용을 검토한다. 새로운 요청을 만들면서 승인 ABC를 고정하려면 그 ABC를 mode:song 입력에 명시한다. ABC를 빼면 새 계획이 만들어질 수 있다. 가사나 style을 바꾸면 기존 metadata를 쓰는 song:render가 아니라 변경한 전체 입력의 새 prepare→generate를 쓴다. 기존 원문은 그대로 두고 악보만 바꿀 때만 render를 사용한다. 실제 빈 가사 프로젝트는 현재 render가 거부하므로 연주곡은 새 mode:song·instrumental:true·abc 또는 무결성이 있는 MLX plan 재사용을 사용한다.

## 1. MLX 기준선: 회중 워십

```prompt
Apple Silicon에서는 engine:"yue-mlx"를 유지해 한국어 회중 워십 1곡을 준비해줘.
승인 가사는 바꾸지 말고 cot:"full", mode:"song"을 사용해줘.
먼저 yue:capabilities와 song:prepare에서 final lyrics·style·effective·notes를 보여주고,
승인 뒤에만 생성해줘. targetSeconds는 목표값으로 기록하고 실제 길이·EOS·truncation은 완료 뒤 따로 보고해줘.
```

**왜 이 조합인가:** `full`은 새 멜로디·화성·노래의 기본 계획 경로다. 가사·편성·전개를 분리해 확인하므로 ACE의 caption 제한을 YuE에 잘못 적용하지 않는다. 회중 음역·실제 합창 규모는 보장하지 않는다.

## 2. 계획만 검토: 후렴 호흡 확인

```prompt
engine:"yue-mlx"로 승인 가사의 후렴 호흡을 먼저 검토해줘.
mode:"plan", cot:"full"으로 ABC 계획 작업 산출물만 만들고, 음원 파일을 만들었다고 말하지 마.
song:prepare의 notes와 결과 ABC의 Verse·Chorus 구조, truncated.abc를 보여줘.
semantic·audio는 이 계획 결과에서 생성되지 않았음을 기록하고, 계획을 승인한 뒤에는 같은 원문과 승인 ABC 내용을 abc로 명시한 별도 mode:"song" 요청을 준비해줘.
또는 원문·style이 동일하고 무결성이 검증된 MLX plan을 song:replay stage:"plan"으로 재사용해줘.
abc 없이 새 song 요청을 제출하면 새 계획이 만들어질 수 있음을 구분해줘.
```

**왜 이 조합인가:** 계획과 음원화를 분리하면 가사 밀도·형식을 비용이 큰 음원 생성 전에 검토할 수 있다. `mode:"plan"`도 실제 모델 계획 단계이므로 단순 정적 검사는 `song:prepare`로 한다. plan-only에서는 semantic·audio와 semantic truncation이 생성되지 않는다.

## 3. 코드 없는 멜로디 조건: 소그룹 워십

```prompt
engine:"yue-mlx"로 작은 소그룹 워십을 준비해줘.
cot:"melody"와 검증한 코드 없는 ABC만 사용하고, 제공 ABC는 score:inspect로 먼저 확인해줘.
piano accompaniment와 acoustic guitar response를 짧은 instrumentation 역할로 두고,
parts.instruments는 함께 넣지 마. 가사·계획·음원 결과는 별도 항목으로 기록해줘.
```

**왜 이 조합인가:** `melody`는 코드 없는 멜로디 조건과 함께 쓸 수 있지만, 코드를 자동 삭제하거나 악보를 고치지 않는다. 외부 ABC가 있으면 planner를 우회하므로 ABC 샘플링 변경 비교는 의미가 없다.

## 4. 묵상 연주: 악보 없는 직접 생성

```prompt
engine:"yue-mlx"로 새벽 묵상용 연주곡을 준비해줘.
instrumental:true, cot:"off"를 사용하고 가사와 abc는 제공하지 마.
piano accompaniment와 synth pads texture만 parts.instrumentation에 넣고,
song:prepare 결과를 검토한 뒤 승인 후 1곡만 생성해줘.
```

**왜 이 조합인가:** `off`는 악보 없는 직접 생성이다. `instrumental:true`는 보컬 없는 의도이며, 완전한 보컬 부재·정확한 길이·특정 질감은 생성 후 청취로 확인한다.

## 5. 한국어 특송: 가사 전달 우선 새 계획

```prompt
engine:"yue-mlx"로 한국어 특송을 준비해줘.
승인 가사의 지정 구절과 반복 위치만 유지하고, 선율 고정 요구가 없으므로 cot:"full"의 새 계획을 검토해줘.
과거 ABC는 입력으로 넣지 말고 song:prepare에서 새 계획의 전달본을 확인해줘.
생성 뒤에는 입력·새 score 출처·실제 길이·가사 전사 가능 여부·직접 청취 여부를 분리해 기록해줘.
```

**왜 이 조합인가:** 가사 전달이 우선이고 선율 고정 요구가 없을 때만 새 계획을 검토한다. 새 score의 해시가 달라졌다는 사실만으로 새 계획의 음악적 우위를 증명하지 않는다.

## 6. 기존 찬송 편곡: 선율 보존 ABC 렌더

```prompt
선택한 engine:"yue-mlx"에서 기존 찬송의 권한 있는 ABC 원본과 편곡 사본을 비교해줘.
melody:true, form:true, allowTempoChange:false를 유지하고 harmony 보존 여부는 별도로 정해줘.
가사와 style은 기존 곡 metadata를 그대로 유지한다는 조건에서만,
score:inspect·score:compare 뒤 실제 dir과 승인한 abc로 song:render 전체 새 녹음을 준비해줘.
```

**왜 이 조합인가:** `song:render`는 기존 가사·style을 바꾸지 않은 악보 편곡 전용이다. 부분 파형 수정이 아니며 같은 가창·음색·파형은 보장하지 않는다.

## 7. 정확한 64비트 seed 비교: 청년 워십

```prompt
engine:"yue-mlx" 청년 워십의 title·lyrics·style·cot·advanced를 고정해줘.
seed만 "9007199254740992"와 다른 정확한 십진 문자열 하나로 달리한 두 후보를 각각 song:prepare해줘.
생성 후 실제 파일 길이·EOS·truncation·소요시간을 표로 비교하고,
같은 seed의 완전 재현이나 품질 우위는 보장하지 마.
```

**왜 이 조합인가:** JavaScript 안전 정수보다 큰 YuE seed는 숫자가 아니라 정확한 십진 문자열이어야 한다. seed 외에 advanced나 가사를 바꾸면 결과 차이를 해석하기 어렵다.

## 8. semantic 한 요소: temperature 비교

```prompt
완주한 engine:"yue-mlx" 회중곡 기준선에서 lyrics·style·seed·cot·ABC·runtime을 고정해줘.
advanced.temperature 하나만 바꾼 후보를 별도로 song:prepare·생성하고,
semantic 계획·실제 길이·truncation·소요시간을 기준선과 비교해줘.
높은 temperature가 더 좋은 예배곡이라는 결론은 내리지 말고 순이득이 없으면 중단해줘.
```

**왜 이 조합인가:** `temperature`는 semantic 음악 토큰 후보 폭의 한 변수다. `topP`, `cfgScale`, `odeSteps`, seed를 동시에 바꾸지 않아야 비용·차이를 추적할 수 있다.

## 9. ABC 한 요소: 새 계획에서만 abcTemperature 비교

```prompt
engine:"yue-mlx" 찬송의 새 계획에서 lyrics·style·seed·cot을 고정하고,
외부 abc는 넣지 않은 채 advanced.abcTemperature 하나만 바꾼 mode:"plan" 후보를 준비해줘.
각 ABC를 score:inspect로 읽고 melody·harmony·form 차이와 truncated.abc를 기록해줘.
계획 차이를 음원 품질이나 실제 길이 보장으로 설명하지 마.
```

**왜 이 조합인가:** 외부 ABC를 주지 않은 새 planner 경로에서만 ABC 샘플링 값의 차이를 해석할 수 있다. `mode:"plan"`은 음원 생성 결과가 아니다.

## 10. 기존 artifact replay: semantic CFG 한 요소

```prompt
완주한 engine:"yue-mlx" 작업 산출물의 실제 dir을 song:detail로 확인해줘.
새 가사·style·ABC는 넣지 말고, yue:capabilities가 허용할 때만 song:replay stage:"plan"을 준비해줘.
저장된 ABC 뒤 semantic부터 시작하는 replay에서 cfgScale 하나만 바꾸고,
다른 advanced·runtime은 원본과 같게 유지해줘.
```

**왜 이 조합인가:** `cfgScale`은 semantic AR 조건 유도에 관한 값이다. plan replay는 새 ABC를 작곡하는 작업이 아니라 저장된 ABC를 바탕으로 다시 실행하는 작업이며, 허용 키는 실행 중 capabilities가 정한다.

## 11. 기존 artifact replay: acoustic ODE 한 요소

```prompt
완주한 engine:"yue-mlx" 작업 산출물에서 현재 replay 지원을 확인해줘.
song:replay stage:"synthesize"에는 advanced.odeSteps 하나만 바꾼 후보를 준비하고,
cfgScale·가사·style·ABC·seed는 바꾸지 마.
새 job의 실제 시간·메모리 상태·결과 파일을 원본과 나란히 기록하고,
더 높은 odeSteps가 더 좋은 품질을 보장하지 않는다고 밝혀줘.
```

**왜 이 조합인가:** `odeSteps`는 acoustic ODE 단계에 해당한다. `synthesize` replay에는 stage가 허용한 ODE 관련 override만 사용하고, semantic CFG 변경을 섞지 않는다.

## 12. 최종 검수와 반복 중단

```prompt
engine:"yue-mlx" CCM 후보를 마무리 검수해줘.
각 후보의 승인 입력·song:prepare effective·ABC·실제 파일·실제 길이·EOS·truncation·로컬 ASR 여부·SheetSage 여부·직접 청취 여부·소요시간을 각각 기록해줘.
자동 전사나 악보 전사만으로 가창·음질을 확정하지 말고,
명확한 우위가 없으면 가장 안정적인 후보 하나를 채택하고 추가 생성은 중단해줘.
```

**왜 이 조합인가:** SheetSage는 음악 ABC/MIDI 추정이고, 로컬 ASR은 가사 전달의 보조 근거이며, 둘 다 청취 품질 판정을 대체하지 않는다. 실측과 선택 이유를 남기면 다음 수정에서 한 요소만 바꿀 수 있다.

## 참고 근거

고정 공식 YuE2의 생성·수정·ABC·청취 지침은 [공식 generation](vendor/yue2/official/docs/generation.md), [editing](vendor/yue2/official/docs/editing.md), [generation-and-covers](vendor/yue2/official/skills/yue2-music/references/generation-and-covers.md), [ABC editing](vendor/yue2/official/skills/yue2-music/references/abc-editing.md), [listening](vendor/yue2/official/skills/yue2-music/references/listening-and-evaluation.md)에 보관되어 있다. Apple Silicon 실행 경계는 [MLX usage](vendor/yue2/mlx/docs/usage.md)와 [YuE2 Apple Silicon](yue-mlx.md)을 따른다.


## 공식 자료를 대조한 범위

공식 YuE2 고정판 yue2-v0.1.6과 2026-10-20 조회 main의 generation 문서를 대조했고, 실제 설치 계약은 고정 커뮤니티 MLX와 현재 공개 CLI로 확인했다. 조사했다고 엔진·모델을 업데이트하지 않는다. 공식 원생 Python 예제의 snake_case 키를 Road Music 최상위 JSON으로 옮기지 않는다.

- [공식 고정 generation](https://raw.githubusercontent.com/multimodal-art-projection/YuE/9c6c4b349be978b06a9d0d958471a07a6cdeff4d/docs/generation.md)
- [공식 입력·재사용·수정 경계](https://raw.githubusercontent.com/multimodal-art-projection/YuE/9c6c4b349be978b06a9d0d958471a07a6cdeff4d/skills/yue2-music/references/generation-and-covers.md)
- [고정 커뮤니티 MLX usage](https://raw.githubusercontent.com/vanch007/mlx-Yue/c5b5a8190f78c74aa671a4caa19dae8b8e04b3d8/docs/usage.md)

새 실제 음악 생성·직접 가창 청취는 이번 문서 검수에서 수행하지 않았다. 한국어 입력의 전달과 실제 한국어 가창 품질, 회중이 부르기 적합한 음역은 다른 검수 항목이다.
