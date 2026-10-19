---
name: road-music-video-studio
description: 제작 설정과 음악별 내 작업물 보관함·상세·가이드 HTML을 연결한다. 영상·음원·가사·자막·스토리보드·프로젝트 검수 기록과 그룹 ZIP을 제공한다. 렌더 엔진 자체를 대체하지 않는다.
---

# Road Music 영상 제작실

## 제작 기록

음악 상세의 내부 메뉴는 6개로 유지하고 프롬프트·작업·파일, 버전 비교, 변경 이력, 검수 자료는 `제작 기록` 안에 모은다. 제작 분석·업데이트는 내 작업물의 `전체 제작 분석·업데이트`에서 열며 음악별 분석은 해당 상세의 문맥 링크를 쓴다. `production-ui.js`의 공통 표현·복사 복구와 공통 디자인 자산을 재사용한다. 복사 거절, 상태 조회 실패, 숨김 버튼, 320px 폭과 키보드 이동을 실제 화면에서 확인한다.

제작실에서 실제 제작을 시작하거나 수정할 때는 [제작 기록 스킬](../road-music-production-records/SKILL.md)을 적용한다. 프롬프트·작업 시간·결과 파일은 SQLite 메타데이터로만 기록하고 미디어를 중복 저장하지 않는다.

HTML을 만들거나 수정할 때는 프로젝트 루트 `DESIGN.md`를 먼저 읽고, 없으면 설치에 포함된 [공통 DESIGN.md](assets/design/DESIGN.md)를 읽는다. 제작실·선택·카탈로그·검수 UI는 이 토큰과 로컬 Paperlogy를 사용한다. `assets/design`의 공통 자산과 `scripts/html_design.py`·`scripts/html-design.mjs`를 재사용하고 독립 HTML에는 상대경로 글꼴도 함께 복사한다. 실제 폰트 로딩, 저장 기능, 좁은 화면을 검수하며 원본 영상의 미술·가사·싱크는 보존한다.

섹션은 공통 `--rm-divider`의 진한 중립 구분선과 제목 여백으로 구분한다. 카드에는 입력·선택·실제 결과를 모으고, 모든 섹션을 중첩 카드로 감싸지 않는다. 단계의 해야 할 일·완료 후는 별도 행으로 표시하며 샘플·파일 종류 태그와 의미 있는 중요·주의 콜아웃을 사용한다. 가이드 H2도 같은 경계 규칙을 적용하고 데스크톱·모바일에서 실제 선과 대비를 확인한다.

실행 중인 제작실을 고칠 때는 사용자가 보고 있는 주소에서 CSS·폰트 응답과 CSP를 확인한다. 템플릿만 바뀌고 서버가 예전 정적 경로를 유지하는 부분 적용을 완료로 보고하지 않는다. 필요한 경우 저장된 선택·피드백을 보존해 해당 제작실 서버만 갱신하고 실제 구분선·카드·글꼴을 확인한다.

Showreel CD 호환 경로, Showreel MV, JIZURA, Showreel 음악 모션그래픽의 **공통 제작·결과·검수·가이드 화면 모음**이다. 원곡·가사·기존 프로젝트와 각 스킬의 엔진을 보존한다. HTML에서 저장한 선택은 다음 제작 단계가 읽는 입력이며, 브라우저 선택만으로 영상이 만들어졌다고 말하지 않는다.

시작 시에는 현재 읽은 이 `SKILL.md`의 실제 절대 부모 경로를 `VIDEO_STUDIO_SKILL`에 넣어 [사용 시 업데이트 확인](../road-music-skills-update/references/use-time-check.md)을 한 번만 적용한다.

## 프로젝트 저장공간

작업 시작·수정·완료의 저장공간은 [저장공간 운영 스킬](../road-music-storage/SKILL.md)을 함께 적용한다. 새 제작실 프로젝트는 `.roadmusic/work/<원음SHA12 또는 unassigned>/<프로젝트--ID>/`에서 진행하며 새 `Output/...` 요청은 이 실제 경로로 변환해 반환한다. `Output`에는 게시 검증을 마친 최종 납품만 두고, 버전 이력은 SQLite에 남긴다. 원음·완성본·승인 자산·편집 소스를 보존하고 프로젝트별 `.roadmusic/cache`와 중간본·상세 이력을 분리한다. 기존 자료는 임의 이동·삭제하지 않고 등록된 항목의 보호 사유·미리보기를 확인한다.

## 시작하기

새 프로젝트는 실제 절대 음악 경로를 선택적으로 받는다. 이 명령은 원본 음악을 복제하지 않는다.

```bash
VIDEO_STUDIO_SKILL="/absolute/skills/road-music-video-studio" # 현재 읽은 이 SKILL.md의 실제 부모
VIDEO_STUDIO_PY="${SHOWREEL_PYTHON:-python3}"
VIDEO_STUDIO_HOST="${ROAD_MUSIC_HOST:-codex}" # Claude Code에서는 claude
SKILLS_PARENT="$(dirname "$VIDEO_STUDIO_SKILL")"
UPDATE_SKILL="$SKILLS_PARENT/road-music-skills-update"
node "$UPDATE_SKILL/scripts/manage.cjs" check --target "$SKILLS_PARENT"
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" init \
  --out /absolute/output/my-video \
  --music /absolute/music/song.wav \
  --mode showreel-motion --host "$VIDEO_STUDIO_HOST"
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" serve \
  --project /absolute/output/my-video --host "$VIDEO_STUDIO_HOST" --open
```

음원 파일을 나중에 고르려면 같은 `--host "$VIDEO_STUDIO_HOST"`를 붙여 `init --out /absolute/output/my-video --host "$VIDEO_STUDIO_HOST"`만 실행한다. 제작실의 파일 선택은 해당 파일을 프로젝트 `inputs/music/`에만 보관한다.

제작 방식은 `showreel-cd`, `showreel-mv`, `jizura`, `showreel-motion` 중 하나다. `serve`는 루프백 URL을 stderr JSONL로 알리고, 사용자가 **선택·제작 요청 저장**을 누르면 stdout JSON 한 줄로 `selection.json`과 `production-request.json` 경로를 돌려준다. 브라우저가 먼저 닫혀도 이미 저장된 두 파일을 읽어 제작을 계속한다. 새로 고르라고 반복해서 묻지 않는다.

Showreel CD 또는 등록 프리셋을 고른 모션그래픽 모드에서는 같은 저장 순간에 기존 `plan/create --selection`이 바로 읽을 수 있는 `showreel-request.json`도 만든다. 이 파일은 `schemaVersion`, `styleId`, 정규화된 `display`, 원곡 절대 `music`과 선택적 `host`를 가진다. `plan`의 명시 `--host`가 우선하고, 없으면 저장한 host를 상속하며 이전 입력처럼 둘 다 없으면 `codex`다. MV와 JIZURA 선택을 CD 프리셋으로 바꾸거나 이 파일을 만들지 않는다.

작업 호스트는 `codex`, `claude`, `antigravity`, `antigravity-cli`다. Codex는 ChatGPT/Codex의 `image_gen`을, 로컬 Claude Code CLI/IDE는 실제로 읽은 `gpt-image` 스킬의 ChatGPT 로그인 Codex CLI 브리지를, Antigravity 앱과 CLI는 해당 호스트가 제공하는 같은 계열의 이미지 생성 모델을 사용한다. 앱과 CLI는 설치·실행 표면만 다르다. Claude에서 `gpt-image`가 없으면 이미지 의존성 누락을 기록하며 로그인·설치·유료 API 대체를 하지 않는다. Showreel MV의 기본 정책은 이 호스트 이미지 도구만 쓰며, 유료 API는 품질이나 실패 복구를 이유로 자동 사용하지 않는다. 제작실은 공급자를 기록하고 입력·자산 검수를 공통으로 처리할 뿐, 지원하지 않는 모델 목록이나 가짜 모델 선택을 만들지 않는다.

`--music` 없이 시작한 뒤에는 제작실에서 브라우저 파일을 고를 수 있다. 이 파일은 프로젝트의 `inputs/music/`에만 저장되며, 웹 페이지는 등록된 음원·미리보기·검수 산출물만 재생한다.

단계별 화면은 [페이지 열기·복귀·완성 파일 검수](references/page-flow.md)를 따른다. 필요한 화면을 실제 Ego 브라우저에서 열고 제목·현재 원음·기본 동작을 확인하며, URL 준비만으로 화면 표시 완료라고 하지 않는다.

## CLI 시작과 페이지 이동

명시적인 Road Music `service:start`가 성공하면 제작실 화면을 연다. 이미 유효한 서버가 있으면 프로젝트와 원음·결과를 보존해 기존 Ego 페이지를 재사용한다. 같은 주소에서는 다시 로드하지 않고 다른 제작 단계는 같은 페이지로 이동한다. `schema`·일반 조회·배치는 새 창을 열지 않으며 `ROADMUSIC_STUDIO_AUTO_OPEN=0`은 자동 열기를 생략한다. 제작실 준비 실패는 서비스 성공을 취소하지 않고 별도 경고로 알린다.

제작실·스타일 카탈로그·JIZURA·선택기·독립 검수 HTML에는 공통 페이지 이동 메뉴를 사용한다. 실행 중인 제작실은 `ROADMUSIC_DATA_DIR`(기본 앱 데이터 폴더)의 `video-studio-session.json`에 URL·프로젝트·만료 시각을 등록하고, 유효한 로컬 주소만 연결한다. 임의 외부 주소로 토큰을 전달하지 않는다. 배포용 원본 템플릿에 실행 중 토큰을 박아 넣지 않으며, 서버가 응답할 때 메뉴를 연결한다. 연결된 제작실이 없으면 페이지 안 이동만 제공한다.

작성 중 선택과 의견은 같은 브라우저 세션에서 페이지 왕복 시 보존한다. JIZURA의 내부 메뉴는 숨김 탭도 함께 열며, 영상 렌더 장면과 공식 iframe에는 메뉴를 주입하지 않는다.

## 네 진입점

- **Road Music Showreel CD**: `road-music-showreel-cd`의 호환 경로이며 실제 Showreel 프리셋 미리보기를 고른다.
- **Road Music 쇼릴 MV**: `road-music-showreel-mv`의 스토리보드·리듬 편집 단계로 제작 방향을 넘긴다.
- **JIZURA 음악 스튜디오**: 선택을 저장한 뒤 `JIZURA_SKILL="$SKILLS_PARENT/road-music-jizura-playlist"`의 `"$JIZURA_SKILL/scripts/studio.py"`로 별도 편집기를 연다. 런타임이 없으면 미설치 상태를 알리며 설치하지 않는다.
- **Showreel 음악 모션그래픽**: `road-music-showreel-playlist`의 실제 프리셋 미리보기와 연결한다.

스타일 카드가 없는 방식은 실제 공통 샘플이 등록되지 않았다는 뜻이다. 임의 동영상이나 엔진 완료 표시를 만들지 않는다.

## 표시와 검수

스펙트럼, 대기 곡 목록, 현재 곡 이름, 채널명은 모두 표시/비표시/SKIP으로 기록한다. SKIP은 이전 값을 보존하고, 처음 SKIP한 값은 선택한 제작 스킬에 전달하지 않는다. `feedback.json`은 초안·수정 요청·승인 상태와 피드백을 원자적으로 저장한다.

음악·영상 제작 완료 후 같은 프로젝트에 실제 완성 음원(`audio`), 원가사(`lyrics`, 있는 경우), 최종 영상(`video`)을 명시적인 manifest로 등록한다. 음악만 완성된 단계에서는 음원·가사부터 등록하고 영상 완료 후 기존 납품 파일도 포함한 manifest로 다시 게시한다. `publish`는 기존 결과 목록을 교체하므로 보존할 버전·자막·스토리보드를 빠뜨리지 않는다. 입력 음원과 명시한 완성 음원이 같은 바이트여도 `audio` 등록은 유지한다. 게시 도구가 물리 파일은 한 번만 보관하며 화면에서는 원음·완성 음원 역할을 구분한다. 등록 뒤에는 `/works/`에서 실제 음원·영상 재생과 다운로드를 확인한다. URL·manifest·화면 저장만으로 재생 가능하거나 완성됐다고 하지 않는다. 원문 가사는 TXT/Markdown 그대로 표시·다운로드하며 SRT/LRC 자막과 구분한다. 입력 음원이나 형식 예시만 있는 상태를 새 제작 완료로 표시하지 않는다.

제작실(`/`)에는 설정만 둔다. 내 작업물(`/works/`)에서 음악별 상세를 열어 실제 음원·영상 재생, 가사·SRT 개별 다운로드와 음악 그룹 ZIP을 확인한다. 기본 목록과 크게 보기 전환을 제공하고 실제 파일이 없는 자료는 안내만 한다. 스토리보드·원문/자막 대조·수정 의견·승인은 음악 상세의 내부 메뉴에서 다룬다. 검수 세션 종료가 필요한 기존 자동화는 호환 `/review/`의 검수 완료 버튼을 사용한다.

가이드의 역할 설명은 개요 박스로, 둘 이상의 숫자 목록은 단계 카드로, `**명칭**: 설명` 목록은 비교 행 카드로 표시한다. H2·H3 경계와 본문 간격을 유지하고, 주의·한계는 기존 문장을 중복 없이 의미 콜아웃으로 옮긴다. 문서 제목 아래 복사·다운로드 행동을 두며 모바일에서는 비교 행의 명칭 아래 설명이 오도록 한다. 일반 문단을 모두 카드로 감싸지 않는다.

사용 가이드(`/guide/`)의 원본은 `assets/guides/*.md`다. 가이드를 먼저 Markdown으로 작성하고 `guide_content.py`로 HTML을 만든다. 페이지의 기능·절차·오류 복구·한계를 설명하고, 각 화면은 해당 주제에 직접 연결한다. 문서와 주요 화면 우측 상단의 Markdown 복사는 원문을 그대로 복사하며 실패하면 수동 복사란을 제공한다. 독립 HTML에도 가이드·CSS·Paperlogy를 함께 생성한다. 긴 설명을 제작 화면에 다시 합치지 않는다. 각 가이드는 실제 화면·완성 프레임 예시와 절차 도식을 해당 단계에 배치하고, 예시가 현재 곡의 완료 결과가 아님을 설명한다. `assets/guides/media/`의 등록 자산만 사용하고 의미 있는 대체 설명을 쓴다. `prompt`·`bash`·`json`·`text` 코드 블록은 개별 복사 버튼과 권한 차단 시 수동 복사를 제공한다. 명령은 실제 지원 여부·실행 위치·변수 정의·교체할 예시 경로·기대 결과를 설명하며 복사만으로 실행하지 않는다. 휴대형 HTML에도 이미지·도식 원본을 함께 복사하고, 라이브 가이드는 인증된 `/guide-media/`에서 제공한다.

```json
{
  "title": "봄의 노래",
  "sourceMusicSha256": "렌더에-사용한-원음의-64자리-sha256",
  "video": ["/absolute/output/master.mp4"],
  "audio": ["/absolute/output/master.wav"],
  "lyrics": ["/absolute/output/original-lyrics.txt"],
  "captions": ["/absolute/output/lyrics.srt"],
  "storyboard": ["/absolute/output/storyboard-01.png"]
}
```

```bash
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" publish \
  --project /absolute/output/my-video \
  --manifest /absolute/output/publish.json
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" serve \
  --project /absolute/output/my-video --host "$VIDEO_STUDIO_HOST" --review --open
```

`publish`는 존재하는 절대 파일과 허용된 미디어 확장자만 등록하고 이전 검수 등록을 누적하지 않는다. 렌더·음원 생성·다운로드·JIZURA 설치를 실행하지 않는다. `--review` 세션은 선택·피드백 저장 후에도 열려 있으며, 브라우저의 **검수 마치기**로만 종료한다.

자세한 입출력 형식과 보안 경계는 [제작실 API](references/studio-api.md)를 읽는다. 결과·제작자료·감상용 ZIP·싱크 근거의 구분은 [결과 등록 계약](references/result-contract.md)을 따른다.

Showreel 모션그래픽의 `styleId:null`은 곡별 새 native 연출을 뜻한다. 이 경우 실제 음원은 필요하지만 기존 프리셋을 강제하지 않으며 `production-request.json`을 읽어 native 제작으로 이어간다. 등록 프리셋용 `showreel-request.json`은 새로 만들거나 반환하지 않는다. CD 모드는 계속 실제 프리셋 id가 필요하다.

## 음악별 내 작업물과 상세

전역 메뉴는 제작실·내 작업물·스타일·사용 가이드다. 제작 이후의 결과는 `/works/` 목록에서 음악 그룹을 고른 뒤 `/works/<원음SHA256>/` 상세의 요약·영상/스타일·음원·가사/자막·스토리보드·검수/제작 기록 내부 메뉴로 확인한다. `/results/`와 `/review/`는 이전 링크의 호환용으로 유지하며 전역 메뉴에 중복 노출하지 않는다.

완성 결과를 `publish`하거나 완성 파일이 있는 프로젝트를 `serve`하면 보관함에 등록한다. 과거 프로젝트는 `python3 "$VIDEO_STUDIO_SKILL/scripts/studio.py" library-register --project /absolute/project`로 명시 등록한다. 보관함은 앱 데이터의 `video-studio-library.json`에서 누적 관리하며 원본 파일을 이동·복사하지 않는다. 같은 원음 해시는 한 그룹, 같은 종류·내용의 파일은 한 항목이다. 제목만 같은 다른 원음은 합치지 않는다. 원음 해시 불일치는 보고하고 제작 당시의 검증된 원음을 찾아 연결하며 현재 음악 파일을 덮어쓰지 않는다.

`video` 등 각 manifest 파일은 기존 절대 경로 문자열 또는 `{ "path": "/absolute/final.mp4", "styleLabel": "Crimson × Mint × Acid", "styleId": "optional-id" }`를 받을 수 있다. 확인된 실제 스타일만 기록하며 미기록 항목은 추정 이름을 붙이지 않는다. 등록된 원음 해시와 다른 결과는 현재 그룹에서 건너뛰며 확인되지 않은 연결은 상세에 표시한다.

작업물 ZIP은 감상용과 제작자료용으로 나눈다. 감상용 ZIP은 사용한 원음과 완성 파일·가사·자막·스토리보드만, 제작자료 ZIP은 등록한 native 프로젝트·direction·analysis·plan·validation·cue·compose·report 등 허용된 artifact를 담는다. 기존 `/downloads/complete.zip`의 입력 음원 제외 계약과 구분한다. 누락·변경이 있으면 부분 ZIP을 완료처럼 제공하지 않는다. 상세의 프로젝트별 피드백은 그 프로젝트에만 저장하고 새 결과 확인·페이지 왕복의 임시 의견을 보호한다. 날짜 필터와 연월일시분초는 한국 시간, 예전 기록은 파일 생성/수정 시각임을 명시한다.

`syncChecks[]`가 등록된 경우 행 번호·시작/끝 시각·확정/추정·근거와 가능한 영상/자막/가사 SHA를 읽기 전용 역사 기록과 분리해 표시한다. 자동 정렬·ASR·불명확한 발음은 원가사 변경 근거가 아니며, 근거가 부족한 시각은 추정으로 보존한다.

## 상태·레퍼런스·배포 경계

`/status/`는 로컬 제작실·현재 프로젝트·공개 CLI의 읽기 전용 준비 상태이고, `/reference/`는 현재 설치본의 공개 명령과 결과 등록 계획을 읽는 화면이다. 둘 다 서비스·렌더·모델 설치·업데이트를 자동 시작하지 않는다. `publish --dry-run` 또는 `/api/publish-preview`로 등록 교체 계획을 확인한 뒤 실제 helper `publish`를 실행한다.

배포 manifest가 관리하는 스킬은 Showreel CD·MV·JIZURA·Showreel 음악 모션그래픽·제작실·저장공간·제작 기록·업데이터다. 실제 묶음 경로와 버전은 manifest를 기준으로 확인한다. LTX `road-music-mv`와 모델은 별도 경계이며 이 묶음의 업데이트가 모델까지 설치한다고 안내하지 않는다. 사용자 안내는 `assets/guides/workflow.md`, `topics.md`, `status.md`, `reference.md`와 함께 갱신한다.

이 UI는 사용자가 지정한 ProKit의 간결한 구성과 문서 읽기 흐름을 참고한다. Paperlogy·DESIGN.md는 유지하고, Markdown 가이드를 먼저 고친 뒤 공통 HTML·휴대형 템플릿에도 반영한다.

## 설명·도식·이미지 제작 규칙

가이드 기능 설명은 실제 화면 예시와 재사용할 프롬프트·명령을 가까이 배치한다. 제작실은 원음 확인→방식·스타일→화면 표시→요청 저장→제작 후 결과 확인 흐름을 제공한다. 비교나 긴 설명은 명시적으로 여는 `dialog`로 나누고 Escape·닫기·초점 복귀와 작성 중 설정·의견 보존을 검수한다.

UI 아이콘은 `scripts/ui_icons.py`와 `assets/design/heroicons.svg`의 공식 Heroicons Solid를 재사용하고 MIT 출처를 보존한다. 가이드 도식 본문은 `guide_diagrams.py`의 의미 있는 HTML 구조로 반응형 표시하며 동봉 SVG 원본도 제공한다. `guide_content.py`의 등록 미디어와 크기를 함께 관리하고 실제 이미지 크기·폰트·오프라인 사본·인증 경로를 검사한다.

실제 화면·원가사·완성 파일의 증거 이미지를 AI 이미지로 꾸며 바꾸지 않는다. 브랜드 마스코트·분위기 콘셉트처럼 생성이 필요한 래스터는 `image_gen`으로 제작해 설치 자산 안에 저장하며, AI 콘셉트라는 설명과 실제 샘플을 구분한다. 투명 배경과 이미지 로딩·좁은 화면 가독성을 확인한다.

가이드의 안내·활용 팁·중요·주의·경고는 Markdown `> [!NOTE]`, `TIP`, `IMPORTANT`, `WARNING`, `CAUTION`을 사용한다. 의미 있는 위치에 짧게 쓰고 색상·제목·아이콘을 함께 제공한다. 안내 상자에 코드·이미지를 억지로 중첩하지 않고 재사용 예시는 별도의 fenced 블록으로 둔다. 저장·렌더·등록·승인·외부 게시를 혼동시키지 않는다.

그룹 상세의 **제작 기록**은 같은 groupId의 원문 요청·AI/결과 요약·작업·파일을 페이지 조회한다. 버전 diff·검수 의견과 구분하며 복사를 지원한다. 목록/상세의 좋아요는 같은 프로필 SQLite에 저장하고 좋아요 목록·검색·날짜 필터에서 재사용한다. 좋아요는 보존 핀이 아니다.

제작 분석의 업데이트 확인·실행 버튼은 서버가 정한 앱·CLI·관리 스킬 묶음만 기존 공개 업데이터로 처리한다. 정확한 진행량이 없으면 불확정 막대, 완료 후 실제 확인 버전을 표시한다. 앱 재시작 전과 중단 설치를 완료로 표시하지 않으며 응답 유실 시 기존 작업 상태를 재조회한다. 소스 체크아웃 스킬은 수정 보호를 위해 확인만 제공한다.

제작 분석은 프로젝트별 음악·영상 누적과 성공 평균을 비교하고, 내 작업물은 음악 그룹별 누적 및 과정별 파이로 확인한다. 자세한 집계·미측정·병렬 시간 기준은 [제작 기록 가이드](assets/guides/production.md)를 따른다. 레퍼런스는 현재 schema 악기/옵션과 명령·자연어 예시를 구분하고, 스타일 카탈로그는 실제 대표 썸네일·카테고리/장르 태그 필터를 사용한다. 화면 필터나 예시 복사는 생성·설치·정리 실행 승인이 아니다.

## 현재 제작 현황과 대기열

대시보드와 그룹 상세 요약의 현황은 공개 `production:activity`와 같은 SQLite 추정기를 재사용한다. 현재 요청 진행률과 엔진의 실제 단계 비율, 등록된 다음 작업과 과거 흐름의 추정 단계를 구분한다. 추정 단계를 실행 예약이나 전체 예상시간으로 합산하지 않는다. 같은 모델의 성공 표본·목표 길이·프레임으로만 시간 근거를 제시하고, 표본 없음·예상 초과·일시정지·오프라인·순서 미확인은 불확정으로 안내한다. 현황 갱신에서 앱 자동 시작·파일/Git 전체 검사를 실행하지 않는다. 화면 표시 중 저빈도 조회와 100건 단위 페이지 이동을 유지한다.

## 공개 명령 조합과 CCM 전문 지식

`/reference/`에서 실제 schema를 확인하고 `/recipes/`의 일반 장르·옵션·명령 조합이나 `/ccm/`의 ACE·YuE CCM 지식으로 이어간다. 두 활용 페이지는 엔진·용도·스타일·카테고리·태그 검색과 원문/응용 요청 복사만 제공하며 생성하지 않는다. 기존 CCM 스타일·가사·JSON은 `/guide/ccm-library/`, 고급 활용은 `/guide/ccm-advanced/`에서 공통 Markdown 렌더러로 읽는다. CLI `prompt:knowledge`의 `reference-recipes`·`ccm-recipes`·`ccm-advanced`와 같은 정전 자료를 사용한다. CLI 문서를 갱신하면 배포용 `assets/knowledge` JSON과 `assets/guides`의 CCM 읽기 사본도 함께 맞추고 내용 일치 검사를 통과시킨다. 예시를 실제 생성 결과나 품질 보장으로 표시하지 않고 사용자 선택 엔진·원문·권한을 유지한다.

사용 가이드는 기본 YuE이며 명시적 엔진 절로 본문·코드 예시·목차·복사 원문·다운로드까지 필터한다. engine=None의 raw 지식은 원문 보존용이며 사용자 HTML의 기본 뷰로 사용하지 않는다. ACE에서 YuE 전용 전문 문서를 선택하면 ACE용 공통 CCM 문서로 연결한다. 모델 필터는 실제 프로그램 엔진 변경·설치·생성 권한이 아니다. 원문 가사/style을 바꾸는 설명은 새 prepare→generate를 사용하고 song:render로 새 가사를 전달한다고 안내하지 않는다.

CCM 스타일 목록은 **CCM 스타일별 프롬프트**로 안내한다. 각 스타일에 짧은 한국어 설명을 두고, 원문을 보존한 영문 스타일 태그와 선택한 YuE·ACE용 제작 요청의 복사를 구분한다. 한국어 설명을 다듬을 때도 엔진·명령·옵션값·영문 태그·가사 원문은 바꾸지 않는다. 복사 성공은 버튼과 상태 문구로 알리고, 거절되면 원문을 선택한 수동 복사란을 제공한다.
