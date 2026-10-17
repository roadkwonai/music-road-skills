---
name: road-music-video-studio
description: 로컬 HTML 제작실에서 음악·실제 스타일 미리보기·화면 표시·스토리보드·완성 영상 검수를 한 화면으로 연결할 때 사용한다. 렌더 엔진 자체를 대체하지 않는다.
---

# Road Music 영상 제작실

Showreel CD 호환 경로, Showreel MV, JIZURA, Showreel 음악 모션그래픽의 **공통 선택·검수 화면**이다. 원곡·가사·기존 프로젝트와 각 스킬의 엔진을 보존한다. HTML에서 저장한 선택은 다음 제작 단계가 읽는 입력이며, 브라우저 선택만으로 영상이 만들어졌다고 말하지 않는다.

시작 시에는 현재 읽은 이 `SKILL.md`의 실제 절대 부모 경로를 `VIDEO_STUDIO_SKILL`에 넣어 [사용 시 업데이트 확인](../road-music-skills-update/references/use-time-check.md)을 한 번만 적용한다.

## 시작하기

새 프로젝트는 실제 절대 음악 경로를 선택적으로 받는다. 이 명령은 원본 음악을 복제하지 않는다.

```bash
VIDEO_STUDIO_SKILL="/absolute/skills/road-music-video-studio" # 현재 읽은 이 SKILL.md의 실제 부모
VIDEO_STUDIO_PY="${SHOWREEL_PYTHON:-python3}"
SKILLS_PARENT="$(dirname "$VIDEO_STUDIO_SKILL")"
UPDATE_SKILL="$SKILLS_PARENT/road-music-skills-update"
node "$UPDATE_SKILL/scripts/manage.cjs" check --target "$SKILLS_PARENT"
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" init \
  --out /absolute/output/my-video \
  --music /absolute/music/song.wav \
  --mode showreel-motion --host codex
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" serve \
  --project /absolute/output/my-video --open
```

음원 파일을 나중에 고르려면 `init --out /absolute/output/my-video`만 실행한다. 제작실의 파일 선택은 해당 파일을 프로젝트 `inputs/music/`에만 보관한다.

제작 방식은 `showreel-cd`, `showreel-mv`, `jizura`, `showreel-motion` 중 하나다. `serve`는 루프백 URL을 stderr JSONL로 알리고, 사용자가 **선택·제작 요청 저장**을 누르면 stdout JSON 한 줄로 `selection.json`과 `production-request.json` 경로를 돌려준다. 브라우저가 먼저 닫혀도 이미 저장된 두 파일을 읽어 제작을 계속한다. 새로 고르라고 반복해서 묻지 않는다.

Showreel CD·모션그래픽 모드에서는 같은 저장 순간에 기존 `plan/create --selection`이 바로 읽을 수 있는 `showreel-request.json`도 만든다. 이 파일은 `schemaVersion`, `styleId`, 정규화된 `display`, 원곡 절대 `music` 경로만 가진다. MV와 JIZURA 선택을 CD 프리셋으로 바꾸거나 이 파일을 만들지 않는다.

작업 호스트는 `codex`, `antigravity`, `antigravity-cli`다. Codex는 ChatGPT/Codex의 `image_gen`을, Antigravity 앱과 CLI는 해당 호스트가 제공하는 같은 계열의 이미지 생성 모델을 사용한다. 앱과 CLI는 설치·실행 표면만 다르다. Showreel MV의 기본 정책은 이 호스트 이미지 도구만 쓰며, 유료 API는 품질이나 실패 복구를 이유로 자동 사용하지 않는다. 제작실은 공급자를 기록하고 입력·자산 검수를 공통으로 처리할 뿐, 지원하지 않는 모델 목록이나 가짜 모델 선택을 만들지 않는다.

`--music` 없이 시작한 뒤에는 제작실에서 브라우저 파일을 고를 수 있다. 이 파일은 프로젝트의 `inputs/music/`에만 저장되며, 웹 페이지는 등록된 음원·미리보기·검수 산출물만 재생한다.

## 네 진입점

- **Road Music Showreel CD**: `road-music-showreel-cd`의 호환 경로이며 실제 Showreel 프리셋 미리보기를 고른다.
- **Road Music 쇼릴 MV**: `road-music-showreel-mv`의 스토리보드·리듬 편집 단계로 제작 방향을 넘긴다.
- **JIZURA 음악 스튜디오**: 선택을 저장한 뒤 `JIZURA_SKILL="$SKILLS_PARENT/road-music-jizura-playlist"`의 `"$JIZURA_SKILL/scripts/studio.py"`로 별도 편집기를 연다. 런타임이 없으면 미설치 상태를 알리며 설치하지 않는다.
- **Showreel 음악 모션그래픽**: `road-music-showreel-playlist`의 실제 프리셋 미리보기와 연결한다.

스타일 카드가 없는 방식은 실제 공통 샘플이 등록되지 않았다는 뜻이다. 임의 동영상이나 엔진 완료 표시를 만들지 않는다.

## 표시와 검수

스펙트럼, 대기 곡 목록, 현재 곡 이름, 채널명은 모두 표시/비표시/SKIP으로 기록한다. SKIP은 이전 값을 보존하고, 처음 SKIP한 값은 선택한 제작 스킬에 전달하지 않는다. `feedback.json`은 초안·수정 요청·승인 상태와 피드백을 원자적으로 저장한다.

렌더 결과가 생기면 명시적인 manifest로만 검수 화면에 등록한다. `publish`는 등록 미디어 전체를 그 manifest로 교체하므로, 후속 등록에서도 유지할 기존 스토리보드·음원·영상·자막을 모두 다시 넣는다.

```json
{
  "title": "봄의 노래",
  "sourceMusicSha256": "렌더에-사용한-원음의-64자리-sha256",
  "video": ["/absolute/output/master.mp4"],
  "audio": ["/absolute/output/master.wav"],
  "captions": ["/absolute/output/lyrics.srt"],
  "storyboard": ["/absolute/output/storyboard-01.png"]
}
```

```bash
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" publish \
  --project /absolute/output/my-video \
  --manifest /absolute/output/publish.json
"$VIDEO_STUDIO_PY" "$VIDEO_STUDIO_SKILL/scripts/studio.py" serve \
  --project /absolute/output/my-video --review --open
```

`publish`는 존재하는 절대 파일과 허용된 미디어 확장자만 등록하고 이전 검수 등록을 누적하지 않는다. 렌더·음원 생성·다운로드·JIZURA 설치를 실행하지 않는다. `--review` 세션은 선택·피드백 저장 후에도 열려 있으며, 브라우저의 **검수 마치기**로만 종료한다.

자세한 입출력 형식과 보안 경계는 [제작실 API](references/studio-api.md)를 읽는다.
