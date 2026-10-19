"""Read-only Road Music CLI status and public-reference snapshots for the studio."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess


CLI_TIMEOUT_SECONDS = 5
SENSITIVE_KEYS = ('token', 'secret', 'password', 'credential', 'authorization', 'cookie', 'log', 'lyrics', 'prompt')
READ_COMMANDS = frozenset({
    'storage:status', 'storage:list', 'storage:preview', 'storage:history', 'app:state', 'app:capabilities',
    'app:language', 'setup:check', 'setup:location', 'engines:list', 'projects:list',
    'songs:list', 'songs:hidden', 'song:lrc', 'song:score', 'song:backups', 'song:detail',
    'song:info', 'score:check', 'queue:list', 'video:settings', 'video:state',
    'video:chapters', 'settings:get', 'assets:list', 'presets:list', 'recording:state',
    'renderer:catalog', 'lyrics:clean', 'lyrics:check', 'lyrics:sections', 'lyrics:numbers',
    'prompt:catalog', 'prompt:knowledge', 'player:state', 'editor:state', 'system:stats',
    'cli:schema', 'cli:version', 'cli:update:check', 'cli:status', 'about:info',
    'notices:latest', 'update:status', 'update:check'
})
RUNTIME_COMMANDS = ('app:capabilities', 'setup:check', 'engines:list', 'queue:list', 'video:state')
SKILL_CHECKS = (
    ('road-music-video-studio', '영상 제작실', 'scripts/studio.py'),
    ('road-music-showreel-playlist', 'Showreel 플레이리스트', 'scripts/playlist_chooser.py'),
    ('road-music-showreel-mv', 'Showreel MV', 'SKILL.md'),
    ('road-music-jizura-playlist', 'JIZURA 플레이리스트', 'scripts/studio.py'),
)

# These are documentation cards, not an alternate command schema.  Keep their
# values within the public song:generate/prompt:compose contract.
REFERENCE_GUIDES = (
    {
        'id': 'instrument-keyboards', 'category': '악기', 'tags': ['건반', '발라드', '보컬곡', 'ACE'],
        'title': '피아노·첼로 중심의 잔잔한 보컬곡',
        'summary': '`piano`, `cello`처럼 지원되는 악기 이름을 조합하는 기본 예시입니다.',
        'useWhen': '가사 전달을 우선하면서 따뜻하고 절제된 반주를 원할 때 사용합니다.',
        'avoidWhen': '댄스·록처럼 드럼과 강한 리듬이 중심인 곡에 `strict:true`를 함께 켜지 마세요.',
        'expected': '피아노와 첼로가 중심이라는 요청을 전달합니다. 특정 연주나 음색을 보장하지는 않습니다.',
        'prompt': 'ACE로 한국어 발라드 1곡을 준비해줘. 피아노와 첼로, 68 BPM, 절제된 벌스와 커지는 후렴으로 구성하고 생성 전 최종 가사·caption·입력 JSON을 보여줘.',
        'fields': ['parts.instruments', 'bpm', 'lyrics', 'style'], 'source': 'docs/music-options.md',
    },
    {
        'id': 'instrument-guitar-band', 'category': '악기', 'tags': ['기타', '록', '밴드', '보컬곡'],
        'title': '일렉기타가 있는 밴드 편성',
        'summary': '`electric guitar`, `bass guitar`, `drums`는 공개 악기 배열의 정확한 값입니다.',
        'useWhen': '리듬 섹션과 후렴 에너지가 필요한 록·팝 편곡의 첫 시도에 맞습니다.',
        'avoidWhen': '독주나 매우 제한된 편성을 원할 때 많은 악기를 한 번에 나열하지 마세요.',
        'expected': '밴드 편성의 방향을 요청합니다. 모델이 모든 악기를 분리된 트랙으로 만들지는 않습니다.',
        'prompt': '한국어 록발라드 1곡의 입력을 검토해줘. electric guitar·bass guitar·drums, 72 BPM, 후렴에서 에너지가 커지는 방향으로 하고 악기 제한은 끄며 최종 전달 style을 확인해줘.',
        'fields': ['parts.instruments', 'parts.strict', 'parts.dynamics', 'bpm'], 'source': 'docs/music-options.md',
    },
    {
        'id': 'instrument-acoustic', 'category': '악기', 'tags': ['어쿠스틱', '포크', '기타', '잔잔함'],
        'title': '어쿠스틱 포크의 작은 편성',
        'summary': '`acoustic guitar`와 `cello`처럼 핵심 악기부터 적고, 필요하면 역할을 `instrumentation`으로 보탭니다.',
        'useWhen': '공간감과 가사 여백이 중요한 포크·어쿠스틱 곡에 사용합니다.',
        'avoidWhen': '지원 배열에 없는 `guitar`, `strings`, `808`을 `parts.instruments` 값으로 넣지 마세요.',
        'expected': '작은 편성의 질감과 역할을 요청합니다. 실제 편성이 완전히 고정되지는 않습니다.',
        'prompt': '어쿠스틱 포크 보컬곡을 준비해줘. acoustic guitar와 cello를 중심으로 하고, 가사 사이에 짧은 응답 연주가 들리도록 요청하되 생성 전 song:prepare로 실제 전달 style을 확인해줘.',
        'fields': ['parts.instruments', 'parts.instrumentation', 'parts.mix'], 'source': 'docs/music-options.md',
    },
    {
        'id': 'instrument-electronic', 'category': '악기', 'tags': ['전자', '댄스', '신스', '리듬'],
        'title': '신스 중심의 댄스·전자 편곡',
        'summary': '`synthesizer`, `synth pads`, `drums`로 전자음악의 음색과 리듬을 구성하는 예시입니다.',
        'useWhen': '명확한 박자와 밝거나 현대적인 전자 질감이 필요할 때 사용합니다.',
        'avoidWhen': '드럼·신스를 억제하는 `strict:true`와 함께 쓰지 마세요.',
        'expected': '신스와 드럼 중심의 편곡 방향을 요청합니다. 상용 장르 사운드의 복제나 특정 곡과의 유사를 보장하지 않습니다.',
        'prompt': '전자 팝 보컬곡의 초안을 준비해줘. synthesizer·synth pads·drums, 124 BPM, pre-chorus에서 기대감을 쌓고 chorus는 더 크게 느껴지도록 하되 가사는 별도로 검토해줘.',
        'fields': ['parts.instruments', 'parts.dynamics', 'bpm', 'style'], 'source': 'docs/genre-prompts.md',
    },
    {
        'id': 'instrumental-theme', 'category': '구성', 'tags': ['연주곡', '테마', '영상', '구조'],
        'title': '가사 없는 테마형 연주곡',
        'summary': '`instrumental:true`와 `parts.structure:"theme"`은 연주곡용 가사 골격을 만듭니다.',
        'useWhen': '영상·게임·묵상용처럼 보컬보다 멜로디와 전개가 중요한 곡에 사용합니다.',
        'avoidWhen': '보컬 가사를 유지하려는 곡에 켜지 마세요. `instrumental:true`면 입력 가사는 사용하지 않습니다.',
        'expected': '테마형 연주곡 구조를 요청합니다. 시작과 끝이 완벽히 이어지는 루프나 정확한 영상 길이를 보장하지 않습니다.',
        'prompt': '연주곡 1곡을 준비해줘. piano·french horn·orchestra, 96 BPM, cinematic instrumental과 희망적인 점진적 전개, instrumental:true, structure:"theme"으로 하고 targetSeconds는 목표값으로 기록해줘.',
        'fields': ['instrumental', 'parts.structure', 'parts.instruments', 'targetSeconds'], 'source': 'docs/music-options.md',
    },
    {
        'id': 'seed-comparison', 'category': '비교', 'tags': ['seed', '후보', 'A/B', '검수'],
        'title': '같은 입력에서 seed만 바꿔 비교',
        'summary': '`count`는 같은 사양의 후보 수이고, `seed`는 비교 조건을 기록합니다.',
        'useWhen': '가사·장르·악기·BPM을 고정하고 후렴·발음·질감의 차이를 비교할 때 사용합니다.',
        'avoidWhen': '서로 다른 장르를 `count` 하나로 만들려 하거나, 같은 seed가 어디서나 같은 음원을 만든다고 기대하지 마세요.',
        'expected': '같은 요청의 여러 후보를 만들도록 요청합니다. 품질 순위는 실제 청취와 검수로 결정해야 합니다.',
        'prompt': '현재 가사·스타일·악기·BPM은 유지하고 seed만 바꾼 후보 2개를 준비해줘. 생성 전 입력을 확인하고 완료 후 각 결과의 실제 dir·seed·길이를 비교할 수 있게 알려줘.',
        'fields': ['count', 'seed', 'song:prepare', 'song:detail'], 'source': 'docs/music-options.md',
    },
    {
        'id': 'yue-advanced', 'category': '고급 옵션', 'tags': ['YuE', 'MLX', 'advanced', '재현'],
        'title': 'YuE 고급 샘플링은 한 항목씩 비교',
        'summary': '`advanced`의 sampling·`cfgScale`·`odeSteps`는 YuE 계열에만 적용되는 고급 입력입니다.',
        'useWhen': 'YuE 또는 yue-mlx에서 동일 가사·악보·seed의 제한된 실험을 기록하며 비교할 때 사용합니다.',
        'avoidWhen': 'ACE 입력에 YuE 고급 옵션을 넣거나 여러 값을 동시에 바꿔 원인을 알 수 없게 만들지 마세요.',
        'expected': '샘플링 조건과 비용을 바꿉니다. 더 높은 값이 품질을 보장하지 않으며 실제 길이·잘림을 별도로 확인해야 합니다.',
        'prompt': 'yue-mlx로 기존 승인 가사와 seed를 유지한 제한 실험을 준비해줘. advanced에서는 odeSteps 하나만 바꾸고, yue:capabilities·song:prepare 결과와 실제 길이·잘림 여부를 함께 기록해줘.',
        'fields': ['engine', 'advanced', 'yue:capabilities', 'song:prepare'], 'source': 'docs/yue-prompt-guide.md',
    },
    {
        'id': 'knowledge-check', 'category': '가이드', 'tags': ['prompt:knowledge', '검토', '스키마', '안전'],
        'title': '가이드와 실제 지원 필드를 분리해 확인',
        'summary': '`prompt:knowledge`는 번들 가이드를 읽고, `schema`는 현재 CLI가 실제로 받는 필드를 확인합니다.',
        'useWhen': 'ACE·YuE·가사·모델 비교 가이드의 근거를 확인한 뒤 입력을 만들 때 사용합니다.',
        'avoidWhen': '문서에 있는 업스트림 옵션을 현재 Road Music CLI 입력이라고 가정하지 마세요.',
        'expected': '지식과 현재 공개 계약을 확인합니다. 모델 설치·업데이트·생성을 실행하지 않습니다.',
        'prompt': '생성 전에 현재 schema의 song:generate 필드와 prompt:knowledge의 ace 또는 yue 가이드를 확인해줘. 문서에는 있지만 공개 schema에 없는 값은 입력에 넣지 말고 이유를 알려줘.',
        'fields': ['schema', 'prompt:knowledge', 'prompt:catalog'], 'source': 'docs/ace-prompt-guide.md',
    },
)

# Only commands with a stable, documented workflow get an executable example.
# All other cards retain the schema-inspection example supplied below.
COMMAND_HELP = {
    'prompt:compose': {
        'useWhen': '악기·BPM·가사를 조합한 전달 style을 생성 전에 확인할 때 사용합니다.',
        'avoidWhen': '이 명령을 실제 음원 생성으로 보지 마세요.',
        'expected': '조합된 style과 점검 정보를 반환합니다. 음원 파일이나 jobId는 만들지 않습니다.',
        'example': "node cli/road-music.js prompt:compose --json '{\"genre\":\"Korean ballad, female vocal, intimate mood\",\"instruments\":[\"piano\",\"cello\"],\"bpm\":68,\"lyrics\":\"[Verse]\\n골목에 남은 작은 불빛\"}'",
        'guide': 'guide/reference/#빠른-활용-순서',
    },
    'song:generate': {
        'useWhen': '가사·caption·입력 JSON을 검토하고 생성까지 승인된 뒤에 사용합니다.',
        'avoidWhen': '미설치 모델의 자동 설치, 승인 전 생성, 서로 다른 장르를 count 하나로 만드는 데 쓰지 마세요.',
        'expected': '생성 작업의 jobId를 반환합니다. 이어서 job:wait으로 완료와 실제 파일을 확인해야 합니다.',
        'example': "node cli/road-music.js song:generate --json '{\"title\":\"예시 연주곡\",\"engine\":\"ace\",\"style\":\"gentle acoustic instrumental, intimate room\",\"instrumental\":true,\"targetSeconds\":30,\"parts\":{\"instruments\":[\"acoustic guitar\",\"piano\"],\"bpm\":88,\"structure\":\"short\"}}' --events",
        'guide': 'guide/reference/#빠른-활용-순서',
    },
    'job:wait': {
        'useWhen': 'song:generate·song:resume이 돌려준 jobId가 끝났는지 확인할 때 사용합니다.',
        'avoidWhen': '연결 오류 뒤에 같은 생성 요청을 바로 다시 제출하는 용도로 쓰지 마세요.',
        'expected': '완료·실패 상태와 결과를 반환합니다. 연결 오류가 uncertain이면 service:status·queue:list·결과 파일을 먼저 확인합니다.',
        'example': "node cli/road-music.js job:wait --json '{\"jobId\":\"생성-응답의-jobId\",\"timeoutMs\":3600000}'",
        'guide': 'guide/reference/#영상-렌더-연결-오류-복구',
    },
    'production:projects': {
        'useWhen': '프로젝트별 요청·생성·수정 횟수와 제작 기록을 페이지 단위로 볼 때 사용합니다.',
        'avoidWhen': '모든 프롬프트·파일을 내려받아 브라우저에서 직접 합산하려 하지 마세요.',
        'expected': '필터 조건의 프로젝트 행과 다음 cursor를 반환합니다.',
        'example': "node cli/road-music.js production:projects --json '{\"domain\":\"music\",\"limit\":20}'",
        'guide': 'guide/production/',
    },
    'production:dashboard': {
        'useWhen': '음악·모션 제작의 평균·분포·느린 작업을 SQLite 집계로 비교할 때 사용합니다.',
        'avoidWhen': '하위 단계를 더해 실제 경과 시간처럼 표시하거나 미측정 시간을 0으로 취급하지 마세요.',
        'expected': '총량, 프로젝트 그룹별 비교, 평균·중앙값·p95, 일별 추이와 느린 작업을 반환합니다.',
        'example': "node cli/road-music.js production:dashboard --json '{\"domain\":\"motion\",\"limit\":20}'",
        'guide': 'guide/production/',
    },
    'storage:list': {
        'useWhen': '활성화된 저장공간 관리 항목과 프로젝트별 후보를 읽을 때 사용합니다.',
        'avoidWhen': '목록을 확인하지 않고 파일 경로를 추측해 직접 삭제하지 마세요.',
        'expected': '관리 대상·보호 사유·프로젝트 상태를 반환합니다.',
        'example': "node cli/road-music.js storage:list --json '{}'",
        'guide': 'guide/storage/',
    },
    'storage:preview': {
        'useWhen': '선택한 캐시·중간본·이력 정리 전에 대상과 확보 예상 용량을 검토할 때 사용합니다.',
        'avoidWhen': 'preview 없이 실제 정리 명령을 실행하거나 미등록 파일을 대상으로 삼지 마세요.',
        'expected': '불변 planId, 대상·차단 항목, 파일 수와 예상 확보 용량을 반환합니다.',
        'example': "node cli/road-music.js storage:preview --json '{\"projectId\":\"목록에서-받은-projectId\",\"kinds\":[\"cache\",\"intermediate\"]}'",
        'guide': 'guide/storage/',
    },
}

INSTRUMENT_GROUPS = {
    '건반': frozenset({'piano', 'Rhodes electric piano', 'pipe organ', 'celesta', 'music box'}),
    '기타·베이스': frozenset({'acoustic guitar', 'classical guitar', 'electric guitar', 'bass guitar', 'upright bass', 'ukulele', 'mandolin'}),
    '현악': frozenset({'violin', 'viola', 'cello', 'string ensemble', 'harp'}),
    '목관·금관': frozenset({'flute', 'clarinet', 'oboe', 'saxophone', 'trumpet', 'trombone', 'french horn', 'brass section', 'harmonica', 'accordion'}),
    '리듬·타악': frozenset({'drums', 'brushed drums', 'percussion', 'glockenspiel', 'sleigh bells', 'marimba', 'vibraphone'}),
    '전자·합주': frozenset({'synthesizer', 'synth pads', 'orchestra'}),
}

INSTRUMENT_GUIDANCE = {
    '건반': ('가사 여백이나 잔잔한 선율을 중심으로 시작할 때 사용합니다.', '드럼 중심 댄스 편곡의 전체 리듬을 이 값 하나로 해결하려 하지 마세요.', '건반 질감을 중심으로 한 편곡 방향을 요청합니다.'),
    '기타·베이스': ('포크·록·팝에서 반주 또는 리듬 섹션의 중심을 정할 때 사용합니다.', '같은 역할의 악기를 많이 나열해 실제 편성을 고정하려 하지 마세요.', '기타 또는 베이스가 중심이라는 편곡 방향을 요청합니다.'),
    '현악': ('선율 보강, 서정적인 응답, 넓은 배경 질감이 필요할 때 사용합니다.', 'string ensemble을 개별 현악기 트랙이나 완전한 오케스트라로 해석하지 마세요.', '현악 질감을 더한 방향을 요청합니다.'),
    '목관·금관': ('간주·응답 선율이나 밝고 뚜렷한 색채를 더할 때 사용합니다.', '특정 연주법·솔로 길이·정확한 파트를 보장받는 값으로 쓰지 마세요.', '관악기의 선율 또는 색채를 요청합니다.'),
    '리듬·타악': ('박자감·그루브·전환 포인트를 분명히 하고 싶을 때 사용합니다.', '리듬 악기를 지정하면서 strict로 드럼·퍼커션 억제를 함께 요청하지 마세요.', '리듬과 타악의 존재감을 요청합니다.'),
    '전자·합주': ('전자음의 질감이나 넓은 공간감, 규모가 큰 악기 편성을 원할 때 사용합니다.', '특정 상용 사운드나 분리된 스템·믹서 제어를 기대하지 마세요.', '전자 또는 합주 질감을 요청합니다.'),
    '기타': ('공개 스키마에 있는 악기 값을 정확히 전달할 때 사용합니다.', '이 값 하나로 음색·연주법을 보장받으려 하지 마세요.', '지정한 악기를 중심으로 한 편곡 방향을 요청합니다.'),
}


def _instrument_group(name):
    return next((label for label, names in INSTRUMENT_GROUPS.items() if name in names), '기타')


def _instrument_guides(schema):
    """Create one searchable card per currently supported instrument enum value."""
    commands = schema.get('commands') if isinstance(schema, dict) else []
    entry = next((item for item in commands if isinstance(item, dict) and item.get('command') == 'song:generate'), None)
    properties = entry.get('params', {}).get('properties', {}) if isinstance(entry, dict) else {}
    parts = properties.get('parts', {}).get('properties', {}) if isinstance(properties, dict) else {}
    values = parts.get('instruments', {}).get('items', {}).get('enum', []) if isinstance(parts, dict) else []
    cards = []
    for name in values if isinstance(values, list) else []:
        if not isinstance(name, str):
            continue
        group = _instrument_group(name)
        use_when, avoid_when, expected = INSTRUMENT_GUIDANCE[group]
        cards.append({
            'id': f"instrument-{name.lower().replace(' ', '-').replace('·', '-')}",
            'category': '악기', 'tags': ['악기', group, name], 'title': name,
            'summary': f"`parts.instruments`에 넣을 수 있는 현재 공개 값입니다. 분류: {group}.",
            'useWhen': use_when, 'avoidWhen': avoid_when,
            'expected': f"{expected} 실제 음색·연주·완성도는 보장하지 않습니다.",
            'prompt': f"{name}을 parts.instruments의 핵심 악기로 넣은 곡을 준비해줘. 장르·가사·BPM은 내 요청에 맞추고, 생성 전 song:prepare로 실제 전달 style을 확인해줘.",
            'fields': ['parts.instruments', 'song:prepare'], 'source': '현재 schema · song:generate.parts.instruments',
        })
    return cards


def _now(value=None):
    return value or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def cli_root(env=None, script_path=None):
    """Find an actual kit root; a missing root is a visible non-ready state."""
    env = os.environ if env is None else env
    candidates = []
    configured = env.get('ROADMUSIC_CLI_ROOT')
    if configured:
        candidates.append(Path(configured).expanduser())
    source = Path(script_path or __file__).resolve()
    candidates.extend(source.parents)
    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / 'cli' / 'road-music.js').is_file():
            return candidate
        if candidate.name == 'cli' and (candidate / 'road-music.js').is_file():
            return candidate.parent
    return None


def _default_runner(argv, *, cwd, env, timeout):
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)


def _result_value(response):
    if not isinstance(response, dict) or response.get('ok') is not True:
        return None
    value = response.get('result')
    return value if isinstance(value, dict) else value


def _parse_process(process):
    if getattr(process, 'returncode', 1) != 0:
        return {'state': 'failed'}
    lines = [line for line in str(getattr(process, 'stdout', '')).splitlines() if line.strip()]
    if len(lines) != 1:
        return {'state': 'invalid-response'}
    try:
        response = json.loads(lines[0])
    except json.JSONDecodeError:
        return {'state': 'invalid-response'}
    if not isinstance(response, dict):
        return {'state': 'invalid-response'}
    return {'state': 'ready' if response.get('ok') is True else 'failed', 'response': response}


def _invoke(root, command, *, no_start=False, runner=None, env=None):
    argv = ['node', str(root / 'cli' / 'road-music.js'), command]
    if no_start:
        argv.append('--no-start')
    child_env = dict(os.environ if env is None else env)
    child_env['ROADMUSIC_STUDIO_AUTO_OPEN'] = '0'
    try:
        result = (runner or _default_runner)(argv, cwd=str(root), env=child_env, timeout=CLI_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {'state': 'timeout'}
    except OSError:
        return {'state': 'unavailable'}
    return _parse_process(result)


def _safe_data(value, depth=0):
    """Bound response data for UI status; never relay credentials, source text, or logs."""
    if depth > 4:
        return '…'
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key = str(key)
            if any(word in key.lower() for word in SENSITIVE_KEYS):
                continue
            result[key] = _safe_data(item, depth + 1)
        return result
    if isinstance(value, list):
        return [_safe_data(item, depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return value[:240]
    return value if isinstance(value, (bool, int, float)) or value is None else str(value)[:240]


def _service_state(value):
    if not isinstance(value, dict):
        return 'not-running'
    if value.get('stopping') is True:
        return 'stopping'
    if any(value.get(key) is True for key in ('running', 'ready', 'active')):
        return 'connected'
    if isinstance(value.get('pid'), int) and value['pid'] > 0:
        return 'connected'
    if str(value.get('status', '')).lower() in {'running', 'ready', 'active'}:
        return 'connected'
    return 'not-running'


def _schema_summary(value):
    commands = value.get('commands') if isinstance(value, dict) else []
    commands = commands if isinstance(commands, list) else []
    groups = sorted({item.get('command', '').split(':', 1)[0] for item in commands if isinstance(item, dict) and ':' in item.get('command', '')})
    return {'commandCount': len(commands), 'groups': groups}


def _skills(skill_root):
    values = []
    for identifier, label, marker in SKILL_CHECKS:
        root = skill_root if identifier == 'road-music-video-studio' else skill_root.parent / identifier
        ready = (root / 'SKILL.md').is_file() and (root / marker).is_file()
        values.append({'id': identifier, 'label': label, 'state': 'available' if ready else 'missing'})
    return values


def status_snapshot(env=None, runner=None, now=None, script_path=None):
    """Build a bounded read-only status snapshot without starting a service or browser."""
    env = dict(os.environ if env is None else env)
    root = cli_root(env, script_path)
    skill_root = Path(script_path or __file__).resolve().parents[1]
    snapshot = {
        'checkedAt': _now(now),
        'readOnly': True,
        'safety': {'autoStart': False, 'autoOpen': False, 'install': False, 'render': False, 'update': False},
        'cli': {'state': 'available' if root else 'missing', 'root': str(root) if root else None},
        'service': {'state': 'not-checked'},
        'runtime': {'state': 'not-checked', 'checks': {}},
        'storage': {'state': 'unavailable'},
        'skills': _skills(skill_root),
    }
    if root is None:
        snapshot['service'] = {'state': 'unavailable'}
        return snapshot
    schema = _invoke(root, 'schema', runner=runner, env=env)
    version = _invoke(root, 'cli:version', runner=runner, env=env)
    if schema['state'] == 'ready':
        snapshot['cli']['schema'] = _schema_summary(_result_value(schema['response']))
    else:
        snapshot['cli']['schema'] = {'state': schema['state']}
    if version['state'] == 'ready':
        result = _result_value(version['response'])
        snapshot['cli']['version'] = _safe_data(result) if isinstance(result, dict) else None
    else:
        snapshot['cli']['version'] = {'state': version['state']}
    storage = _invoke(root, 'storage:status', runner=runner, env=env)
    if storage['state'] == 'ready':
        snapshot['storage'] = {'state': 'available', 'data': _safe_data(_result_value(storage['response']))}
    else:
        snapshot['storage'] = {'state': storage['state']}
    service = _invoke(root, 'service:status', no_start=True, runner=runner, env=env)
    service_value = _result_value(service.get('response')) if service['state'] == 'ready' else None
    state = _service_state(service_value) if service['state'] == 'ready' else 'not-running'
    snapshot['service'] = {'state': state}
    if state != 'connected':
        return snapshot
    snapshot['runtime']['state'] = 'available'
    for command in RUNTIME_COMMANDS:
        outcome = _invoke(root, command, no_start=True, runner=runner, env=env)
        if outcome['state'] == 'ready':
            snapshot['runtime']['checks'][command] = {'state': 'available', 'data': _safe_data(_result_value(outcome['response']))}
        else:
            snapshot['runtime']['checks'][command] = {'state': outcome['state']}
    return snapshot


def _field(name, spec, required):
    result = {'name': name, 'required': name in required, 'type': spec.get('type', 'value')}
    for key in ('enum', 'minimum', 'maximum', 'minLength', 'maxLength', 'nullable', 'format'):
        if key in spec:
            result[key] = spec[key]
    return result


def _classification(command, entry):
    if entry.get('destructive') is True:
        return 'delete'
    return 'read' if command in READ_COMMANDS else 'change'


def reference_snapshot(env=None, runner=None, now=None, script_path=None):
    """Return the installed public schema and local usage cards without executing product commands."""
    env = dict(os.environ if env is None else env)
    root = cli_root(env, script_path)
    snapshot = {
        'checkedAt': _now(now), 'readOnly': True,
        'cli': {'state': 'available' if root else 'missing', 'root': str(root) if root else None},
        'commands': [], 'guides': [dict(item) for item in REFERENCE_GUIDES],
    }
    if root is None:
        return snapshot
    outcome = _invoke(root, 'schema', runner=runner, env=env)
    if outcome['state'] != 'ready':
        snapshot['cli']['state'] = outcome['state']
        return snapshot
    value = _result_value(outcome['response'])
    if not isinstance(value, dict) or not isinstance(value.get('commands'), list):
        snapshot['cli']['state'] = 'invalid-response'
        return snapshot
    snapshot['guides'].extend(_instrument_guides(value))
    for entry in value['commands']:
        if not isinstance(entry, dict) or not isinstance(entry.get('command'), str):
            continue
        params = entry.get('params') if isinstance(entry.get('params'), dict) else {}
        properties = params.get('properties') if isinstance(params.get('properties'), dict) else {}
        required = params.get('required') if isinstance(params.get('required'), list) else []
        command = entry['command']
        help_item = COMMAND_HELP.get(command, {})
        snapshot['commands'].append({
            'command': command,
            'group': command.split(':', 1)[0],
            'classification': _classification(command, entry),
            'description': str(entry.get('description', ''))[:240],
            'required': [name for name in required if isinstance(name, str)],
            'fields': [_field(name, spec, required) for name, spec in properties.items() if isinstance(spec, dict)],
            'example': f"node cli/road-music.js schema --json '{{\"command\":\"{command}\"}}'",
            'help': _safe_data(help_item),
        })
    snapshot['commands'].sort(key=lambda item: item['command'])
    snapshot['cli']['schema'] = {'commandCount': len(snapshot['commands']), 'groups': sorted({item['group'] for item in snapshot['commands']})}
    return snapshot


def recipe_snapshot(collection, env=None, script_path=None):
    """Read the same bundled recipes as prompt:knowledge, without a service call."""
    filenames = {'general': 'command-recipes.json', 'ccm': 'ccm-recipes.json'}
    if collection not in filenames:
        raise ValueError('지원하지 않는 활용 가이드입니다.')
    root = cli_root(dict(os.environ if env is None else env), script_path)
    bundled = Path(__file__).resolve().parents[1] / 'assets' / 'knowledge' / filenames[collection]
    preferred = root / 'docs' / filenames[collection] if root else bundled
    path = preferred if preferred.is_file() else bundled
    result = {'collection': collection, 'state': 'unavailable', 'readOnly': True, 'guides': [], 'styles': [],
              'safety': {'generation': False, 'install': False, 'serviceStart': False}}
    try:
        raw = path.read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError('활용 가이드 파일이 너무 큽니다.')
        data = json.loads(raw)
        if data.get('schemaVersion') != 1 or not isinstance(data.get('guides'), list):
            raise ValueError('활용 가이드 형식이 올바르지 않습니다.')
        guides = data['guides']
        if any(not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key] for key in ('id', 'title', 'prompt')) for item in guides):
            raise ValueError('활용 가이드에 필수 내용이 없습니다.')
        if len({item['id'] for item in guides}) != len(guides):
            raise ValueError('활용 가이드 ID가 중복됐습니다.')
        result.update(state='ready', guides=guides, styles=data.get('styles', []), source=str(path))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        result['error'] = '활용 자료를 읽지 못했습니다. CLI·스킬 묶음을 확인해 주세요.'
    return result
