# Road Music 영상 제작실

## 화면 역할과 사용자 가이드

제작실은 제작 방향을 저장하는 화면이고, 내 작업물은 음악별 결과 보관함입니다. 한 화면에서 선택·다운로드·승인을 모두 처리하지 않아 현재 작업의 목적을 분명히 구분합니다.

- **제작실**은 원음, 제작 방식, 스타일, 화면 표시를 정하고 선택을 저장합니다. 저장은 실제 렌더가 아닙니다.
- **내 작업물**은 원음 SHA-256별로 모든 완성 음원·원가사·자막·영상·스토리보드·검수·제작 기록을 모아 봅니다.
- **스타일**은 다른 곡의 형식 샘플을 비교하는 화면입니다. 샘플을 현재 결과로 표시하지 않습니다.
- **사용 가이드**는 페이지별 Markdown 원문과 복사 기능을 제공합니다.

`/results/`와 `/review/`는 현재 프로젝트를 바로 보는 호환 경로로 유지하되 전역 메뉴에서는 제외합니다. 기본 결과 확인은 `/works/`에서 시작합니다.

사용자용 문서는 HTML보다 먼저 작성한 Markdown 원문입니다. [처음 사용하기](../skills/road-music-video-studio/assets/guides/start.md)에서 전체 흐름을 보고, [작업 흐름](../skills/road-music-video-studio/assets/guides/workflow.md), [작업별 안내](../skills/road-music-video-studio/assets/guides/topics.md), [제작실](../skills/road-music-video-studio/assets/guides/studio.md), [내 작업물](../skills/road-music-video-studio/assets/guides/works.md), [저장공간 관리](../skills/road-music-video-studio/assets/guides/storage.md), [상태](../skills/road-music-video-studio/assets/guides/status.md), [공개 명령과 등록 계획](../skills/road-music-video-studio/assets/guides/reference.md), [결과 검수](../skills/road-music-video-studio/assets/guides/review.md)로 이어집니다. 가이드 페이지의 Markdown 복사가 실패하면 원문 보기에서 직접 복사합니다.

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

결과 manifest에는 실제 절대 파일과, 가능하면 원음의 SHA-256을 기록합니다. `publish`는 현재 프로젝트의 등록 목록 전체를 이 manifest로 교체하므로, 후속 등록에서도 유지할 기존 스토리보드·음원·영상·자막을 모두 다시 넣습니다. `publish` 뒤에는 원음 SHA-256이 같은 내 작업물 그룹에 결과 이력을 누적합니다. 실제 원음과 다른 `sourceMusicSha256`을 쓴 결과는 다른 그룹에 섞지 않고 건너뜁니다.

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

완성 파일 영역에서 음원·원가사·영상의 재생·미리보기·개별 다운로드를 제공합니다. 원가사는 `lyrics` 필드로 등록하고 SRT/LRC 자막과 구분합니다. 모션그래픽의 기본 ‘곡별 새 연출’은 프리셋 없이 `production-request.json`으로 이어갑니다. 제작 뒤에는 [내 작업물 가이드](../skills/road-music-video-studio/assets/guides/works.md)의 음악별 상세에서 모든 결과와 기록을 확인합니다.

## 완성 결과의 등록·다운로드 기준

완성 결과 페이지에는 manifest의 `audio`, `lyrics`, `captions`, `video`로 등록한 파일만 표시합니다. `storyboard` 이미지는 결과 검수 페이지에서 확인합니다. 입력 음원, 스타일 예시, 중간 미리보기, 아직 생성하지 않은 파일을 완성본으로 올리지 않습니다.

- `lyrics`는 승인된 원가사 원문입니다. 음성 인식 결과가 달라도 자동으로 바꾸지 않습니다.
- `captions`는 SRT, VTT, ASS, LRC 같은 시간 자막입니다. 등록하지 않았으면 자막이 생성됐다고 표시하지 않습니다.
- 음악 그룹 ZIP은 사용한 원음과 등록된 완성 영상·완성 음원·원가사·자막·스토리보드를 포함합니다. 입력 음원을 완성 음원으로 표시하지 않고, 다른 곡의 샘플·중간 결과는 제외합니다. 등록한 파일이 누락되거나 바뀌면 일부만 담긴 ZIP을 만들지 않습니다.
- 결과마다 원음 SHA-256 비교 상태를 표시합니다. `다른 원음의 결과`와 `원음 확인 필요`는 현재 곡의 완료본으로 승인하지 않습니다.

감상용 음악 그룹 ZIP과 제작자료 ZIP은 분리합니다. 감상용 ZIP에는 실제 재생·다운로드할 원음과 media만, 제작자료 ZIP에는 등록한 native 프로젝트·direction·analysis·plan·validation·cue·compose·report 같은 허용 artifact만 넣습니다. 결과 등록 전 `publish --dry-run` 또는 `/api/publish-preview`로 추가·유지·제거·경고를 확인하고, 실제 `publish`가 목록을 교체한다는 점을 다시 확인합니다. 상세 계약은 [결과 등록 계약](../skills/road-music-video-studio/references/result-contract.md)을 따릅니다.

결과 등록 뒤 검수 페이지는 자동 갱신하지 않습니다. **새 결과 확인**을 눌러 목록을 갱신하면 재생과 작성 중인 피드백을 보호할 수 있습니다. manifest는 등록 목록 전체를 교체하므로 유지할 기존 파일도 다음 manifest에 다시 적습니다.

## 가사 싱크 검수

원가사와 자막은 별도 근거로 다룹니다. 확정 시각은 원음·원문·검수 근거가 있는 항목이고, 추정 시각은 자동 정렬이나 불명확한 발음 때문에 확정하지 못한 항목입니다. 공통 검수 페이지는 행별 확정·추정을 자동 판정하거나 라벨로 표시하지 않습니다. JIZURA 제작 검수 기록의 구분을 보존하고, 공통 페이지 피드백에는 행·시각·확정/추정·사유를 명시합니다. 등록된 `syncChecks`는 영상·자막·가사 SHA와 검수 시각을 함께 보관하며, 역사 기록은 읽기 전용입니다. 자세한 절차는 [가사·싱크 검수 가이드](../skills/road-music-video-studio/assets/guides/review.md)를 따릅니다.

## 예시로 따라 하는 사용 가이드

가이드 원본 14개는 `skills/road-music-video-studio/assets/guides/*.md`다. 실제 화면·영상 프레임 5종과 제작 흐름·음악 그룹·싱크 검수·스타일 강약 도식 4종을 관련 단계에 제공한다. 예시는 현재 곡의 상태와 구분하며 이미지 아래 원본 크기 펼치기로 자세히 본다. 프롬프트·명령·JSON·기록 예시는 블록별 복사, 전체 원문은 상단 Markdown 복사를 사용한다. 복사 차단 시 수동 선택을 제공하고 명령을 실행하지 않는다. CLI 예시는 작업 위치·변수·예시 경로와 실행 조건을 확인한 뒤 쓴다.

라이브 서버 3종은 인증된 `/guide-media/<등록된 이름>`으로 이미지를 제공한다. 독립 HTML을 만들면 `guides/media/`에 같은 자산을 함께 복사하므로 외부 이미지 서비스 없이 사용할 수 있다. 새 이미지는 공통 가이드의 허용 목록과 원본 자산을 함께 갱신하고 가이드·라우트·휴대형 검사를 실행한다.

## ProKit을 참고한 흐름과 시각 안내

제작실의 5단계 흐름은 semantic HTML 목록, Heroicons Solid, 44px 아이콘, 점선 연결을 사용한다. 가이드 도식 7종도 HTML로 반응형 표시하고 SVG 원본을 함께 제공한다. 자세한 설명은 제작실·목록·상세의 버튼으로 여는 네이티브 모달에 분리하며 선택·검수 초안을 유지한다.

실제 조작 캡처와 완성 프레임, `image_gen`으로 만든 음악 길잡이 3가지 자세와 스타일 콘셉트 보드를 가이드에 포함한다. 생성한 콘셉트는 실제 렌더 완료로 안내하지 않는다. 공식 Heroicons v2.1.5 Solid 22개는 로컬 sprite와 MIT 라이선스로 동봉한다. 안내·활용 팁·중요·주의·경고는 색과 라벨·아이콘을 함께 사용하고, 가이드는 Markdown admonition에서 렌더링한다.
