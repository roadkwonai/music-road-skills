# HTML에서 보고 선택해 CLI 제작으로 이어가기

스타일을 보고 고르려는 새 제작에서 사용한다. `catalog`는 읽기 전용 샘플 목록이고 `choose`는 실제 선택을 저장하는 화면이다. 이미 명시한 스타일·표시 설정을 다시 고르도록 강제하지 않는다. 이미지 생성·음원 분석·렌더는 선택 저장과 별개인 기존 제작 절차를 따른다.

## 로컬 실행 환경

CLI와 브라우저가 같은 컴퓨터에 연결된 ChatGPT/에이전트 실행 환경을 기준으로 한다. 선택 서버는 `127.0.0.1`에만 열린다. 이 주소가 다른 컴퓨터나 원격 실행기의 같은 주소를 뜻하지는 않는다. 로컬 파일·브라우저 연결이 없는 환경에서 URL이 열린다고 보장하거나 포트를 외부에 공개하지 않는다. 그때는 정적 카탈로그를 볼 수 있는 방식으로 제공하고, 스타일 이름과 미확정 표시 항목을 대화로 받아 같은 검증 입력을 준비한다.

Road Music 앱의 공개 CLI 명령이나 MCP 서버를 새로 설치하는 기능이 아니다. 기존 개인 스킬 helper의 명령이며 음악·모델·서비스 설정을 바꾸지 않는다.

## 선택 세션

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" choose \
  --music '/절대/원곡.mp3' --out '/절대/새-선택세션' --open
```

- `--open`을 명시하면 기본 브라우저를 연다. Codex 패널 등 호스트의 파일/브라우저 표시 도구를 쓸 때는 생략하고 반환된 URL을 연다.
- `--out`은 존재하지 않는 새 폴더다. 이전 선택/프로젝트를 덮어쓰지 않는다.
- 음악 파일은 선택 화면에 이름과 출처를 연결하는 선택 인자다. 여러 곡은 이 옵션을 생략하고 이후 `create --playlist`로 연결한다.
- 기본 대기 시간은 900초이며 `--timeout`으로 1~86400초를 지정할 수 있다. 만료·취소·미응답은 SKIP이나 제작 완료가 아니다.

실행 직후 stderr에 `{"event":"chooser-ready","url":"http://127.0.0.1:포트/?token=...",...}`가 나온다. 이 URL을 사용자에게 보여 주고 CLI 작업은 선택을 기다리게 둔다. 선택을 기다리는 작업을 유지하고, 완료 JSON을 받으면 같은 요청에서 곧바로 `plan/create --selection`과 제작을 이어간다. 완료 응답이나 request.json이 이미 있는데도 선택 대기라고 답하지 않는다. 대화가 새 턴으로 이어졌을 때는 먼저 기존 request.json/완료 응답을 확인하며 같은 선택을 다시 받지 않는다. 선택 전에도 원곡·가사·리듬 분석은 진행할 수 있다. 사용자의 실제 선택 서버에 검수용 응답을 대신 제출하지 않는다. 자동 검수는 별도의 새 세션/폴더에서 한다.

사용자는 등록된 실제 샘플 영상을 재생해 스타일 하나를 선택하고, 스펙트럼·대기곡·현재 곡명은 각각 표시/표시 안 함/SKIP, 채널명은 입력/SKIP으로 답한다. 미응답 항목이 있으면 저장할 수 없다. 샘플은 새 음악으로 이미 제작한 영상이 아니며, 이 선택 저장 단계에서는 이미지를 만들지 않는다. 다음 제작 단계에서 순수 기하 또는 사용자 제공 이미지 재사용을 고르지 않았다면 리듬 캔버스도 곡별 장면 이미지와 첫 0.5초 썸네일을 생성해 음악·가사 방향을 적용한다.

저장하면 서버가 종료되고 stdout JSON 한 줄로 `status=completed`, 선택 파일/표시 파일 경로와 실제 선택을 반환한다. 세션 토큰은 선택 파일에 넣지 않는다.

```json
{"schemaVersion":1,"styleId":"groove-dial","display":{"showSpectrum":true,"showQueue":false,"showNowPlaying":true,"channelName":"사용자가 입력한 채널명"},"music":"/절대/원곡.mp3"}
```

`request.json`과 `display-options.json`은 모두 응답이 갖춰졌을 때만 저장된다. UI의 SKIP은 false/빈 채널명으로 정규화한다. 채널명을 프로젝트명이나 예시 채널명으로 자동 채우지 않는다.

## 계획과 제작에 연결

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" plan \
  --selection '/절대/선택세션/request.json' --genre '록발라드' \
  --vocal female --act solo --brief '확인된 음악·가사·편성에 맞춘 연출' \
  --out '/절대/genre-plan.json'
```

보컬·편성은 실제 생성 기록이나 사용자 설명으로 정한다. 스타일을 선택한 것으로 아티스트·가사 검수가 완료되지는 않는다. 이 plan으로 호스트별 공급자 계약에 따라 이미지 5개를 실제 생성·검수한 뒤 기존 자막과 함께 제작한다. Claude는 `gpt-image` 브리지의 실제 파일을 사용한다. 일반 custom은 이전처럼 `--style`/assetSchema 제작 흐름을 쓰며 CD 장르 planner로 대체하지 않는다.

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" create \
  --selection '/절대/선택세션/request.json' --plan '/절대/genre-plan.json' \
  --music '/절대/원곡.mp3' --captions '/절대/가사타이밍.json' \
  --assets '/절대/images.json' --out '/절대/새프로젝트'
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" render --project '/절대/새프로젝트'
```

스타일과 표시 값은 선택 파일에서 그대로 적용하며 `production.selectionSource`에 경로·SHA-256을 남긴다. 명시한 다른 스타일/plan 또는 선택한 것과 다른 음원은 거부한다. 같은 스타일의 한국어 이름·별칭은 허용한다. `--display`는 사용자가 선택 변경을 요청했을 때만 쓰며 저장 선택보다 우선한다. 원래 선택 파일을 고치지 않고 새 설정으로 남긴다.

HTML로 이미 받은 4개 응답은 다시 질문하지 않는다. 스타일만 대화로 지정했거나 HTML이 열리지 않는 환경에서는 [표시 선택](playlist.md)의 미응답 항목만 받아 기존 `--style`/`--display`로 진행한다. 복잡한 새 플랫폼 설치를 스타일 선택의 선행 조건으로 만들지 않는다.

## 검증

`test_playlist_chooser.py`는 실제 HTTP의 선택 저장·부분 응답 거부·다른 세션/Origin/Host/토큰·경로·본문 크기·기존 출력 보호·동영상 Range·plan/create 선택 전달을 확인한다. 화면 검수는 별도 세션에서 샘플 영상 재생, 미응답 저장 차단, 선택 파일과 화면 응답 일치를 확인한다. 원곡 전체 제작 검수는 [production.md](production.md)를 따른다.
