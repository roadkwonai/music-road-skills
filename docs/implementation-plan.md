# 통합·배포 실행 계획

기준일: 2026-10-18 · 공개 저장소: `roadkwonai/music-road-skills`

## 완료 기준

- Showreel CD 호환 이름, Showreel MV, JIZURA 음악 스튜디오, Showreel 음악 모션그래픽의 원본·상세 문서·HTML을 한 저장소에서 관리한다.
- LTX 2.5 기반 `road-music-mv` 및 모델·엔진·개인 음원·프로젝트는 포함하지 않는다.
- HTML에서 스타일 선택, 음악 재생, 이미지/영상 확인, 표시 설정, 피드백 저장과 제작 요청 전달을 할 수 있다. 저장된 선택은 AI가 실제로 읽고 다음 단계에 반영한다.
- CLI 설치에 고정 버전의 스킬 묶음을 포함하고, 공개 명령으로 설치 상태·새 버전 확인·설치/업데이트·음원 전달을 지원한다.
- `release/YYYY-MM-DD-title.md`를 버전과 연결하고 ZIP·SHA256SUMS·GitHub Release를 만든다.
- 새 Release 알림은 읽기 전용 확인으로 동작하며, 로컬 변경은 보존하고 설치 전에 백업한다.

## 구조

| 경로 | 책임 |
| --- | --- |
| `skills/road-music-showreel-playlist/` | Showreel 모션그래픽 및 CD 프리셋, 기존 선택 화면 |
| `skills/road-music-showreel-cd/` | 기존 이름 호환 |
| `skills/road-music-showreel-mv/` | 이미지·스토리보드·리듬 편집 MV |
| `skills/road-music-jizura-playlist/` | JIZURA Studio·키네틱 타이포 |
| `skills/road-music-video-studio/` | 공통 HTML 제작·리뷰 화면과 음악 전달 |
| `skills/road-music-skills-update/` | 설치·Release 확인·보존 업데이트 |
| `docs/` | 설치, AI/CLI 연계, 각 스킬 상세, HTML, 업데이트, 배포 |
| `release/` | 날짜·제목 기반 Release 노트 |

## 실행 순서

1. 원본과 의존성 조사, 공개 배포용 경로·기록 정리.
2. HTML 공통 Studio와 기존 엔진 편집기 연결, 선택/검수 상태 저장.
3. 설치/업데이트 도구, manifest와 재현 가능한 Release 패키지 구현.
4. CLI 기본 설치와 `skills:*`·`motion:*` 연결, 문서·패키지·테스트 갱신.
5. 격리 폴더 설치·변조 거부·로컬 수정 보존·HTML 조작·실제 API 확인.
6. 공개 저장소 게시와 첫 Release, CLI 변경의 검증·배포, 신규 버전 알림 설정.

스킬·템플릿 설치와 영상 엔진/모델 설치는 분리한다. `image_gen`은 호스트 도구이며 CLI만으로 이미지 생성이 완료됐다고 하지 않는다. HTML 저장·재생 검사는 가창 싱크의 청취 인증이 아니다.
