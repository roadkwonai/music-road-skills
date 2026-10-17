import importlib.util
import json
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

spec = importlib.util.spec_from_file_location('project', Path(__file__).with_name('project.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProjectTests(unittest.TestCase):
    def test_cues_keep_text_timing_and_gaps(self):
        cues = [{'start': 1, 'end': 3, 'text': '네가 머문 자리', 'section': 'verse'},
                {'start': 4, 'end': 6, 'text': '다시 네게 돌아가', 'section': 'chorus'}]
        project = p.build({'duration': 8, 'sha256': 'x', 'path': '/music.wav'},
                          {'profile': 'paper-ballad', 'title': '테스트', 'genre': ['발라드']}, cues)
        self.assertIn('[00:01.000]네가 머문 자리', project['lyrics'])
        self.assertIn('[00:03.000][interlude 1.000000]', project['lyrics'])
        self.assertEqual(project['title'], '')
        self.assertFalse(project['timing']['snap'])
        self.assertFalse(project['typeset'])
        self.assertEqual(project['overrides']['1']['cuts'], 1)
        self.assertEqual(project['overrides']['3']['cuts'], 1)
        self.assertEqual(project['source']['sha256'], 'x')

    def test_invalid_cues_are_not_retimed(self):
        for cues in ([{'start': 1, 'end': 3, 'text': 'one'}, {'start': 2, 'end': 4, 'text': 'two'}],
                     [{'start': 0, 'end': 11, 'text': 'too long'}],
                     [{'start': float('nan'), 'end': 2, 'text': 'NaN'}],
                     [{'start': 0, 'end': 2, 'text': '가사/원문'}]):
            with self.assertRaises(ValueError):
                p.build({'duration': 10}, {'profile': 'paper-ballad'}, cues)

    def test_instrumental_has_no_invented_lyrics_and_covers_full_song(self):
        project = p.build({'duration': 17.25}, {'profile': 'neon-city', 'instrumental': True}, [])
        self.assertTrue(all('interlude' in line for line in project['lyrics'].splitlines()))
        self.assertIn('[00:17.250][interlude 0.01]', project['lyrics'])
        self.assertEqual(project['timing']['bpm'], 0)
        self.assertEqual(project['overrides']['0']['bg'], 'retroGrid')
        self.assertIn('beatRing', project['overrides']['0']['decor'])

    def test_subdivision_requires_word_timing(self):
        cue = {'start': 1, 'end': 4, 'text': '하나 둘 셋', 'jizura': {'cuts': 3}}
        with self.assertRaises(ValueError):
            p.build({'duration': 5}, {'profile': 'red-impact'}, [cue])
        cue['jizura']['cutTime'] = {'1': 1, '2': 2}
        project = p.build({'duration': 5}, {'profile': 'red-impact'}, [cue])
        self.assertEqual(project['overrides']['1']['cutTime'], {'1': 1, '2': 2})

    def test_outputs_are_exclusive(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'new.json'
            p.write_json(path, {'value': 1})
            with self.assertRaises(FileExistsError):
                p.write_json(path, {'value': 2})
            self.assertIn('1', path.read_text())

    def test_native_output_and_composition_settings_are_preserved(self):
        custom = {'themeId': 'kinetic', 'aspect': '9:16', 'res': 720, 'fps': 60,
                  'quality': 'max', 'includeAudio': False, 'keyBg': 'green',
                  'centerFree': True, 'centerDir': 'lr', 'typeset': True,
                  'locks': {'tech': {'layout': True}, 'params': {'motion': True}}}
        result = p.build({'duration': 4}, {'profile': 'neon-city', 'instrumental': True,
                                          'jizura': custom}, [])
        for key, value in custom.items():
            self.assertEqual(result[key], value)
        self.assertEqual(result['timing']['snap'], False)

    def test_native_output_settings_reject_unsupported_values(self):
        for key, value in [('aspect', '2:1'), ('fps', 0), ('res', 99999),
                           ('quality', 'ultra'), ('includeAudio', 'false'),
                           ('centerDir', 'sideways'), ('keyBg', 'blue')]:
            with self.assertRaises(ValueError):
                p.build({'duration': 4}, {'profile': 'neon-city', 'instrumental': True,
                                          'jizura': {key: value}}, [])

    def test_manual_grid_and_section_controls_reach_interludes(self):
        direction = {'profile': 'paper-ballad', 'instrumental': True, 'bpm': 120, 'beatOffset': .25,
                     'sections': [{'id': 'intro', 'start': 0, 'end': 5,
                                   'jizura': {'bg': 'auroraRibbons', 'decor': []}},
                                  {'id': 'chorus', 'start': 5, 'end': 12,
                                   'jizura': {'bg': 'bigStripes', 'decor': ['beatRing']}}]}
        value = p.build({'duration': 12, 'beats': [0, 1, 2]}, direction, [])
        self.assertIn('[00:04.250]', value['lyrics'])
        self.assertIn('[00:05.000]', value['lyrics'])
        self.assertEqual(value['overrides']['0']['bg'], 'auroraRibbons')
        self.assertTrue(any(v.get('bg') == 'bigStripes' for v in value['overrides'].values()))

    def test_short_rest_keeps_vocal_times_and_repeated_motif_mapping(self):
        direction = {'profile': 'paper-ballad', 'sections': [{'id': 'chorus', 'start': 0, 'end': 6,
                                                           'jizura': {'hold': 'heartbeat', 'decor': ['beatRing']}}]}
        cues = [{'start': 1, 'end': 2, 'text': '같은 노래가 되어', 'motif': 'hook'},
                {'start': 2.1, 'end': 3.5, 'text': '같은 노래가 되어', 'motif': 'hook'}]
        value = p.build({'duration': 6}, direction, cues)
        self.assertIn('[00:02.100]같은 노래가 되어', value['lyrics'])
        self.assertEqual(value['cueMap'][0]['end'], 2)
        self.assertEqual(value['cueMap'][0]['displayHoldUntil'], 2.1)
        self.assertEqual(value['timingNotes'][0]['type'], 'short-rest-held')
        self.assertEqual(value['overrides']['1']['hold'], 'heartbeat')
        self.assertEqual(value['directing']['motifs'], [{'lines': [1, 2]}])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe 필요')
    def test_playlist_keeps_audio_clock_across_fractional_frame_boundaries(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            audio, video, project = (root / name for name in ('tone.wav', 'source.mp4', 'project.json'))
            rate, duration = 48000, 1.013
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                stream.writeframes(b''.join(struct.pack('<h', int(8000 * math.sin(2 * math.pi * 440 * n / rate)))
                                           for n in range(round(rate * duration))))
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=30',
                            '-t', '1.1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
            p.write_json(project, {'source': {'sha256': p.sha256(audio), 'duration': duration}})
            tracks = root / 'tracks.json'
            p.write_json(tracks, {'tracks': [dict(audio=str(audio), video=str(video), project=str(project))] * 3})
            result = p.assemble(tracks, root / 'playlist.mp4')
            self.assertAlmostEqual(result['chapters'][2]['start'], 2.026, places=5)
            streams = result['actual']['streams']
            self.assertEqual(int(next(s for s in streams if s['codec_type'] == 'video')['nb_frames']), 91)
            self.assertAlmostEqual(float(next(s for s in streams if s['codec_type'] == 'audio')['duration']), 3.039, places=3)
            # AAC has end padding; the track boundary itself must not gain a silent frame.
            pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(root / 'playlist.mp4'),
                                           '-ss', '1.015', '-t', '0.01', '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'])
            values = struct.unpack('<' + 'f' * (len(pcm) // 4), pcm)
            self.assertGreater(math.sqrt(sum(v*v for v in values) / len(values)), .05)
            with self.assertRaises(ValueError):
                p.assemble(tracks, root / 'playlist.mp4')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe 필요')
    def test_compose_switches_styles_on_one_audio_clock(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            audio = root / 'tone.wav'
            rate, duration = 48000, 1.013
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                stream.writeframes(b''.join(struct.pack('<h', int(12000 * math.sin(2 * math.pi * 440 * n / rate)))
                                           for n in range(round(rate * duration))))
            actual_duration = float(p.probe(audio)['format']['duration'])

            def render(name, color, fps, seconds):
                path = root / name / 'clip.mp4'
                path.parent.mkdir()
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s=160x90:r={fps}',
                                '-t', str(seconds), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)
                actual, video, _, frames = p.video_stream(path)
                return path, {'ok': True, 'output': str(path), 'duration': float(actual['format']['duration']),
                              'sourceDuration': actual_duration, 'actualExportSpan': {},
                              'video': {'width': video['width'], 'height': video['height'], 'frames': frames}}

            base = {'source': {'sha256': p.sha256(audio), 'duration': actual_duration}, 'lyrics': '[00:00.000]테스트',
                    'timing': {'bpm': 120, 'snap': False}, 'overrides': {'1': {'cutTime': {'1': .2}}}}
            boundary = .347
            blue, blue_result = render('blue', 'blue', 30, .5)
            red, red_result = render('red', 'red', 30, .813)
            blue_result['actualExportSpan'] = {'t0': .006, 'dur': .5}
            red_result['actualExportSpan'] = {'t0': .2, 'dur': .813}
            first, second = root / 'blue-project.json', root / 'red-project.json'
            p.write_json(first, dict(base, style='paperBallad'))
            p.write_json(second, dict(base, style='acid'))
            p.write_json(root / 'blue' / 'result.json', blue_result)
            p.write_json(root / 'red' / 'result.json', red_result)
            end = actual_duration - .017
            manifest = {'audio': str(audio), 'sourceSha256': p.sha256(audio), 'start': .017, 'end': end, 'segments': [
                {'start': .017, 'end': boundary, 'project': str(first), 'render': str(root / 'blue' / 'result.json')},
                {'start': boundary, 'end': end, 'project': str(second), 'render': str(root / 'red' / 'result.json')}]}
            manifest_path = root / 'compose.json'
            p.write_json(manifest_path, manifest)
            result = p.compose(manifest_path, root / 'composed.mp4')
            self.assertEqual(p.frame_count(root / 'composed.mp4'), round((end - .017) * 30))
            self.assertEqual(result['sourceSha256'], p.sha256(audio))
            self.assertEqual([row['frames'] for row in result['segments']], [10, 19])
            self.assertEqual(result['segments'][1]['style'], 'acid')
            for row in result['segments']:
                trim = row['trim']
                self.assertLessEqual(abs(trim['sourceClockStartSeconds'] - trim['outputClockStartSeconds']), 1 / 60)

            def pixel(frame):
                raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(root / 'composed.mp4'),
                                               '-vf', f'select=eq(n\\,{frame})', '-frames:v', '1',
                                               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
                return raw[0], raw[1], raw[2]

            self.assertGreater(pixel(9)[2], 120)
            self.assertGreater(pixel(10)[0], 120)
            pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(root / 'composed.mp4'),
                                           '-ss', '0.34', '-t', '0.02', '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'])
            values = struct.unpack('<' + 'f' * (len(pcm) // 4), pcm)
            self.assertGreater(math.sqrt(sum(v*v for v in values) / len(values)), .05)
            with self.assertRaises(ValueError):
                p.compose(manifest_path, root / 'composed.mp4')
            command = subprocess.run(['python3', str(Path(p.__file__)), 'compose', '--manifest', str(manifest_path),
                                      '--out', str(root / 'cli-composed.mp4')], text=True, capture_output=True, check=True)
            self.assertEqual(len(command.stdout.splitlines()), 1)
            self.assertTrue(json.loads(command.stdout)['ok'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe 필요')
    def test_compose_rejects_invalid_segments_and_render_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            audio = root / 'tone.wav'
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                stream.writeframes(b'\0\0' * 48000)
            duration = float(p.probe(audio)['format']['duration'])

            def fixture(name, color, fps=30):
                render = root / name
                render.mkdir()
                video = render / 'clip.mp4'
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s=160x90:r={fps}',
                                '-t', '1.1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
                actual, stream, _, frames = p.video_stream(video)
                project = root / f'{name}.json'
                p.write_json(project, {'style': name, 'source': {'sha256': p.sha256(audio), 'duration': duration},
                                       'lyrics': '[00:00.000]동일', 'timing': {'snap': False},
                                       'overrides': {'1': {'cutTime': {'1': .2}}}})
                result = {'ok': True, 'output': str(video), 'duration': float(actual['format']['duration']),
                          'sourceDuration': duration, 'actualExportSpan': {'t0': 0, 'dur': 1.1},
                          'video': {'width': stream['width'], 'height': stream['height'], 'frames': frames}}
                result_path = render / 'result.json'
                p.write_json(result_path, result)
                return project, result_path

            first, first_result = fixture('first', 'blue')
            second, second_result = fixture('second', 'red')

            def write_manifest(name, value):
                path = root / name
                p.write_json(path, value)
                return path

            base = {'audio': str(audio), 'sourceSha256': p.sha256(audio), 'segments': [
                {'start': 0, 'end': .5, 'project': str(first), 'render': str(first_result)},
                {'start': .5, 'end': duration, 'project': str(second), 'render': str(second_result)}]}
            bad_hash = dict(base, sourceSha256='0' * 64)
            with self.assertRaises(ValueError): p.compose(write_manifest('bad-hash.json', bad_hash), root / 'hash.mp4')
            gap = dict(base, segments=[base['segments'][0], dict(base['segments'][1], start=.6)])
            with self.assertRaises(ValueError): p.compose(write_manifest('gap.json', gap), root / 'gap.mp4')
            overlap = dict(base, segments=[base['segments'][0], dict(base['segments'][1], start=.4)])
            with self.assertRaises(ValueError): p.compose(write_manifest('overlap.json', overlap), root / 'overlap.mp4')
            nan = dict(base, segments=[dict(base['segments'][0], start=float('nan')), base['segments'][1]])
            (root / 'nan.json').write_text(json.dumps(nan), encoding='utf-8')
            with self.assertRaises(ValueError): p.compose(root / 'nan.json', root / 'nan.mp4')
            third, third_result = fixture('third', 'green', fps=24)
            conflict = dict(base, segments=[base['segments'][0], dict(base['segments'][1], project=str(third), render=str(third_result))])
            with self.assertRaises(ValueError): p.compose(write_manifest('fps.json', conflict), root / 'fps.mp4')
            narrow = p.read_json(second_result)
            narrow['actualExportSpan'] = {'t0': .6, 'dur': .4}
            narrow_path = root / 'narrow-result.json'
            p.write_json(narrow_path, narrow)
            insufficient = dict(base, segments=[base['segments'][0], dict(base['segments'][1], render=str(narrow_path))])
            with self.assertRaises(ValueError): p.compose(write_manifest('narrow.json', insufficient), root / 'narrow.mp4')
            negative = p.read_json(second_result)
            negative['actualExportSpan'] = {'t0': -.01, 'dur': 1.01}
            negative_path = root / 'negative-result.json'
            p.write_json(negative_path, negative)
            with self.assertRaises(ValueError):
                p.compose(write_manifest('negative.json', dict(base, segments=[base['segments'][0], dict(base['segments'][1], render=str(negative_path))])), root / 'negative.mp4')
            beyond = p.read_json(second_result)
            beyond['actualExportSpan'] = {'t0': .5, 'dur': .6}
            beyond_path = root / 'beyond-result.json'
            p.write_json(beyond_path, beyond)
            with self.assertRaises(ValueError):
                p.compose(write_manifest('beyond.json', dict(base, segments=[base['segments'][0], dict(base['segments'][1], render=str(beyond_path))])), root / 'beyond.mp4')
            mismatched = p.read_json(second_result)
            mismatched['video']['frames'] += 1
            mismatch_path = root / 'mismatch-result.json'
            p.write_json(mismatch_path, mismatched)
            mismatch = dict(base, segments=[base['segments'][0], dict(base['segments'][1], render=str(mismatch_path))])
            with self.assertRaises(ValueError): p.compose(write_manifest('mismatch.json', mismatch), root / 'mismatch.mp4')


if __name__ == '__main__':
    unittest.main()
