# 가상 아티스트 이미지

이미지 공급자는 [호스트별 이미지 생성](../../road-music-video-studio/references/image-providers.md)을 따른다. `image_gen` 인자 설명은 ChatGPT에 해당하며 Antigravity에서는 해당 세션의 이미지 기능/참조 입력으로 연결한다.


이 문서는 `requiresArtist:true`인 프리셋에만 적용한다. 프리셋은 시각 문법, 인물은 곡마다 설계한다. 장르·명시된 보컬·편성·무드와 사용자 설정을 `artist.json`에 기록하고 성인 가상 인물의 얼굴/헤어/의상/인원/공간을 고정한다. 실존 인물이나 데모 가수를 새 곡에 자동 복사하지 않는다. 보컬 성별은 장르·음역·사진의 인상으로 추정하지 않고 사용자 설명 또는 확인 가능한 음악 생성 메타데이터를 쓴다. 근거가 없으면 `unknown`으로 남긴다.

`requiresArtist:false`인 추상·풍경·절차형 프리셋은 artist·보컬·5개 CD 사진을 요구하지 않는다. `assetSchema`의 역할에 따라 필요한 이미지/자산만 준비하고, 빈 `assetSchema:{}`는 이미지 0개의 절차형 템플릿이다. 가사·스펙트럼·곡목록과 시간 시계는 동일하게 검수한다.

`plan --vocal female --act band`는 여성 리드 보컬과 악기 편성에 맞는 밴드를 뜻한다. 전원 여성 밴드는 사용자가 명시할 때만 프롬프트에 넣는다. `male`, `mixed`, `none`도 각각 남성, 혼성, 가수 없는 연주 이미지로 일치시킨다. 같은 곡의 B/C와 케이스는 A의 실제 로컬 참조를 써서 같은 인물/밴드/의상/공간을 보존한다.

기존 CD 또는 그루브 다이얼의 장르별 `plan`이 있다면 `imageGeneration.assets`의 5개 프롬프트를 출발점으로 삼는다. `referenceRoles`는 아직 파일 경로가 아니다. photoA를 먼저 생성/검수한 뒤 B/C/case의 참조 역할을 실제 로컬 경로로 바꿔 `referenced_image_paths`에 전달한다. 일반 커스텀 프리셋은 Codex가 자체 prompts와 assetSchema 역할을 계획한다. 그루브 다이얼도 장르 계획의 5역할 프롬프트를 사용하며 새 음악의 아티스트·사진·공간을 생성한다. 선택한 재질이 prism이면 낡은 종이·찢김·필름 그레인을 넣지 않고, vintage/retro는 실제 촬영·인쇄 물성으로 표현한다. `prompt`와 `transparent_background`를 도구에 전달하고 `referenceRoles` 같은 계획용 필드를 도구 인자로 넘기지 않는다. 완료 여부는 실제 도구 결과와 저장 파일로 판단하며 `prompts-ready-not-generated`를 이미지 생성 완료로 보고하지 않는다.

ChatGPT에서는 내장 `image_gen`을, Antigravity에서는 호스트가 제공하는 이미지 기능을 사용한다. 로컬 참조는 view_image로 본 뒤 `referenced_image_paths`로 전달한다. 생성 결과를 프로젝트에 복사해 default generated_images 경로만 참조하지 않는다. 유료 API로 임의 전환하지 않는다.

| 자산 | 제작 |
|---|---|
| photoA | 16:9 대표 사진. 얼굴을 중앙 55% 안에 두어 원형 CD 크롭에도 남긴다 |
| photoB/C | A를 identity 참조로 삼아 같은 인물/의상/공간의 다른 구도. 카탈로그만 단일 사진 재사용 가능하며 이를 여러 구도 생성으로 보고하지 않는다 |
| case | 같은 사진이 인쇄된 주얼케이스. 정면에 가까운 정사각, 4모서리와 바깥 6% 여유. transparent_background=true. 책상·별도 CD·글자 제외. 프리즘은 새것 같은 투명 아크릴·크롬 반사, 빈티지 프리셋은 해당 마모 질감을 따른다 |
| paper | 16:9 촬영된 종이/바탕. 중앙/오른쪽은 비우고 하단 15%는 가사 대비가 확보되는 조용한 영역. 프리즘에서는 새 진주 아크릴/크롬 스튜디오 바탕을 쓴다 |

프리셋별 실제 생성 프롬프트와 파일 출처는 `assets/presets/<id>/generation.json`이다. 이 분위기와 새 음악의 설정을 결합한다.

```text
Use case: photorealistic-natural
Asset: 16:9 fictional artist photo for physical CD cover and intro.
Subject: [adult fictional singer/band; fixed faces, hair, clothing, instruments]
Scene: [music-specific setting]
Look: [preset artDirection, photographic medium]
Framing: candid, slightly imperfect; faces within central 55%.
Texture: [preset-specific physical texture; natural skin/fabric].
Constraints: no real celebrity, logos, text, or glossy plastic skin.
```

빈티지는 단순 저화질이 아니라 촬영 매체·구김·인쇄 어긋남·종이/플라스틱 물성으로 표현한다. 인체 구조 오류를 입자로 덮지 않는다. 케이스는 A를 표지 내용 참조로 주어 얼굴 일관성을 확인한다. 원형 디스크·허브·반사·전환은 템플릿에서 합성하므로 사진 안에 CD를 중복 생성하지 않는다. 생성 자산 수정도 해당 호스트의 이미지 편집 기능을 사용한다.

크롬 프리즘은 반대 기준을 적용한다. 자연스러운 피부 결은 남기되 필름 그레인·스크래치·먼지·찢긴 종이·테이프·노후 색조를 프롬프트와 이미지에서 제외한다. `factory-new` 지시는 사진 프롬프트에만 쓰지 않고 프리즘 합성의 케이스·배경·빛 표현에도 적용되므로, 이미지 생성 뒤에도 스틸로 새 제품 질감이 유지되는지 확인한다.

CD 이미지 manifest에는 기존 다섯 경로와 함께 캐스팅 검수 기록을 넣는다. `reviewed:true`는 실제 이미지에서 photoA/B/C·case의 보컬/편성이 계획과 같은지 시각 검수한 뒤에만 쓴다. custom manifest는 해당 preset의 assetSchema를 따르며, 캐스팅 기록은 requiresArtist일 때만 넣는다. demo 재사용은 `demo-only`이며 캐스팅 일치 증거가 아니다.

```json
{
  "photoA":"images/artist-a.png", "photoB":"images/artist-b.png", "photoC":"images/artist-c.png",
  "case":"images/case.png", "paper":"images/paper.png",
  "casting":{"vocal":"female","act":"band","reviewed":true,"artistId":"fictional-act-01","evidence":"photoA/B/C/case visual review"}
}
```

프로젝트 `assets/generation.json`에 도구, 프롬프트, 참조 역할, 원본 결과 경로, 실제 복사 경로, 가상 인물 설정을 남긴다. 내장 도구를 사용했다고 보고한다.
