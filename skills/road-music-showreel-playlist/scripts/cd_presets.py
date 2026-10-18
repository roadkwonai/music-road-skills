#!/usr/bin/env python3
"""이름으로 고르는 Showreel 플레이리스트 프리셋과 전곡 연결·자막·네이티브 렌더."""
import argparse
import copy
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import wave
from urllib.parse import quote

from playlist_tools import concat_wavs, normalize_display, spectrum_data
from vocal_cast import casting_spec, check_asset_casting

ROOT = Path(__file__).resolve().parents[1]
DESIGN_SCRIPTS = ROOT.parent / 'road-music-video-studio' / 'scripts'
if str(DESIGN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DESIGN_SCRIPTS))
from html_design import apply_design
PRESETS = ROOT / 'assets' / 'presets'
SHOWREEL = Path(os.environ.get('SHOWREEL_HOME', str(Path.home() / '.local/share/roadmusic-video-tools/showreel')))
PYTHON = os.environ.get('SHOWREEL_PYTHON', sys.executable)
ASSETS = ('photoA', 'photoB', 'photoC', 'case', 'paper')
NAMES = dict(zip(ASSETS, ('photo-a.png', 'photo-b.png', 'photo-c.png', 'case.png', 'paper.png')))
STOPS = (0, 3.692, 5.712, 8.963, 10.17)
GENRES = ROOT / 'assets/genre-profiles.json'
MOTION_MODES = ('balanced', 'drive', 'soft')
WORD_TIMING_PRESET_ID = 'groove-dial'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args):
    subprocess.run([str(x) for x in args], check=True, stdout=sys.stderr)


def number(value, label, low=0, high=float('inf')):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label}: 유한한 숫자 {low}..{high} 필요')
    return float(value)


def key(value):
    return re.sub(r'[\s_-]+', '', unicodedata.normalize('NFKC', value).casefold())


def category(spec):
    return spec.get('category', 'cd')


def local_path(root, value, label, directory=False):
    """Resolve an untrusted preset path without following a symlink or escaping its folder."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label}: 상대 경로 필요')
    relative = Path(value)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError(f'{label}: 부모 밖/절대 경로 불가')
    current = Path(root)
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f'{label}: symlink 불가')
    if not current.exists() or (directory and not current.is_dir()) or (not directory and not current.is_file()):
        raise ValueError(f'{label}: 존재하는 {"폴더" if directory else "파일"} 필요')
    return current


def template_dir(spec, base):
    if category(spec) == 'cd':
        return ROOT / 'assets/template'
    template = local_path(base, spec['template'], 'template', directory=True)
    if not (template / 'index.html').is_file() or any(path.is_symlink() for path in template.rglob('*')):
        raise ValueError('template: symlink 없는 local folder와 index.html 필요')
    return template


def asset_schema(spec):
    if category(spec) == 'cd':
        return {role: {'file': NAMES[role], 'minSide': 500, 'alpha': role == 'case'} for role in ASSETS}
    return spec['assetSchema']


def asset_files(spec):
    return {role: rule['file'] for role, rule in asset_schema(spec).items()}


def default_assets(spec):
    return spec['referenceAssets'] if category(spec) == 'cd' else asset_files(spec)


def is_cd_asset_planner(spec):
    return category(spec) == 'rhythm-cd' and spec.get('genrePlanner') == 'cd-assets'


def required_word_timing_metadata(spec, required):
    if not isinstance(required, bool):
        raise ValueError('require_word_timing은 bool 필요')
    if not required:
        return None
    if spec['id'] != WORD_TIMING_PRESET_ID:
        raise ValueError('--require-word-timing은 words 검증이 된 groove-dial 프리셋에서만 지원')
    return {
        'required': True,
        'presetId': WORD_TIMING_PRESET_ID,
        'source': 'cues[].words',
        'verificationScope': 'presentation-visible-vocal-cues',
        'allowEmptyVisibleCues': True,
    }


def word_timing_summary(cues, requirement=None):
    summary = {'cueCount': len(cues), 'timedCueCount': sum(bool(c.get('words')) for c in cues), 'timedUnitCount': sum(len(c.get('words', [])) for c in cues)}
    if requirement:
        summary.update(requirement, visibleCueCount=len(cues))
    return summary


def validate_cd_visual(spec):
    if spec.get('variant') not in ('archive', 'noir', 'neon', 'notebook', 'prism'):
        raise ValueError('variant: archive/noir/neon/notebook/prism 중 선택')
    number(spec.get('discPeriodSeconds'), 'discPeriodSeconds', 2, 60)
    cap = spec.get('caption', {})
    if cap.get('font') not in ('serif', 'sans') or cap.get('effect') not in ('underline', 'bracket', 'glow', 'marker'):
        raise ValueError('caption font/effect 지원값 확인')
    number(cap.get('size'), 'caption.size', 40, 74)
    for field in ('paper', 'ink', 'light', 'dark', 'accent'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', spec.get('palette', {}).get(field, '')):
            raise ValueError(f'palette.{field}: #RRGGBB 필요')
    for field in ('artist', 'case', 'paper'):
        if not isinstance(spec.get('prompts', {}).get(field), str) or not spec['prompts'][field].strip():
            raise ValueError(f'prompts.{field} 필요')


def validate_preset(spec):
    if spec.get('schemaVersion') != 1 or not re.fullmatch(r'[a-z][a-z0-9-]{1,62}', spec.get('id', '')):
        raise ValueError('schemaVersion=1, 영문 소문자 id 필요')
    for field in ('name', 'description', 'artDirection'):
        if not isinstance(spec.get(field), str) or not spec[field].strip():
            raise ValueError(f'{field}: 빈 문자열 불가')
    for field in ('aliases', 'genres'):
        if not isinstance(spec.get(field), list) or any(not isinstance(x, str) or not x.strip() for x in spec[field]):
            raise ValueError(f'{field}: 문자열 목록 필요')
    if not isinstance(category(spec), str) or not category(spec).strip():
        raise ValueError('category: 비어 있지 않은 문자열 필요')
    spec.setdefault('category', 'cd')
    if spec['category'] != 'cd':
        spec.setdefault('requiresArtist', False)
        if not isinstance(spec['requiresArtist'], bool):
            raise ValueError('requiresArtist: bool 필요')
        if not isinstance(spec.get('template'), str) or not spec['template'].strip():
            raise ValueError('비CD 프리셋은 template 상대 폴더 필요')
        schema = spec.get('assetSchema')
        if not isinstance(schema, dict):
            raise ValueError('비CD 프리셋은 assetSchema 객체 필요')
        if spec['requiresArtist'] and not schema:
            raise ValueError('requiresArtist=true 비CD 프리셋은 검수할 assetSchema 역할이 필요')
        files = set()
        for role, rule in schema.items():
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,62}', role) or not isinstance(rule, dict) or set(rule) - {'file', 'minSide', 'alpha'}:
                raise ValueError('assetSchema는 role과 file/minSide/alpha만 지원')
            file = rule.get('file')
            if not isinstance(file, str) or Path(file).suffix.lower() != '.png' or Path(file).is_absolute() or '..' in Path(file).parts or not Path(file).parts:
                raise ValueError('assetSchema.file: 상대 PNG 경로 필요')
            if file in files:
                raise ValueError('assetSchema.file 중복 불가')
            files.add(file)
            number(rule.get('minSide'), f'assetSchema.{role}.minSide', 1)
            if 'alpha' in rule and not isinstance(rule['alpha'], bool):
                raise ValueError(f'assetSchema.{role}.alpha: bool 필요')
            rule.setdefault('alpha', False)
        if spec.get('genrePlanner') is not None and spec['genrePlanner'] != 'cd-assets':
            raise ValueError('genrePlanner: cd-assets만 지원')
        if spec.get('genrePlanner') == 'cd-assets':
            if spec['category'] != 'rhythm-cd' or spec['requiresArtist'] is not True or set(schema) != set(ASSETS):
                raise ValueError('genrePlanner=cd-assets는 rhythm-cd, requiresArtist=true, photoA/photoB/photoC/case/paper assetSchema 필요')
            validate_cd_visual(spec)
            if spec['caption']['font'] != 'sans' or spec['caption']['effect'] != 'underline':
                raise ValueError('genrePlanner=cd-assets caption은 Paperlogy sans/underline 필요')
            if spec.get('motionMode') not in MOTION_MODES:
                raise ValueError('motionMode: balanced/drive/soft 중 선택')
        return spec
    spec.setdefault('requiresArtist', True)
    if spec['requiresArtist'] is not True:
        raise ValueError('CD 프리셋 requiresArtist=true 필요')
    validate_cd_visual(spec)
    return spec


def registry():
    result, seen = [], {}
    for path in sorted(PRESETS.glob('*/preset.json')):
        spec = validate_preset(read(path))
        if path.parent.name != spec['id']:
            raise ValueError(f'폴더와 id 불일치: {path}')
        for name in [spec['id'], spec['name'], *spec['aliases']]:
            normalized = key(name)
            if normalized in seen and seen[normalized] != spec['id']:
                raise ValueError(f'스타일 이름 충돌: {name}')
            seen[normalized] = spec['id']
        result.append((spec, path.parent))
    return result


def select(name):
    for spec, directory in registry():
        if key(name) in [key(x) for x in [spec['id'], spec['name'], *spec['aliases']]]:
            return spec, directory
    raise ValueError(f'알 수 없는 스타일: {name}. list로 확인')


def load_genres():
    doc = read(GENRES)
    if doc.get('schemaVersion') != 1 or not isinstance(doc.get('profiles'), list):
        raise ValueError('장르 프로필 schemaVersion=1/profiles 목록 필요')
    seen, ids = {}, set()
    for profile in doc['profiles']:
        if profile['id'] in ids or not re.fullmatch(r'[a-z][a-z0-9-]{1,62}', profile['id']):
            raise ValueError('장르 id는 고유한 영문 소문자 이름 필요')
        ids.add(profile['id'])
        base, _ = select(profile['baseStyle'])
        if not isinstance(profile.get('visual'), dict) or set(profile['visual']) - {'palette', 'caption', 'discPeriodSeconds', 'motionMode'}:
            raise ValueError('장르 visual은 지원되는 팔레트/자막/회전/motionMode 설정만 사용')
        if profile['visual'].get('motionMode') not in MOTION_MODES:
            raise ValueError('장르 visual.motionMode: balanced/drive/soft 중 선택')
        validate_preset(dict(base, **{name: value for name, value in profile['visual'].items() if name != 'motionMode'}))
        for field in ('artistDirection', 'sceneDirection', 'photoDirection', 'paperDirection', 'motionDirection'):
            if not isinstance(profile.get(field), str) or not profile[field].strip():
                raise ValueError(f'장르 프로필 {field} 필요')
        for name in [profile['id'], profile['name'], *profile['aliases']]:
            normalized = key(name)
            if not normalized or normalized in seen and seen[normalized] != profile['id']:
                raise ValueError(f'장르 이름 충돌: {name}')
            seen[normalized] = profile['id']
    return doc['profiles']


def resolve_genres(text, profiles):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('음악 장르를 입력할 것')
    for profile in profiles:
        if key(text) in {key(n) for n in [profile['id'], profile['name'], *profile['aliases']]}:
            return [profile], []
    matched, unmatched = [], []
    for part in re.split(r'[+,/|;·]', text):
        normalized = key(part)
        if not normalized:
            continue
        candidates = []
        for profile in profiles:
            for alias in {key(n) for n in [profile['id'], profile['name'], *profile['aliases']]}:
                at = normalized.find(alias)
                if at >= 0:
                    candidates.append((at, at + len(alias), profile))
        occupied, selected = set(), []
        for start, end, profile in sorted(candidates, key=lambda c: -(c[1] - c[0])):
            span = set(range(start, end))
            if not span & occupied:
                selected.append((start, profile)); occupied.update(span)
        for _, profile in sorted(selected, key=lambda item: item[0]):
            if profile['id'] not in [p['id'] for p in matched]:
                matched.append(profile)
        remainder = ''.join(c for i, c in enumerate(normalized) if i not in occupied)
        if remainder:
            unmatched.append(remainder)
    return matched, unmatched


def genre_plan(genre, brief='', artist='', instrumental=False, style=None, look=None, vocal=None, act='auto', host='codex', require_word_timing=False):
    if host not in ('codex', 'claude', 'antigravity', 'antigravity-cli'):
        raise ValueError('host: codex/claude/antigravity/antigravity-cli 필요')
    image_tool, image_mode = ('image_gen', 'built-in') if host == 'codex' else ('gpt-image', 'codex-cli-bridge') if host == 'claude' else ('antigravity-native', 'host-native')
    casting = casting_spec(vocal, act, artist, instrumental)
    instrumental = casting['instrumental']
    if style:
        selected, _ = select(style)
        if category(selected) != 'cd' and not is_cd_asset_planner(selected):
            raise ValueError('비CD 프리셋은 plan --genre를 지원하지 않습니다. --style과 --assets, 곡별 casting으로 create하세요')
    profiles, unlisted = resolve_genres(genre, load_genres())
    look = {} if look is None else look
    base, _ = select(style or (profiles[0]['baseStyle'] if profiles else 'autumn-archive'))
    planner = is_cd_asset_planner(base)
    allowed_look = {'palette', 'caption', 'discPeriodSeconds', 'photoDirection', 'paperDirection'} | ({'motionMode', 'variant'} if planner else set())
    if not isinstance(look, dict) or set(look) - allowed_look:
        raise ValueError('look은 선택 프리셋에서 지원하는 팔레트/자막/회전/방향 설정만 사용')
    for name in ('photoDirection', 'paperDirection'):
        if name in look and (not isinstance(look[name], str) or not look[name].strip()):
            raise ValueError(f'look.{name}: 비어 있지 않은 문자열 필요')
    effective = copy.deepcopy(base)
    if profiles and (style is None or planner):
        visual = copy.deepcopy(profiles[0]['visual'])
        if planner:
            effective['variant'] = select(profiles[0]['baseStyle'])[0]['variant']
            effective.update({name: value for name, value in visual.items() if name != 'caption'})
        else:
            effective.update({name: value for name, value in visual.items() if name != 'motionMode'})
    for name in ('palette', 'caption'):
        if name in look:
            supported = {'paper', 'ink', 'light', 'dark', 'accent'} if name == 'palette' else {'size'} if planner else {'font', 'size', 'effect'}
            if not isinstance(look[name], dict) or set(look[name]) - supported:
                raise ValueError(f'look.{name}: 설정 객체 필요')
            effective[name].update(look[name])
    if 'discPeriodSeconds' in look:
        effective['discPeriodSeconds'] = look['discPeriodSeconds']
    if planner:
        for name in ('motionMode', 'variant'):
            if name in look:
                effective[name] = look[name]
    validate_preset(effective)
    word_timing = required_word_timing_metadata(effective, require_word_timing)
    directions = [p['photoDirection'] if i == 0 and style is None else p['sceneDirection'] for i, p in enumerate(profiles)]
    direction = look.get('photoDirection') or ' '.join(directions) or f'음악 스타일 {genre}를 곡 브리프에 맞는 촬영 매체와 공간으로 해석한다.'
    artist_brief = artist.strip() or (casting['subject'] if casting['vocal'] != 'unknown' or act != 'auto' else ' '.join(p['artistDirection'] for p in profiles) or '음악에 맞는 가상의 성인 아티스트')
    subject = casting['subject'] + f' Artist details (preserve): {artist_brief}.'
    if instrumental:
        subject += ' No singer or singing gestures; instrumental performance or artwork only.'
    context = f'Music genre (preserve): {genre}. Song brief (preserve): {brief}. Artist: {subject}. {direction}'
    modern = effective['variant'] == 'prism'
    medium = {'archive': 'Tactile vintage print archive, imperfect paper edges and warm photographic halation.', 'noir': 'Black-and-white silver gelatin photography and dark film paper.', 'neon': 'Low-key photographic violet/cyan reflections, subtle prism light outside the central face.', 'notebook': 'Soft instant-film photography, pastel notebook paper and handmade scrapbook texture.', 'prism': 'Contemporary high-end studio photography, pristine optical acrylic, polished cold chrome, pearl-white surfaces and controlled holographic highlights.'}[effective['variant']]
    surface = 'Natural skin pores and crisp fabrics; factory-new acrylic and chrome, no grain, scratches, tape, distressed paper or glossy AI skin.' if modern else 'Natural skin/fabric/plastic/paper texture, analog grain; no glossy AI skin.'
    texture = f'{medium} Palette: {json.dumps(effective["palette"], ensure_ascii=False)}. {surface} No text, logos, or watermarks.'
    photo = f'Use case: photorealistic-natural. 16:9 music photograph. {context} {texture} Faces or main instruments in central 55% for circular CD crop. No CD or case inside the photograph.'
    paper = look.get('paperDirection') or ('선택한 팔레트의 새 진주빛 아크릴 스튜디오 바탕, 깨끗한 유리 반사와 크롬. 낡은 종이·테이프·스크래치 없음.' if modern else '소재는 선택한 화면의 팔레트와 촬영 매체를 따르는 거친 종이. 장르의 고유 색상 대신 선택한 팔레트를 사용한다.' if style is not None else ' '.join(p['paperDirection'] for p in profiles)) or '사진으로 촬영한 종이/바탕을 곡 브리프에 맞게 설계한다.'
    case_material = 'a factory-new crystal-clear square jewel case with flawless polished edges' if modern else 'a worn square transparent jewel case'
    case_detail = '' if planner else effective['prompts']['case']
    background = 'Empty 16:9 pearl-acrylic photographic studio stage' if modern else 'Empty 16:9 photographic paper desktop'
    assets = {
        'photoA': {'prompt': photo, 'transparent_background': False, 'referenceRoles': []},
        'photoB': {'prompt': f'{photo} Reference photoA fixes identity, clothing, and space. Change only camera angle to an intimate side view; preserve the same people/objects.', 'transparent_background': False, 'referenceRoles': ['photoA']},
        'photoC': {'prompt': f'{photo} Reference photoA fixes identity, clothing, and space. Change only camera angle to a wider candid view with distinct framing; preserve the same people/objects.', 'transparent_background': False, 'referenceRoles': ['photoA']},
        'case': {'prompt': f'Use case: product-mockup. {context} Use photoA as the exact printed cover inside {case_material}. {case_detail} {texture} Nearly straight-on; all four corners inside with 6% transparent margin. True alpha outside, no desk, no separate disc, no extra people.', 'transparent_background': True, 'referenceRoles': ['photoA']},
        'paper': {'prompt': f'Use case: photorealistic-natural. {background}. Music: {genre}. Brief: {brief}. {paper} {texture} Empty centre/right for compositing; bottom 15% quiet for lyrics. No people, CD, case, text or logos.', 'transparent_background': False, 'referenceRoles': []}}
    effective['artDirection'] = f'화면 형식: {base["name"]}. {medium} 음악 장르: {genre}. {direction} 곡 브리프: {brief}'
    effective['prompts'] = {'artist': photo, 'case': assets['case']['prompt'], 'paper': assets['paper']['prompt']}
    validate_preset(effective)
    mode = 'mixed-custom' if profiles and unlisted else 'mixed' if len(profiles) > 1 else 'mapped' if profiles else 'custom'
    plan = {'schemaVersion': 1, 'type': 'showreel-cd-genre-plan', 'genre': {'input': genre, 'mode': mode, 'matched': [{'id': p['id'], 'name': p['name']} for p in profiles], 'unlisted': unlisted}, 'brief': brief, 'artistBrief': artist_brief, 'instrumental': bool(instrumental), 'basePresetId': base['id'], 'selection': {'explicitStyle': style is not None, 'customDirectionNeedsAdaptation': bool(unlisted), 'defaultRule': '사용자 지정 스타일 우선. 미지정은 먼저 적은 장르를 기본값으로 삼고 혼합 장르와 브리프로 보완. 미등록 장르는 Codex가 곡을 해석해 화면과 촬영 방향을 구체화.'}, 'effectivePreset': effective, 'motionGuidance': [p['motionDirection'] for p in profiles], 'imageGeneration': {'host': host, 'requiredTool': image_tool, 'mode': image_mode, 'status': 'prompts-ready-not-generated', 'assets': assets}, 'captions': {'required': not instrumental, 'timing': 'actual-vocal-onset; preserve original clock; full line visible at cue onset'}, 'renderEngine': 'native-showreel', 'previewNote': '저장된 미리보기는 화면 스타일 참고이며 새 곡의 신규 이미지/영상 생성 완료를 뜻하지 않음.'}
    plan['lookOverrides'] = copy.deepcopy(look)
    plan['casting'] = casting
    if word_timing:
        plan['wordTiming'] = word_timing
    return plan


def plan_command(a):
    selection = None
    if getattr(a, 'selection', None):
        from playlist_chooser import load_selection
        selection = load_selection(a.selection)
        if a.style and select(a.style)[0]['id'] != selection['value']['styleId']:
            raise ValueError('--style과 --selection의 styleId가 다릅니다')
    host = getattr(a, 'host', None)
    if host is None:
        host = selection['value'].get('host', 'codex') if selection else 'codex'
    plan = genre_plan(a.genre, a.brief, a.artist, a.instrumental, selection['value']['styleId'] if selection else a.style, read(a.look) if a.look else None, getattr(a, 'vocal', None), getattr(a, 'act', 'auto'), host, getattr(a, 'require_word_timing', False))
    if getattr(a, 'display', None):
        plan['display'] = normalize_display(read(a.display))
    elif selection:
        plan['display'] = selection['value']['display']
    if selection:
        plan['selectionSource'] = {'path': str(selection['path']), 'sha256': selection['sha256']}
    if a.out:
        target = Path(a.out).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        return {'plan': str(target), 'genre': plan['genre'], 'preset': plan['basePresetId'], 'imageTool': plan['imageGeneration']['requiredTool'], 'host': plan['imageGeneration']['host'], 'imagesGenerated': False, **({'wordTiming': plan['wordTiming']} if 'wordTiming' in plan else {})}
    return plan


def load_plan(path):
    plan = read(path)
    if not isinstance(plan, dict) or plan.get('schemaVersion') != 1 or plan.get('type') != 'showreel-cd-genre-plan':
        raise ValueError('지원되는 Showreel 장르 계획 JSON 필요')
    images, genre = plan.get('imageGeneration'), plan.get('genre')
    provider = (images.get('host', 'codex'), images.get('requiredTool'), images.get('mode')) if isinstance(images, dict) else None
    supported = {('codex', 'image_gen', 'built-in'), ('claude', 'gpt-image', 'codex-cli-bridge'), ('antigravity', 'antigravity-native', 'host-native'), ('antigravity-cli', 'antigravity-native', 'host-native')}
    if provider not in supported or not isinstance(genre, dict) or not isinstance(genre.get('input'), str) or not isinstance(plan.get('instrumental'), bool) or not isinstance(plan.get('effectivePreset'), dict):
        raise ValueError('지원되는 호스트 이미지 생성 장르 계획 JSON 필요')
    if 'casting' in plan and not isinstance(plan['casting'], dict):
        raise ValueError('계획 casting은 객체 필요')
    validate_preset(plan['effectivePreset'])
    word_timing = plan.get('wordTiming')
    if word_timing is not None:
        if not isinstance(word_timing, dict) or word_timing.get('required') is not True or word_timing != required_word_timing_metadata(plan['effectivePreset'], True):
            raise ValueError('계획 wordTiming은 지원되는 필수 words 검증 설정 필요')
    return plan


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def asset_paths(manifest, base, schema=None):
    from PIL import Image
    if not isinstance(manifest, dict):
        raise ValueError('이미지 manifest는 객체 필요')
    schema = asset_schema({'category': 'cd'}) if schema is None else schema
    result = {}
    for role, rule in schema.items():
        if not isinstance(manifest.get(role), str):
            raise ValueError(f'이미지 manifest에 {role} 필요')
        path = (base / manifest[role]).resolve()
        with Image.open(path) as img:
            if img.format != 'PNG' or min(img.size) < rule['minSide']:
                raise ValueError(f'{role}: 최소 {rule["minSide"]}px PNG 필요: {path}')
            if rule.get('alpha'):
                if 'A' not in img.getbands():
                    raise ValueError(f'{role}: 투명 alpha PNG 필요')
                lo, hi = img.getchannel('A').getextrema()
                if lo > 10 or hi < 180:
                    raise ValueError(f'{role}: 실제 투명 외곽과 충분히 불투명한 이미지 필요')
        result[role] = path
    return result


def srt_seconds(text):
    h, m, s, ms = map(int, re.fullmatch(r'(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})', text.strip()).groups())
    if m > 59 or s > 59:
        raise ValueError('SRT 분/초 범위 오류')
    return h * 3600 + m * 60 + s + ms / 1000


def load_captions(path):
    path = Path(path)
    if path.suffix.lower() == '.json':
        doc = read(path)
        if not isinstance(doc, dict) or not isinstance(doc.get('cues'), list):
            raise ValueError('자막 JSON은 cues 목록 필요')
        return doc
    if path.suffix.lower() != '.srt':
        raise ValueError('자막은 JSON 또는 SRT 지원')
    cues = []
    for block in re.split(r'\n\s*\n', path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').strip()):
        lines = block.splitlines()
        if not lines or not lines[0].isdigit() or len(lines) < 3:
            raise ValueError('표준 SRT 번호/시간/텍스트 형식 필요')
        interval = re.fullmatch(r'(.+?)\s+-->\s+(.+)', lines[1])
        if not interval:
            raise ValueError('SRT 시간 구분자 오류')
        cues.append({'id': lines[0], 'startSeconds': srt_seconds(interval[1]), 'endSeconds': srt_seconds(interval[2]), 'text': '\n'.join(lines[2:])})
    return {'schemaVersion': 1, 'status': 'provided-timing-review-unconfirmed', 'cues': cues}


def caption_token_text(text):
    return ''.join(unicodedata.normalize('NFKC', text).split())


def map_caption_words(words, text, cue_start, cue_end, origin, start, duration):
    if not isinstance(words, list) or not words:
        raise ValueError('자막 어절 목록 필요')
    if ''.join(caption_token_text(word.get('text', '')) for word in words if isinstance(word, dict)) != caption_token_text(text):
        raise ValueError('자막 본문과 어절 토큰 불일치')
    result, previous = [], cue_start
    for index, word in enumerate(words):
        if not isinstance(word, dict) or not isinstance(word.get('text'), str) or not word['text'].strip():
            raise ValueError(f'자막 어절 {index + 1}: text 필요')
        s = number(word.get('startSeconds'), f'자막 어절 {index + 1} start')
        e = number(word.get('endSeconds'), f'자막 어절 {index + 1} end')
        if s >= e or s < previous - 1e-7 or s < cue_start - 1e-7 or e > cue_end + 1e-7:
            raise ValueError(f'자막 어절 {index + 1}: 역전/겹침/본문 범위 밖')
        previous = e
        a, b = round(s + origin - start, 6), round(e + origin - start, 6)
        if b <= 0 or a >= duration or a >= b:
            continue
        item = dict(word, startSeconds=round(max(0, a), 6), endSeconds=round(min(duration, b), 6))
        if a < 0 or b > duration:
            item['clippedByPresentation'] = True
        result.append(item)
    return result


def map_captions(doc, start, duration, origin=None, *, allow_multiline=False, require_word_timing=False):
    origin = number(doc.get('source', {}).get('cutStartSeconds', 0) if origin is None else origin, 'caption origin')
    result, previous = [], 0
    for index, cue in enumerate(doc['cues']):
        s = number(cue.get('startSeconds'), '자막 start')
        e = number(cue.get('endSeconds'), '자막 end')
        if s >= e or s < previous - 1e-7:
            raise ValueError(f'자막 {index + 1}: 역전 또는 겹침')
        if not isinstance(cue.get('text'), str) or not cue['text'].strip():
            raise ValueError('빈 자막 불가')
        if not allow_multiline and ('\n' in cue['text'] or '\r' in cue['text']):
            raise ValueError('이 CD 템플릿은 한 줄 자막 지원. 원문은 보존하고 실제 가창 경계를 확인해 큐를 나눌 것')
        words = cue.get('words')
        mapped_words = map_caption_words(words, cue['text'], s, e, origin, start, duration) if words is not None else None
        previous = e
        # 시간축 변환의 부동소수점 잔여가 0초짜리 이전 구절을 남기지 않게 한다.
        a, b = round(s + origin - start, 6), round(e + origin - start, 6)
        if b <= 0 or a >= duration or a >= b:
            continue
        item = dict(cue, id=cue.get('id', index + 1), startSeconds=round(max(0, a), 6), endSeconds=round(min(duration, b), 6))
        if mapped_words is not None:
            item['words'] = mapped_words
        if a < 0 or b > duration:
            item['clippedByPresentation'] = True
        result.append(item)
    if not result and not require_word_timing:
        raise ValueError('선택한 음악 구간과 겹치는 자막이 없음')
    if require_word_timing and any(not cue.get('words') for cue in result):
        raise ValueError('현재 화면의 모든 가창 자막 cue에 검증된 words 필요')
    return result, origin


def stamp(t):
    ms = int(round(t * 1000))
    seconds, ms = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}'


def srt(cues):
    return '\n\n'.join(f'{i}\n{stamp(c["startSeconds"])} --> {stamp(c["endSeconds"])}\n{c["text"]}' for i, c in enumerate(cues, 1)) + ('\n' if cues else '')


def song_inputs(items, base, default_instrumental=False, default_casting=None, asset_schema_value=None, *, allow_multiline=False, require_word_timing=False):
    """음원/가사 입력을 모두 검증한 뒤에만 출력 프로젝트를 만든다."""
    if not isinstance(items, list) or not items:
        raise ValueError('playlist.tracks에 한 곡 이상 필요')
    tracks, cache = [], {}
    supported = {'path', 'title', 'startSeconds', 'durationSeconds', 'captions', 'captionOriginSeconds', 'instrumental', 'vocal', 'act', 'artist', 'assets', 'plan'}
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) - supported or not isinstance(item.get('path'), str):
            raise ValueError('곡 입력은 path/title/컷/자막/instrumental/vocal/act/artist/assets/plan 지원')
        artist_plan_path = (base / item['plan']).resolve(strict=True) if isinstance(item.get('plan'), str) else None
        artist_plan = load_plan(artist_plan_path) if artist_plan_path else None
        track_word_timing_requirement = (artist_plan or {}).get('wordTiming') if not require_word_timing else None
        track_requires_word_timing = require_word_timing or bool(track_word_timing_requirement and track_word_timing_requirement.get('required'))
        music = (base / item['path']).resolve(strict=True)
        if music not in cache:
            media = probe(music)
            if not any(s['codec_type'] == 'audio' for s in media['streams']):
                raise ValueError(f'음악에 오디오 스트림 없음: {music}')
            cache[music] = (media, digest(music))
        media, music_hash = cache[music]
        total = number(float(media['format']['duration']), '음악 길이', .01)
        start = number(item.get('startSeconds', 0), '곡 start', 0, total)
        duration = number(item.get('durationSeconds', total - start), '곡 duration', .01, total - start + .001)
        instrumental = item.get('instrumental', artist_plan['instrumental'] if artist_plan else default_instrumental)
        if not isinstance(instrumental, bool):
            raise ValueError('곡 instrumental은 bool 필요')
        inherited = (artist_plan or {}).get('casting') or default_casting or {}
        casting = casting_spec(item.get('vocal', inherited.get('vocal')), item.get('act', inherited.get('act', 'auto')), item.get('artist', ''), instrumental)
        instrumental = casting['instrumental']
        cap = item.get('captions')
        if cap is not None and not isinstance(cap, str):
            raise ValueError('captions는 파일 경로 문자열 필요')
        if (instrumental and cap) or (not instrumental and not cap):
            raise ValueError('보컬 곡은 captions 필요. 연주곡은 instrumental=true로 지정하고 가사를 넣지 않을 것')
        captions = (base / cap).resolve(strict=True) if isinstance(cap, str) and cap else None
        doc = load_captions(captions) if captions else {'status': 'instrumental-no-lyrics', 'cues': []}
        expected = doc.get('source', {}).get('sha256')
        if expected and expected != music_hash:
            raise ValueError('자막 원곡 SHA256과 입력 음악 불일치. 해당 원곡을 쓰거나 자막 출처를 다시 검증')
        if captions:
            map_captions(doc, start, duration, item.get('captionOriginSeconds'), allow_multiline=allow_multiline, require_word_timing=track_requires_word_timing)
        tags = media['format'].get('tags', {})
        metadata_title = tags.get('title') or tags.get('TITLE')
        title = item.get('title', metadata_title or music.stem)
        if not isinstance(title, str) or not title.strip() or len(title) > 240 or any(ord(c) < 32 for c in title):
            raise ValueError('곡 title은 제어문자 없는 1~240자 문자열 필요')
        asset_manifest_path = (base / item['assets']).resolve(strict=True) if isinstance(item.get('assets'), str) else None
        if ('assets' in item and not asset_manifest_path) or ('plan' in item and not artist_plan_path):
            raise ValueError('곡별 assets/plan은 파일 경로 문자열 필요')
        asset_manifest = read(asset_manifest_path) if asset_manifest_path else None
        track_assets = asset_paths(asset_manifest, asset_manifest_path.parent, asset_schema_value) if asset_manifest_path else None
        tracks.append({'id': f'track-{index + 1:03d}', 'title': title.strip(), 'titleSource': 'provided' if 'title' in item else 'metadata' if metadata_title else 'filename', 'path': music, 'sha256': music_hash, 'start': start, 'duration': duration, 'instrumental': instrumental, 'captions': captions, 'captionDoc': doc, 'captionOrigin': item.get('captionOriginSeconds'), 'requireWordTiming': track_requires_word_timing, 'wordTimingRequirement': track_word_timing_requirement, 'casting': casting, 'trackAssets': track_assets, 'assetManifest': asset_manifest, 'assetManifestPath': asset_manifest_path, 'artistPlan': artist_plan, 'artistPlanPath': artist_plan_path})
    return tracks


def prepare_playlist(tracks, output, multiple, *, allow_multiline=False, require_word_timing=False):
    paths, records, cues, offset_samples = [], [], [], 0
    for track in tracks:
        target = output / ('audio/tracks/' + track['id'] + '.wav') if multiple else output / 'audio/music/music.wav'
        target.parent.mkdir(parents=True, exist_ok=True)
        run(['ffmpeg', '-v', 'error', '-i', track['path'], '-ss', track['start'], '-t', track['duration'], '-vn', '-ac', 2, '-ar', 48000, '-c:a', 'pcm_s16le', target])
        with wave.open(str(target), 'rb') as stream:
            samples = stream.getnframes()
            if samples <= 0:
                raise ValueError('선택 구간에 실제 오디오 샘플이 없음')
        duration = samples / 48000
        start, end = offset_samples / 48000, (offset_samples + samples) / 48000
        doc = track['captionDoc']
        local_cues, origin = map_captions(doc, track['start'], duration, track['captionOrigin'], allow_multiline=allow_multiline, require_word_timing=require_word_timing or track['requireWordTiming']) if track['captions'] else ([], 0)
        for cue in local_cues:
            item = copy.deepcopy(cue)
            item.update(startSeconds=max(start, start + cue['startSeconds']), endSeconds=min(end, start + cue['endSeconds']))
            if 'words' in item:
                item['words'] = [dict(word, startSeconds=round(max(start, start + word['startSeconds']), 6), endSeconds=round(min(end, start + word['endSeconds']), 6)) for word in item['words']]
            if multiple:
                item.update(id=f'{track["id"]}:{cue["id"]}', sourceCueId=cue['id'], trackId=track['id'])
            cues.append(item)
        record = {'id': track['id'], 'title': track['title'], 'titleSource': track['titleSource'], 'startSeconds': start, 'endSeconds': end, 'durationSeconds': duration, 'startSample': offset_samples, 'endSample': offset_samples + samples, 'instrumental': track['instrumental'], 'captionStatus': doc.get('status', 'provided-timing-review-unconfirmed'), 'source': {'path': str(track['path']), 'sha256': track['sha256'], 'cutStartSeconds': track['start'], 'cutEndSeconds': track['start'] + duration, 'requestedDurationSeconds': track['duration']}, 'audio': {'path': str(target.relative_to(output)), 'sha256': digest(target), 'samples': samples}, 'inputTiming': {'path': str(track['captions']), 'sha256': digest(track['captions']), 'originSeconds': origin} if track['captions'] else None}
        if track['wordTimingRequirement']:
            record['wordTiming'] = word_timing_summary(local_cues, track['wordTimingRequirement'])
        record['casting'] = track['casting']
        paths.append(target); records.append(record); offset_samples += samples
    if multiple:
        if concat_wavs(paths, output / 'audio/music/music.wav') != offset_samples:
            raise ValueError('플레이리스트 오디오 샘플 합계 불일치')
    return {'schemaVersion': 1, 'sampleRate': 48000, 'durationSeconds': offset_samples / 48000, 'tracks': records}, cues


def create(a):
    plan_path = Path(a.plan).resolve(strict=True) if a.plan else None
    plan = load_plan(plan_path) if plan_path else None
    selection = None
    if getattr(a, 'selection', None):
        from playlist_chooser import load_selection
        selection = load_selection(a.selection)
        selected_style = selection['value']['styleId']
        if a.style and select(a.style)[0]['id'] != selected_style:
            raise ValueError('--style과 --selection의 styleId가 다릅니다')
        if plan and plan['basePresetId'] != selected_style:
            raise ValueError('--plan과 --selection의 styleId가 다릅니다')
        if selection['value'].get('music'):
            if getattr(a, 'playlist', None):
                raise ValueError('음악이 기록된 --selection은 단일 --music에만 사용할 수 있습니다')
            if Path(a.music).resolve(strict=True) != Path(selection['value']['music']).resolve(strict=True):
                raise ValueError('--music과 --selection에 기록된 music이 다릅니다')
    style = a.style or (selection['value']['styleId'] if selection else None) or (plan['basePresetId'] if plan else None)
    if not style:
        raise ValueError('--style 또는 --plan 필요')
    base, directory = select(style)
    spec = validate_preset(copy.deepcopy(plan['effectivePreset'])) if plan else base
    if category(spec) != 'cd' and not is_cd_asset_planner(spec) and plan:
        raise ValueError('비CD 프리셋은 plan --genre를 지원하지 않습니다. --style과 --assets, 곡별 casting으로 create하세요')
    if plan and (spec['id'] != base['id'] or plan['basePresetId'] != base['id']):
        raise ValueError('장르 계획과 지정 스타일 불일치. plan을 다시 만들 것')
    requested_word_timing = getattr(a, 'require_word_timing', False)
    if not isinstance(requested_word_timing, bool):
        raise ValueError('require_word_timing은 bool 필요')
    require_word_timing = requested_word_timing or bool((plan or {}).get('wordTiming', {}).get('required'))
    word_timing_requirement = required_word_timing_metadata(spec, require_word_timing)
    allow_multiline = getattr(a, 'allow_multiline', False)
    playlist_path = Path(a.playlist).resolve(strict=True) if getattr(a, 'playlist', None) else None
    instrumental = a.instrumental or bool(plan and plan.get('instrumental'))
    if not playlist_path and ((instrumental and a.captions) or (not instrumental and not a.captions)):
        raise ValueError('보컬 곡은 --captions 필요. 연주곡은 --instrumental/연주곡 plan으로 지정하고 가사를 넣지 않을 것')
    output = Path(a.out).resolve()
    if output.exists():
        raise ValueError('출력 폴더가 이미 존재함. 새 경로 사용')
    schema = asset_schema(spec)
    if schema and a.demo_assets == bool(a.assets):
        raise ValueError('--assets manifest.json 또는 --demo-assets 중 하나 필요')
    if not schema and (a.assets or a.demo_assets):
        raise ValueError('assetSchema가 빈 프리셋은 --assets/--demo-assets를 받지 않습니다')
    common_asset_manifest = read(a.assets) if a.assets else default_assets(base)
    assets = asset_paths(common_asset_manifest, Path(a.assets).resolve().parent if a.assets else directory, schema)
    reel_template = template_dir(spec, directory)
    display_path = getattr(a, 'display', None)
    display = normalize_display(read(display_path) if display_path else selection['value']['display'] if selection else plan.get('display') if plan else None)
    if playlist_path:
        if a.start != 0 or a.duration is not None or a.caption_origin is not None or a.captions or getattr(a, 'title', None):
            raise ValueError('playlist는 각 tracks 안에 제목/컷/자막을 지정. 단일 곡용 옵션과 혼용 불가')
        playlist_input = read(playlist_path)
        if not isinstance(playlist_input, dict) or playlist_input.get('schemaVersion') != 1:
            raise ValueError('playlist schemaVersion=1 필요')
        album_cast = playlist_input.get('casting')
        if album_cast is not None and not isinstance(album_cast, dict):
            raise ValueError('playlist.casting은 보컬/편성 설정 객체 필요')
        tracks = song_inputs(playlist_input.get('tracks'), playlist_path.parent, instrumental, album_cast, schema, allow_multiline=allow_multiline, require_word_timing=require_word_timing)
    else:
        item = {'path': a.music, 'startSeconds': a.start, 'instrumental': instrumental}
        for field, value in [('durationSeconds', a.duration), ('captions', a.captions), ('captionOriginSeconds', a.caption_origin), ('title', getattr(a, 'title', None))]:
            if value is not None:
                item[field] = value
        tracks = song_inputs([item], Path.cwd(), instrumental, (plan or {}).get('casting'), schema, allow_multiline=allow_multiline, require_word_timing=require_word_timing)
    for track in tracks:
        if track['artistPlan']:
            planned = track['artistPlan']['effectivePreset']
            if any(planned[field] != spec[field] for field in ['variant', 'palette', 'caption', 'discPeriodSeconds']):
                raise ValueError('곡별 plan은 앨범의 공통 화면 설정과 일치해야 함. 동일 --style/--look으로 다시 계획')
        if is_cd_asset_planner(spec):
            track['motionMode'] = (track['artistPlan'] or {}).get('effectivePreset', {}).get('motionMode', spec['motionMode'])
        track['castingReview'] = (check_asset_casting(track['casting'], track['assetManifest'] or common_asset_manifest, allow_demo=bool(a.demo_assets and not track['trackAssets']), required_assets=tuple(schema)) if spec['requiresArtist'] else {'status': 'not-applicable', 'vocal': track['casting']['vocal'], 'act': track['casting']['act']})
    number(sum(t['duration'] for t in tracks), '전체 길이', 12)
    if not (SHOWREEL / 'scripts/timeline.py').is_file():
        raise ValueError(f'Showreel 설치를 찾지 못함: {SHOWREEL}')
    for sub in ('assets/img', 'audio/music', 'captions', 'out', 'qa'):
        (output / sub).mkdir(parents=True, exist_ok=True)
    shutil.copytree(reel_template, output / 'reel')
    reel_index = output / 'reel' / 'index.html'
    reel_index.write_text(apply_design(reel_index.read_text(encoding='utf-8'), reel_index, ui=False), encoding='utf-8')
    shutil.copy2(ROOT / 'assets/LICENSE.showreel', output / 'LICENSE.showreel')
    names = asset_files(spec)
    for role, path in assets.items():
        target = output / 'assets/img' / names[role]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    write(output / 'assets/img/images.json', dict(common_asset_manifest, **names))
    if a.demo_assets and (directory / 'generation.json').is_file():
        write(output / 'assets/generation.json', {'mode': 'preset-reference-reuse', 'newImagesGenerated': False, 'referencePreset': spec['id'], 'referenceGeneration': read(directory / 'generation.json')})
    write(output / 'preset.json', spec)
    if plan:
        write(output / 'genre-plan.json', plan)
    actual_audio = output / 'audio/music/music.wav'
    playlist, cues = prepare_playlist(tracks, output, bool(playlist_path), allow_multiline=allow_multiline, require_word_timing=require_word_timing)
    duration = number(playlist['durationSeconds'], '실제 전체 길이', 12)
    for track, record in zip(tracks, playlist['tracks']):
        record['castingReview'] = track['castingReview']
        if 'motionMode' in track:
            record['motionMode'] = track['motionMode']
        if track['trackAssets']:
            folder = output / 'assets/tracks' / track['id']
            folder.mkdir(parents=True)
            record['assets'] = {}
            record['assetSources'] = {}
            for role, path in track['trackAssets'].items():
                target = folder / names[role]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                record['assets'][role] = '../' + str(target.relative_to(output))
                record['assetSources'][role] = {'path': str(path), 'sha256': digest(path)}
            write(folder / 'images.json', dict(track['assetManifest'], **names))
            record['assetManifestSource'] = {'path': str(track['assetManifestPath']), 'sha256': digest(track['assetManifestPath'])}
        if track['artistPlanPath']:
            folder = output / 'artist-plans';folder.mkdir(exist_ok=True)
            write(folder / (track['id'] + '.json'), track['artistPlan'])
            record['artistPlanSha256'] = digest(track['artistPlanPath'])
    write(output / 'playlist.json', playlist)
    write(output / 'artist.json', {'schemaVersion': 1, 'tracks': [{'id': t['id'], 'casting': t['casting'], 'review': t['castingReview']} for t in playlist['tracks']]})
    write(output / 'display-options.json', display)
    statuses = {t['captionStatus'] for t in playlist['tracks']}
    status = next(iter(statuses)) if len(statuses) == 1 else 'mixed-caption-statuses'
    playlist_input_record = {'path': str(playlist_path), 'sha256': digest(playlist_path)} if playlist_path else None
    source = {'path': str(actual_audio), 'sha256': digest(actual_audio), 'kind': 'playlist-audio', 'cutStartSeconds': 0, 'cutEndSeconds': duration} if playlist_path else playlist['tracks'][0]['source']
    timing = {'tracks': [t['inputTiming'] for t in playlist['tracks']]} if playlist_path else playlist['tracks'][0]['inputTiming']
    caption_doc = {'schemaVersion': 1, 'status': status, 'source': source, 'inputTiming': timing, 'cues': cues}
    if playlist_input_record:
        caption_doc['playlistInput'] = playlist_input_record
    write(output / 'captions/lyrics.json', caption_doc)
    (output / 'captions/lyrics.srt').write_text(srt(cues), encoding='utf-8')
    globals_prefix = 'CD' if category(spec) == 'cd' else 'PLAYLIST'
    lyrics_global = 'ARCHIVE_LYRICS' if category(spec) == 'cd' else 'PLAYLIST_LYRICS'
    (output / 'reel/lyrics.js').write_text(f'window.{lyrics_global}=' + json.dumps(cues, ensure_ascii=False, allow_nan=False) + ';\n', encoding='utf-8')
    scene_names = ('focus', 'print', 'memory', 'bokeh', 'cd') if category(spec) == 'cd' else ('playlist',)
    frame_count = math.ceil(duration * 30 - 1e-9)
    render_duration = frame_count / 30
    scenes = [{'id': n, 'start': STOPS[i], 'end': STOPS[i+1] if i < 4 else render_duration} for i, n in enumerate(scene_names)] if category(spec) == 'cd' else [{'id': 'playlist', 'start': 0, 'end': render_duration}]
    script = {'duration': render_duration, 'fps': 30, 'lines': [], 'sfx': [], 'scenes': scenes, 'music': {'file': 'audio/music/music.wav', 'start': 0, 'gain_db': 0, 'duck': 0, 'analysis': 'audio/music/analysis.json'}}
    write(output / 'script.json', script)
    config = {'duration': render_duration, 'fps': 30, 'audio': '../audio/mix.wav', 'preset': spec, 'assets': {role: '../assets/img/' + names[role] for role in schema}, 'display': display, 'playlist': {'schemaVersion': 1, 'tracks': [{k: t[k] for k in ['id', 'title', 'startSeconds', 'endSeconds', 'durationSeconds', 'assets', 'motionMode'] if k in t} for t in playlist['tracks']]}}
    (output / 'reel/config.js').write_text(f'window.{globals_prefix}_CONFIG=' + json.dumps(config, ensure_ascii=False, allow_nan=False) + ';\n', encoding='utf-8')
    run([PYTHON, SHOWREEL / 'scripts/music_tools.py', 'analyze', actual_audio, '--out', output / 'audio/music/analysis.json'])
    run([PYTHON, SHOWREEL / 'scripts/timeline.py', output / 'script.json'])
    with wave.open(str(actual_audio), 'rb') as audio:
        audible = False
        while block := audio.readframes(65536):
            if any(block):
                audible = True
                break
    if audible:
        run([PYTHON, SHOWREEL / 'scripts/mix.py', output / 'timeline.json', '--out', output / 'audio/mix.wav', '--music-db', 0, '--duck', 0])
    else:
        # 무음 스타일 미리보기는 loudnorm의 -inf 측정값 대신 원래 무음을 보존한다.
        run(['ffmpeg', '-v', 'error', '-i', actual_audio, '-af', f'apad=whole_dur={render_duration}', '-t', render_duration, '-ar', 48000, '-c:a', 'pcm_s24le', output / 'audio/mix.wav'])
    spectrum = spectrum_data(output / 'audio/mix.wav') if display['showSpectrum'] else None
    (output / 'reel/spectrum.js').write_text(f'window.{globals_prefix}_SPECTRUM=' + json.dumps(spectrum, separators=(',', ':'), allow_nan=False) + ';\n', encoding='utf-8')
    warnings = [{'id': c['id'], 'durationSeconds': round(c['endSeconds'] - c['startSeconds'], 6), 'reason': 'clip-cut-short-caption'} for c in cues if c.get('clippedByPresentation') and c['endSeconds'] - c['startSeconds'] < .5]
    manifest = {'schemaVersion': 1, 'presetId': spec['id'], 'presetSha256': digest(output / 'preset.json'), 'source': caption_doc['source'], 'audio': {'path': 'audio/music/music.wav', 'sha256': digest(actual_audio), 'sampleRate': 48000}, 'durationSeconds': duration, 'renderDurationSeconds': render_duration, 'fps': 30, 'expectedFrames': frame_count, 'framePaddingSeconds': render_duration - duration, 'captionStatus': caption_doc['status'], 'captionWarnings': warnings, 'demoAssets': a.demo_assets, 'assets': {role: {'source': str(path), 'sha256': digest(path)} for role, path in assets.items()}}
    manifest.update(instrumental=all(t['instrumental'] for t in playlist['tracks']), genre=plan['genre'] if plan else None, genrePlanSha256=digest(plan_path) if plan_path else None, display=display, displaySource='argument' if display_path else 'selection' if selection else 'plan' if plan and 'display' in plan else 'legacy-default', selectionSource={'path': str(selection['path']), 'sha256': selection['sha256']} if selection else None, playlistSha256=digest(output / 'playlist.json'), playlistInput=playlist_input_record, trackCount=len(tracks), spectrumAudioSha256=digest(output / 'audio/mix.wav') if spectrum else None)
    word_timing = word_timing_summary(cues, word_timing_requirement)
    manifest['wordTiming'] = word_timing
    write(output / 'production.json', manifest)
    return {'project': str(output), 'preset': spec['id'], 'trackCount': len(tracks), 'display': display, 'captions': len(cues), 'wordTiming': word_timing, 'captionStatus': caption_doc['status'], 'captionWarnings': warnings, 'demoAssets': a.demo_assets, 'next': 'render --project ' + str(output)}


def render(a):
    project = Path(a.project).resolve(strict=True)
    manifest = read(project / 'production.json')
    out = project / 'out'
    name = 'preview' if a.preview else ('cd-video' if category(read(project / 'preset.json')) == 'cd' else 'playlist-video')
    if (out / (name + '.mp4')).exists() or (out / (name + '-picture.mp4')).exists():
        raise ValueError('해당 렌더 출력이 이미 존재함. 수정본은 새 프로젝트/출력 경로 사용')
    picture = out / (name + '-picture.mp4')
    run(['node', SHOWREEL / 'scripts/render.mjs', '--dir', project / 'reel', '--out', picture, '--scale', 1, '--workers', 1 if a.preview else 2, '--sub', 1 if a.preview else 4, '--format', 'png'])
    run([PYTHON, SHOWREEL / 'scripts/finish.py', '--video', picture, '--audio', project / 'audio/mix.wav', '--name', name, '--outdir', out, '--poster', min(manifest['durationSeconds'] - .5, 16.2), '--no-web'])
    shutil.copy2(project / 'captions/lyrics.srt', out / (name + '.srt'))
    media = probe(out / (name + '.mp4'))
    v = next(s for s in media['streams'] if s['codec_type'] == 'video')
    au = next(s for s in media['streams'] if s['codec_type'] == 'audio')
    checks = {'dimensions': [v['width'], v['height']], 'fps': v['r_frame_rate'], 'frames': int(v.get('nb_frames', 0)), 'pixelFormat': v.get('pix_fmt'), 'range': v.get('color_range'), 'audioRate': au.get('sample_rate'), 'audioChannels': au.get('channels')}
    if checks['frames'] != manifest['expectedFrames'] or checks['fps'] != '30/1' or checks['pixelFormat'] != 'yuv420p' or checks['dimensions'] != [1920, 1080] or checks['range'] != 'tv' or checks['audioRate'] != '48000' or checks['audioChannels'] != 2:
        raise ValueError(f'렌더 규격 불일치: {checks}')
    run(['ffmpeg', '-v', 'error', '-i', out / (name + '.mp4'), '-f', 'null', '-'])
    write(project / 'qa' / (name + '-media.json'), checks)
    return {'video': str(out / (name + '.mp4')), 'poster': str(out / (name + '_포스터.jpg')), 'srt': str(out / (name + '.srt')), 'checks': checks}


def catalog(output=None):
    target = Path(output).resolve() if output else ROOT / 'assets/catalog.html'
    target.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    esc = html.escape
    profiles = load_genres()
    genre_options = ''.join(f'<option value="{esc(p["name"])}" data-style="{esc(p["baseStyle"])}" data-direction="{esc(p["photoDirection"])}">{esc(p["name"])}</option>' for p in profiles)
    for spec, directory in registry():
        preview = spec.get('preview', {})
        video, poster = directory / preview.get('video', 'preview.mp4'), directory / preview.get('poster', 'poster.jpg')
        ready = preview.get('status') == 'ready' and video.is_file() and poster.is_file()
        def link(path):
            return quote(os.path.relpath(path, target.parent), safe='/')
        cd = category(spec) == 'cd'
        invocation = f'$road-music-showreel-playlist 이 음악으로 {spec["name"]} 스타일의 ' + ('가상 아티스트 CD 영상을 자막과 함께 만들어줘.' if cd else '플레이리스트 모션그래픽 영상을 자막과 함께 만들어줘.')
        player = f'<video controls playsinline preload="metadata" poster="{link(poster)}" aria-label="{esc(spec["name"])} 영상"><source src="{link(video)}" type="video/mp4"></video>' if ready else '<p class="pending">미리보기 준비 중</p>'
        media_note = f'{preview.get("durationSeconds", "")}초 · {preview.get("width", "")}×{preview.get("height", "")}' if ready and preview.get('durationSeconds') else ''
        audio_note = preview.get('audioNote', '')
        audio_note_html = f'<p class="note">{esc(audio_note)}</p>' if isinstance(audio_note, str) and audio_note else ''
        genre_terms = [name for p in profiles if p['baseStyle'] == spec['id'] for name in [p['name'], *p['aliases']]]
        controls = f'<button data-time="0">인트로</button> <button data-time="{6.5 if is_cd_asset_planner(spec) else 10.3}">CD 회전</button>' if cd or is_cd_asset_planner(spec) else ''
        details = f'회전 {spec["discPeriodSeconds"]}초/바퀴 · 자막 {esc(spec["caption"]["effect"])} · {esc(spec["variant"])}' if cd else f'카테고리 {esc(spec["category"])} · 템플릿 {esc(spec["template"])}'
        cards.append(f'<article data-search="{esc(" ".join([spec["id"], spec["name"], *spec["aliases"], *spec["genres"], *genre_terms]))}">{player}<div class="body"><p class="slug">{esc(spec["id"])} · {esc(spec["category"])}</p><h2>{esc(spec["name"])}</h2><p>{esc(spec["description"])}</p><p class="genres">{" · ".join(map(esc, spec["genres"]))}</p><p class="note">{esc(media_note)}</p>{audio_note_html}{controls}<details><summary>설정과 제작 요청</summary><p>{details}</p><p>{esc(spec["artDirection"])}</p><p class="note">자막 상태: {esc(preview.get("captionStatus", "검수 여부 미확인"))}</p><a href="{link(directory / "preset.json")}" download="{esc(spec["id"])}-preset.json">설정 파일 다운로드</a><pre>{esc(invocation)}</pre></details></div></article>')
    page = '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Showreel 플레이리스트 프리셋</title><style>
*{box-sizing:border-box}main{max-width:1460px;margin:auto;padding:52px 32px}header{max-width:850px;margin-bottom:32px}h1{letter-spacing:-.04em}h2{margin:0 0 8px}.eyebrow,.slug{font-size:12px;letter-spacing:.12em;color:var(--rm-muted)}.note,.genres{color:var(--rm-muted);font-size:14px}input{width:min(100%,520px)}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px}article{border:1px solid var(--rm-border);overflow:hidden}article[hidden]{display:none}video{display:block;width:100%;aspect-ratio:16/9;background:#111}.body{padding:22px 26px}.body>p{margin:9px 0}button{padding:8px 14px;margin:10px 0;border:0;cursor:pointer}details{border-top:1px solid var(--rm-border);margin-top:12px;padding-top:14px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--rm-bg);padding:14px;border-radius:5px}.pending{padding:80px;text-align:center}@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:30px 18px}.body{padding:20px}}
</style></head><body><main><header><p class="eyebrow">ROAD MUSIC / SHOWREEL PLAYLIST</p><h1>음악에 어울리는 프리셋을 고르세요.</h1><p>CD 플레이와 다른 로컬 모션그래픽 템플릿을 함께 저장한 플레이리스트 프리셋입니다.</p><p class="note">저장된 프리셋 수와 무음 미리보기 여부는 각 카드의 실제 상태를 따릅니다. 실제 제작 기본은 1920×1080 / 30fps입니다.</p><label for="filter">스타일 또는 장르 찾기</label><br><input id="filter" type="search" placeholder="예: 네온, 인디, 재즈"></header><section class="grid" aria-label="프리셋 영상 목록">''' + ''.join(cards) + '''</section><p id="count" role="status"></p><footer><p class="note">새 프리셋은 로컬 템플릿, 자산 스키마와 실제 미리보기 영상으로 등록합니다.</p></footer></main><script>
const cards=[...document.querySelectorAll('article')],videos=[...document.querySelectorAll('video')];
document.querySelector('#filter').addEventListener('input',e=>{const q=e.target.value.normalize('NFKC').toLowerCase().trim();cards.forEach(c=>c.hidden=!c.dataset.search.normalize('NFKC').toLowerCase().includes(q));document.querySelector('#count').textContent=cards.filter(c=>!c.hidden).length+'개 스타일';});
document.querySelector('#genre-select').addEventListener('change',e=>{const search=document.querySelector('#filter');search.value=e.target.value||'';search.dispatchEvent(new Event('input'));document.querySelector('#genre-request').textContent=e.target.value?'$road-music-showreel-playlist 이 음악을 '+e.target.value+' 장르에 맞는 플레이리스트 영상으로 만들어줘.':'';});
videos.forEach(v=>v.addEventListener('play',()=>videos.forEach(other=>{if(other!==v)other.pause();})));
document.querySelectorAll('[data-time]').forEach(b=>b.addEventListener('click',()=>{const v=b.closest('article').querySelector('video');if(v){v.currentTime=Number(b.dataset.time);v.play().catch(()=>{});}}));
</script></body></html>'''
    genre_panel = '<section style="margin:24px 0"><label for="genre-select">음악 장르별 제작 방향</label><br><select id="genre-select"><option value="">전체 프리셋 보기</option>' + genre_options + '</select><p id="genre-request" role="status" aria-live="polite" style="overflow-wrap:anywhere"></p></section>'
    page = page.replace('<label for="filter">', genre_panel + '<label for="filter">', 1)
    target.write_text(apply_design(page, target, navigation_home=False if target.parent == ROOT / 'assets' else None), encoding='utf-8')
    return {'catalog': str(target), 'count': len(cards)}


def add(a):
    source = Path(a.spec).resolve(strict=True)
    spec = validate_preset(read(source))
    existing = {key(n) for p, _ in registry() for n in [p['id'], p['name'], *p['aliases']]}
    if any(key(n) in existing for n in [spec['id'], spec['name'], *spec['aliases']]):
        raise ValueError('등록된 스타일/별칭과 충돌. 새 이름 사용')
    schema = asset_schema(spec)
    if category(spec) != 'cd':
        template_dir(spec, source.parent)
        for rule in schema.values():
            local_path(source.parent, rule['file'], 'assetSchema.file')
    assets = asset_paths(default_assets(spec), source.parent, schema)
    preview = spec.get('preview', {})
    if preview.get('status') != 'ready':
        raise ValueError('미리보기 렌더·검수 후 preview.status=ready로 등록')
    video = (source.parent / preview.get('video', '')).resolve(strict=True)
    poster = (source.parent / preview.get('poster', '')).resolve(strict=True)
    media = probe(video)
    v = next((s for s in media['streams'] if s['codec_type'] == 'video'), None)
    if not v or float(media['format']['duration']) < 12 or abs(v['width'] / v['height'] - 16 / 9) > .01:
        raise ValueError('12초 이상의 실제 16:9 미리보기 영상 필요')
    from PIL import Image
    with Image.open(poster) as img:
        img.verify()
    destination = PRESETS / spec['id']
    if destination.exists():
        raise ValueError('기존 프리셋 덮어쓰기 금지')
    temp = Path(tempfile.mkdtemp(prefix='.adding-', dir=PRESETS))
    try:
        names = asset_files(spec)
        for role, path in assets.items():
            target = temp / names[role]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if category(spec) != 'cd':
            shutil.copytree(template_dir(spec, source.parent), temp / spec['template'])
        shutil.copy2(video, temp / 'preview.mp4')
        shutil.copy2(poster, temp / 'poster.jpg')
        if (source.parent / 'generation.json').is_file():
            shutil.copy2(source.parent / 'generation.json', temp / 'generation.json')
        if (source.parent / 'verification.json').exists():
            shutil.copy2(local_path(source.parent, 'verification.json', 'verification'), temp / 'verification.json')
        if category(spec) == 'cd':
            spec['referenceAssets'] = NAMES.copy()
        spec['preview'] = dict(preview, video='preview.mp4', poster='poster.jpg', durationSeconds=float(media['format']['duration']), width=v['width'], height=v['height'])
        write(temp / 'preset.json', spec)
        os.rename(temp, destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return {'registered': spec['id'], 'path': str(destination), **catalog()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('list')
    subs.add_parser('genres')
    p = subs.add_parser('plan'); p.add_argument('--genre', required=True)
    p.add_argument('--host', choices=['codex', 'claude', 'antigravity', 'antigravity-cli'])
    p.add_argument('--brief', default=''); p.add_argument('--artist', default=''); p.add_argument('--style')
    p.add_argument('--vocal', help='female/male/mixed/unknown/none 또는 한국어 보컬 유형')
    p.add_argument('--act', default='auto', choices=['auto','solo','duo','band','ensemble','artwork'])
    p.add_argument('--look', help='사용자 지정 재질/팔레트/자막 설정 JSON')
    p.add_argument('--display', help='스펙트럼/목록/현재곡/채널명 표시 옵션 JSON (선택값 변경 시 우선 적용)')
    p.add_argument('--selection', help='choose가 만든 request.json; style/display 자동 적용')
    p.add_argument('--instrumental', action='store_true'); p.add_argument('--out')
    p.add_argument('--require-word-timing', action='store_true')
    p = subs.add_parser('show'); p.add_argument('style')
    p = subs.add_parser('catalog'); p.add_argument('--out')
    p = subs.add_parser('choose'); p.add_argument('--out', required=True)
    p.add_argument('--music'); p.add_argument('--open', action='store_true')
    p.add_argument('--timeout', type=float, default=900)
    p = subs.add_parser('add'); p.add_argument('--spec', required=True)
    p = subs.add_parser('create')
    p.add_argument('--out', required=True)
    music_input = p.add_mutually_exclusive_group(required=True)
    music_input.add_argument('--music'); music_input.add_argument('--playlist')
    p.add_argument('--style'); p.add_argument('--plan'); p.add_argument('--captions')
    p.add_argument('--instrumental', action='store_true')
    p.add_argument('--display', help='선택값 변경 시 우선 적용'); p.add_argument('--selection', help='choose가 만든 request.json; style/display 자동 적용'); p.add_argument('--title', help='단일 곡의 표시 제목')
    p.add_argument('--assets'); p.add_argument('--demo-assets', action='store_true')
    p.add_argument('--start', type=float, default=0); p.add_argument('--duration', type=float)
    p.add_argument('--caption-origin', type=float)
    p.add_argument('--allow-multiline', action='store_true')
    p.add_argument('--require-word-timing', action='store_true')
    p = subs.add_parser('render'); p.add_argument('--project', required=True); p.add_argument('--preview', action='store_true')
    a = parser.parse_args()
    try:
        if a.command == 'list':
            result = [{'id': s['id'], 'name': s['name'], 'aliases': s['aliases'], 'genres': s['genres'], 'category': s['category'], 'template': s.get('template'), 'preview': str(d / s.get('preview', {}).get('video', 'preview.mp4'))} for s, d in registry()]
        elif a.command == 'show':
            result = select(a.style)[0]
        elif a.command == 'catalog':
            result = catalog(a.out)
        elif a.command == 'genres':
            result = [{'id': p['id'], 'name': p['name'], 'aliases': p['aliases'], 'baseStyle': p['baseStyle']} for p in load_genres()]
        elif a.command == 'plan':
            result = plan_command(a)
        elif a.command == 'choose':
            from playlist_chooser import choose_command
            result = choose_command(a)
        else:
            result = {'create': create, 'render': render, 'add': add}[a.command](a)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, OSError, KeyError, TypeError, AttributeError, TimeoutError, subprocess.CalledProcessError) as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
