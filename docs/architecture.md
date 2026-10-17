# 구성과 라이선스 경계

```text
music-road-skills/
├── skills/                 Codex 스킬과 HTML·스크립트
├── docs/                   설치·사용·운영 문서
├── release/                날짜·제목 기반 릴리스 노트
├── manifest.json           묶음 버전과 스킬 목록의 기준
└── VERSION                 읽기 쉬운 묶음 버전
```

## 책임 분리

| 구성 | 포함 | 포함하지 않음 |
| --- | --- | --- |
| Showreel/JIZURA 스킬 | 계획·프로젝트·HTML·검수 흐름 | 엔진 바이너리·사용자 프로젝트 |
| HTML 제작실 | 선택·재생·피드백·manifest | 원격 공개·임의 명령 실행 |
| 업데이트 도구 | Release 확인·백업형 설치 | 자동 덮어쓰기·모델 설치 |
| Road Music CLI 연계 | 공개 handoff 계약 | 이미지 생성 모델 자체 |

## 라이선스

- 이 저장소: [MIT](../LICENSE)
- Showreel upstream: `64521220a2f8e91cb9894400c48c15b7f45205d6`, MIT
- JIZURA upstream: `fc16bfe43ea4a6c25a21f1caf04d17326de14f00`, MIT
- 글꼴: 각 자산 디렉터리의 라이선스 파일을 함께 유지

개인 음원, 사용자 입력, 생성 이미지, 렌더 MP4의 이용 권한은 이 저장소의 MIT 라이선스와 별개입니다. 외부 업로드 전에는 사용 권한을 확인하세요.

## 호스트와 이미지 생성

Codex와 Antigravity는 같은 프로젝트 선택·미디어·이미지 manifest 계약을 사용합니다. Codex 기본 스킬 대상은 `CODEX_HOME/skills`(기본 `~/.codex/skills`)이고, Antigravity App/IDE는 `~/.gemini/config/skills`, Antigravity CLI는 `~/.gemini/antigravity-cli/skills`, 공통 프로젝트는 `.agents/skills`입니다. Codex는 대화 환경의 내장 `image_gen`을, Antigravity는 그 환경에서 실제로 제공되는 네이티브 이미지 도구를 선택합니다. 어느 쪽도 이 저장소의 Python/Node 스크립트가 이미지 모델을 내장 실행하거나 유료 API 권한을 추정한다는 뜻은 아닙니다. [Antigravity 설치·실행](antigravity.md)
