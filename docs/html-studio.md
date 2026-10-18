# Road Music 영상 제작실

공통 HTML 제작실은 선택, 듣기, 보기, 피드백, 검수의 기록을 프로젝트에 남기는 로컬 인터페이스입니다. 화면 입력은 명령 실행 권한이 아니며, 선택 저장과 실제 렌더를 구분합니다.

## 화면에서 할 수 있는 일

| 단계 | HTML에서 확인·조작하는 내용 |
| --- | --- |
| 기획 | 스타일 카드·설명·미리보기 영상 비교 |
| 선택 | 스펙트럼·곡 목록·현재 곡명·채널명 저장 |
| 편집 | 형식·프리셋·음원·4개 표시와 피드백 저장 |
| 별도 JIZURA 편집기 | 강도·색·서체·구간을 JIZURA 전용 화면에서 편집 |
| 검수 | 원음, 영상, 자막, 프로젝트 산출물, 피드백 |

제작실은 사용자가 지정한 최근 프로젝트인 아직 나의 봄(CD 24초), 프리즘(MV v5 18초), 어디든 좋아(JIZURA 18초), 내일로 달려(모션그래픽 24초)를 카드로 재생합니다. 이들은 현재 선택한 곡의 결과가 아니며, 목록·길이·제작 근거는 `skills/road-music-video-studio/assets/examples.json`이 기준입니다.

## 시작

```bash
VIDEO_STUDIO_SKILL="/absolute/skills/road-music-video-studio" # 현재 읽은 SKILL.md의 실제 부모
VIDEO_STUDIO_PY="${SHOWREEL_PYTHON:-python3}"
VIDEO_STUDIO_HOST="${ROAD_MUSIC_HOST:-codex}" # Claude Code에서는 claude
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" init \
  --out /absolute/path/to/project --host "$VIDEO_STUDIO_HOST"
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" serve \
  --project /absolute/path/to/project --host "$VIDEO_STUDIO_HOST" --open
```

`init`은 음악 없이도 새 프로젝트의 입력 기록을 만들고, `serve`는 로컬 화면을 엽니다. 화면에서 파일을 올려 음악을 등록할 수 있습니다. 이미 확정한 음악이 있으면 `init --music /absolute/path/to/song.wav`로 바로 등록합니다. `publish`는 결과 파일 목록을 검수 화면에 등록하는 단계입니다.

Claude Code에서 만든 프로젝트는 `--host claude`, Antigravity에서 만든 프로젝트는 `--host antigravity`를 사용합니다. 이 값은 어떤 공급자를 기록할지 정할 뿐, 브라우저나 Python 스크립트가 이미지 모델을 임의로 실행하게 하지 않습니다. Codex는 내장 `image_gen`, 로컬 Claude Code CLI/IDE는 로드된 `gpt-image`의 ChatGPT 로그인 Codex CLI 브리지, Antigravity는 Nano Banana 네이티브 기능을 사용하며 결과 이미지 manifest 형식은 공통입니다. Showreel MV는 이 기본 경로에서 별도 유료 API로 자동 전환하지 않습니다. `gpt-image-2.5` 등의 유료 모델은 사용자가 해당 제작에 명시적으로 요청할 때만 사용합니다. [Claude Code 설치·실행](claude.md) · [Antigravity 설치·실행](antigravity.md)

```bash
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" publish \
  --project /absolute/path/to/project --manifest /absolute/path/to/output-manifest.json
```

결과 manifest에는 실제 절대 파일과, 가능하면 원음의 SHA-256을 기록합니다. `publish`는 등록 목록 전체를 이 manifest로 교체하므로, 후속 등록에서도 유지할 기존 스토리보드·음원·영상·자막을 모두 다시 넣습니다.

```json
{
  "title": "봄의 노래",
  "sourceMusicSha256": "원음에서 계산한 64자리 SHA-256",
  "video": ["/absolute/output/master.mp4"],
  "captions": ["/absolute/output/lyrics.srt"],
  "storyboard": ["/absolute/output/storyboard-01.png"]
}
```

## 검수 세션과 새 결과

전곡 또는 수정본을 보는 동안에는 `--review`로 제작실을 엽니다. 선택·피드백을 저장해도 이 세션은 닫히지 않습니다. 브라우저에서 **검수 마치기**를 누를 때만 완료 JSON을 반환하고 서버가 종료됩니다.

```bash
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" serve \
  --project /absolute/path/to/project --host "$VIDEO_STUDIO_HOST" --review --open
```

렌더가 끝난 뒤 같은 프로젝트에 새 결과 manifest를 등록하면, 열린 검수 화면에서 **새 결과 확인**을 눌러 재생·다운로드 목록을 갱신합니다. 각 결과는 등록된 원음 SHA-256을 현재 음악과 비교해 `현재 원음과 일치`, `다른 원음의 결과`, `원음 확인 필요`로 표시합니다.

```bash
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" publish \
  --project /absolute/path/to/project --manifest /absolute/path/to/new-result.json
```

## 보안과 기록

- 서버는 `127.0.0.1`에서만 열리고 임시 토큰을 사용합니다.
- 음악 파일은 절대 경로로 기록하며, 저장 전 파일 존재와 프로젝트 경계를 확인합니다.
- `selection.json`은 host, mode와 정규화된 표시 값을 기록합니다. SKIP은 이전에 저장한 표시 값으로 정규화하고, 이전 값이 없으면 `null`로 남깁니다. 저장된 선택과 피드백은 다음 제작 단계가 읽을 수 있는 데이터이며, 렌더 완료, 가사 정답, 외부 게시의 증거는 아닙니다.
- Showreel CD 또는 등록 프리셋의 Showreel 음악 모션그래픽을 고르면 `showreel-request.json`도 만듭니다. 이 파일은 `{schemaVersion, styleId, display, music, host?}` 계약이며 `plan`/`create --selection`에 바로 전달할 수 있습니다. `plan`의 명시 `--host`가 우선하고, 없으면 저장한 host를 쓰며, 이전 입력처럼 host가 없으면 `codex`입니다.
- Showreel MV·JIZURA 선택을 CD 프리셋으로 바꾸거나 `showreel-request.json`을 임의 생성하지 않습니다.

> [!NOTE]
> 실제 사용 가능한 명령과 manifest 필드는 설치된 제작실 스킬의 `SKILL.md`가 우선합니다.

## 한 페이지에서 제작 단계 이동

CLI와 각 스킬의 자동 열기는 기존 Ego 페이지 한 개를 재사용합니다. 같은 주소는 다시 로드하지 않고 필요한 제작실·카탈로그·JIZURA·선택기 화면으로 이동합니다. 이미 연 화면을 별도 브라우저 명령으로 또 열지 않습니다. [단계별 화면 계약](../skills/road-music-video-studio/references/page-flow.md)을 따릅니다.

모든 제작·검수 HTML은 [DESIGN.md](../DESIGN.md)와 Paperlogy를 사용합니다. 스킬만 설치한 환경에도 [공통 디자인 계약](../skills/road-music-video-studio/assets/design/DESIGN.md), CSS·9개 글꼴·OFL 라이선스가 포함됩니다. 곡별 영상 미술과 공식 엔진 원본에는 제작 UI 메뉴를 넣지 않습니다.

완성 파일 영역에서 음원·원가사·영상의 재생·미리보기·개별 다운로드를 제공합니다. 원가사는 `lyrics` 필드로 등록하고 SRT/LRC 자막과 구분합니다. 모션그래픽의 기본 ‘곡별 새 연출’은 프리셋 없이 `production-request.json`으로 이어갑니다.
