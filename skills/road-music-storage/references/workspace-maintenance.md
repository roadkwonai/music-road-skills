# Git·과거 설치 검증·제작 자료 유지보수

등록 cache 정리는 `.roadmusic`의 명시 자료를 다룬다. 이 문서는 현재 소스 저장소의 과거 Git 객체, 검증된 설치/다운로드 복제본, 검증 가능한 과거 제작·참조 자료를 대상으로 하는 별도 절차다. 큰 파일·폴더 이름·중복 해시는 그 자체로 삭제 근거가 아니다.

## 확인과 선택

1. 현재 설치본 schema에서 `storage:status`, `storage:maintenance-list`, `storage:maintenance-preview`, `storage:maintenance-cleanup`, `storage:maintenance-history`를 확인한다. `storage:status`의 capability가 `enabled:true`인 범위만 다음 검사 대상으로 삼고, `enabled:false`면 `reason`만 보여 준다. 상태 조회는 Electron·Git 심층 검사·전체 재스캔을 시작하지 않는다.
2. 일반 `storage:maintenance-list`는 현재 CLI 작업 폴더의 메타데이터와 비Git 후보만 확인한다. 최종본 외 제작 자료는 `scope:"retirement"` 또는 `includeRetirement:true`일 때만 빠른 메타데이터 검사를 한다. Git 객체는 일반 목록에 섞지 않으며, Git 저장소가 있는 개발 환경에서만 `scope:"git"`을 명시해 심층 보호 상태를 검사한다. Git이 없거나 지원하지 않으면 capability의 비활성 사유를 유지하고 prune·fsck·재시도를 자동 실행하지 않는다. 오류·권한·한도 문제로 `complete:false`면 정리하지 않는다. symlink는 따라가지 않고 알 수 없는 파일은 보호한다. 서로 다른 범위를 하나의 계획에 섞지 않는다.
3. 완료 스캔의 `scanId`와 `scope:git`, `scope:verification,candidateIds:[목록의 ID]`, `scope:artifacts,candidateIds:[목록의 ID]`, 또는 `scope:retirement,candidateIds:[목록의 ID]`로 미리보기한다. 스캔/계획은 같은 작업 폴더의15분 안의 상태여야 한다. 조건·보호 자료·파일 수·용량·만료 시각을 확인한다. 미리보기만 요청받았으면 실행하지 않는다. 이미 정리까지 맡긴 요청은 같은 범위에 재승인을 요구하지 않는다.
4. 받은 `planId`와 top-level `--confirm`으로 실행한다. 계획은15분 일회용이다. 작업 상태·파일·영수증·보호 조건이 바뀌면 새로 점검하며 기존 계획을 고쳐 재사용하지 않는다. HTML은 세션에서 받은 계획만 확인 실행하며 임의 경로나 Git 명령을 전달하지 않는다.

## Git 경계

현재 refs/태그/stash·복구 reflog·모든 정상 worktree HEAD/index·현재 수정·미추적 파일은 유지한다. 최근24시간 객체도 보존한다. 바쁜 Git writer/잠금, 누락된 worktree, 대체 객체 저장소·부분/얕은 clone 등 지원 밖 구조는 보호 이유를 알리고 중단한다. 작업 중인 사용자 파일을 commit/stash/reset하라고 요구하지 않는다.

Git 자체의 유지보수 명령으로만 객체를 정리하고 pack을 직접 삭제하지 않는다. reflog·worktree 만료·강제 이력 재작성·prune=now는 사용하지 않는다. 정리 중에는 다른 Git 쓰기 작업을 하지 않는다. 조회 시각과 실행 직전에 보존 상태를 대조하고 끝난 뒤 필요한 객체/현재 작업이 남았는지 검사한다.

Git의 미참조 논리량은 압축 전 합계이므로 확보 예정 GB로 확정하지 않는다. 실제 `freedAllocatedBytes`와 디스크 전체 `diskFreeDeltaBytes`를 구분해 보고한다. 다른 프로그램의 디스크 쓰기로 전체 여유 변화가 다를 수 있다.

## 검증 복제본 경계

지원한 producer/원본 출처/receipt와 현재 미사용이 확인되는 과거 확장 설치본·다운로드 캐시만 후보로 제공한다. 현재 설치 모델·프로그램·음악/영상·작업 프로젝트·배포 원본ZIP·승인 자료는 제외한다. 과거 프로필 안의 모델이 현재 설치 경로와 hardlink/symlink를 공유할 수 있으므로 상위 runtime 전체를 삭제하지 않는다.

삭제 전에 선택과 파일 지문·설치/검증 증거를 최소 manifest로 보존한다. 입력/설정/검수 의견을 복제본과 함께 무조건 버리지 않는다. 바뀐 파일·열린 파일·symlink·알 수 없는 중요 자료는 보호한다. 부분 실패는 실제 삭제 수량과 남은 항목을 보고한다.

## 과거 제작·참조 자료 경계

HTML에서는 **저장공간 관리 → 기타 관리 → 과거 제작·참조 자료**에만 표시한다. 자동 일괄 정리는 이 범위를 만들거나 실행하지 않는다. 현재 참조 원본·설치 모델·최종 결과물·필요한 코드/JSON 보고서·전체 contact sheet와 처음/중간/끝 대표 프레임은 보존한다.

`artifacts` 후보는 다음처럼 증거가 모두 있는 자료에 한정한다.

- 원본 SHA와 완료된 추출 색인이 일치하는 조밀 분석 프레임의 나머지 프레임
- 최종 납품 해시·최종 검수 기록이 일치하는 QA runtime/style 세부 PNG
- 보존된 배포 ZIP의 해당 멤버와 바이트·SHA-256이 같은 이전 버전 binary 복제본. 계획에는 복구 ZIP 멤버 매핑을 남긴다.
- 출처·원본 SHA가 있고 모든 음성/영상 스트림 해시가 원본과 같은 capture-remux 복제본

`qa`·`before`·`frames`라는 이름만으로는 후보가 되지 않는다. 원본/납품/추출·검수 근거, 파일 지문, 열림/제작 중 상태, hardlink·symlink를 실행 직전 다시 검사한다. 하나라도 달라지거나 확인할 수 없으면 보호하고 새 전체 스캔부터 다시 한다.

## 최종본 외 제작 자료 경계

`retirement`은 완성한 음악 작업에서만 명시 선택한다. 자동 일괄 정리 대상이 아니며, 작업 폴더 전체 스캔에 `includeRetirement:true`를 명시해 후보와 보호 용량을 먼저 검토한다. 원음, 등록 최종 음원·영상, 현재 프로그램·모델, 제작 입력/승인 자산, 코드·JSON/문서 판정, 최소 감사 이력, 열린 파일과 hardlink/symlink는 보존한다.

후보는 최종 원음 SHA와 등록 납품 해시·스트림·길이가 검증된 프로젝트의 명시 소유 파생 WAV, 이전 draft/proof/부분 렌더, 대표 세 장과 요약 시트를 뺀 QA 세부 이미지, 출처·원본 SHA·프레임 색인·대표 시트가 검증된 참조 분석 중간본처럼 재생성 가능한 자료에 한정한다. `publish`가 최종 MP3 또는 영상과 원음을 검증한 뒤 자동으로 다룰 수 있는 WAV는 `audio/mix_bed.wav`, `audio/mix_premaster.wav`, `audio/mix_vo.wav`뿐이다. 원음·입력 WAV·production의 주 믹스, 가져온 WAV, FLAC 등 가져온 오디오는 정리 대상이 아니다.

과거 배포 ZIP은 현재 canonical 보관본과 동일한 멤버를 그 보관본으로 연결하고, 고유 멤버는 content history에 보존·검증한다. 이 검증은 컨테이너 바이트가 같은지를 뜻하지 않으므로, 정리 후 원래 ZIP 바이트와 완전히 동일한 재생성을 약속하지 않는다.

## 결과와 남은 자료

실행 뒤 전체 스캔을 다시 수행해 폴더/파일/캐시의 전후 차이를 확인하고, `storage:maintenance-history`와 `.roadmusic`의 작은 실행 manifest를 남긴다. artifacts 계획의 파일 목록/지문은 압축 감사 목록으로 별도 보존한다. 현재 결과물·모델·유효 Git 이력 보존, 실제 회수량·건너뜀·경고를 보고한다. 후보의 논리 크기와 `freedAllocatedBytes`, 전체 디스크 `diskFreeDeltaBytes`는 서로 다른 값으로 보고한다. 애니매틱/프레임 전체 증거/과거 완성본/참조된 렌더 중간본은 현재 기능의 무조건 삭제 대상으로 포함하지 않는다. 지원 근거가 없다면 이유와 크기를 보여주며 셸 삭제로 우회하지 않는다.
