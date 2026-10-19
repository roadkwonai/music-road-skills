# CCM 고급 활용 가이드

![요청·실제 제작 단계·결과 기록을 연결하는 운영 흐름 예시](media/production-flow.svg)


[CCM 기본 가이드](ccm-prompts.md) · [ACE 가이드](ace-prompt-guide.md) · [YuE 가이드](yue-prompt-guide.md) · [공개 명령 레퍼런스](cli-reference.md)

이 문서는 CCM 전문 페이지와 `prompt:knowledge`가 함께 사용하는 고급 활용 원칙이다. 복사 가능한 ACE·YuE 조합은 [CCM 레시피 데이터](ccm-recipes.json)에 있으며, 스타일 48개와 목적·태그·명령·검수 항목을 같은 데이터에서 읽는다. 제안은 입력 설계이며 보컬, 음역, 악기, 박자, 실제 길이, 품질을 보장하지 않는다.

## 먼저 목적과 엔진을 고른다

| 목적 | 출발 스타일 | 권장 조합 |
| --- | --- | --- |
| 회중 예배 | C17·C20 | 짧은 후렴, `song:prepare`, 승인 뒤 1곡 |
| 특송·가스펠 | C03·C23 | 실제 가사 줄로 응답 구조를 작성하고 특정 가수 모사는 제외 |
| 개인 기도·묵상 | C33·C35·C40 | 편성을 줄이고 가사·연주곡 여부를 먼저 고정 |
| 청년·감상형 | C27·C32 | seed 또는 한 스타일 문구만 바꿔 후보를 비교 |
| 절기 | C41~C44 | 새 창작 가사인지, 원전·번역·녹음 사용 허락이 있는지 분리 |

### ACE 모델의 입력 검증

song:prepare에서 최종 caption512자·정리 가사4,096자를 확인한다.

### YuE 모델의 입력 검증

`yue`와 Apple Silicon `yue-mlx`를 구분하고 사용자 선택을 유지한다. `yue:capabilities`와 `song:prepare`로 현재 공개 지원·실효 입력을 확인한다. targetSeconds는 목표 기록이며 원생 요청의 duration 필드가 아니다. 실제 길이·EOS·잘림은 완료 후 확인한다. 다른 모델의 문자 수 한계로 가사를 잘라 맞추지 않는다. 컨텍스트는 런타임 tokenizer 검증이 필요하며 준비 통과만으로 완주가 검증된 것은 아니다.

## 조합 순서

1. 스타일 하나와 예배 목적 하나를 고른다.
2. 사용자 가사·프롬프트가 있으면 원문을 보존한다. 새 가사는 승인 또는 명시적 전체 자동 위임 범위에서만 작성한다.
3. `song:prepare`로 생성 없이 입력을 검수한다. YuE의 ABC 작업은 필요할 때만 `score:inspect`, `score:compare`, `score:strip-chords`를 추가한다.
4. 비교는 seed, 가사 한 구절, 악기 한 가지처럼 한 요소만 바꾼다. 서로 다른 장르는 별도 요청으로 나눈다.
5. 승인 뒤에만 `song:generate`를 시작하고, 반환된 `jobId`는 `job:wait`으로 완료·실패와 실제 결과 경로를 확인한다. YuE 결과는 입력·악보·파일·실제 길이/EOS·전사·청취를 서로 다른 확인 상태로 기록한다.

## 권리와 검수 경계

- 원전이 만료됐더라도 현행 번역, 편곡, 녹음, 참조 음원 사용 허락은 별도로 확인한다.
- ABC 검사는 악보 형태를 읽는 도구다. 가창 품질, 한국어 자연스러움, 청취 만족도를 대신 판정하지 않는다.
- 사용자 제공·승인 원문은 임의로 고치지 않는다. 한 구절 수정은 수정 전후·이유·남은 한계를 기록한다.

## 화면에서 찾는 법

CCM 전문 페이지에서 엔진(ACE/YuE), 목적, 스타일, 태그를 함께 선택한다. 엔진 버튼은 하나씩만 선택하며 기본은 YuE다. 카드의 조합 요소와 명령 순서에서 각 입력의 역할을 확인한다. 기본 요청은 준비·검토용이며 응용 복사는 기본안과 변경 범위를 함께 담는다. 복사나 문서 읽기는 실제 생성 승인이 아니다.

## 대표 활용 사례

아래 요청문은 모두 우선 준비·검토만 수행한다. 실제 생성은 가사와 입력을 확인한 뒤 승인하거나, 사용자가 가사·프롬프트 결정부터 생성을 명시적으로 위임했을 때만 이어진다.

### ACE 회중 워십: 짧은 후렴과 단계적 편성

```prompt
ACE로 한국어 회중 워십 1곡을 준비해줘. 사용자가 준 가사는 바꾸지 말고,
가사가 없을 때만 감사 주제의 새 초안을 작성해줘. C17 방향으로 76 BPM,
piano·acoustic guitar·drums, [Verse]의 개인 고백과 2~4줄 [Chorus]의 공동체 고백을 조합해줘.
lyrics:clean·lyrics:check·prompt:compose·song:prepare 결과와 최종 caption을 보여주고 승인 전에는 생성하지 마.
```

**조합 이유:** 회중이 따라 부르는 핵심은 후렴의 문장 밀도다. 악기·템포는 `parts`에, 가사 구조는 `lyrics`에, 상승감은 `style`에 분리한다. ACE에서는 정리 가사 4,096자와 caption 512자를 준비 단계에서 확인한다.

**응용:** 가사가 길면 후렴을 늘리는 대신 벌스 장면을 한 개로 줄인다. 편성 비교는 piano를 Rhodes로 바꾸는 식으로 한 요소만 바꾼 별도 요청으로 만든다.

### ACE 작은 교회 피아노 특송: 가사 전달 우선

```prompt
ACE로 작은 교회 피아노 특송 1곡을 준비해줘. 제공 가사가 있으면 그대로 유지하고,
없을 때만 새 창작 가사를 초안으로 제안해줘. piano 중심, 68 BPM, 180초,
절제된 단독 리드 보컬로 두고 장식적 콰이어·드럼·대형 밴드는 요청하지 마.
song:prepare에서 style·가사·caption을 검수한 뒤 승인 전에는 생성하지 마.
```

**조합 이유:** 작은 공간에서는 편성보다 문장이 먼저 들려야 한다. 단독 리드·피아노·낮은 BPM을 함께 두되, 실제 보컬 음역이나 반주 밀도는 결과 후 들어 보고 판단한다.

**응용:** 가사가 너무 빽빽하면 한 절의 문장을 줄이고, 피아노를 유지한 채 cello 하나만 더한 별도 후보를 만든다.

### ACE 가스펠 특송: 실제 가사 줄의 응답

```prompt
ACE로 한국어 가스펠 특송을 준비해줘. C23 방향, 104 BPM,
piano·bass guitar·drums을 사용하고 리드와 응답은 [Verse]·[Chorus]의 실제 가사 줄로 번갈아 써줘.
[Leader]·[Choir]처럼 지원되지 않는 태그로 배정을 약속하지 말고,
song:prepare에서 가사·style·caption을 확인한 뒤 승인용 입력만 보여줘.
```

**조합 이유:** 응답 관계를 가사 본문에 두면 미지원 가수 배정 태그에 기대지 않는다. 소울 장식은 `style`의 한 표현으로만 추가하고, 실제 콰이어 인원·파트는 보장하지 않는다.

**응용:** 같은 응답 가사를 유지한 채 piano만 Rhodes로 바꾸거나 handclap feel 하나만 더해 비교한다.

### YuE MLX 회중 워십: 선택 엔진과 길이 기록

```prompt
Apple Silicon에서 선택한 engine:"yue-mlx"를 유지해 한국어 회중 워십을 준비해줘.
C17 방향, mode:"plan", cot:"full", targetSeconds:180을 사용하고 yue:capabilities와 song:prepare로
현재 공개 지원·실효 설정을 먼저 보여줘. targetSeconds는 요청값이며 실제 길이와 자연 EOS는 완료 후 따로 기록해줘.
```

**조합 이유:** `yue`와 `yue-mlx`는 설치·실행 경로가 다르므로 사용자가 고른 엔진을 바꾸지 않는다. 계획 결과는 생성 품질이나 회중 음역의 보장이 아니다.

**응용:** 엔진·가사·style·seed를 유지하고 cot만 melody로 바꾼 계획을 비교할 수 있다. mode:plan 제출은 실제 악보 모델 추론이며 음원은 없다. targetSeconds만 바꿨다고 다른 음악적 계획으로 평가하지 않는다. 검토한 계획을 음원화할 때는 mode:song의 새 생성 입력에 ABC를 포함하거나, 원문이 동일하고 무결성을 확인한 MLX plan 작업 산출물을 stage:plan으로 재사용한다.

### YuE 가사 수정과 선율 보존: ABC 사본 비교

```prompt
선택한 engine:"yue" 또는 engine:"yue-mlx"를 유지해 기존 CCM의 [Verse] 두 번째 줄만 수정할 준비를 해줘.
원 ABC는 보존하고 사본을 만든 뒤 score:inspect와 score:compare로 source·candidate를 검사해줘.
melody:true, form:true, allowTempoChange:false를 유지하고, song:prepare 결과를 보여줘.
수정한 전체 lyrics와 기존 style·선택 engine·검증한 abc를 포함한 새 song:prepare 입력을 만들어줘.
승인 뒤 같은 입력으로 song:generate를 제출하고 job:wait으로 완료를 확인해줘. 원곡은 보존해줘.
song:render는 원래 metadata의 가사/style을 재사용하므로 수정 가사 전달에 사용하지 마.
```

**조합 이유:** 가사/style 변경은 새 생성 요청에 명시해야 한다. 현재 song:render는 dir·abc·title만 받고 원곡의 lyrics/style을 재사용하므로 변경 가사 전달에는 맞지 않는다. 한 구절·반복 위치를 정확히 지정하고 invariants 객체 안의 melody/form/allowTempoChange로 후보 악보를 검사한다. 선율의 기호 보존과 실제 가창·파형 동일성은 다르다. 기존 가사/style을 그대로 두고 악보만 바꾸는 경우에만 song:render와 job:wait을 사용한다.

**응용:** 화성만 바꾸려면 `harmony:false`로 비교하고, 새 악보가 필요하면 선율 고정 요구가 없는지 먼저 확인한다.

### YuE 고급 한 변수 비교: seed와 검수 분리

```prompt
선택한 engine:"yue" 또는 engine:"yue-mlx"를 유지해 C27 방향 CCM 두 후보를 준비해줘.
title·style·lyrics·cot·targetSeconds·advanced는 유지하고 seed만 두 값으로 바꿔 각각 song:prepare를 검증해줘.
생성 뒤에는 targetSeconds와 실제 길이·EOS, 입력·악보·파일 검사, 전사, 실제 청취를 서로 다른 항목으로 기록해줘.
로컬 전사 환경이 이미 가용할 때만 전사를 실행하고, 없으면 미확인으로 남겨. 설치·다운로드·외부 전송은 하지 마.
```

**조합 이유:** seed 비교는 다른 샘플링 값이나 편성을 함께 바꾸지 않을 때만 해석할 수 있다. 전사 결과는 가창 품질·한국어 자연스러움·청취 만족도를 대신하지 않는다.

**응용:** seed를 고정한 뒤에는 `advanced.temperature` 하나만 바꾸는 새 비교를 만들고, 두 비교를 한 요청에 섞지 않는다.

## 참조 오디오의 모델별 경계

### ACE 모델의 참조 입력

`coverAudio`와 `recording`은 현재 Road Music에서 **ACE 전용** 입력이다. 권한 있는 실제 경로와 사용 허락이 있어도 YuE·YuE MLX 입력에 붙이지 않는다. ACE 참조 입력도 특정 원곡·보컬의 완전 재현을 보장하지 않으며, 커버와 녹음 입력은 같은 요청에 섞지 않는다.


### YuE 모델의 참조 음악 활용

직접 coverAudio·recording·strength를 입력하지 않는다. 권한 있는 참조 음원을 사용할 때는 이미 설치한 로컬 전사 도구가 있는지 확인한다. 가용하면 음악 ABC를 얻어 보정·검사하고 코드 없는 선율 조건을 준비한 뒤 실제 lyrics/style/선택 engine/abc를 넣은 새 생성 입력을 검토한다. 도구가 없으면 미확인으로 남기며 임의 설치나 외부 업로드를 하지 않는다. SheetSage2 음악 전사와 ASR 가사 전사는 서로 다른 작업이다.

## YuE 모델의 고급 활용 핵심

- 준비 검증(song:prepare), 실제 악보 모델 추론(mode:plan), 음원 생성(mode:song)을 구분한다. off에는 ABC와 plan을 붙이지 않는다.
- advanced의 ABC샘플링7개·semantic샘플링7개·semantic CFG·acoustic ODE를 구분한다. 제공 ABC는 planner를 우회하므로 ABC sampling을 바꿔 새 악보가 생긴다고 보지 않는다.
- plan replay는 저장된 plan 이후 단계를 다시 실행하고, synthesize는 semantic/noise, decode는 latent를 재사용한다. 가사/style/ABC를 바꾸려면 새 생성 요청을 쓴다. 단계별 허용 override와 작업 산출물의 무결성을 먼저 확인한다.
- instrumental은 현재 무보컬 의도이며 Vocal 성부 이동이나 보컬 제거를 보장하지 않는다. 빈 가사 프로젝트는 현재 song:render가 거부하므로 새 mode:song 생성 또는 검증된 MLX plan 재사용을 검토한다.
- 한국어 CCM의 문장 밀도·받침·후렴 호흡·신앙 대상을 원문과 대조한다. ABC검사·기술 파일·가사 전사·직접 청취를 별도 판정하며 benchmark를 한국어 품질 보장으로 확대하지 않는다.

상세 단계별 설명·기본값·고급 조합은 [YuE 전용 고급 활용 프롬프트](yue-advanced-prompts.md)를 읽는다. 근거는 [고정 공식 generation](vendor/yue2/official/docs/generation.md), [공식 generation-and-covers](vendor/yue2/official/skills/yue2-music/references/generation-and-covers.md), [고정 MLX usage](vendor/yue2/mlx/docs/usage.md)와 현재 공개 schema다.
