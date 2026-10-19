# 릴리스

이 저장소는 GitHub 공개 저장소 `roadkwonai/music-road-skills`에서 버전화합니다. Release는 묶음 버전, manifest, 릴리스 노트, 배포 파일의 연결을 보존해야 합니다.

## 준비

1. `VERSION`과 `manifest.json`의 `version`을 같은 새 버전으로 맞춥니다.
2. `release/YYYY-MM-DD-title.md`를 새로 만듭니다.
3. 스킬·HTML·업데이터의 관련 테스트와 설치 검증을 실행합니다.
4. 아카이브와 SHA256SUMS를 만들고 GitHub Release에 새 태그로 올립니다.

## 릴리스 노트 형식

```md
---
version: 0.1.1
date: 2026-10-18
title: short-title
---

# 0.1.1 — short title

## 변경
- 사용자에게 보이는 변경

## 검증
- 실행한 검사와 결과

## 제한
- 남아 있는 환경·엔진·청취 검증 범위
```

동일한 정식 버전을 다시 올리거나 기존 GitHub Release를 덮어쓰지 않습니다. 새 버전은 새 태그와 새 노트를 사용합니다. 2026-10-20의 `0.1.0` 수정본 재배포는 사용자 승인으로 기록한 버전 초기화 예외이며, 이후 릴리스 절차의 예시나 일반 규칙으로 사용하지 않습니다.

> [!TIP]
> 개인 음원, 절대 사용자 경로, 토큰, 로컬 생성물, 대형 모델 파일은 Release asset에 포함하지 않습니다.
