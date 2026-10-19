# CCM·워십 상세 프롬프트와 제작 옵션

![요청·실제 제작 단계·결과 기록을 연결하는 운영 흐름 예시](media/production-flow.svg)


[Road Music](../README.md) · [장르 프롬프트](genre-prompts.md#ccm) · [문서 지도](README.md)

**CCM을 주로 제작할 때 사용하는 한국어 창작곡 가이드**다. 과거 사운드부터 최근 예배 제작 사례까지 참고해 48개 스타일 예시, 상세 요청문 12개, 창작 가사 8편, 엔진을 구분한 실행 JSON을 제공한다. 기본 활용은 YuE2이며 Apple Silicon에서는 선택한 `engine:"yue-mlx"`를 유지한다. ACE 입력은 별도 절에 남긴다. 기본 추천은 **C17 여성 모던 워십 / 76 BPM / 180초**이며 개인 기도곡은 C33, 과거 복음성가 질감은 C05부터 시작한다. 이것은 제작 추천이며 앱의 전역 기본값을 바꾸지 않는다.

CCM은 신앙 내용을 다루는 대중음악을 폭넓게 부르는 말이다. 이 문서는 회중 워십·찬송 형식·가스펠도 함께 다루지만 모두 같은 음악 장르로 간주하지 않는다. 특히 한국 복음성가와 미국 Southern Gospel을 동일한 계보라고 단정하지 않는다.

[YuE 제작 가이드](yue-prompt-guide.md)·[YuE 고급 프롬프트](yue-advanced-prompts.md)와 [가사 태그](lyrics-tags.md)·[검토 규칙](music-review.md)을 먼저 따른다. ACE를 명시 선택한 경우에만 [ACE 적용 가이드](ace-prompt-guide.md)를 사용한다. 아래 예시를 문서에 추가하는 작업만으로 엔진 설치나 음원 생성을 실행하지 않는다. **보컬·박자·조성·화성·회중 음역은 모델에 요청하는 표현이며 보장되는 전용 옵션이 아니다.**

**사용자가 가사·프롬프트를 제공했다면 그 원문을 우선한다.** 이 문서의 새 작사·후렴 반복·편곡 예시로 임의 교체하지 않는다. 개선안은 [근거 기반 추천](music-review.md#preserve-input)으로 제시하고 승인된 변경만 반영한다. 옛 찬송을 활용할 때는 [원전 목록·권리·리메이크 프롬프트](hymn-remake-guide.md)를 함께 읽는다. CLI에서는 `prompt:knowledge --json '{"topic":"ccm"}'`, `topic:"hymn-remake"`로 조회할 수 있다.

<a id="quick"></a>

## 바로 복사하는 기본 요청

이미 CLI를 설치했다면 [기존 설치 연결](ai-cli.md#new-session)을 먼저 사용한다. 아래 기본 요청은 가사·프롬프트를 보여준 뒤 생성 승인을 받는 모드다.

### YuE 모델 기본 요청 1

```text
제공/승인 가사가 있으면 그대로 보존하고 없을 때만 새 작사 지시를 적용해줘.
기존 Road Music CLI 설치를 찾아 AGENTS.md와 docs/ccm-prompts.md, docs/yue-prompt-guide.md를 읽어줘.
Apple Silicon에 선택된 engine:"yue-mlx"를 유지하고 ACE로 바꾸지 마.
준비된 YuE가 없으면 설치하지 말고 미설치 상태를 알려줘.
C17을 기준으로 한국어 여성 모던 워십 1곡을 준비해줘.
은혜에 대한 감사와 일상에서 주님을 따르는 고백, 76 BPM, 180초,
piano·acoustic guitar·drums, 혼자 시작해 마지막 후렴은 함께 부르는 분위기로 해줘.
제공 가사가 없을 때의 새 초안·최종 style·실제 지원 JSON을 검증해 먼저 보여주고 승인 후 생성해줘.
목표 초는 기록용이고 완료 뒤 실제 길이·EOS·잘림을 확인해줘.
```

### YuE 모델 기본 요청 2

```text
제공/승인 가사가 있으면 그대로 보존하고 없을 때만 새 작사 지시를 적용해줘.
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
C05의 소그룹 복음성가 질감으로 86 BPM, 180초의 감사 찬양 1곡을 준비해줘.
통기타와 담백한 혼성 유니즌, 모든 세대가 따라 부르기 쉬운 후렴으로 설계해줘.
목표 초는 기록용이고 완료 뒤 실제 길이·EOS·잘림을 확인해줘.
```

### YuE 모델 기본 요청 3

```text
제공/승인 가사가 있으면 그대로 보존하고 없을 때만 새 작사 지시를 적용해줘.
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
C33의 여성 피아노 기도곡으로 64 BPM, 180초를 준비해줘.
두려움을 숨기지 않되 주님의 동행을 신뢰하는 내용, 가까운 보컬과 긴 쉼을 원해.
목표 초는 기록용이고 완료 뒤 실제 길이·EOS·잘림을 확인해줘.
```

### YuE 모델 기본 요청 4

```text
제공/승인 가사가 있으면 그대로 보존하고 없을 때만 새 작사 지시를 적용해줘.
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
C40의 기도·묵상용 앰비언트 연주곡 1곡을 준비해줘.
보컬 없이 60 BPM, 240초, piano·synth pads·harp, instrumental=true로 설계해줘.
목표 초는 기록용이고 완료 뒤 실제 길이·EOS·잘림을 확인해줘.
```

### 공통 제작 위임 범위

가사와 프롬프트부터 생성까지 전부 맡기려면 다음 문장을 **직접 덧붙인다**. 문서를 읽은 것만으로 자동 생성 위임이 되지는 않는다.

```text
가사와 프롬프트의 결정부터 생성까지 모두 자동으로 맡길게.
입력을 자체 검증한 뒤 1곡 생성하고 음원·가사·caption·옵션·출처·선택 이유를 제공해줘.
```

<a id="research"></a>

## 과거와 최근 자료에서 확인한 것

**확인일: 2026-10-15 KST.** 공식 카탈로그·제작자 소개·CCLI 자료를 조사했다. 음원을 직접 청취하거나 BPM·조성·음역을 실측한 조사는 아니다. 아래는 확인 사실이며, 뒤의 BPM·악기·보컬·길이는 그 자료를 바탕으로 만든 **창작용 제안**이다. 48개 항목을 모두 “현재 유행하는 장르”로 해석하지 않는다.

### 과거부터 이어지는 제작 계보

| 계보·시기 | 확인한 사실과 근거 | 제작 방향으로 해석한 것 |
| --- | --- | --- |
| 1960년대 말~1970년대 Jesus Music | [Calvary Chapel 계열 회고 기사](https://calvarychapelmagazine.org/articles/jesus-movement-music)는 초기 음악 활동과 록·팝의 접점을 다룬다. 기사 발행연도 표시는 불완전해 조회일로 관리 | 통기타·소규모 밴드·개인 신앙고백을 C01·C05로 제안 |
| 복음성가 중창과 공동체 노래 | [BGEA의 2011-05-09 기사](https://media.billygraham.org/gaithers-film-homecoming-tent-revival-special-at-billy-graham-library/)는 1967년 활동과 1991년 Homecoming 시작 맥락을 소개 | 중창·공동체 노래의 질감을 C02로 제안. C03 소울·C23 콰이어는 별도 가스펠 표현을 사용한 창작 변형이며 이 자료로 같은 계보임을 증명하지 않음 |
| 1980년대 스튜디오 팝 CCM | 권리자 제공 [Apple Music의 Unguarded 카탈로그](https://music.apple.com/us/album/unguarded/1536221839)는 원 발매일 1985-05-15를 표시. 재발매 권리 연도와 구분 | 아날로그 신스·팝 리듬·간결한 훅을 C06·C07로 제안 |
| 친밀한 기도형 워십 | [Vineyard의 2016-03-25 설명](https://vineyardusa.org/why-do-we-worship-who-do-we-worship/)은 하나님께 직접 드리는 단순한 노래와 예배의 관계를 설명 | 적은 악기·가까운 리드·기도 문장과 쉼을 C14·C24·C33으로 제안 |
| 1990년대 한국 서정 CCM | [국민일보의 2021-03-02 전문 큐레이터 해설](https://www.kmib.co.kr/article/view.asp?arcid=0924180737)은 소리엘 1992년 1집을 발라드 어법과 개인 신앙고백의 사례로 다룸. 이 행은 공식 당사자 자료가 아닌 **2차 자료** | 한국어 간증·위로·서정적 후렴을 C08·C09·C10의 제작 예시로 제안 |
| 1990~2000년대 회중 라이브 | [Hillsong Worship 공식 카탈로그](https://hillsong.com/music/worship)에 1992·1996·2006년 등 라이브 음반 연혁이 기록됨 | 느린 고백형과 빠른 찬양형을 C18·C21로 분리. 시대 전체를 한 BPM으로 규정하지 않음 |
| 2000년대 한국 창작 예배실황 | [어노인팅 3집 공식 소개](https://anointing.co.kr/albumview.php?cate=&idx=276&page=2&s_keyfield=&s_keyword=), 2003-08-06은 2001년 실황 음반 시작과 3집의 국내 창작곡 구성을 설명 | 한국어 발음·공동체 고백·밴드와 혼성 백킹을 C09·C17·C20에 적용 |
| 현대 찬송 창작·옛 찬송 재해석 | [Getty 소개](https://www.gettymusic.com/about-us)는 2001년 대표 작품과 회중 노래의 목적을, [Indelible Grace 소개](https://hymnbook.igracemusic.com/pages/about-us)는 2000년 첫 음반과 옛 찬송에 새 음악을 붙이는 작업을 설명 | 절이 논리적으로 이어지는 새 찬송, 어쿠스틱·현악 편곡을 C04·C12·C13으로 제안 |
| 2010년대 청년 워십의 여러 버전 | [Young & Free 공식 카탈로그](https://hillsong.com/music/youngandfree)는 2013 라이브·2015 리믹스·2016 라이브·2017 어쿠스틱 프로젝트를 보여줌 | 신스 팝과 어쿠스틱이 함께 존재하는 제작 선택지로 C21·C25·C29를 제안 |

같은 시대에도 밴드·피아노·신스·어쿠스틱이 공존한다. “옛 CCM은 통기타뿐, 최신 CCM은 전자음악뿐”이라는 식으로 단순화하지 않는다. 위 인명·음반명은 역사적 근거이며 생성 style에는 아티스트 이름 대신 음악적 특징을 사용한다.

### 2025~2026 자료에서 확인한 최근 흐름

| 출처·기간 | 직접 확인한 내용 | 활용과 한계 |
| --- | --- | --- |
| [CCLI / WorshipFuel 미국 Top 100](https://www.worshipfuel.com/ccli-top-100/), 페이지 발표일 **2026-08-01** | 미국 CCLI 이용 교회의 보고 기반. 1~5위에 Goodness Of God, Holy Forever, Gratitude, Great Are You Lord, Praise가 표시됨 | 오래 쓰이는 회중 레퍼토리와 찬양·감사의 주제를 함께 참고. 한국 차트·스트리밍 순위·신곡만의 순위가 아니며 정확한 보고 기간은 페이지에서 별도 확인하지 못함 |
| [Elevation Worship — SO BE IT 공식 음반](https://www.elevationworship.com/album/so-be-it-album), **2026**, 10곡 | 정식 음반과 여러 참여 보컬 크레디트를 확인 | 공동체·여러 보컬이 참여하는 제작 형식을 참고. 개별 곡의 BPM·음색·흥행 원인을 이 페이지로 증명하지 않음 |
| [어노인팅 공식 음반 목록](https://anointing.kr/album.php), **14집 2025-09-09 / 예배캠프 2025 음원 2026-02-03** | 정규 음반·실황·찬송가 프로젝트가 병존. 캠프 이름의 연도와 실제 음원 발매일이 다름 | 최근 한국 제작 사례와 지속되는 찬송 프로젝트를 함께 탐색. 국내 전체 인기 순위로 확대하지 않음 |
| [어노인팅 예배캠프 2025 공식 상세](https://anointing.co.kr/albumview.php?idx=1529&page=1&s_keyfield=&s_keyword=&cate=), **2026-02-03**, 녹음 **2025-08-12~14** | 고난 속 소망이라는 주제, 20트랙, 국내 창작곡·해외곡의 병치, 건반·신스·기타·베이스·드럼·퍼커션·여러 싱어 크레디트 | 소망·말씀 응답·회중 노래와 밴드 편성을 C17~C24로 풀었다. 공식 편성 전체를 CLI 악기 3개에 모두 강제할 수는 없음 |
| [Bethel Music 공식 홈페이지](https://bethelmusic.com/), **2026-10-15 조회**, 각 카드 발매일 미표기 | 현재 소개에 라이브 싱글과 어쿠스틱 버전, 새 음반·EP가 함께 표시됨 | 라이브·어쿠스틱을 병행하는 공개 제작 사례. 표시만으로 장르별 시장 점유율이나 증가율을 추정하지 않음 |

따라서 **회중이 참여하는 모던 워십·단순한 고백·라이브와 어쿠스틱의 병행**을 기본 제작 방향으로 잡았다. R&B·로파이·보사노바·하우스·재즈는 취향과 감상 목적을 넓히는 변형이며, 이 조사로 최신 인기 순위가 입증된 항목이 아니다. 새 “요즘 CCM” 요청은 [리서치 절차](music-research.md)를 따라 기준일·국가·집계 지표를 다시 확인한다.

<a id="purpose"></a>

## 예배·감상 목적부터 선택

| 목적 | 우선 후보 | 설계할 때 집중할 것 |
| --- | --- | --- |
| 주일 회중 찬양 | C17·C18·C20 | 제목 훅 1개, 반복 가능한 짧은 후렴, 독창 애드리브보다 유니즌 |
| 청년·수련회 찬양 | C21·C22·C29·C32 | 박이 명료한 리듬, 짧은 프리코러스, 고백이 남는 후렴 |
| 개인 기도·새벽 예배 | C10·C24·C33·C34 | 적은 악기, 낮은 에너지, 문장 사이 호흡 |
| 간증·위로 특송 | C08·C09·C11·C15·C35 | 구체적인 삶의 장면→기도→소망의 변화 |
| 세대 통합·가정 예배 | C04·C05·C12·C13 | 쉬운 어휘, 절과 후렴의 일관된 호흡, 담백한 화음 |
| 가스펠·찬양 축제 | C03·C23·C44 | 리드와 응답, 기쁨의 리듬, 후렴 발음 |
| 일상 감상용 CCM | C25~C28·C36·C37 | 독창의 전달과 장르 질감. 회중용과 다른 자유도 |
| 기도·묵상 BGM | C39·C40 | `instrumental:true`, 보컬·허밍 없는지 청취, 보컬곡과 별도 요청 |
| 대림·성탄·고난·부활·감사·파송 | C41~C46 | 절기의 의미와 주제 일관성, 과도한 장르 혼합 줄이기 |

찬양의 대상은 주님·예수 그리스도 등으로 분명하게 정한다. “너·그대·운명”만 반복해 대상이 연인처럼 들리지 않게 한다. 개인의 고백은 `나`, 회중의 고백은 `우리`를 중심으로 시점을 정하고, 성경 주제를 쓰면 본문의 문맥을 확인해 자기 표현으로 풀어 쓴다. 특정 교단의 세부 표현은 요청받았을 때 반영한다.

<a id="options"></a>

## 세부 옵션과 조절법

### YuE 모델의 실제 입력과 목표 기록

| 항목 | 공개 입력 | 실제 적용과 한계 |
| --- | --- | --- |
| 선택 엔진 | `engine:"yue-mlx"` 또는 `"yue"` | Apple Silicon과 Windows NVIDIA 경로를 구분하며 선택한 엔진을 유지 |
| 음악과 가사 | `style`, `lyrics`, `parts` | 보컬·편성·박자·회중 호흡은 의도. `song:prepare`의 실제 전달본과 대조 |
| 계획 선택 | `cot:"full"/"melody"/"off"` | full은 화성+선율, melody는 선율 계획, off는 기호 계획 없음. off에 abc/plan을 결합하지 않음 |
| 작업 종류 | `mode:"song"` 또는 `"plan"` | song은 음원, plan은 모델로 악보만 생성. 무추론 검사는 song:prepare |
| 목표 길이 | `targetSeconds` 20~360 | 목표 기록일 뿐 원생 duration 제어가 아님. 실제 길이·EOS·잘림 확인 |
| 재현 seed | 0~9223372036854775807 | JavaScript 안전 정수 밖은 정확한 십진 문자열. 환경 간 동일 음원 보장 아님 |
| 제공 ABC | `abc`와 full 또는 melody | planner 우회. 가사 삽입용 w:·음소나 임의 다성 악보 사용 금지 |
| 고급 제어 | `advanced` 16개 | ABC7·semantic7·semantic CFG1·acoustic ODE1. 하나씩 비교하고 높은값 품질보장 금지 |
| 원문 변경 | 새 `song:prepare`→`song:generate` | 가사/style 변경은 새 요청에 명시. 기존 song:render는 원곡 가사/style을 재사용 |

YuE에는 ACE의 caption512자·가사4,096자 한계를 적용하지 않는다. `bpm` 문구나 targetSeconds만 바꾼 설정을 정확한 템포·종료 또는 새로운 음악적 계획이라고 안내하지 않는다. `coverAudio`·`recording`은 YuE 입력이 아니다. 48개 스타일과 창작 가사는 편곡을 시작할 때 참고하는 예시일 뿐, 현재 모델의 한국어 가창 성능 인증이 아니다.

### 음악적 세부 표현은 style에서 하나씩 조절

아래 선택지는 전부 **모델에 대한 요청**이다. 여러 값을 한꺼번에 넣지 말고 기존 태그를 교체한다.

| 축 | 선택 표현 | 선택 기준 |
| --- | --- | --- |
| 리드 | `warm female lead` / `warm baritone lead` / `mixed vocal duet` | 여성·남성·듀엣 선택. 듀엣의 줄별 가수 배정은 강제되지 않음 |
| 회중 비중 | `solo lead` / `congregational unison` / `mixed choir harmonies` | 개인 묵상→함께 부르기→합창 순으로 질감 확장 |
| 발음 | `clear Korean diction` | 자음이 묻히면 가사 밀도를 먼저 줄이고 한 번에 한 요소 비교 |
| 보컬 장식 | `restrained vocal runs` / `soulful vocal runs` | 회중은 절제, 가스펠 특송은 장식 허용 |
| 흐름 | `restrained verses` / `gradual build` / `joyful steady groove` | 모든 구간을 최대 강도로 요청하지 않음 |
| 후렴 | `simple singable chorus` / `anthemic chorus` / `call and response` | 짧고 쉬운 후렴, 웅장한 후렴, 리드·응답 중 선택 |
| 박자 느낌 | `common time feel` / `six eight time` / `three four waltz feel` | 박자 전용 필드는 없음. BPM 하나만으로 6/8의 박 세는 기준까지 고정되지 않음 |
| 조성·화성 | `D major` / `minor verses` / `suspended chord colors` | 참고 의도. 실제 조성·음역·코드는 생성 뒤 확인 |
| 공간 | `dry intimate room` / `small room ambience` / `spacious live worship` | 개인 기도와 집회 질감 구분. 실제 공연 녹음·실제 회중이라는 뜻은 아님 |
| 밴드 기타 | `clean delay guitar` / `warm acoustic strumming` / `overdriven guitar chorus` | 기타 종류는 악기 enum, 주법·이펙트는 style |
| 리듬 | `gentle brushed groove` / `half time groove` / `four on the floor` | 브러시·하프타임·댄스 비트 중 목적에 맞춰 선택 |
| 마무리 | `resolved ending` / `gentle instrumental outro` | 초 단위 종료·완벽한 루프·무한 반복은 보장하지 않음 |

**무리 없이 시작할 조합:** 회중 워십은 72~84 BPM·180~210초·주악기 3개·strict false, 기도곡은 58~70 BPM·150~180초·악기 1~2개, 빠른 찬양은 100~120 BPM·150~180초에서 비교한다. 이는 통계적 최적값이나 회중 음역 측정값이 아니다.

### 가사와 구조

- 회중형: `[Verse] → [Chorus] → [Verse] → [Chorus] → [Bridge] → [Chorus]`. 후렴은 2~4줄로 시작하고 실제 문장을 반복해서 쓴다.
- 간증형: 절에서 삶의 장면, 후렴에서 신앙고백, 브리지에서 응답·헌신을 쓴다. 매 줄에 교회 용어를 쌓기보다 한 주제를 전개한다.
- 옛 찬송 형식: 비슷한 길이의 절이 논리적으로 이어지게 작성한다. 익숙한 찬송가 가사를 붙여 넣는 대신 새 가사로 형식의 장점을 활용한다.
- 가스펠 응답형: 리드와 응답에 해당하는 **실제 가사 줄**을 번갈아 둔다. `[Leader]`·`[Choir]` 같은 미지원 태그로 가수 배정을 약속하지 않는다.
- 연주곡: `lyrics:""`, `instrumental:true`. 전체 연주곡과 보컬곡 중간의 `[Interlude]`는 다른 설정이다.

현재 스타일 정리는 `/`를 태그 구분자로 바꾸므로 `6/8 feel`을 그대로 넣으면 `6, 8 feel`로 전달된다. 박자 느낌은 `six eight time`처럼 슬래시 없는 짧은 표현을 사용하고 최종 caption을 확인한다.

## 48개 스타일 레시피

표의 `style`을 원문으로 사용하고 BPM은 `parts.bpm`, 초는 `targetSeconds`, 악기는 `parts.instruments`로 옮긴다. 보컬 행은 `instrumental:false`와 새 한국어 가사, 연주곡 행은 `instrumental:true`와 빈 가사를 사용한다. 표의 기본 `engine`은 ace, `count`는 1, `parts.strict`는 false다. 다른 문구를 잔뜩 덧붙이기보다 필요한 보컬·박자 태그 하나를 교체한다.

### A. 과거 사운드·복음성가·찬송 형식

| ID | 제작 방향 | style | BPM | 초 | parts.instruments | 유형 |
| --- | --- | --- | ---: | ---: | --- | --- |
| C01 | 포크 신앙고백 | `Korean Christian folk, warm male lead, acoustic strumming, close harmonies, analog warmth, simple chorus` | 92 | 180 | `acoustic guitar, piano, bass guitar` | 보컬 |
| C02 | 컨트리 가스펠 중창 | `Korean country gospel, mixed vocal harmonies, gentle two beat groove, joyful testimony, natural room` | 104 | 180 | `acoustic guitar, violin, upright bass` | 보컬 |
| C03 | 소울 가스펠 | `Korean soul gospel, expressive female lead, call and response, soulful backing vocals, warm groove` | 96 | 180 | `piano, bass guitar, drums` | 보컬 |
| C04 | 정통 찬송 형식 | `Korean sacred hymn, mixed choir, four part harmony, steady hymn phrasing, reverent, resolved ending` | 72 | 180 | `pipe organ, piano, string ensemble` | 보컬 |
| C05 | 소그룹 복음성가 | `Korean acoustic gospel, mixed unison vocals, warm strumming, simple singalong chorus, modest room ambience` | 86 | 180 | `acoustic guitar, piano, percussion` | 보컬 |
| C06 | 1980년대 CCM 소프트록 발라드 | `Korean retro Christian soft rock, warm male lead, rounded bass, analog warmth, restrained verses, broad chorus` | 78 | 180 | `piano, electric guitar, bass guitar` | 보컬 |
| C07 | 1980~1990년대 CCM 팝 | `Korean retro Christian pop, clear female lead, warm synth chords, steady pop groove, hopeful hook` | 108 | 165 | `synthesizer, bass guitar, drums` | 보컬 |
| C08 | 1990년대 CCM 파워 발라드 | `Korean Christian power ballad, expressive male lead, piano led verses, soaring guitar chorus, hopeful resolution` | 72 | 210 | `piano, electric guitar, drums` | 보컬 |

### B. 한국어 고백·위로·찬송 재해석

| ID | 제작 방향 | style | BPM | 초 | parts.instruments | 유형 |
| --- | --- | --- | ---: | ---: | --- | --- |
| C09 | 한국어 간증 발라드 | `Korean testimony ballad, warm male lead, clear Korean diction, intimate verses, sincere chorus, gentle build` | 74 | 180 | `piano, acoustic guitar, string ensemble` | 보컬 |
| C10 | 여성 고백 CCM | `Korean devotional ballad, tender female lead, clear Korean diction, prayerful, restrained vibrato, intimate` | 68 | 180 | `piano, cello, string ensemble` | 보컬 |
| C11 | 남성 위로 CCM | `Korean comfort worship ballad, warm baritone lead, gentle phrasing, quiet assurance, sparse arrangement` | 70 | 180 | `acoustic guitar, piano, cello` | 보컬 |
| C12 | 성가대형 새 찬송 | `Korean choral hymn, mixed choir harmonies, legato phrases, reverent, measured dynamics, resolved cadence` | 76 | 180 | `piano, pipe organ, string ensemble` | 보컬 |
| C13 | 어쿠스틱 현대 찬송 | `Korean modern hymn, clear female lead, hymnlike melody, acoustic warmth, congregational harmonies, steady phrasing` | 82 | 180 | `acoustic guitar, piano, violin` | 보컬 |
| C14 | 친밀한 기도형 워십 | `Korean intimate worship, gentle male lead, direct prayer, simple repeated chorus, small room ambience, restrained` | 72 | 180 | `acoustic guitar, piano, synth pads` | 보컬 |
| C15 | 여성 CCM 록발라드 | `Korean Christian rock ballad, powerful female lead, restrained verses, melodic guitar, soaring chorus, faithful hope` | 76 | 210 | `piano, electric guitar, drums` | 보컬 |
| C16 | 남녀 듀엣 고백 | `Korean worship duet, warm male and female vocals, conversational verses, blended chorus harmonies, intimate` | 80 | 180 | `piano, acoustic guitar, cello` | 보컬 |

### C. 최근 제작 사례를 참고한 회중·라이브 워십

| ID | 제작 방향 | style | BPM | 초 | parts.instruments | 유형 |
| --- | --- | --- | ---: | ---: | --- | --- |
| C17 | 기본 여성 모던 워십 | `Korean contemporary worship, warm female lead, congregational unison, clear Korean diction, gradual build, spacious chorus` | 76 | 180 | `piano, acoustic guitar, drums` | 보컬 |
| C18 | 남성 앤섬 워십 | `Korean worship anthem, warm male lead, congregational backing vocals, clean delay guitar, restrained verses, expansive chorus` | 78 | 210 | `piano, electric guitar, drums` | 보컬 |
| C19 | 6/8 느낌의 장엄한 워십 | `Korean worship ballad, expressive female lead, six eight time, gentle sway, gradual build, congregational final chorus` | 72 | 210 | `piano, electric guitar, string ensemble` | 보컬 |
| C20 | 말씀 응답·공동체 고백 | `Korean congregational worship, clear male lead, simple singable chorus, mixed unison backing, steady pulse, reverent` | 82 | 180 | `piano, acoustic guitar, bass guitar` | 보컬 |
| C21 | 청년 집회 라이브 | `Korean youth worship, bright mixed vocals, energetic live band feel, clear pulse, communal chorus, joyful` | 116 | 180 | `electric guitar, bass guitar, drums` | 보컬 |
| C22 | 미드템포 감사 찬양 | `Korean praise pop, bright female lead, rhythmic acoustic strumming, joyful steady groove, simple uplifting chorus` | 100 | 165 | `acoustic guitar, piano, drums` | 보컬 |
| C23 | 가스펠 콰이어 워십 | `Korean gospel worship, soulful female lead, mixed choir responses, handclap feel, joyful groove, clear Korean diction` | 104 | 180 | `piano, bass guitar, drums` | 보컬 |
| C24 | 작은 방 라이브 워십 | `Korean stripped worship, soft female lead, dry intimate room, gentle group harmonies, quiet prayer, restrained dynamics` | 70 | 180 | `acoustic guitar, piano, cello` | 보컬 |

### D. 감상·청년용 장르 변형

아래는 폭을 넓히기 위한 창작 변형이다. 조사 자료가 이 여덟 장르를 현재 인기 순위로 입증한 것은 아니다.

| ID | 제작 방향 | style | BPM | 초 | parts.instruments | 유형 |
| --- | --- | --- | ---: | ---: | --- | --- |
| C25 | 인디 포크 워십 | `Korean indie worship folk, intimate female lead, fingerpicked guitar, organic warmth, gentle harmonies, reflective` | 88 | 180 | `acoustic guitar, piano, cello` | 보컬 |
| C26 | 베드룸 CCM 팝 | `Korean bedroom Christian pop, soft male lead, close microphone, mellow electric piano, understated beat, hopeful` | 84 | 165 | `Rhodes electric piano, bass guitar, brushed drums` | 보컬 |
| C27 | 부드러운 CCM R&B | `Korean Christian R&B, warm female lead, restrained vocal runs, laid back groove, clear Korean diction, intimate` | 78 | 180 | `Rhodes electric piano, bass guitar, drums` | 보컬 |
| C28 | 네오소울 기도곡 | `Korean gospel neo soul, warm male lead, soulful harmonies, relaxed pocket, reflective prayer, mellow` | 82 | 180 | `Rhodes electric piano, bass guitar, brushed drums` | 보컬 |
| C29 | 청년 신스팝 찬양 | `Korean worship synth pop, bright female lead, pulsing synth chords, crisp dance groove, joyful communal hook` | 118 | 165 | `synthesizer, bass guitar, drums` | 보컬 |
| C30 | 고백형 CCM 힙합 | `Korean Christian hip hop, clear rhythmic male rap, melodic sung chorus, steady head nod groove, hopeful testimony` | 88 | 165 | `piano, bass guitar, drums` | 보컬 |
| C31 | 칠 하우스 CCM | `Korean Christian chill house, airy female lead, warm synth chords, four on the floor, gentle uplifting chorus` | 112 | 165 | `synthesizer, bass guitar, drums` | 보컬 |
| C32 | 팝록 찬양 | `Korean worship pop rock, clear mixed vocals, driving guitars, melodic bass, bright communal chorus, energetic` | 128 | 165 | `electric guitar, bass guitar, drums` | 보컬 |

### E. 개인 기도·시편 묵상·잔잔한 플레이리스트

| ID | 제작 방향 | style | BPM | 초 | parts.instruments | 유형 |
| --- | --- | --- | ---: | ---: | --- | --- |
| C33 | 여성 피아노 기도곡 | `Korean piano prayer song, soft female lead, clear Korean diction, spacious pauses, humble, intimate, quiet ending` | 64 | 180 | `piano` | 보컬 |
| C34 | 밤기도·남성 저음 | `Korean night prayer ballad, warm baritone lead, gentle legato, spacious pauses, comforting, restrained` | 62 | 180 | `piano, cello, synth pads` | 보컬 |
| C35 | 시편 탄식에서 신뢰로 | `Korean psalm inspired lament, tender female lead, minor verse colors, hopeful chorus, spacious phrasing, restrained` | 68 | 180 | `piano, cello, string ensemble` | 보컬 |
| C36 | 보사노바 묵상 CCM | `Korean acoustic devotional bossa nova, gentle female lead, light syncopation, warm intimate mix, reflective joy` | 92 | 165 | `classical guitar, upright bass, percussion` | 보컬 |
| C37 | 재즈 기도 CCM | `Korean devotional jazz, tender female lead, mellow harmony, gentle swing, clear Korean diction, intimate room` | 84 | 180 | `Rhodes electric piano, upright bass, brushed drums` | 보컬 |
| C38 | 가족 저녁 기도·자장가 | `Korean Christian lullaby, gentle female lead, simple melody, soft dynamics, reassuring, peaceful bedtime prayer` | 60 | 165 | `piano, music box, cello` | 보컬 |
| C39 | 로파이 기도 연주 | `contemplative Christian lofi instrumental, mellow electric piano, relaxed pocket, warm texture, restrained percussion` | 72 | 180 | `Rhodes electric piano, upright bass, brushed drums` | 연주곡 |
| C40 | 앰비언트 기도 연주 | `contemplative Christian ambient instrumental, soft piano motifs, slow evolving textures, spacious, gentle dynamics` | 60 | 240 | `piano, synth pads, harp` | 연주곡 |

### F. 절기·공동체·축복

| ID | 제작 방향 | style | BPM | 초 | parts.instruments | 유형 |
| --- | --- | --- | ---: | ---: | --- | --- |
| C41 | 대림절 기다림 | `Korean Advent worship, gentle female lead, reflective folk hymn, patient phrasing, growing hope, warm acoustic texture` | 70 | 180 | `acoustic guitar, piano, cello` | 보컬 |
| C42 | 성탄의 기쁨 | `Korean Christmas praise, bright mixed choir, festive acoustic pop, joyful singalong chorus, warm bells` | 110 | 165 | `piano, sleigh bells, percussion` | 보컬 |
| C43 | 고난·십자가 묵상 | `Korean Passion worship ballad, restrained female lead, solemn intimate prayer, sparse strings, humble resolution` | 66 | 180 | `piano, cello, string ensemble` | 보컬 |
| C44 | 부활의 환희 | `Korean Easter praise anthem, bright mixed vocals, jubilant choir responses, driving band, triumphant chorus` | 108 | 180 | `electric guitar, brass section, drums` | 보컬 |
| C45 | 추수·일상의 감사 | `Korean thanksgiving gospel folk, warm male lead, natural strumming, gentle two beat groove, communal gratitude` | 94 | 180 | `acoustic guitar, mandolin, bass guitar` | 보컬 |
| C46 | 파송·선교의 고백 | `Korean sending worship anthem, clear mixed vocals, restrained verses, expansive final chorus, faithful resolve` | 80 | 210 | `piano, electric guitar, drums` | 보컬 |
| C47 | 어린이·가족 찬양 | `Korean family praise, bright mixed vocals, clear Korean diction, playful acoustic groove, short simple chorus` | 112 | 150 | `ukulele, glockenspiel, percussion` | 보컬 |
| C48 | 가정·결혼 축복 | `Korean blessing worship duet, warm male and female vocals, gentle harmonies, tender phrasing, prayerful, intimate` | 74 | 180 | `piano, string ensemble, harp` | 보컬 |

<a id="requests"></a>

## 상세 요청 프롬프트 12개

각 블록은 **AI에게 주는 작업 지시**이며 그대로 `style`에 붙여 넣는 긴 caption이 아니다. AI는 지침을 읽고 표의 값과 짧은 태그를 실제 CLI JSON으로 옮긴다. 기본은 검토 후 생성이고, 생성 수량을 명시한 범위에서 실행한다.

### YuE 모델 1. 기본 여성 모던 워십 — C17

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
Road Music의 AGENTS.md와 docs/ccm-prompts.md를 따라 C17 기반 한국어 CCM 1곡을 준비해줘.
제목은 "주의 손을 따라", 여성 리드, 76 BPM, 180초, seed 42로 해줘.
주악기는 piano·acoustic guitar·drums, strict=false로 설정해줘.
가사는 작은 일상에서 받은 은혜에 감사하고 주님의 손을 따라 걷는 고백으로 새로 써줘.
Verse 2개, 같은 Chorus 반복, 짧은 Bridge 뒤 마지막 Chorus로 구성해줘.
clear Korean diction·congregational unison·gradual build를 짧은 style에 담아줘.
실제 가사·최종 전달 style·지원 JSON·검증 결과를 보여주고 승인 후 1곡 생성해줘.
```

### YuE 모델 2. 과거 복음성가의 담백한 공동체 감성 — C05

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C05를 기준으로 "오늘의 자리에서"라는 한국어 감사 복음성가 1곡을 준비해줘.
86 BPM, 180초, acoustic guitar·piano·percussion, 담백한 혼성 유니즌을 원해.
작은 방에서 함께 부르는 질감, 과한 솔로와 애드리브를 줄인 후렴으로 설계해줘.
가사는 노동과 식탁과 이웃의 장면에서 은혜를 발견하는 내용으로 새로 써줘.
특정 옛 노래를 재현하지 말고 통기타·쉬운 후렴·소박한 화음의 특징만 사용해줘.
가사와 옵션을 검토받은 뒤 생성하고 완성 음원과 실제 설정을 제공해줘.
```

### YuE 모델 3. 남성 레트로 소프트록 CCM — C06

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C06으로 한국어 남성 보컬 CCM 1곡을 준비해줘.
78 BPM, 180초, piano·electric guitar·bass guitar, 아날로그 온기와 절제된 기타를 원해.
가사는 지친 하루 끝에 받은 위로를 주님께 고백하는 간증으로 새로 써줘.
절은 구체적인 하루의 장면, 후렴은 짧고 넓게 펼쳐지는 신앙고백으로 구성해줘.
1980년대 음향 질감을 참고하되 실존 가수 이름·기존 가사·멜로디는 사용하지 마.
전체 가사와 전달 style이 잘리지 않는지 검증하고 검토 후 생성해줘.
```

### YuE 모델 4. 남성 앤섬·집회형 워십 — C18

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C18을 기준으로 한국어 남성 리드의 회중 워십 1곡을 준비해줘.
78 BPM, 210초, piano·electric guitar·drums, strict=false로 해줘.
clean delay guitar와 넓은 후렴을 요청하되 첫 Verse는 작게 시작해줘.
가사는 "우리" 시점으로 주님의 신실하심을 고백하고 마지막 Bridge에서 헌신으로 응답해줘.
회중이 따라 부르는 의도로 짧은 후렴과 절제된 보컬 장식을 요청해줘.
회중 음역과 조성이 실제로 보장되는 옵션인 것처럼 안내하지 말고 검증안을 먼저 보여줘.
```

### YuE 모델 5. 여성 6/8 느낌의 예배 발라드 — C19

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C19 기반의 한국어 여성 워십 발라드 1곡을 준비해줘.
72 BPM, 210초, piano·electric guitar·string ensemble, six eight time로 요청해줘.
가사는 불확실한 길에서도 주님이 동행하신다는 고백으로 새로 써줘.
여백 있는 Verse, 짧은 Pre-Chorus, 넓은 Chorus, Bridge와 마지막 Chorus로 구성해줘.
6/8 느낌은 six eight time, 조성 의도는 D major로 style에 넣고 박자·조성 전용 JSON 키는 추가하지 마.
최종 전달 style과 가사·JSON을 보여주고 승인받은 안으로만 생성해줘.
```

### YuE 모델 6. 리드와 콰이어가 응답하는 가스펠 — C23

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C23으로 한국어 가스펠 워십 1곡을 준비해줘.
104 BPM, 180초, piano·bass guitar·drums, 소울풀한 여성 리드와 혼성 응답 화음을 원해.
회중의 감사 고백을 주제로 리드 문장과 짧은 응답 문장을 실제 가사에 번갈아 써줘.
mixed choir responses·handclap feel은 style에 넣고 가사에는 지원 섹션 태그만 사용해줘.
choirSize나 줄별 가수 배정 필드는 만들지 말고 요청의 한계를 설명해줘.
원곡을 차용하지 않은 가사·최종 옵션을 먼저 검토받고 생성해줘.
```

### YuE 모델 7. 일상 감상용 CCM R&B — C27

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C27 기반의 한국어 여성 CCM R&B 1곡을 준비해줘.
78 BPM, 180초, Rhodes electric piano·bass guitar·drums로 해줘.
가사는 관계 속에서 용서를 배우는 하루와 주님의 은혜를 연결해 새로 작성해줘.
laid back groove, warm female lead, restrained vocal runs, clear Korean diction을 요청해줘.
회중용 큰 브리지보다 짧고 기억에 남는 후렴과 리듬의 여백을 우선해줘.
이 레시피를 현재 CCM 시장 1위 스타일로 소개하지 말고 취향별 변형으로 설명해줘.
가사·전달 style·JSON을 검토받은 뒤 1곡 생성해줘.
```

### YuE 모델 8. 청년 팝록 찬양 — C32

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C32로 한국어 청년 팝록 찬양 1곡을 준비해줘.
128 BPM, 165초, electric guitar·bass guitar·drums, 밝은 혼성 후렴을 원해.
가사는 부활의 새 삶과 일상의 담대한 걸음을 "우리" 시점으로 새로 써줘.
짧은 Verse와 Pre-Chorus, 모두 함께 외우기 쉬운 Chorus, 마지막 Chorus로 설계해줘.
빠른 템포에서 발음이 빽빽하지 않게 한 줄을 짧게 하고 장식적인 고음을 줄여줘.
완성 가사·최종 전달 style·옵션을 먼저 보여주고 승인 후 생성해줘.
```

### YuE 모델 9. 로파이 묵상 플레이리스트용 연주 — C39

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C39의 기도·묵상용 로파이 연주곡 1곡을 준비해줘.
72 BPM, 180초, Rhodes electric piano·upright bass·brushed drums로 해줘.
instrumental=true, lyrics는 빈 문자열, parts.structure="loop", strict=false로 해줘.
부드러운 전기피아노 모티프와 절제된 리듬을 요청하고 성가대·보컬 태그는 넣지 마.
실제 예배 현장 녹음이나 특정 찬송가 멜로디 재현이라고 소개하지 마.
최종 style에 무보컬 의도가 전달되는지 확인해줘. Vocal 성부가 자동으로 비워진다고 보장하지 마.
승인 후 생성하며 허밍·보컬 유무와 반복 연결은 청취하지 않았다면 미확인으로 남겨줘.
```

### YuE 모델 10. 잔잔한 기도 앰비언트 — C40

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C40 기반의 기도·성경 읽기용 앰비언트 연주곡 1곡을 준비해줘.
60 BPM, 240초, piano·synth pads·harp, instrumental=true, lyrics=""로 해줘.
parts.structure="theme", strict=false로 하고 느리게 변하는 배경과 짧은 피아노 모티프를 요청해줘.
큰 드럼·보컬 합창·극적인 클라이맥스 태그를 동시에 넣지 마.
주제는 평안과 동행이지만 연주만으로 특정 성경 내용을 전달한다고 주장하지 마.
지원 입력과 최종 전달 style을 검토받은 뒤 1곡 생성해줘.
```

### YuE 모델 11. 부활절 공동체 찬양 — C44

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
C44로 한국어 부활절 찬양 1곡을 준비해줘.
108 BPM, 180초, electric guitar·brass section·drums, 밝은 혼성 리드와 응답형 후렴을 원해.
가사는 십자가의 슬픔에서 부활의 소망과 이웃에게 전하는 새 삶으로 이어지게 새로 써줘.
Verse 2개와 같은 Chorus 반복, 짧은 Bridge, 마지막 Chorus의 구조로 해줘.
예배 대상과 부활의 의미가 분명하게 드러나며 기존 부활 찬송가 문장을 복사하지 않게 해줘.
전체 가사·전달 style·JSON을 검증해 보여주고 승인 후 생성해줘.
```

### YuE 모델 12. 같은 고백을 세 편곡으로 비교

mode:"song"과 cot:"full"을 기본 설정으로 검토하고 목표 초를 실제 길이 제어로 보지 마.
공개 yue:capabilities·song:prepare로 실효 입력을 확인하고 완료 뒤 EOS·잘림·가창을 확인해줘.
```text
선택한 engine:"yue" 또는 engine:"yue-mlx"를 명시해 그대로 유지해줘.
제공/승인 가사가 있으면 보존하고, 아래 새 작사 지시는 가사가 없을 때만 적용해줘.
"주님의 동행을 신뢰한다"는 같은 한국어 창작 가사를 먼저 작성해 검토받아줘.
승인 후 C05 소그룹 복음성가, C17 여성 모던 워십, C27 CCM R&B로 각각 1곡씩 생성해줘.
세 곡 모두 길이는 180초, seed는 42로 기록하고 각 레시피의 BPM·악기는 적용해줘.
서로 다른 세 입력이므로 count=3 한 번으로 묶지 말고 count=1인 별도 요청 3개로 제출해줘.
이 비교는 여러 옵션을 의도적으로 바꾼 편곡 비교이며 단일 요소 A/B 실험이라고 부르지 마.
기존 곡은 보존하고 결과 3곡의 음원·가사·전달 style·BPM·악기·실제 경로를 함께 제공해줘.
청취하지 않았다면 우열을 평가하지 말고 비교할 수 있도록 파일을 모두 가져와줘.
```

## 한국어 창작 가사 8편

문서용 새 창작 예시다. 기존 찬송가·현대 워십 가사나 특정 성경 번역문을 옮긴 것이 아니다. 실제 곡의 길이와 호흡에 맞춰 검토하고, 사용자에게 원문 보존을 요청받았다면 임의로 바꾸지 않는다. “마지막 후렴 반복” 같은 지시문 대신 실제 부를 문장을 다시 적었다.

### L01. 주의 손을 따라 — C17·C18

```lyrics
[Verse]
아직 잠든 길을 걸을 때
작은 빛이 발끝에 머물러
오늘 내게 맡긴 한 걸음
주의 손을 따라 내딛네
[Chorus]
주님 내 곁에 계시니
멀리 보이지 않아도 걸어가리
오늘도 먼저 주신 은혜
내 작은 노래로 응답하리
[Verse]
서로 다른 하루를 안고
다시 모여 주 앞에 서네
우리 곁의 이웃을 향해
받은 사랑 흘려보내리
[Chorus]
주님 내 곁에 계시니
멀리 보이지 않아도 걸어가리
오늘도 먼저 주신 은혜
내 작은 노래로 응답하리
[Bridge]
내 손을 펴서 이웃을 안고
주의 손을 따라 살아가리
[Chorus]
주님 내 곁에 계시니
멀리 보이지 않아도 걸어가리
오늘도 먼저 주신 은혜
내 작은 노래로 응답하리
```

### L02. 오늘의 자리에서 — C05·C09

```lyrics
[Verse]
일을 마친 손을 모으니
분주했던 마음도 쉬네
함께 앉은 작은 식탁에
오늘 받은 은혜를 놓네
[Chorus]
오늘의 자리에서 주를 찬양해
작은 나눔 속에 사랑을 배우네
우리에게 맡긴 평범한 하루
감사의 노래로 주께 드리네
[Verse]
이름 없이 건넨 인사도
지친 이를 기다린 시간도
주께 받은 사랑 기억해
서로에게 선물이 되네
[Chorus]
오늘의 자리에서 주를 찬양해
작은 나눔 속에 사랑을 배우네
우리에게 맡긴 평범한 하루
감사의 노래로 주께 드리네
[Bridge]
큰 말보다 작은 섬김으로
주님의 사랑 전하게 하소서
[Chorus]
오늘의 자리에서 주를 찬양해
작은 나눔 속에 사랑을 배우네
우리에게 맡긴 평범한 하루
감사의 노래로 주께 드리네
```

### L03. 주께 드리는 아침 — C21·C22

```lyrics
[Verse]
새로 열린 하루의 문에
어제 걱정 내려놓아요
먼저 우리 찾아온 은혜
기쁜 노래 되어 흐르네
[Pre-Chorus]
두 손을 들고 마음을 열어
우리의 주를 함께 찬양해
[Chorus]
주께 드리는 이 아침
우리의 걸음 새로워져
받은 사랑 나누면서
오늘도 주와 함께 가요
[Verse]
서로 다른 목소리 모여
하나 되어 노래할 때에
우리 곁에 지친 이에게
따뜻한 손 먼저 내밀리
[Chorus]
주께 드리는 이 아침
우리의 걸음 새로워져
받은 사랑 나누면서
오늘도 주와 함께 가요
[Bridge]
기쁨도 어려움도 주께 맡겨요
함께 걸어갈 길을 열어 주소서
[Chorus]
주께 드리는 이 아침
우리의 걸음 새로워져
받은 사랑 나누면서
오늘도 주와 함께 가요
```

### L04. 눈물 곁의 기도 — C10·C33·C35

```lyrics
[Verse]
말이 되지 않는 마음을
조용하게 주 앞에 놓네
답을 찾지 못한 오늘도
나의 기도 들어 주소서
[Chorus]
눈물 곁에 머무시는 주
서둘러 웃지 않아도 안아 주시네
아직 다 알 수 없는 길 위에
주님의 동행을 신뢰하네
[Verse]
닫힌 문을 바라보면서
작은 숨을 다시 고르네
이 밤에도 홀로 두지 않으실
주를 향해 마음을 여네
[Chorus]
눈물 곁에 머무시는 주
서둘러 웃지 않아도 안아 주시네
아직 다 알 수 없는 길 위에
주님의 동행을 신뢰하네
[Bridge]
지친 이의 손을 잡을 힘을 주시고
받은 위로 나누며 걷게 하소서
[Chorus]
눈물 곁에 머무시는 주
서둘러 웃지 않아도 안아 주시네
아직 다 알 수 없는 길 위에
주님의 동행을 신뢰하네
```

### L05. 함께 부르는 은혜 — C03·C23

```lyrics
[Verse]
누가 우리 먼저 찾으셨나
주님의 사랑 우리를 찾으셨네
누가 작은 손을 붙드셨나
주님의 은혜 우리를 세우셨네
[Chorus]
함께 부르자 받은 은혜를
감사로 부르자 주님의 사랑
서로를 향해 손을 내밀며
기쁨으로 주께 응답하자
[Verse]
누가 닫힌 마음 열어 주셨나
주님의 사랑 우리를 만나셨네
누가 새 길 걷게 하셨나
주님의 은혜 우리를 이끄셨네
[Chorus]
함께 부르자 받은 은혜를
감사로 부르자 주님의 사랑
서로를 향해 손을 내밀며
기쁨으로 주께 응답하자
[Bridge]
한 사람의 노래 모여
우리의 감사 되리라
[Chorus]
함께 부르자 받은 은혜를
감사로 부르자 주님의 사랑
서로를 향해 손을 내밀며
기쁨으로 주께 응답하자
```

### L06. 새벽 문을 여신 주 — C44

```lyrics
[Verse]
슬픔 안고 기다린 새벽
고요 속에 빛이 번지네
죽음보다 크신 사랑이
우리에게 새 길 여셨네
[Chorus]
다시 사신 예수님
우리의 소망 되시네
새벽 문을 여신 주
새로운 삶으로 부르시네
[Verse]
두려움에 닫혀 있던 손
이웃 향해 다시 펴 보네
부활하신 주를 따르며
오늘 여기 사랑 심으리
[Chorus]
다시 사신 예수님
우리의 소망 되시네
새벽 문을 여신 주
새로운 삶으로 부르시네
[Bridge]
우리의 기쁨 작은 섬김 되어
소망 기다리는 이에게 닿으리
[Chorus]
다시 사신 예수님
우리의 소망 되시네
새벽 문을 여신 주
새로운 삶으로 부르시네
```

### L07. 기다림의 불빛 — C41

```lyrics
[Verse]
긴 저녁에 불을 밝히고
조용하게 마음을 모아
낮은 곳에 오신 주님을
기다리는 노래 부르네
[Chorus]
기다림의 작은 불빛
주를 향해 오늘도 켜 두리
외로운 이 곁을 지키며
주님의 평화 맞이하리
[Verse]
차가워진 거리 끝에도
함께 나눌 온기를 찾아
우리에게 오신 사랑을
작은 환대 속에 담으리
[Chorus]
기다림의 작은 불빛
주를 향해 오늘도 켜 두리
외로운 이 곁을 지키며
주님의 평화 맞이하리
[Outro]
낮은 자리 찾아오신 주
우리 마음에도 머무소서
```

### L08. 평안을 전하는 집 — C48

```lyrics
[Verse]
같은 문을 열고 들어와
서로 다른 하루를 듣네
옳은 말보다 먼저 안아 줄
넓은 마음 주께 구하네
[Chorus]
주님 이 집에 평안을 주시고
우리의 말에 사랑을 담아 주소서
받은 은혜 이웃에게 흘러
함께 쉬어 가는 집 되게 하소서
[Verse]
서툰 날도 함께 배우며
먼저 건넬 용서를 찾아
작은 약속 지켜 가는 길
주님 우리 손을 잡으소서
[Chorus]
주님 이 집에 평안을 주시고
우리의 말에 사랑을 담아 주소서
받은 은혜 이웃에게 흘러
함께 쉬어 가는 집 되게 하소서
[Outro]
우리 곁에 머문 이들에게
주의 평안 전하게 하소서
```

<a id="json"></a>

## YuE 모델의 완전한 CLI 입력 JSON 4개

아래는 같은 창작 가사·편성 의도를 보존한 **Apple Silicon yue-mlx 전용 song:prepare/song:generate 입력**이다. Windows NVIDIA에서 yue를 명시 선택한 경우에만 해당 설치 상태에 맞는 engine 값을 사용한다. 숫자 목표 길이를 맞추려고 가사를 줄이거나 오디오를 자르지 않는다. advanced는 생략하여 선택 모드의 실효 기본값을 확인한다. runtime이나 모델·VAE 경로도 임의 변경하지 않는다.

### YuE MLX 입력 1. 주의 손을 따라

```json
{
  "title": "주의 손을 따라",
  "engine": "yue-mlx",
  "style": "Korean contemporary worship, warm female lead, congregational unison, clear Korean diction, gradual build, spacious chorus",
  "lyrics": "[Verse]\n아직 잠든 길을 걸을 때\n작은 빛이 발끝에 머물러\n오늘 내게 맡긴 한 걸음\n주의 손을 따라 내딛네\n[Chorus]\n주님 내 곁에 계시니\n멀리 보이지 않아도 걸어가리\n오늘도 먼저 주신 은혜\n내 작은 노래로 응답하리\n[Verse]\n서로 다른 하루를 안고\n다시 모여 주 앞에 서네\n우리 곁의 이웃을 향해\n받은 사랑 흘려보내리\n[Chorus]\n주님 내 곁에 계시니\n멀리 보이지 않아도 걸어가리\n오늘도 먼저 주신 은혜\n내 작은 노래로 응답하리\n[Bridge]\n내 손을 펴서 이웃을 안고\n주의 손을 따라 살아가리\n[Chorus]\n주님 내 곁에 계시니\n멀리 보이지 않아도 걸어가리\n오늘도 먼저 주신 은혜\n내 작은 노래로 응답하리",
  "targetSeconds": 180,
  "count": 1,
  "seed": "831001",
  "instrumental": false,
  "parts": {
    "instruments": [
      "piano",
      "acoustic guitar",
      "drums"
    ],
    "bpm": 76
  },
  "mode": "song",
  "cot": "full"
}
```

### YuE MLX 입력 2. 함께 부르는 은혜

```json
{
  "title": "함께 부르는 은혜",
  "engine": "yue-mlx",
  "style": "Korean gospel worship, soulful female lead, mixed choir responses, handclap feel, joyful groove, clear Korean diction",
  "lyrics": "[Verse]\n누가 우리 먼저 찾으셨나\n주님의 사랑 우리를 찾으셨네\n누가 작은 손을 붙드셨나\n주님의 은혜 우리를 세우셨네\n[Chorus]\n함께 부르자 받은 은혜를\n감사로 부르자 주님의 사랑\n서로를 향해 손을 내밀며\n기쁨으로 주께 응답하자\n[Verse]\n누가 닫힌 마음 열어 주셨나\n주님의 사랑 우리를 만나셨네\n누가 새 길 걷게 하셨나\n주님의 은혜 우리를 이끄셨네\n[Chorus]\n함께 부르자 받은 은혜를\n감사로 부르자 주님의 사랑\n서로를 향해 손을 내밀며\n기쁨으로 주께 응답하자\n[Bridge]\n한 사람의 노래 모여\n우리의 감사 되리라\n[Chorus]\n함께 부르자 받은 은혜를\n감사로 부르자 주님의 사랑\n서로를 향해 손을 내밀며\n기쁨으로 주께 응답하자",
  "targetSeconds": 180,
  "count": 1,
  "seed": "831001",
  "instrumental": false,
  "parts": {
    "instruments": [
      "piano",
      "bass guitar",
      "drums"
    ],
    "bpm": 104
  },
  "mode": "song",
  "cot": "full"
}
```

### YuE MLX 입력 3. 고요한 기도의 자리

```json
{
  "title": "고요한 기도의 자리",
  "engine": "yue-mlx",
  "style": "contemplative Christian lofi instrumental, mellow electric piano, relaxed pocket, warm texture, restrained percussion",
  "lyrics": "",
  "targetSeconds": 180,
  "count": 1,
  "seed": "831001",
  "instrumental": true,
  "parts": {
    "instruments": [
      "Rhodes electric piano",
      "upright bass",
      "brushed drums"
    ],
    "bpm": 72,
    "structure": "loop"
  },
  "mode": "song",
  "cot": "full"
}
```

### YuE MLX 입력 4. 말씀 곁의 여백

```json
{
  "title": "말씀 곁의 여백",
  "engine": "yue-mlx",
  "style": "contemplative Christian ambient instrumental, soft piano motifs, slow evolving textures, spacious, gentle dynamics",
  "lyrics": "",
  "targetSeconds": 240,
  "count": 1,
  "seed": "831001",
  "instrumental": true,
  "parts": {
    "instruments": [
      "piano",
      "synth pads",
      "harp"
    ],
    "bpm": 60,
    "structure": "theme"
  },
  "mode": "song",
  "cot": "full"
}
```

먼저 JSON 하나를 파일로 저장해 `song:prepare --file`로 engine·최종 style/lyrics·effective·nativeRequest를 확인한다. 승인된 경우에만 같은 파일로 song:generate를 제출하고 job:wait을 기다린다. 연주곡은 무보컬 의도와 실제 보컬 누출·Vocal/Ins 성부를 별도로 검수한다. 빈 가사 계획을 음원화할 때는 현재 song:render가 아닌 새 mode:song 생성 또는 검증 가능한 MLX plan 작업 산출물 재사용을 사용한다.

<a id="workflow"></a>

## 입력 점검·프리셋·비교

### YuE 모델에서 생성 전에 확인

`yue:capabilities`로 선택 엔진과 16개 입력·replay 허용키를 읽고 `song:prepare`로 원문/전달본/실효 옵션을 대조한다. mode:plan은 악보 모델 추론이며 음원을 만들지 않는다. 목표 길이는 기록용이다. 가사 또는 style을 바꾸면 새 song:generate 입력을 준비하고, 악보만 바꾸면서 원문을 유지하는 경우에만 song:render를 사용한다.

### 자주 쓰는 CCM 프리셋 저장

기존 이름은 먼저 확인한다. 아래 명령은 **사용자가 저장을 요청했을 때** 실행한다. 프리셋은 스타일·parts·연주곡 여부를 재사용하며 가사·길이·seed 전체를 저장하는 기능이 아니다.

```bash
node cli/road-music.js presets:list
node cli/road-music.js presets:save --json '{"preset":{"name":"CCM 여성 모던 워십 C17","style":"Korean contemporary worship, warm female lead, congregational unison, clear Korean diction, gradual build, spacious chorus","instrumental":false,"parts":{"instruments":["piano","acoustic guitar","drums"],"bpm":76,"strict":false},"folder":"CCM"}}'
```

곡 전체 설정을 다시 쓰려면 승인한 입력 JSON을 함께 보관한다. C17 프리셋을 불러왔더라도 새 곡의 가사·180초 길이·seed 등은 생성 요청에서 확인한다.

### YuE 모델에서 한 요소를 바꾸는 비교

가사·style·선택 engine·실제 ABC/seed를 기준선으로 기록한다. 제공 ABC를 고정하면 ABC샘플러는 적용 대상이 아니며 targetSeconds만 바꾸는 것도 새 음악 조건 비교가 아니다. semantic sampler나 semantic CFG를 비교하려면 저장 plan 이후 재실행을 검토하고, ODE만 비교하려면 검증 semantic/noise를 재사용할 수 있는지 확인한다. 실제 가사나 style을 바꾸면 replay가 아니라 새 생성 입력을 사용한다. 각 비교는 승인한 곡 수 안에서 하나의 변수만 바꾸고 원문·원곡을 보존한다.

### 생성 후 확인할 것

| 확인 항목 | 실제로 확인할 내용 |
| --- | --- |
| 신앙 주제·전달 | 대상이 명확한지, 선택한 감사·탄식·소망·절기 주제가 가사와 일치하는지 |
| 가사 | 잘림·빠뜨림·임의 영어·의미 변화·한국어 발음 문제가 있는지 |
| 회중용 적합성 | 함께 부르기 쉬운 후렴과 음역인지, 길고 복잡한 애드리브가 방해하는지 |
| 편곡 | 개인 기도와 집회형 대비, 요청한 주악기·박자 느낌·보컬 질감이 실제로 들리는지 |
| 연주곡 | 허밍·합창·발화가 섞이지 않았는지, 끝이 부자연스럽게 끊기지 않는지 |
| 파일 | 완료 상태·실제 길이·내보내기 경로·클리핑·시작과 끝의 잘림 |

청취하지 않았다면 음질·정확한 보컬 음역·키·박자·회중 적합성은 미확인으로 남긴다. 현재 문서의 예시는 스키마·프롬프트 조합·태그·길이를 검사한 기본 자료이며, 48개 스타일을 전부 생성해 들어본 품질 인증이 아니다.

다음 작업은 [일반 옵션](music-options.md), [가사 태그](lyrics-tags.md), [조사 절차](music-research.md), [검토·자동 생성](music-review.md)에서 이어간다.
