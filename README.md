<p align="center">
  <a href="https://github.com/roadkwonai/music-road-skills"><img src="docs/assets/banner.svg" alt="Music Road Skills — AI 음악을 HTML 검토와 모션그래픽 영상으로 잇는 스킬 모음" width="900"></a>
</p>

<h1 align="center">Music Road Skills</h1>

<p align="center"><strong>Road Music에서 만든 음악을 보고, 듣고, 고른 뒤 모션그래픽 영상으로 완성하는 공개 Codex·Claude Code·Antigravity 스킬 묶음입니다.</strong></p>

<p align="center">
  <a href="https://github.com/roadkwonai/music-road-skills/releases/tag/v0.1.0"><img src="https://img.shields.io/badge/release-v0.1.0-172942?style=flat-square" alt="Release v0.1.0"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-172942?style=flat-square" alt="MIT License"></a>
  <a href="docs/install.md"><img src="https://img.shields.io/badge/runtime-Node.js%2024-172942?style=flat-square" alt="Node.js 24"></a>
  <a href="docs/html-studio.md"><img src="https://img.shields.io/badge/studio-local%20HTML-172942?style=flat-square" alt="local HTML Studio"></a>
</p>

<p align="center"><a href="#quickstart">빠른 시작</a> · <a href="#skills">스킬</a> · <a href="docs/README.md">문서</a> · <a href="release/README.md">릴리스 노트</a> · <a href="https://github.com/roadkwonai/music-road-skills/releases/latest">다운로드</a></p>

> [!IMPORTANT]
> 이 저장소는 **Showreel/JIZURA용 스킬·HTML 템플릿·업데이트 도구**를 배포합니다. LTX 2.5 모델을 설치해 만드는 `road-music-mv` 감독 스킬과 모델·개인 음원·생성 프로젝트는 포함하지 않습니다.

<details>
<summary><strong>목차 펼치기</strong></summary>

- [무엇을 할 수 있나요?](#what)
- [빠른 시작](#quickstart)
- [스킬](#skills)
- [음악에서 영상까지](#workflow)
- [HTML 제작실](#studio)
- [업데이트와 릴리스](#updates)
- [문서와 라이선스](#docs)

</details>

---

<a id="what"></a>

## 무엇을 할 수 있나요?

| 작업 | 결과 | 사용하는 스킬 |
| --- | --- | --- |
| 회전 CD·스펙트럼 플레이리스트 | 장르별 CD/리듬 템플릿, 대기곡·채널명·가사 표시 | [Showreel 음악 모션그래픽](docs/showreel-motion.md) |
| 한 곡 M/V | 스토리보드, 생성 이미지, Showreel 전곡 편집 | [Road Music 쇼릴 MV](docs/showreel-mv.md) |
| 키네틱 타이포 | JIZURA 네이티브 프로젝트와 MP4 | [JIZURA 음악 스튜디오](docs/jizura-studio.md) |
| 화면에서 선택·검수 | 스타일 선택, 음악/영상 재생, 저장된 선택·피드백 | [Road Music 영상 제작실](docs/html-studio.md) |
| 설치 상태·신규 버전 확인 | 보존형 설치, 확인과 설치를 분리한 업데이트 | [스킬 업데이트](docs/updates.md) |

`road-music-showreel-cd`는 이전 호출을 보존하는 호환 이름입니다. 새 작업은 `road-music-showreel-playlist`를 사용합니다. 자세한 차이는 [Showreel CD 호환 안내](docs/showreel-cd.md)에 있습니다.

## 실제 형식 샘플

모든 샘플은 형식 비교용 기존 제작물입니다. 현재 선택한 곡의 결과가 아니며, 샘플의 길이·원음·제작 근거는 [예시 목록](skills/road-music-video-studio/assets/examples.json)이 기준입니다.

| 형식 | 최근 프로젝트 샘플 | 길이 | 구간 |
| --- | --- | --- | --- |
| Road Music Showreel CD | [락발라드 — 아직 나의 봄](skills/road-music-video-studio/assets/examples/showreel-cd.mp4) | 24초 | 0–12초 · 27–39초 |
| Road Music 쇼릴 MV | [벨루나 — 프리즘 (VELUNE·벨루네 MV v5)](skills/road-music-video-studio/assets/examples/20261018-confirmed/showreel-mv-prism.mp4) | 18초 | 0–18초 |
| JIZURA 음악 스튜디오 | [벨루나 — 어디든 좋아](skills/road-music-video-studio/assets/examples/20261018-confirmed/jizura-eodideun-joha.mp4) | 18초 | 원곡 40–58초 |
| Showreel 음악 모션그래픽 | [벨루나 — 내일로 달려](skills/road-music-video-studio/assets/examples/20261018-confirmed/showreel-motion-tomorrow.mp4) | 24초 | 원곡 53.82–77.82초 |

[최근 샘플 선정·출처·구간 안내](docs/samples.md)

<a id="quickstart"></a>

## 빠른 시작

Node.js 24와 Git이 필요합니다. 이 명령은 현재 체크아웃을 Codex 스킬 경로(`CODEX_HOME/skills`, 기본 `~/.codex/skills`)에 설치합니다.

```bash
git clone https://github.com/roadkwonai/music-road-skills.git
cd music-road-skills
node skills/road-music-skills-update/scripts/manage.cjs install --source "$PWD"
```

위 상대 경로와 `$PWD`는 바로 앞의 `cd music-road-skills`로 들어간 저장소 루트 기준이다. 설치본을 다른 작업 디렉터리에서 관리할 때는 현재 읽은 `SKILL.md`의 실제 절대 경로를 사용한다.

설치 도구는 기본적으로 `CODEX_HOME/skills`(없으면 `~/.codex/skills`)를 대상으로 하며, 기존 대상은 먼저 보존용 백업을 만듭니다. 영상 엔진, AI 모델, 음원은 설치하지 않습니다. [설치 상세](docs/install.md)

Antigravity App/IDE는 `~/.gemini/config/skills`, Antigravity CLI는 `~/.gemini/antigravity-cli/skills`, 공통 프로젝트 설치는 `.agents/skills`를 사용합니다. 두 호스트는 같은 스킬·프로젝트 manifest를 공유하지만, 스킬을 찾는 위치는 각각의 공식 설정이 기준입니다. [Antigravity 설치·실행 안내](docs/antigravity.md)

Claude Code는 전역 `~/.claude/skills`, 프로젝트 `.claude/skills`에 설치합니다. 새 이미지가 필요한 Showreel 작업은 별도 `gpt-image` 스킬이 있어야 하며, 그 스킬이 ChatGPT 로그인 Codex CLI를 통해 내장 `image_gen`으로 연결합니다. [Claude Code 설치·사용 안내](docs/claude.md)

```bash
# 현재 저장소를 Antigravity App/IDE 전역 스킬 경로에 설치
node skills/road-music-skills-update/scripts/manage.cjs install --source "$PWD" --host antigravity
```

Codex에서 다음처럼 요청할 수 있습니다.

```text
$road-music-showreel-playlist로 이 음악을 분석해 HTML에서 스타일과 채널명을 고르게 하고,
선택값을 반영한 전체 길이 모션그래픽 플레이리스트를 만들어줘.
```

<a id="skills"></a>

## 스킬

| 이름 | 용도 | 시작 문서 |
| --- | --- | --- |
| `road-music-showreel-playlist` | CD·리듬 캔버스·여러 곡 Showreel 플레이리스트 | [가이드](docs/showreel-motion.md) |
| `road-music-showreel-cd` | 기존 CD 프리셋 이름의 호환 경로 | [호환 안내](docs/showreel-cd.md) |
| `road-music-showreel-mv` | 이미지·스토리보드·리듬 편집형 Showreel M/V | [가이드](docs/showreel-mv.md) |
| `road-music-jizura-playlist` | JIZURA 키네틱 타이포와 편집 가능한 프로젝트 | [가이드](docs/jizura-studio.md) |
| `road-music-video-studio` | 선택·재생·검수·피드백을 위한 로컬 HTML 제작실 | [가이드](docs/html-studio.md) |
| `road-music-skills-update` | 설치·버전 확인·보존 업데이트 | [가이드](docs/updates.md) |

<a id="workflow"></a>

## 음악에서 영상까지

```mermaid
flowchart LR
  A[Road Music CLI로 음악 생성] --> B[job:wait로 완료 확인]
  B --> C[songs:list의 절대 음원 경로]
  C --> D[motion:handoff]
  D --> E[HTML 제작실: 듣기·스타일 선택·피드백]
  E --> F[Showreel 또는 JIZURA 스킬]
  F --> G[MP4·프로젝트·검수 페이지]
```

Road Music CLI를 새로 설치할 때에는 Node 런타임을 준비한 뒤, CLI가 번들한 이 스킬 묶음도 함께 설치합니다. AI는 `song:generate` → `job:wait` → `songs:list`에서 반환한 **절대 경로** → `motion:handoff` 순서로 넘깁니다. CLI의 `skills:status`, `skills:check`, `skills:install`, `skills:update`, `skills:watch`, `motion:studio`, `motion:handoff`는 이 연결을 위한 공개 명령입니다. 각 명령의 실제 입력값은 설치한 Road Music CLI의 `schema`가 기준입니다. [CLI 연계 가이드](docs/cli-workflow.md)

> [!NOTE]
> Codex는 호스트의 내장 `image_gen`, Antigravity는 Nano Banana 네이티브 기능을 사용합니다. Claude Code는 설치된 `gpt-image` 스킬의 ChatGPT 로그인 Codex CLI 브리지를 사용합니다. Showreel MV는 이 기본 경로를 벗어나 `gpt-image-2.5` 같은 별도 유료 API로 자동 전환하지 않습니다. CLI가 이미지 생성을 내장 실행하는 기능은 아닙니다. ASR 기반 자막 시간도 자동 초안일 수 있으므로 100% 가창 싱크로 표현하지 않습니다.

<a id="studio"></a>

## HTML 제작실

제작 중에는 텍스트 선택만 받지 않습니다. 로컬 HTML 페이지에서 다음을 확인하고 저장합니다.

- 스타일·프리셋을 영상 카드로 비교하고 선택 — 대표 썸네일·제작 스타일/장르 태그 필터와 전체 보기를 제공
- 음악과 미리보기 영상을 재생하고, 표시 요소와 채널명을 정함
- 선택값·피드백을 프로젝트 기록으로 저장해 다음 제작 단계에 전달. Showreel 선택은 기존 `plan/create --selection`에 바로 쓸 수 있는 요청 파일도 만듦
- 완성본·자막·프로젝트 산출물을 검수 페이지에서 다시 확인
- 프로젝트별 음악·영상 제작 시간 비교, 그룹 상세의 과정별 시간 파이와 프롬프트/결과 이력 확인
- 현재 schema 기반 악기·옵션 활용 참고를 카테고리/태그로 찾아 예시 복사. [기능 검수](docs/ui-feature-review.md)

검수 전용으로 열면 선택과 피드백을 여러 번 저장해도 창이 종료되지 않습니다. 다른 터미널에서 새 결과를 `publish`한 뒤 화면의 **새 결과 확인**으로 갱신하고, 마지막에 **검수 마치기**를 눌러 세션을 종료합니다.

```bash
VIDEO_STUDIO_HOST="${ROAD_MUSIC_HOST:-codex}" # Claude Code에서는 claude
python3 skills/road-music-video-studio/scripts/studio.py init \
  --out /absolute/path/to/project --host "$VIDEO_STUDIO_HOST"
python3 skills/road-music-video-studio/scripts/studio.py serve \
  --project /absolute/path/to/project --host "$VIDEO_STUDIO_HOST" --open
```

처음에는 음악 없이 프로젝트를 만들고 HTML에서 파일을 올려도 됩니다. 이미 확정한 곡이 있다면 `init`에 `--music /absolute/path/to/song.wav`를 더합니다. 로컬 루프백 서버 URL은 현재 컴퓨터의 브라우저에서만 열립니다. 화면 저장은 렌더나 외부 게시가 아닙니다. [HTML 템플릿과 조작](docs/html-studio.md)

Claude Code 작업에서는 `--host claude`, Antigravity 작업에서는 `--host antigravity`로 같은 프로젝트를 엽니다. 이미지 생성은 Codex에서는 내장 `image_gen`, 로컬 Claude Code에서는 로드된 `gpt-image`의 ChatGPT 로그인 Codex CLI 브리지, Antigravity에서는 해당 환경이 실제로 제공하는 네이티브 이미지 도구를 사용합니다. 특정 모델명이나 유료 API 권한을 추정하지 않으며, 세 경우 모두 결과 이미지의 경로·해시·프롬프트를 같은 manifest 계약에 남깁니다.

<a id="updates"></a>

## 업데이트와 릴리스

새 Release 유무 확인은 읽기 전용입니다. 설치는 명시적으로 분리합니다.

```bash
node skills/road-music-skills-update/scripts/manage.cjs check
node skills/road-music-skills-update/scripts/manage.cjs update
```

`watch`는 요청한 경우에만 새 Release를 주기적으로 알려주며, 설치·덮어쓰기는 하지 않습니다. 릴리스마다 `release/YYYY-MM-DD-title.md` 형식의 노트를 작성하고 `version` frontmatter를 묶음 버전과 맞춥니다. [업데이트](docs/updates.md) · [릴리스 절차](docs/releasing.md)

<a id="docs"></a>

## 문서와 라이선스

[전체 문서 지도](docs/README.md)에서 설치, 각 스킬, HTML 제작실, Road Music CLI 연계, 업데이트, 릴리스, 구조를 확인할 수 있습니다.

이 저장소는 [MIT License](LICENSE)로 배포됩니다. 내장 Showreel은 MIT, JIZURA는 MIT이며 각 글꼴의 별도 라이선스를 유지합니다. [아키텍처와 라이선스 경계](docs/architecture.md)

## 그룹별 제작 기록·좋아요·업데이트

그룹 상세에서 같은 음악의 프롬프트·AI 응답·결과·작업 파일을 확인하고 복사합니다. 좋아요는 SQLite에 저장하고 좋아요 전용 목록으로 조회합니다. 제작 분석에서 업데이트 확인·실행·진행·완료를 연결하며, 관리 설치가 없는 소스 체크아웃은 보호합니다. 자세한 내용은 [제작 기록 가이드](docs/production-records.md)와 제작실 내 작업물·제작 분석 HTML 가이드에서 확인합니다.

음악 상세의 제작 기록, 복사·상태 복구, 정리 확인 경계와 공통 디자인 보완은 [UI/UX 검수와 개선](docs/ui-ux-review.md)에 정리했습니다.

### CCM·공개 명령 활용 가이드

영상 제작실 상단의 **CCM 전문 가이드**에서 `/ccm/`를 바로 엽니다. ACE·YuE 버튼은 하나씩만 선택하며 기본값과 필터 초기화는 YuE입니다. 일반 명령 조합(`/recipes/`)과 CCM 고급 사례는 용도·장르/스타일·태그로 찾고 조합 이유·명령 역할·검수 기준을 펼쳐 봅니다. 기본 프롬프트 또는 기본안+응용 요청을 복사할 수 있습니다. CCM 기존48스타일·창작가사·입력JSON과 고급6대표 예시는 HTML 가이드에서 함께 읽습니다. 정전은 CLI의 `prompt:knowledge`이며, 스킬 묶음은 `road-music-video-studio/assets/knowledge`와 `assets/guides`의 동일 자료를 동봉합니다. 이 화면은 설치·생성을 실행하지 않습니다.

YuE를 주 모델로 쓰는 전문 자료는 `road-music-video-studio/assets/guides/yue-advanced.md`와 CLI `prompt:knowledge`의 `yue-advanced`에서 읽습니다. 사용 가이드도 YuE 기본·ACE 전환으로 본문·예시·목차·복사·다운로드를 분리하고 휴대형 HTML은 `*-ace.html`로 전환합니다. YuE 고급 사례는 CCM37개·일반20개이며, 준비/계획/음원과 가사 변경/악보만 렌더, 단계별 replay를 구별합니다.
