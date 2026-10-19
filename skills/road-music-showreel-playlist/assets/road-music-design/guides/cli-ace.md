# CLI: 음악을 제작실과 완성 결과로 연결하기

## 이 문서의 역할

CLI에서 현재 음악의 경로를 확인하고 제작실을 열며, 완성 음원·원가사·자막·영상·스토리보드를 등록하는 순서입니다. 제작 뒤 모든 결과를 살펴보는 방법은 [내 작업물](works.md)을 보세요. 현재 프로젝트 전용 호환 화면은 [완성 결과](results.md), [결과 검수](review.md)입니다.

## 사용할 수 있는 명령부터 확인하기

설치된 CLI의 `schema`가 최종 기준입니다. 다른 버전 문서에 나온 `motion:*`·`skills:*` 명령이 현재 schema에 없으면 실행하지 않습니다. 아래의 공통 스킬 helper 경로로 같은 작업을 진행할 수 있습니다.

```bash
node cli/road-music.js schema
node cli/road-music.js songs:list
```

공개 CLI 예시는 `cli/road-music.js`가 있는 Road Music 키트 루트에서 실행합니다. Python helper는 별도로 설치한 스킬 경로를 사용하며 해당 명령의 `--help`가 기준입니다.

목록 응답의 절대 `path`와 `dir`를 그대로 씁니다. 이름이 같아도 다른 음악일 수 있으므로 경로를 추측하거나 파일명만 바꾸지 마세요.

![원음 확인부터 결과 등록까지의 보조 명령 흐름](media/production-flow.svg)

도식은 명령을 실행하는 순서의 예시이며, 음악·렌더·설치를 자동으로 시작한다는 뜻이 아닙니다. 아래에서 `/absolute/...`는 사용자가 직접 확인한 실제 절대 경로로 바꿉니다.

> [!WARNING]
> `/absolute/...` 예시는 그대로 실행하지 않습니다. `songs:list`에서 확인한 실제 경로와 새 프로젝트 경로로 바꾸고, 기존 프로젝트에는 `init`을 다시 실행하지 않습니다.

```bash
STUDIO_SKILL="/absolute/skills/road-music-video-studio" # 현재 읽은 SKILL.md의 부모
PROJECT_DIR="/absolute/output/video-project"             # init으로 만든 새 프로젝트 또는 기존 프로젝트
MUSIC_PATH="/absolute/music/approved-source.wav"         # songs:list 응답에서 확인한 원음 경로
MANIFEST_PATH="/absolute/output/publish.json"             # 새로 준비한 결과 등록 manifest
```

## CLI 시작과 제작실

명시적인 `service:start`는 서비스를 준비하고 설치된 제작실 화면을 엽니다. 이미 열린 Road Music 페이지가 있으면 같은 탭을 재사용합니다. 일반 조회·schema·배치 명령은 페이지를 열지 않습니다.

```bash
node cli/road-music.js service:start
```

제작실 스킬이 없으면 서비스 성공과 화면 열기 실패를 구분해 알려 줍니다. 자동 설치하지 않으며, 자동화에서 화면이 필요 없으면 `ROADMUSIC_STUDIO_AUTO_OPEN=0`을 사용합니다.

## 특정 음악으로 제작실 열기

현재 읽은 `road-music-video-studio/SKILL.md`의 실제 부모 경로를 `STUDIO_SKILL`에 넣습니다. `init`의 출력 폴더는 새 프로젝트이며, 기존 프로젝트는 `serve --project`로 다시 엽니다. 음악·엔진·모델을 새로 만드는 명령이 아닙니다.

```bash
python3 "$STUDIO_SKILL/scripts/studio.py" init \
  --out "$PROJECT_DIR" --music "$MUSIC_PATH" --mode showreel-motion --host codex
```

성공하면 새 프로젝트가 준비됩니다. 기존 프로젝트에는 위 `init`을 실행하지 말고, 앞서 정의한 `PROJECT_DIR`를 해당 프로젝트로 바꾼 뒤 아래 명령만 실행합니다. `serve`는 화면을 제공하는 동안 실행 상태를 유지합니다. 결과 등록 명령은 별도 터미널에서 실행하거나 이 세션이 종료된 뒤 실행하세요.

```bash
python3 "$STUDIO_SKILL/scripts/studio.py" serve \
  --project "$PROJECT_DIR" --review --open
```

제작실에서 설정만 저장하고 실제 생성·렌더는 선택한 스킬이 이어서 진행합니다. `--review`를 사용하면 설정 저장 후에도 서버가 유지되고, 결과 검수 페이지의 **검수 마치기**로 세션을 끝냅니다.

> [!IMPORTANT]
> `serve --review --open`을 실행한 터미널은 검수 세션이 끝날 때까지 유지합니다. 창을 닫거나 같은 명령을 반복해 새 페이지를 열지 말고, 열린 제작실 탭 하나에서 다음 단계로 이동합니다.

프로젝트가 준비된 뒤에는 해당 제작 스킬에 실제 제작을 요청합니다. 위 명령은 음악·영상 생성이나 모델 설치를 하지 않습니다.

## 생성 작업은 완료를 기다리기

음악 생성을 요청했다면 반환된 `jobId`를 `job:wait`으로 확인합니다. 아래 값은 실제 생성 응답의 값으로 바꿉니다. 완료 전에 입력 음악을 최종 납품 파일로 등록하지 않습니다.

```bash
node cli/road-music.js job:wait --json '{"jobId":"RETURNED_JOB_ID"}'
```

연결 오류에 `uncertain:true`가 있으면 같은 생성을 자동으로 다시 제출하지 않고 서비스·대기열·곡 목록을 확인합니다. 영상 렌더라면 `service:status`, `queue:list`, `video:state`, 지정한 `--output` 파일을 차례로 확인합니다. 이미 진행 중이거나 출력이 생긴 렌더를 겹쳐 제출하지 마세요.

## 원가사와 SRT 준비

원가사는 승인된 TXT/Markdown을 유지합니다. 이미 준비된 SRT가 있으면 그대로 등록합니다. `song:srt`·`song:save-srt`가 schema에 있는 설치본에서는 해당 명령의 입력·출력 규칙으로 자막을 준비할 수 있습니다. 시간 정보가 있다는 이유로 직접 청취로 확정된 싱크라고 판단하지 않습니다.

저장 모드의 `song:srt`는 실제 곡의 절대 `dir`와 새 `--output` 파일을 사용합니다. 결과 자막을 확인한 뒤 등록하며 기존 파일을 덮어쓰지 않습니다.

```bash
node cli/road-music.js song:srt --json '{"dir":"/absolute/from-song-list","save":true}' --output /absolute/new-captions.srt
```

자막이 없다면 완성 결과는 **SRT 미등록**으로 안내합니다. LRC를 SRT로 이름만 바꾸거나, 음성 인식 문장으로 원가사를 교체하지 않습니다.

## 완성 파일 등록

manifest에는 실제 존재하는 절대 경로만 넣습니다. 아래 JSON을 `MANIFEST_PATH`로 정한 UTF-8 파일에 저장합니다. 제작하지 않은 항목은 빼고, 보존할 이전 버전은 빠짐없이 포함하세요.

- **audio**: 완성 음원입니다.
- **lyrics**: 원가사입니다.
- **captions**: 시간 자막입니다.
- **video**: 완성 영상입니다.
- **storyboard**: 검수 이미지입니다.

```json
{
  "title": "예시 곡 - 최종본",
  "video": [{
    "path": "/absolute/output/final-motion.mp4",
    "styleLabel": "예시 조합 스타일",
    "styleId": "optional-style-id"
  }],
  "audio": ["/absolute/output/final-audio.wav"],
  "lyrics": ["/absolute/output/original-lyrics.txt"],
  "captions": ["/absolute/output/lyrics.srt"],
  "storyboard": ["/absolute/output/storyboard-01.png"]
}
```

```bash
python3 "$STUDIO_SKILL/scripts/studio.py" publish \
  --project "$PROJECT_DIR" --manifest "$MANIFEST_PATH"
```

> [!CAUTION]
> `publish`는 프로젝트의 등록 목록 전체를 교체합니다. 이전 버전·원가사·자막·스토리보드를 유지하려면 다음 manifest에도 함께 넣습니다. 원음 SHA-256을 기록하면 현재 원음과 결과의 일치 여부를 확인할 수 있습니다. `publish` 뒤 결과는 음악별 보관함에도 누적 등록됩니다. [내 작업물](works.md)에서 같은 원음의 이전 결과와 비교합니다.

`video` 항목은 기존처럼 절대 경로 문자열을 쓸 수 있으며, 스타일 기록이 필요하면 `path`, `styleLabel`, `styleId`를 가진 객체를 씁니다. 현재 설치본이 지원하는 정확한 manifest 형식은 스킬 문서와 명령 출력으로 확인하세요.

## 예전 프로젝트를 보관함에 추가하기

결과가 이미 등록된 기존 프로젝트는 공통 제작실 helper로 보관함에 추가할 수 있습니다. 이 helper는 원본 파일을 복사하지 않으며, 실제 결과와 원음 근거가 있는 파일만 기록합니다.

```bash
python3 "$STUDIO_SKILL/scripts/studio.py" library-register --project /absolute/existing-project
```

이 명령은 Road Music CLI의 공개 `motion:*` 명령이 아닙니다. 현재 CLI schema에 없는 명령을 추측해 실행하지 마세요.

## 스킬 묶음 상태 확인

현재 읽은 updater 스킬의 절대 경로와 실제 설치 부모를 지정합니다. `status`·`check`는 읽기 전용이며, 새 버전이 있다는 사실만으로 설치·watch·모델 다운로드를 실행하지 않습니다.

```bash
UPDATE_SKILL="/absolute/skills/road-music-skills-update"
node "$UPDATE_SKILL/scripts/manage.cjs" status --target /absolute/skills
node "$UPDATE_SKILL/scripts/manage.cjs" check --target /absolute/skills
```

## 오류와 복구

### 서비스는 켜졌는데 제작실이 보이지 않아요

화면 열기 경고를 확인하고 설치된 제작실·Ego 브라우저를 확인합니다. 같은 요청을 반복해 새 탭을 늘리지 않습니다. [문제 해결](troubleshooting.md)을 보세요.

### 결과 등록 뒤 파일이 안 보여요

열린 프로젝트 경로와 manifest의 절대 경로를 확인한 뒤 완성 결과의 **새 결과 확인**을 누릅니다. 없는 파일을 등록하거나 입력 음원을 완성본으로 표시하지 않습니다.

### 다른 버전의 명령 예시는 실행해도 되나요

현재 schema에 있는 명령과 필드만 사용합니다. 지원하지 않는 명령은 현재 스킬 helper로 작업하고, 업데이트는 별도로 요청받은 범위에서만 진행합니다.
