---
name: road-music-video-studio
description: 로컬 HTML 제작실에서 음악·실제 스타일 미리보기·화면 표시·스토리보드·완성 영상 검수를 한 화면으로 연결할 때 사용한다. 렌더 엔진 자체를 대체하지 않는다.
---

# Road Music 영상 제작실

HTML을 만들거나 수정할 때는 프로젝트 루트 `DESIGN.md`를 먼저 읽고, 없으면 설치에 포함된 [공통 DESIGN.md](assets/design/DESIGN.md)를 읽는다. 제작실·선택·카탈로그·검수 UI는 이 토큰과 로컬 Paperlogy를 사용한다. `assets/design`의 공통 자산과 `scripts/html_design.py`·`scripts/html-design.mjs`를 재사용하고 독립 HTML에는 상대경로 글꼴도 함께 복사한다. 실제 폰트 로딩, 저장 기능, 좁은 화면을 검수하며 원본 영상의 미술·가사·싱크는 보존한다.

실행 중인 제작실을 고칠 때는 사용자가 보고 있는 주소에서 CSS·폰트 응답과 CSP를 확인한다. 템플릿만 바뀌고 서버가 예전 정적 경로를 유지하는 부분 적용을 완료로 보고하지 않는다. 필요한 경우 저장된 선택·피드백을 보존해 해당 제작실 서버만 갱신하고 실제 구분선·카드·글꼴을 확인한다.

Showreel CD 호환 경로, Showreel MV, JIZURA, Showreel 음악 모션그래픽의 **공통 선택·검수 화면**이다. 원곡·가사·기존 프로젝트와 각 스킬의 엔진을 보존한다. HTML에서 저장한 선택은 다음 제작 단계가 읽는 입력이며, 브라우저 선택만으로 영상이 만들어졌다고 말하지 않는다.

시작 시에는 현재 읽은 이 `SKILL.md`의 실제 절대 부모 경로를 `VIDEO_STUDIO_SKILL`에 넣어 [사용 시 업데이트 확인](../road-music-skills-update/references/use-time-check.md)을 한 번만 적용한다.

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

음악·영상 제작 완료 후 같은 프로젝트에 실제 완성 음원(`audio`), 원가사(`lyrics`, 있는 경우), 최종 영상(`video`)을 명시적인 manifest로 등록한다. 음악만 완성된 단계에서는 음원·가사부터 등록하고 영상 완료 후 기존 납품 파일도 포함한 manifest로 다시 게시한다. `publish`는 기존 결과 목록을 교체하므로 보존할 버전·자막·스토리보드를 빠뜨리지 않는다. 원문 가사는 TXT/Markdown 그대로 표시·다운로드하며 SRT/LRC 자막과 구분한다. 입력 음원이나 형식 예시만 있는 상태를 새 제작 완료로 표시하지 않는다.

제작실의 **완성 파일 바로 보기**와 **완성 파일 · 재생과 다운로드**에서 실제 음원·영상 재생, 가사 원문·줄바꿈, 파일별 다운로드와 한글 파일명을 확인한다. 진행 중인 화면은 **새 결과 확인**으로 갱신한다. 제작 설정 전달은 생성 버튼이 아니며, 스토리보드·자막·수정 의견은 별도로 펼쳐 확인한다.

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

자세한 입출력 형식과 보안 경계는 [제작실 API](references/studio-api.md)를 읽는다.

Showreel 모션그래픽의 `styleId:null`은 곡별 새 native 연출을 뜻한다. 이 경우 실제 음원은 필요하지만 기존 프리셋을 강제하지 않으며 `production-request.json`을 읽어 native 제작으로 이어간다. 등록 프리셋용 `showreel-request.json`은 새로 만들거나 반환하지 않는다. CD 모드는 계속 실제 프리셋 id가 필요하다.
