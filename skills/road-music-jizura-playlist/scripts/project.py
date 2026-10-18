#!/usr/bin/env python3
"""Build native JIZURA projects and finish one or more tracks with original audio."""
import argparse
import copy
import hashlib
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{name}: 유한한 숫자가 필요합니다')
    return float(value)


def stamp(seconds):
    millis = round(seconds * 1000)
    return f'{millis // 60000:02d}:{(millis % 60000) / 1000:06.3f}'


def build(audio, direction, cues):
    duration = number(audio['duration'], 'audio.duration')
    if duration <= 0:
        raise ValueError('빈 음원입니다')
    profiles = read_json(ROOT / 'assets/directions.json')['profiles']
    profile = next((p for p in profiles if p['id'] == direction.get('profile')), None)
    if profile is None:
        raise ValueError('알 수 없는 profile; styles 명령으로 확인하세요')
    if not cues and not direction.get('instrumental'):
        raise ValueError('가사 시각이 없습니다. 연주곡은 instrumental:true를 명시하세요')
    if direction.get('instrumental') and any(c.get('kind', 'lyric') == 'lyric' for c in cues):
        raise ValueError('연주곡에 가창 가사가 지정되었습니다')
    project = {
        'version': 1, 'timingOrder': 2, 'appVersion': '0.10.1',
        'title': '', 'artist': '', 'style': profile['style'], 'mood': profile['mood'],
        'seed': direction.get('seed', 20261017), 'lang': direction.get('lang', 'auto'),
        'aspect': '16:9', 'res': 1080, 'fps': 30, 'quality': 'high', 'includeAudio': True,
        'extra': True, 'typo': True, 'kinetic': True, 'wa': False, 'horror': False,
        'unify': True, 'typeset': False,
        'timing': {'bpm': 0, 'snap': False, 'offset': 0, 'tail': 0, 'useAudioLength': False},
        'fx': dict(profile['fx'], flash=False, onTwos=False, koma=0, hud='off', hideNo=True, hideTime=True),
        'overrides': {}, 'source': {k: audio[k] for k in ('path', 'sha256', 'duration') if k in audio},
        'targetDuration': duration,
    }
    for key in ('timingStatus', 'timingEvidence', 'lyricsTimingProvenance'):
        if key in direction:
            project[key] = copy.deepcopy(direction[key])
    # Keep engine settings separate from the agent's interpretation and research ledger.
    custom = direction.get('jizura', {})
    allowed = {'style', 'mood', 'lang', 'seed', 'fx', 'enabled', 'colors', 'fonts',
               'wa', 'horror', 'unify', 'kinetic', 'typo', 'extra', 'themeId',
               'aspect', 'res', 'fps', 'quality', 'includeAudio', 'keyBg',
               'centerFree', 'centerDir', 'typeset', 'locks', 'userFonts', 'exportRange'}
    if set(custom) - allowed:
        raise ValueError(f'지원하지 않는 jizura 설정: {set(custom) - allowed}')
    choices = {'aspect': {'16:9', '9:16', '4:3', '3:4', '1:1', '4:5', '21:9'},
               'res': {720, 1080, 1440, 2160}, 'fps': {24, 30, 60},
               'quality': {'standard', 'high', 'max'}, 'keyBg': {'off', 'green', 'black'},
               'centerDir': {'tb', 'lr'},
               'themeId': {None, 'lyricpv', 'kinetic', 'wa', 'horror', 'pop', 'ballad'}}
    for key, values in choices.items():
        if key in custom and (isinstance(custom[key], (dict, list, bool)) or custom[key] not in values):
            raise ValueError(f'지원하지 않는 JIZURA {key}: {custom[key]}')
    for key in ('includeAudio', 'centerFree', 'typeset', 'wa', 'horror', 'unify', 'kinetic', 'typo', 'extra'):
        if key in custom and not isinstance(custom[key], bool):
            raise ValueError(f'{key}는 true/false여야 합니다')
    for key, value in custom.items():
        if key == 'fx':
            project['fx'].update(value)
        else:
            project[key] = copy.deepcopy(value)
    if direction.get('bpm') is not None:
        bpm = number(direction['bpm'], 'bpm')
        if not 20 <= bpm <= 400 or 'beatOffset' not in direction:
            raise ValueError('수동 BPM에는 20~400 BPM과 실측 beatOffset이 함께 필요합니다')
        project['timing'].update(bpm=bpm, beatOffset=number(direction['beatOffset'], 'beatOffset'))
    sections = direction.get('sections', [])
    previous_end = 0
    for section in sections:
        start, stop = number(section['start'], 'section.start'), number(section['end'], 'section.end')
        if start < previous_end or stop <= start or stop > duration + .001:
            raise ValueError('sections는 원곡 범위 안에서 순서대로 겹치지 않아야 합니다')
        previous_end = stop

    def section_at(time):
        return next((s for s in sections if s['start'] <= time < s['end']), {})

    beats = audio.get('beats', [])
    if project['timing']['bpm'] > 0:
        period = 60 / project['timing']['bpm']
        origin = project['timing']['beatOffset']
        beats = [round(origin + i * period, 4) for i in range(max(0, math.ceil((duration - origin) / period)))
                 if origin + i * period >= 0]
    rows, end, cue_map, motifs, timing_notes = [], 0.0, [], {}, []

    def interlude(start, stop, settings=None):
        if stop - start >= .35:
            # Change background at phrase-sized beat groups, including in instrumental tracks.
            boundaries = [t for i, t in enumerate(beats) if i % 8 == 0 and start + .35 < t < stop - .35]
            section_bounds = [s['start'] for s in sections if start + .35 <= s['start'] <= stop - .35]
            boundaries = [t for t in boundaries if all(abs(t - b) >= .35 for b in section_bounds)]
            boundaries = [start] + sorted(set(boundaries + section_bounds)) + [stop]
            for left, right in zip(boundaries, boundaries[1:]):
                index = sum(bool(row) for row in rows)
                graphic = profile['interlude']
                chosen = {'bg': graphic['backgrounds'][index % len(graphic['backgrounds'])],
                          'decor': graphic['decor']}
                chosen.update({k: v for k, v in section_at(left).get('jizura', {}).items() if k in ('bg', 'decor')})
                chosen.update(copy.deepcopy(settings or {}))
                project['overrides'][str(index)] = chosen
                rows.append(f'[{stamp(left)}][interlude {right - left:.6f}]')

    for cue in cues:
        start, stop = number(cue['start'], 'cue.start'), number(cue['end'], 'cue.end')
        text = cue.get('text', '')
        if start < end - .0005 or stop - start < .35 or stop > duration + .0005:
            raise ValueError('큐가 겹치거나 너무 짧거나 음원 범위를 벗어납니다')
        if cue.get('kind') == 'interlude':
            interlude(end, start)
            settings = cue.get('jizura', {})
            if set(settings) - {'bg', 'decor'}:
                raise ValueError('간주 연출은 bg와 decor를 지원합니다')
            interlude(start, stop, settings)
            end = stop
            continue
        if not isinstance(text, str) or not text.strip() or '\n' in text or '\r' in text:
            raise ValueError('text는 한 줄 원문이어야 합니다')
        if any(c in text for c in ('/', '*', '|')) or text.startswith(('[', '#')) or text.endswith('!'):
            raise ValueError('원문이 JIZURA 예약 구문과 충돌합니다. 임의 삭제하지 말고 별도 자막 합성을 사용하세요')
        if cue_map and .0005 < start - end < .35 and abs(cue_map[-1]['end'] - end) < .0005:
            cue_map[-1]['displayHoldUntil'] = start
            timing_notes.append({'type': 'short-rest-held', 'line': cue_map[-1]['line'],
                                 'vocalEnd': end, 'displayEnd': start})
        interlude(end, start)
        section = section_at(start)
        ov = copy.deepcopy(section.get('jizura', {}))
        ov.update(copy.deepcopy(cue.get('jizura', {})))
        count = ov.get('cuts', 1)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 6:
            raise ValueError('cuts는 1~6 정수입니다')
        if set(ov) - {'cuts', 'layout', 'enter', 'hold', 'exit', 'decor', 'treat', 'bg', 'cam', 'trans', 'cutTime', 'cutTech'}:
            raise ValueError('지원하지 않는 행별 연출입니다')
        ov['cuts'] = count
        if count > 1:
            times = ov.get('cutTime', {})
            if set(times) != {str(i) for i in range(1, count)}:
                raise ValueError('분절 타이포에는 원음에서 확인한 모든 cutTime(행 시작 기준 초)이 필요합니다')
            bounds = [0] + [number(times[str(i)], 'cutTime') for i in range(1, count)] + [stop - start]
            if any(b - a < .35 for a, b in zip(bounds, bounds[1:])):
                raise ValueError('분절 구간은 각각 최소 0.35초가 필요합니다')
        if cue.get('breakBefore') or (cue_map and cue_map[-1].get('section') != section.get('id', cue.get('section'))):
            rows.append('')
        # Blank lines mark sections but do not consume native parsed line indices.
        index = str(sum(bool(row) for row in rows))
        project['overrides'][index] = ov
        mapped = copy.deepcopy(cue)
        mapped.update(line=int(index), section=section.get('id', cue.get('section')))
        mapped.setdefault('timingStatus', direction.get('timingStatus', 'unreviewed'))
        if 'timingEvidence' not in mapped and 'timingEvidence' in direction:
            mapped['timingEvidence'] = copy.deepcopy(direction['timingEvidence'])
        cue_map.append(mapped)
        if cue.get('motif'):
            motifs.setdefault(cue['motif'], []).append(int(index))
        rows.append(f'[{stamp(start)}]{text}')
        end = stop
    interlude(end, duration)
    # Native timing otherwise estimates the last lyric length; finish uses the source sample duration.
    rows.append(f'[{stamp(duration)}][interlude 0.01]')
    project['lyrics'] = '\n'.join(rows)
    project['cueMap'] = cue_map
    project['timingNotes'] = timing_notes
    directing = copy.deepcopy(direction.get('directing', {}))
    groups = [{'lines': lines} for lines in motifs.values() if len(lines) > 1]
    if directing or groups:
        directing.setdefault('schemaVersion', 1)
        directing.setdefault('sourceSha256', audio.get('sha256'))
        directing['motifs'] = directing.get('motifs', []) + groups
        project['directing'] = directing
    if 'reviewTimes' in direction:
        project['reviewTimes'] = copy.deepcopy(direction['reviewTimes'])
    return project


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                                              '-show_format', '-of', 'json', str(path)], text=True))


def encode_final(args, filters, fps, output):
    subprocess.run(args + ['-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]',
                           '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-r', str(fps),
                           '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', str(output)], check=True)


def review_video(output, inputs, review_out):
    result = json.loads(subprocess.check_output([
        'node', str(ROOT / 'scripts/readability.mjs'), *inputs,
        '--video', str(Path(output).resolve()), '--out', str(Path(review_out).resolve())], text=True))
    if not result.get('ok'):
        raise ValueError(f'MP4는 보존했습니다. 가독성 자료 생성 실패: {result}')
    return result


def assemble(manifest_path, output):
    manifest = read_json(manifest_path)
    tracks = manifest.get('tracks', [])
    if not tracks or Path(output).exists() or Path(str(output) + '.json').exists():
        raise ValueError('tracks가 필요하며 출력 영상/검증 JSON은 새 경로여야 합니다')
    args = ['ffmpeg', '-nostdin', '-hide_banner', '-v', 'error', '-n']
    filters, video_order, audio_order, chapters, lyric_tracks, total, dimensions = [], [], [], [], [], 0.0, None
    for i, track in enumerate(tracks):
        video, audio, project_path = (Path(track[key]).resolve(strict=True) for key in ('video', 'audio', 'project'))
        project = read_json(project_path)
        if project.get('cueMap'):
            plan_path = absolute_file(track.get('plan', str(video.parent / 'plan.json')), 'track.plan')
            lyric_tracks.append((i, project_path, plan_path, total))
        if project.get('source', {}).get('sha256') != sha256(audio):
            raise ValueError('프로젝트와 원음 해시가 다릅니다')
        ap, vp = probe(audio), probe(video)
        dur = number(project['source']['duration'], 'source.duration')
        if dur <= 0 or abs(float(ap['format']['duration']) - dur) > .25:
            raise ValueError('분석된 길이와 입력 오디오 길이가 다릅니다')
        videos = [s for s in vp['streams'] if s['codec_type'] == 'video']
        if not videos:
            raise ValueError('영상 트랙이 없습니다')
        v = videos[0]
        shape = (v['width'], v['height'], v['avg_frame_rate'])
        if dimensions and shape != dimensions:
            raise ValueError('모든 곡의 영상 규격을 먼저 통일하세요')
        dimensions = shape
        fps = float(Fraction(v['avg_frame_rate']))
        frames = round((total + dur) * fps) - round(total * fps)
        if float(v.get('duration', vp['format']['duration'])) < dur - .04:
            raise ValueError('원음보다 영상이 짧습니다. 전체 길이로 재렌더하세요')
        if frames < 1 or int(v.get('nb_frames', 0)) < frames:
            raise ValueError('원음 시계에 맞출 영상 프레임이 부족합니다')
        args += ['-i', str(video), '-i', str(audio)]
        filters += [f'[{2*i}:v]trim=end_frame={frames},setpts=N/({fps}*TB),setsar=1[v{i}]',
                    f'[{2*i+1}:a]atrim=duration={dur:.9f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{i}]']
        video_order.append(f'[v{i}]')
        audio_order.append(f'[a{i}]')
        chapters.append({'title': track.get('title', ''), 'start': total, 'duration': dur,
                         'audio': str(audio), 'sha256': sha256(audio), 'video': str(video)})
        total += dur
    # Concatenate audio independently so video-frame rounding never inserts silence between songs.
    filters += [''.join(video_order) + f'concat=n={len(tracks)}:v=1:a=0[v]',
                ''.join(audio_order) + f'concat=n={len(tracks)}:v=0:a=1[a]']
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    encode_final(args, filters, fps, output)
    actual = probe(output)
    if not any(s['codec_type'] == 'audio' for s in actual['streams']) or abs(float(actual['format']['duration']) - total) > .1:
        raise ValueError('최종 파일의 오디오/길이가 예상과 다릅니다; 파일은 보존했습니다')
    report = {'ok': True, 'output': str(Path(output).resolve()), 'sourceDuration': total,
              'actual': actual, 'chapters': chapters, 'listeningReviewed': False, 'visualReady': False}
    if lyric_tracks:
        review_root = Path(str(output) + '.readability')
        review_root.mkdir(exist_ok=False)
        report['readability'] = [review_video(output, ['--project', str(project_path), '--plan', str(plan_path),
                                '--video-start', str(video_start)], review_root / f'track-{i + 1}')
                                 for i, project_path, plan_path, video_start in lyric_tracks]
    else:
        report['readability'] = {'status': 'unavailable', 'reason': '검수할 cueMap 없음'}
    write_json(str(output) + '.json', report)
    return report


def absolute_file(value, name):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(f'{name}는 로컬 절대 경로여야 합니다')
    path = Path(value).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f'{name}는 파일이어야 합니다')
    return path


def frame_count(path):
    result = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
        '-show_entries', 'stream=nb_read_frames', '-of', 'json', str(path)], text=True))
    value = (result.get('streams') or [{}])[0].get('nb_read_frames')
    if value in (None, 'N/A'):
        raise ValueError(f'영상 실제 프레임 수를 읽을 수 없습니다: {path}')
    try:
        frames = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'영상 실제 프레임 수가 올바르지 않습니다: {path}') from error
    if frames < 1:
        raise ValueError(f'영상 프레임이 없습니다: {path}')
    return frames


def video_stream(path):
    actual = probe(path)
    videos = [stream for stream in actual.get('streams', []) if stream.get('codec_type') == 'video']
    if len(videos) != 1:
        raise ValueError(f'영상 트랙은 정확히 하나여야 합니다: {path}')
    video = videos[0]
    try:
        rate = Fraction(video['avg_frame_rate'])
    except (KeyError, ValueError, ZeroDivisionError) as error:
        raise ValueError(f'영상 fps를 읽을 수 없습니다: {path}') from error
    if rate <= 0 or not video.get('width') or not video.get('height'):
        raise ValueError(f'영상 규격이 올바르지 않습니다: {path}')
    return actual, video, rate, frame_count(path)


def clock_signature(project):
    if not isinstance(project.get('lyrics'), str) or not isinstance(project.get('timing'), dict) or not isinstance(project.get('overrides'), dict):
        raise ValueError('프로젝트의 lyrics/timing/overrides가 올바르지 않습니다')
    cuts = {str(index): value['cutTime'] for index, value in project['overrides'].items()
            if isinstance(value, dict) and 'cutTime' in value}
    return json.dumps({'lyrics': project['lyrics'], 'timing': project['timing'], 'cutTime': cuts},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def compose(manifest_path, output):
    manifest_path = Path(manifest_path)
    if not manifest_path.is_absolute() or not manifest_path.is_file():
        raise ValueError('manifest는 로컬 절대 파일 경로여야 합니다')
    manifest = read_json(manifest_path.resolve(strict=True))
    if not isinstance(manifest, dict):
        raise ValueError('합성 manifest는 객체여야 합니다')
    audio = absolute_file(manifest.get('audio'), 'audio')
    expected_hash = manifest.get('sourceSha256')
    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(c not in '0123456789abcdef' for c in expected_hash.lower()):
        raise ValueError('sourceSha256은 SHA-256 64자리여야 합니다')
    if sha256(audio) != expected_hash.lower():
        raise ValueError('manifest sourceSha256과 원음 해시가 다릅니다')
    audio_info = probe(audio)
    source_duration = number(float(audio_info.get('format', {}).get('duration')), 'audio.duration')
    if source_duration <= 0:
        raise ValueError('빈 음원입니다')
    start = number(manifest.get('start', 0), 'start')
    end = number(manifest.get('end', source_duration), 'end')
    if start < 0 or end <= start or end > source_duration:
        raise ValueError('합성 범위는 실제 원음 길이 안의 start..end여야 합니다')
    segments = manifest.get('segments')
    if not isinstance(segments, list) or not segments:
        raise ValueError('segments가 필요합니다')
    output = Path(output)
    if not output.is_absolute():
        raise ValueError('out은 로컬 절대 경로여야 합니다')
    sidecar = Path(str(output) + '.json')
    if output.exists() or sidecar.exists():
        raise ValueError('출력 영상/검증 JSON은 새 경로여야 합니다')

    prepared, dimensions, source_clock, cursor = [], None, None, start
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            raise ValueError(f'segments[{index}]는 객체여야 합니다')
        segment_start = number(item.get('start'), f'segments[{index}].start')
        segment_end = number(item.get('end'), f'segments[{index}].end')
        if segment_start != cursor or segment_end <= segment_start or segment_end > end:
            raise ValueError('segments는 start..end를 빈틈/겹침 없이 순서대로 덮어야 합니다')
        cursor = segment_end
        project_path = absolute_file(item.get('project'), f'segments[{index}].project')
        render_path = absolute_file(item.get('render'), f'segments[{index}].render')
        project, result = read_json(project_path), read_json(render_path)
        if not isinstance(project, dict) or not isinstance(result, dict) or result.get('ok') is not True:
            raise ValueError(f'segments[{index}]의 프로젝트/렌더 결과가 완료 상태가 아닙니다')
        source = project.get('source')
        if not isinstance(source, dict) or not isinstance(source.get('sha256'), str) or source['sha256'].lower() != expected_hash.lower():
            raise ValueError(f'segments[{index}] 프로젝트와 원음 해시가 다릅니다')
        if abs(number(source.get('duration'), f'segments[{index}].source.duration') - source_duration) > .25:
            raise ValueError(f'segments[{index}] 프로젝트 원음 길이가 다릅니다')
        signature = clock_signature(project)
        if source_clock is not None and signature != source_clock:
            raise ValueError('모든 프로젝트의 가사/타이밍/cutTime 시계가 같아야 합니다')
        source_clock = signature
        if abs(number(result.get('sourceDuration'), f'segments[{index}].result.sourceDuration') - source_duration) > .25:
            raise ValueError(f'segments[{index}] 렌더 메타데이터 원음 길이가 다릅니다')
        video_path = absolute_file(result.get('output'), f'segments[{index}].result.output')
        try:
            video_path.relative_to(render_path.parent)
        except ValueError as error:
            raise ValueError(f'segments[{index}] 렌더 출력이 result.json 폴더 밖에 있습니다') from error
        actual, video, rate, actual_frames = video_stream(video_path)
        shape = (video['width'], video['height'], rate)
        if dimensions is not None and shape != dimensions:
            raise ValueError('모든 구간의 실제 해상도와 fps를 통일하세요')
        dimensions = shape
        reported_video = result.get('video')
        if not isinstance(reported_video, dict) or any(reported_video.get(key) != value for key, value in
                                                       (('width', video['width']), ('height', video['height']), ('frames', actual_frames))):
            raise ValueError(f'segments[{index}] result.json과 실제 영상 규격이 다릅니다')
        if abs(number(result.get('duration'), f'segments[{index}].result.duration') - number(float(actual.get('format', {}).get('duration')), 'video.duration')) > .01:
            raise ValueError(f'segments[{index}] result.json과 실제 영상 길이가 다릅니다')
        span = result.get('actualExportSpan')
        if not isinstance(span, dict):
            raise ValueError(f'segments[{index}] actualExportSpan이 필요합니다')
        t0, duration = number(span.get('t0'), f'segments[{index}].actualExportSpan.t0'), number(span.get('dur'), f'segments[{index}].actualExportSpan.dur')
        span_slack = .01 + .5 / float(rate)
        if t0 < 0 or duration <= 0 or t0 + duration > source_duration + span_slack:
            raise ValueError(f'segments[{index}] actualExportSpan이 원음 범위를 벗어납니다')
        if t0 > segment_start + 1e-9 or t0 + duration < segment_end - 1e-9:
            raise ValueError(f'segments[{index}] 렌더 범위가 요청 구간을 덮지 않습니다')
        prepared.append({'start': segment_start, 'end': segment_end, 'project': project, 'projectPath': project_path,
                         'video': video_path, 'actual': actual, 'actualFrames': actual_frames, 'spanStart': t0, 'spanDuration': duration})
    if cursor != end:
        raise ValueError('segments가 합성 범위 끝까지 이어지지 않습니다')

    rate = dimensions[2]
    total_frames = round((end - start) * float(rate))
    args, filters, reports = ['ffmpeg', '-nostdin', '-hide_banner', '-v', 'error', '-n'], [], []
    for index, item in enumerate(prepared):
        left = round((item['start'] - start) * float(rate))
        right = round((item['end'] - start) * float(rate))
        output_clock = start + left / float(rate)
        source_start = round((output_clock - item['spanStart']) * float(rate))
        source_end = source_start + right - left
        if source_start < 0 or source_end > item['actualFrames'] or source_end <= source_start:
            raise ValueError(f'segments[{index}] 실제 영상 프레임이 trim 범위에 부족합니다')
        source_clock = item['spanStart'] + source_start / float(rate)
        visual_offset = source_clock - output_clock
        if abs(visual_offset) > .5 / float(rate) + 1e-9:
            raise ValueError(f'segments[{index}] 영상 프레임 시계 오차가 반 프레임을 넘습니다')
        args += ['-i', str(item['video'])]
        filters.append(f'[{index}:v]trim=start_frame={source_start}:end_frame={source_end},setpts=N/({float(rate)}*TB),setsar=1[v{index}]')
        reports.append({'style': item['project'].get('style'), 'project': str(item['projectPath']),
                        'sourceRange': {'start': item['start'], 'end': item['end']},
                        'trim': {'sourceFrameStart': source_start, 'sourceFrameEnd': source_end,
                                 'sourceOffsetSeconds': source_start / float(rate),
                                 'sourceClockStartSeconds': source_clock,
                                 'outputClockStartSeconds': output_clock,
                                 'visualFrameOffsetSeconds': visual_offset}, 'frames': source_end - source_start})
    audio_index = len(prepared)
    args += ['-i', str(audio)]
    filters += [''.join(f'[v{i}]' for i in range(len(prepared))) + f'concat=n={len(prepared)}:v=1:a=0[v]',
                f'[{audio_index}:a]atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a]']
    output.parent.mkdir(parents=True, exist_ok=True)
    encode_final(args, filters, float(rate), output)
    actual = probe(output)
    out_video = next((stream for stream in actual.get('streams', []) if stream.get('codec_type') == 'video'), None)
    out_audio = next((stream for stream in actual.get('streams', []) if stream.get('codec_type') == 'audio'), None)
    if not out_video or not out_audio or frame_count(output) != total_frames:
        raise ValueError('최종 파일의 영상 프레임/오디오가 예상과 다릅니다; 파일은 보존했습니다')
    final_audio_duration = number(float(out_audio.get('duration', actual.get('format', {}).get('duration'))), 'final.audio.duration')
    container_duration = number(float(actual.get('format', {}).get('duration')), 'final.container.duration')
    if abs(final_audio_duration - (end - start)) > .1 or abs(container_duration - (end - start)) > 1 / float(rate) + .03:
        raise ValueError('최종 파일의 오디오/컨테이너 길이가 원음 범위와 다릅니다; 파일은 보존했습니다')
    report = {'ok': True, 'output': str(output.resolve()), 'sourceSha256': expected_hash.lower(), 'sourceDuration': source_duration,
              'sourceRange': {'start': start, 'end': end, 'duration': end - start}, 'actual': actual,
              'segments': reports, 'listeningReviewed': False, 'visualReady': False}
    report['readability'] = (review_video(output, ['--manifest', str(manifest_path)], str(output) + '.readability')
                             if any(item['project'].get('cueMap') for item in prepared)
                             else {'status': 'unavailable', 'reason': '검수할 cueMap 없음'})
    write_json(sidecar, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('styles')
    b = sub.add_parser('build')
    for name in ('analysis', 'direction', 'out'):
        b.add_argument('--' + name, required=True)
    b.add_argument('--cues')
    a = sub.add_parser('assemble')
    a.add_argument('--manifest', required=True)
    a.add_argument('--out', required=True)
    c = sub.add_parser('compose')
    c.add_argument('--manifest', required=True)
    c.add_argument('--out', required=True)
    opt = parser.parse_args()
    if opt.command == 'styles':
        result = read_json(ROOT / 'assets/directions.json')
    elif opt.command == 'build':
        analysis = read_json(opt.analysis)
        audio = analysis['audio']
        if sha256(audio['path']) != audio['sha256']:
            raise ValueError('음원 변경: 분석 결과를 다시 만드세요')
        direction = read_json(opt.direction)
        cues = read_json(opt.cues) if opt.cues else []
        project = build(audio, direction, cues)
        out = Path(opt.out)
        out.mkdir(parents=True, exist_ok=False)
        write_json(out / 'project.jizura.json', project)
        write_json(out / 'direction.json', direction)
        write_json(out / 'cues.json', cues)
        result = {'ok': True, 'project': str((out / 'project.jizura.json').resolve()), 'source': project['source'],
                  'timingStatus': direction.get('timingStatus', 'unreviewed'),
                  'shortRestHolds': len(project['timingNotes']), 'rendered': False}
    elif opt.command == 'assemble':
        result = assemble(opt.manifest, opt.out)
    else:
        result = compose(opt.manifest, opt.out)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
