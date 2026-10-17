# Antigravity에서 음악부터 영상까지

[처음으로](../README.md) · [설치](install.md) · [CLI 연계](cli-workflow.md) · [HTML 제작실](html-studio.md)

> [!TIP]
> 같은 스킬과 Road Music CLI를 사용합니다. 이미지는 Antigravity가 제공하는 이미지 기능으로 생성하고, 프로젝트와 HTML 검수 방식은 공통으로 유지합니다.

## 설치할 환경 선택

| 사용하는 환경 | 설치 옵션 | 기본 스킬 폴더 |
| --- | --- | --- |
| Antigravity App / IDE | `--host antigravity` | `~/.gemini/config/skills` |
| Antigravity CLI | `--host antigravity-cli` | `~/.gemini/antigravity-cli/skills` |
| 특정 프로젝트만 사용 | `--target /절대/프로젝트/.agents/skills` | 명시한 폴더 |

이 경로는 2026-10-18의 [공식 Skills 문서](https://www.antigravity.google/docs/skills/) 기준입니다. 구형 폴더를 자동으로 옮기지 않습니다. 기존 수정·다른 스킬도 보존합니다.

저장소를 내려받은 폴더에서 실행하세요.

```bash
node skills/road-music-skills-update/scripts/manage.cjs install \
  --source "$PWD" --host antigravity

node skills/road-music-skills-update/scripts/manage.cjs status \
  --host antigravity
```

Antigravity CLI이면 두 명령의 host를 `antigravity-cli`로 바꿉니다. 작업 공간 한 곳에만 설치하려면 `--target`으로 절대 경로를 지정하세요. 설치 후 새 세션에서 스킬이 발견되는지 확인합니다. [공식 Rules](https://www.antigravity.google/docs/rules/)에 따라 `AGENTS.md`도 사용할 수 있어 동일 지침을 `GEMINI.md`에 다시 복제할 필요는 없습니다.

## 첫 요청 예시

```text
설치된 Road Music CLI와 road-music-video-studio 스킬을 사용해줘.
먼저 CLI의 공개 schema와 준비 상태를 확인하고, 이 음악을 HTML 제작실에서 들려줘.
Showreel/CD/JIZURA/MV의 차이를 보여주고 내가 고른 스타일과 표시 설정을 저장해서 이어가줘.
새 이미지가 필요한 단계에서는 Antigravity의 현재 이미지 생성 도구나 내장 image-generator를 사용해줘.
기존 가사와 음악의 시간축을 지키고 이미지·부분 영상·완성본을 HTML에서 검수할 수 있게 해줘.
```

새 음악도 맡기려면 가사·프롬프트 검토 또는 전체 자동 위임 범위를 함께 적습니다. 생성은 Road Music의 `song:generate` → `job:wait` → `songs:list` 흐름을 따릅니다. 반환된 절대 음원 경로를 영상 제작에 전달하며 제목만 보고 다른 곡을 고르지 않습니다.

## 이미지 생성 차이

ChatGPT/Codex는 `image_gen`, Antigravity는 **현재 Antigravity가 제공하는 Nano Banana 이미지 기능**을 사용합니다. Antigravity의 모델 선택 메뉴를 영상 이미지 모델용 옵션으로 바꾸거나, 존재하지 않는 `--image-model` 값을 CLI에 넣지 않습니다. [공식 Models](https://www.antigravity.google/docs/models/#additional-models)

Showreel CD 장르 계획은 아래처럼 공급자를 기록할 수 있습니다.

```bash
python3 skills/road-music-showreel-playlist/scripts/playlist_presets.py plan \
  --genre '록 발라드' --style '그루브 다이얼' \
  --host antigravity --out '/절대/새-계획.json'
```

이 명령은 **프롬프트 계획만** 만듭니다. 실제 생성은 Antigravity의 도구가 수행합니다. 반환된 파일을 검수하고 같은 이미지 manifest와 HTML에 연결합니다. [호스트별 이미지 생성 계약](../skills/road-music-video-studio/references/image-providers.md)

## 확인 범위와 한계

- 원음 재생, 표시 선택, 파일 확인, 피드백 저장은 공통 HTML이 담당합니다.
- Showreel/JIZURA 엔진과 이미지 생성 기능은 스킬 설치와 별도입니다. 없는 도구를 설치 완료·생성 완료로 표시하지 않습니다.
- 공개 CLI 명령과 JSON 출력은 호스트와 무관합니다. Antigravity의 터미널 권한은 해당 환경의 정책을 따릅니다.
- 이 통합의 자동 검사는 설치 경로·공통 계획·HTML·CLI 연결을 확인합니다. Antigravity 계정의 실제 이미지 생성과 청취 싱크를 보증하지 않습니다.

Showreel MV는 추가 유료 API를 기본 사용하지 않습니다. 유료 모델은 별도 요청이 있을 때만 적용하며, 이미지 기능이 없거나 제한에 걸렸다는 이유로 자동 전환하지 않습니다.
