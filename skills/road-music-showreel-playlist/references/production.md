# 새 음악 전용 native 제작

자유 연출의 기본 실행 경로다. 사용자가 프리셋을 명시한 경우만 [기존 제작](preset-production.md)을 따른다. 두 경로를 겹쳐 부트하거나 새 콘셉트를 4개 스타일 enum으로 낮추지 않는다.

## 기존 도구

- Showreel: `SHOWREEL_HOME` 또는 `~/.local/share/roadmusic-video-tools/showreel`.
- Python: `SHOWREEL_PYTHON` 또는 기존 `~/.local/share/roadmusic-ltx23/src/.venv/bin/python`.
- Node.js24, FFmpeg/ffprobe, Chrome, Showreel의 기존 playwright-core·NumPy·Pillow.

누락을 확인하면 현재 설치를 찾고 제한을 보고한다. 모델/새 의존성/유료 API를 자동 설치하지 않는다. 설치본 `SKILL.md`와 필요한 brief/design/engine/techniques/qa를 읽고 사용하는 API를 확인한다. 그 경로의 예시 화면을 곡의 기본 디자인으로 복제하지 않는다.

## 1. 원음과 시계만 준비

네 표시 항목이 모두 답해진 display-options.json을 저장한다. 미응답을 false로 채우지 않는다. 곡명은 사용자·오디오 태그·파일명 근거를 구분한다. 보컬곡의 현재 JSON/SRT와 [가사 출처](captions.md)를 먼저 준비한다.

display/composition/media 입력 파일은 이미 존재하는 작업 루트에 둔다. `--out`은 아직 존재하지 않는 새 하위 프로젝트다. 입력 파일을 넣으려고 output을 먼저 mkdir하면 prepare가 충돌로 거부한다.

```bash
"$SHOWREEL_PYTHON" "$PLAYLIST_SKILL/scripts/native_project.py" prepare \
  --music '/절대/원곡.mp3' --captions '/절대/현재-가사.json' \
  --title '확인한 곡명' --display '/절대/display-options.json' \
  --out '/절대/새-프로젝트'
```

여러 곡은 [playlist 입력](playlist.md)의 path/title/captions/원곡 start/duration 목록을 `--playlist`로 준다. 무가사곡만 `--instrumental`을 지정한다. 정확한 구간 proof는 `--start/--duration`을 원곡 초로 지정한다. 같은 output을 덮지 않는다.

prepare는 원곡/가사 복사본, PCM 샘플 경계, playlist.json, captions/lyrics.json·srt, 분석/timeline/mix/실제 FFT, film-input.js와 **빈 native 저자 파일**을 준비한다. style/preset 선택은 없다. source 준비 상태를 새 아트·이미지 생성·모션 구현 완료로 보고하지 않는다.

## 2. 방향과 실제 자산

[음악 연출](music-direction.md)로 콘셉트와 subject/action/space를 설계하고 [이미지 역할](image-direction.md)에 따라 실제 image_gen 결과를 생성·열어 검수한다. 새 음악의 technical/sample 검증도 같은 방식으로 장면 자산과 전용 썸네일을 만든다. composition.json과 media.json은 [계약](composition-contract.md)을 따른다. 원곡 시간·cue id·sourceSha는 준비 입력을 사용한다.

```bash
"$SHOWREEL_PYTHON" "$PLAYLIST_SKILL/scripts/native_project.py" apply \
  --project '/절대/새-프로젝트' --composition '/절대/composition.json' \
  --media '/절대/media.json'
```

사람이 이미지 없이 하라고 명시한 순수 기하 또는 제공·승인 재사용 자산만 --media 생성 자산을 생략할 수 있다. 도구 미설치/rate limit, 테스트·예산·빠른 작업·단순 그래픽 선호는 예외가 아니며 유료 API나 코드 대체를 선택하지 않는다. apply가 asset 이름을 모션으로 바꾸지는 않는다. 정규화된 장면/자산·named cue를 연결하며 저자가 쓴 scenes.js를 덮지 않는다. 일반 production에는 presetId나 CD자산이 필요하지 않다.

## 3. 스타일 프레임에서 장면으로

Codex가 native `REEL.scene`을 직접 작성한다. 먼저 핵심 프레임과 새로운 재질/동작을 시험해 방향을 보고, 가장 약한 안을 고친 뒤 전곡을 확장한다. 같은 index에 motion.js와 새 씬을 함께 로드하지 않는다. [native 표현](showreel-motion.md)을 따른다.

전체 장면 등록 전의 기술/미술 시험은 기본 `render.mjs --dir <project>/reel --stills <실제로 구현한 시각들> --outdir <project>/qa/style-frames`로 할 수 있다. 이는 부분 style frame이며 전곡 구현/최종 검사 통과를 뜻하지 않는다. 빈/미구현 구간을 데모로 채워 최종 checker를 통과시키지 않는다.

저장공간·캐시 검증용 샘플도 같은 production 정책을 따른다. 실제 image_gen 장면 자산·전용 썸네일·media ledger·decode·scene 사용 증거를 생략해 절차형 샘플로 바꾸거나, 다른 엔진·유료 API로 대체하지 않는다.

공통 film-runtime.js는 자산 decode와 기존 표시/전문 가사/실제 FFT/선택 카드만 제공한다. 이것은 아트 디렉션이나 장면 템플릿이 아니다. 기본 레이아웃이 긴 제목/자막·구도와 충돌하면 그 프로젝트에서 읽기 크기/영역을 고치고 검사한다. 본문을 빼거나 너무 작게 해서 문제를 숨기지 않는다.

```bash
node "$PLAYLIST_SKILL/scripts/check-native-project.mjs" \
  '/절대/새-프로젝트' '/절대/새-프로젝트/qa/runtime-v1'
"$SHOWREEL_PYTHON" "$PLAYLIST_SKILL/scripts/native_project.py" render \
  --project '/절대/새-프로젝트' --draft --name draft-v1
```

빈 씬/누락 자산/원문·가사 경계/계획 범위/잘못된 시크는 실패다. 새 checker는 먼저 Python `check`로 동결 입력·captions·미디어·장면 binding을 확인한 뒤 실제 REEL 등록과 frame을 보고 runtime 보고서를 기록한다. --draft는 원음 proof이며 최종 납품/미술 합격을 뜻하지 않는다. 저운동(`still_ratio`/`p90`/긴 정지) 경고는 draft를 `needs-review`로 남기며 섬광·decode·알 수 없는 motion 문제는 계속 실패한다. 다음 수정은 새 이름으로 내보내고 현재 fingerprint의 runtime을 다시 확인한다.

## 4. 비평과 최종 마감

[미술 검수](native-qa.md)와 [기술 품질](production-quality.md)을 함께 적용한다. 실제 proof를 검토한 결과를 creative-review.json에 남기고 가장 약한 장면을 수정한다. 이미지 도구 호출·workspace 자산·media ledger·decode·scene draw/렌더 프레임·전용 썸네일이 모두 현재 fingerprint와 맞을 때만 image-backed 진행으로 기록한다. 이름/색/효과 개수만 바꿔 같은 구성을 반복하지 않는다. 입력/코드/이미지/폰트 변경 뒤 과거 검수 문서를 재사용하지 않는다.

```bash
"$SHOWREEL_PYTHON" "$PLAYLIST_SKILL/scripts/native_project.py" check --project '/절대/새-프로젝트'
"$SHOWREEL_PYTHON" "$PLAYLIST_SKILL/scripts/native_project.py" render --project '/절대/새-프로젝트' --name final-v1
```

기본 Showreel render.mjs/finish.py/QA를 사용한다. final은 sub4 PNG, H.264/yuv420p/BT.709/TV, AAC48k stereo, 실제 전체 길이/프레임/디코드와 음량·정지·섬광을 확인한다. native QA의 종료코드0만 읽지 말고 실제 ‘고칠 것’과 motion issues를 읽는다. 완성 master의 실제 전곡 시트를 직접 보고 납품한다. helper의 rendered 응답만으로 미술·가창 싱크를 자동 완료 처리하지 않는다.

FFmpeg 버전 문제로 native contact_sheet가 실패하면 현재 오류를 확인한 뒤 프로젝트 QA용 사본에서 추출 옵션만 호환 수정하고 시트를 다시 만든다. 설치본/검사 기준을 바꾸지 않는다. renderer --scale 로그를 실제 규격으로 간주하지 말고 ffprobe 결과를 읽는다.

납품은 전곡·공유용·포스터/썸네일·SRT·입력/타이밍/계획·편집 프로젝트·이미지 ledger·검수 기록을 연결한다. 자동/청취/ASR/단어 정렬의 확인 범위를 밝힌다. 렌더러는 하나씩 실행하며 외부 게시·정식 배포는 별도 요청 범위다.

## 최종 출력 재검증

실제 최종 시트를 검토한 뒤 `native_project.py finalize --project '/절대/새-프로젝트' --name final-v1`로 마감한다. render가 저장한 입력·출력·QA 해시 기록과 현재 runtime/creative review를 대조하며 영상을 덮어쓰거나 다시 렌더하지 않는다. 입력/출력이 바뀌었으면 새 이름으로 렌더한다. 저운동 경고가 남으면 실제 final motion JSON과 master를 본 뒤 [검토 계약](composition-contract.md)의 motionReview를 기록하고 finalize한다. 섬광·규격·디코드·미분류 QA 실패는 이 경로로 허용하지 않는다.

이미지 공급자·생성 기록은 [공통 이미지 계약](../../road-music-video-studio/references/image-providers.md)을 따른다. Claude Code는 로드된 `gpt-image`의 Codex CLI 브리지를 사용하며 실제 provider·프롬프트·생성 파일 해시를 기록한다.
