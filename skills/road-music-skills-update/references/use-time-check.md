# 스킬 사용 시 업데이트 확인

스킬 제작·수정 요청을 시작할 때에만, 해당 설치본의 절대 부모 스킬 경로를 대상으로 **한 번** 읽기 전용 확인한다.

```bash
node /absolute/skills/road-music-skills-update/scripts/manage.cjs check \
  --target /absolute/skills
```

- Codex, Antigravity, 프로젝트 범위마다 실제 설치 부모가 다르므로 `--target`은 그 스킬 폴더들을 담는 절대 경로로 쓴다.
- 같은 요청에서 이미 확인했거나 버전 변화가 없으면 조용히 제작을 계속한다.
- 새 Release만 짧게 알리고, 설치·업데이트·`watch`는 사용자의 명시 요청이 있을 때만 실행한다.
- 관리 상태가 없는 체크아웃도 현재 `manifest.json`/`VERSION`과 최신 Release를 비교한다. 설치되지 않았다는 이유만으로 새 버전이라고 알리지 않는다.
