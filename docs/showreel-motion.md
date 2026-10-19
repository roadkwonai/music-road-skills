# Showreel 음악 모션그래픽

음악의 실제 타격과 강약, 가사의 정서 변화에 맞춰 Showreel 플레이리스트 영상을 만듭니다. 기본은 리듬 캔버스이며, 필요한 경우 CD 프리셋과 그루브 다이얼을 고를 수 있습니다.

아래 상대 실행 경로는 저장소 루트에서만 쓴다. 설치본을 다른 작업 디렉터리에서 관리할 때는 현재 읽은 `SKILL.md`의 실제 절대 경로를 쓴다.

```text
$road-music-showreel-playlist로 이 음악에 맞는 모션그래픽을 만들어줘.
먼저 HTML에서 스타일과 스펙트럼·대기곡·현재 곡명·채널명을 선택하게 하고,
선택을 그대로 반영해 전체 길이 영상과 검수 페이지를 만들어줘.
```

## 선택과 표시 요소

HTML 선택 화면에서는 다음을 각각 설정합니다.

| 항목 | 저장되는 값 |
| --- | --- |
| 스타일 | 실제 프리셋 ID |
| 선형 스펙트럼 | 표시/숨김 |
| 대기 곡 목록 | 표시/숨김 |
| 현재 곡명 | 표시/숨김 |
| 채널명 | 문자열 또는 SKIP |

선택 파일은 이후 `plan`과 `create`에 전달됩니다. Studio가 저장한 선택에는 선택적 `host`가 들어가며 `plan --selection`은 명시 `--host`가 없을 때만 이를 상속합니다. 이전 선택처럼 host가 없으면 `codex`를 사용합니다. 미응답을 자동 SKIP으로 처리하지 않으며, 채널명을 파일명에서 추측하지 않습니다.

공통 HTML 제작실에서 Showreel CD 또는 Showreel 음악 모션그래픽을 저장하면 `showreel-request.json`이 함께 생성됩니다. 이 파일은 chooser의 `request.json`과 같은 계약이므로 `plan`과 `create`의 `--selection` 입력으로 쓸 수 있습니다. `create`에는 원음과 새 출력 경로, 선택한 템플릿이 요구하는 자산 등도 함께 전달합니다.

```bash
python3 skills/road-music-showreel-playlist/scripts/playlist_presets.py plan \
  --genre '락 발라드' --selection /absolute/path/to/project/showreel-request.json \
  --out /absolute/path/to/project/plan.json
```

MV나 JIZURA 모드를 이 입력으로 바꾸지 않습니다. 해당 모드는 저장된 `selection.json`과 `production-request.json`을 각 제작 스킬이 읽습니다.

```bash
python3 skills/road-music-showreel-playlist/scripts/playlist_presets.py choose \
  --out /absolute/path/to/selection --music /absolute/path/to/song.wav
```

## 장면과 자막

- 현재 호스트에서 실제로 생성한 장면·표지 이미지는 프롬프트와 해시를 프로젝트에 기록합니다. Codex/ChatGPT에서는 내장 `image_gen`, 로컬 Claude Code CLI/IDE에서는 로드된 `gpt-image`의 ChatGPT 로그인 Codex CLI 브리지, Antigravity에서는 해당 환경의 네이티브 이미지 기능을 사용하며 공통 [Claude Code 이미지 계약](claude.md)과 [Antigravity 계약](antigravity.md)을 따릅니다.
- 리듬 캔버스는 첫 0.5초에 확인된 제목·아티스트·채널명으로 만든 썸네일을 씁니다. 음악 시계는 밀지 않습니다.
- 그루브 다이얼은 검증된 `cues[].words`가 있을 때만 현재 어절을 호박색으로 강조하고 작은 확대·기울임을 적용합니다.
- 자동 ASR 시간은 검토 전 초안입니다. 원문·원음 시계·cut offset을 보존하고 100% 싱크라고 주장하지 않습니다.

## 여러 곡

여러 곡은 각 원음의 전체 시계와 제목을 유지해 연결합니다. 하나의 렌더에서 가사·커버·현재 곡·대기 목록이 경계에서 전환되는지 확인합니다. 새 음악을 만들거나 외부 게시하는 권한은 이 스킬에 포함되지 않습니다.
