# JIZURA 음악 스튜디오

JIZURA 네이티브 스타일·타이포·기하 모션을 음악 길이와 원문 가사 시계에 맞춰 제작합니다. 단일 스타일뿐 아니라 구간별 리듬 변주와 여러 전역 스타일의 조합을 비교할 수 있습니다.

로컬 Claude Code CLI/IDE에서는 `--host claude`로 같은 HTML 제작실과 프로젝트 기록을 사용합니다. 이미지 없는 절차형 JIZURA 제작에는 `gpt-image`가 필요 없으며, 이미지가 필요할 때만 [Claude Code 이미지 브리지](claude.md)를 적용합니다.

아래 상대 실행 경로는 저장소 루트에서만 쓴다. 설치본을 다른 작업 디렉터리에서 관리할 때는 현재 읽은 `SKILL.md`의 실제 절대 경로를 쓴다.

```text
$road-music-jizura-playlist로 이 음악을 분석해 서로 다른 세 연출안을 HTML에서 비교하게 하고,
선택한 안으로 편집 가능한 JIZURA 프로젝트와 MP4를 만들어줘.
```

## 실제 산출물

- 편집 가능한 `.jizura.json` 및 원음·큐·방향 기록
- 선택한 구간 연출을 반영한 MP4
- 스타일·자막·전환·타이밍의 검수 자료

## 편집기

JIZURA 스튜디오는 루프백 HTML에서 추천·빠른 설정·전체 편집기를 제공합니다. 추천을 고른 뒤에도 색, 서체, 강도, 구간, 자막을 조정할 수 있습니다. 저장은 검수 완료 선언이 아니며, 렌더와 원음 재생 확인은 별도 단계입니다.

```bash
python3 skills/road-music-jizura-playlist/scripts/studio.py \
  --out /absolute/path/to/studio --audio /absolute/path/to/song.wav
```

표준 출력의 JSON 한 줄에 로컬 URL이 반환됩니다. `127.0.0.1` 서버는 현재 기기에서만 접근합니다.

> [!TIP]
> 제공된 단어 타임스탬프가 없으면 문장 단위를 그대로 보존합니다. 임의 단어 시간 분할을 가창 동기화로 표시하지 않습니다.
