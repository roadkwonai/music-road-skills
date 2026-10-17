# 이름으로 저장하고 다시 쓰기

저장소는 `assets/presets/<id>/`다. CD 계열은 참고 PNG 5개를 쓸 수 있지만, 커스텀 계열은 자체 template과 선언한 자산만 보존한다. 모든 프리셋은 실제 `preview.mp4`, `poster.jpg`, 검수 근거를 로컬에 보존하며 실행은 외부 출력 폴더에 의존하지 않는다.

`show <스타일>`의 JSON을 새 작업 폴더에서 복사·수정한다.

| 필드 | 지원값 |
|---|---|
| schemaVersion / id | 1 / 소문자 시작, 영문 소문자·숫자·하이픈, 2~63자 |
| name / aliases / genres | 한국어 이름 / 별칭 목록 / 추천 장르 목록 |
| description / artDirection | 보이는 설명 / 촬영·인물·질감 방향 |
| category | `cd`(기본) 또는 CD가 아닌 커스텀 분류 문자열. 검색·표시 정보이며 실행 hook이 아니다 |
| template | custom은 자체 번들 폴더 `template`을 지정하며, 그 안에 `index.html`이 필요하다. 상대 경로 밖·symlink는 거부한다 |
| assetSchema | 자산 역할별 `file`, `minSide`, 선택 `alpha`. 역할명은 임의이며 CD 이름을 강제하지 않는다. 빈 객체 `{}`는 절차형으로 이미지 자산을 요구하지 않는다 |
| genrePlanner / motionMode | 그루브 다이얼은 `category:"rhythm-cd"`, `genrePlanner:"cd-assets"`로 5개 CD 자산 장르 계획을 명시 지원. `motionMode=soft/balanced/drive`. 일반 custom은 기존 계약을 유지한다 |
| requiresArtist | CD 기본 true, custom 기본 false. true일 때만 가상 아티스트 캐스팅·이미지 검수를 요구한다 |
| variant / discPeriodSeconds / caption / palette | CD 전용 설정. custom은 선택 템플릿이 필요한 설정을 자체적으로 해석한다 |
| prompts / referenceAssets | CD의 artist/case/paper 및 photoA/photoB/photoC/case/paper 기본값. custom 등록 자산은 assetSchema.file의 로컬 파일이며, 제작 시 --assets manifest가 각 역할의 실제 이미지 경로를 지정한다 |
| preview | status=ready, video/poster 실제 파일 경로, 가사·영상 검수 범위·음원 메모 |

`category:"cd"`는 레거시 CD 템플릿과 설정을 사용한다. custom은 template을 제공하고 assetSchema는 선언 자산 또는 빈 객체 `{}`의 절차형으로 정한다. requiresArtist는 custom에서 선택 사항이며 기본 false다. template 폴더 안의 HTML/JS와 필요한 일반 소스 파일을 함께 복사한다. `PLAYLIST_CONFIG`, `PLAYLIST_LYRICS`, `PLAYLIST_SPECTRUM`, 순수 함수 `__seek(t)`, boolean `window.__ready=true` 계약을 지키는 실제 템플릿 없이 새 스타일을 등록하지 않는다. JSON에만 없는 효과를 적어 구현된 것으로 보고하지 않는다.

`chrome-prism`은 새 투명 케이스·차가운 크롬·진주 아크릴·절제된 홀로그램 반사를 쓰는 `prism` variant다. K-POP/댄스 팝/일렉트로닉의 현대적 새 제품 요청에 적합하지만, 최신이라는 표현만으로 장르나 유행을 단정하지 않는다. `preview.status=pending`은 프리셋을 선택할 수 있다는 뜻일 뿐 검수된 미리보기가 있다는 뜻이 아니다.

## 등록

1. 뜻이 분명한 한국어 이름, 영문 id, 별칭을 정한다. 예: `새벽 테이프`, `dawn-tape`. 기존 이름/별칭 충돌은 거부된다.
2. CD는 5개 자산·캐스팅 검수를, custom은 assetSchema의 각 선언 자산 또는 빈 assetSchema의 절차형 결과를 준비한다. 인물을 요구하지 않는 custom에 가수를 만들지 않는다.
3. custom은 자체 `template/index.html`과 필요한 로컬 JS/CSS를 준비하고, 실제로 seek 가능한 미리보기를 검수한다. 미등록 스타일 시험은 새 프로젝트 경로에서 진행한다.
4. 등록용 JSON에 선언 자산, template, preview.video/poster의 실제 상대 경로, status=ready와 검수 상태를 넣는다.
5. 등록하고 재선택을 확인한다.

```bash
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" add --spec '/절대/새스타일/preset.json'
"$PLAYLIST_PY" "$PLAYLIST_SKILL/scripts/playlist_presets.py" show '새벽 테이프'
```

`add`는 선언 자산·template·미리보기·포스터·설정을 원자적으로 스킬로 복사해 외부 임시 경로 의존성을 없앤다. 기존 항목은 덮어쓰지 않고 카탈로그도 갱신한다. 검수 문서는 새 프리셋 폴더에 보존한다.

다음 요청: “새벽 테이프로 이 노래에 맞는 포토월 플레이리스트를 만들어줘.” 등록된 이름은 다음 제작에서 `--style`로 선택한다. 현재 실제 등록은 CD 5종, 리듬 CD 그루브 다이얼, 비 CD 음악 모션그래픽 리듬 캔버스다. 리듬 캔버스는 [음악 해석·구간 연출](music-direction.md)의 direction 적용을 거친다. 다른 형식은 template과 미리보기까지 등록된 뒤에만 제공한다.
