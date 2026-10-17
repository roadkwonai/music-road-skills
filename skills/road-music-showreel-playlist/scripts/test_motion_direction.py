import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from PIL import Image

from motion_direction import apply, compile_direction


class MotionDirectionTests(unittest.TestCase):
    def setUp(self):
        self.playlist = {'durationSeconds': 12, 'tracks': [
            {'id': 'track-001', 'startSeconds': 0, 'endSeconds': 6, 'source': {'sha256': 'a'*64, 'cutStartSeconds': 10, 'cutEndSeconds': 16}},
            {'id': 'track-002', 'startSeconds': 6, 'endSeconds': 12, 'source': {'sha256': 'b'*64, 'cutStartSeconds': 2, 'cutEndSeconds': 8}},
        ]}
        def track(i, sha, start, end, style):
            return {'id': i, 'sourceSha256': sha, 'interpretation': {'genre': '복합 장르', 'mood': '차분함에서 해방감으로', 'lyricTheme': '집으로 돌아가는 밤', 'rationale': '원문과 에너지 변화에 맞춘 선택'}, 'sections': [
                {'startSeconds': start, 'endSeconds': end, 'style': style, 'intensity': .6, 'motif': 'stars', 'palette': {'background': '#122038', 'foreground': '#F8F2E8', 'accent': '#FFBD71', 'secondary': '#72C8DC'}},
            ]}
        self.direction = {'schemaVersion': 1, 'type': 'showreel-music-direction', 'tracks': [track('track-001', 'a'*64, 0, 20, 'orbit'), track('track-002', 'b'*64, 0, 10, 'grid')]}
        self.analysis = {'bpm': 120, 'hits': [0, .3, 1, 2, 6, 7, 8, 11.9], 'energy': [[0, -14], [6, -10], [12, -14]]}

    def compile(self):
        return compile_direction(self.direction, self.playlist, self.analysis, 12)

    def test_source_clock_clips_and_maps_to_actual_track_boundaries(self):
        self.direction['tracks'][1]['accents'] = [{'timeSeconds': 3, 'kind': 'sweep', 'strength': .8}]
        result = self.compile()
        self.assertEqual([(s['startSeconds'], s['endSeconds'], s['style']) for s in result['sections']], [(0, 6, 'orbit'), (6, 12, 'grid')])
        self.assertIn({'timeSeconds': 7, 'kind': 'sweep', 'strength': .8, 'origin': 'manual-choice'}, result['accents'])
        self.assertEqual(self.compile(), result)

    def test_manual_accent_uses_neutral_provenance(self):
        self.direction['tracks'][0]['accents'] = [{'timeSeconds': 12, 'kind': 'ring', 'strength': .6}]
        manual = next(item for item in self.compile()['accents'] if item['origin'] == 'manual-choice')
        self.assertEqual(manual, {'timeSeconds': 2, 'kind': 'ring', 'strength': .6, 'origin': 'manual-choice'})

    def test_hash_track_coverage_gaps_and_overlaps_rejected(self):
        for mutation in ('hash', 'missing-track', 'gap', 'overlap'):
            with self.subTest(mutation=mutation):
                saved = copy.deepcopy(self.direction)
                if mutation == 'hash': self.direction['tracks'][0]['sourceSha256'] = 'c'*64
                elif mutation == 'missing-track': self.direction['tracks'].pop()
                elif mutation == 'gap': self.direction['tracks'][0]['sections'][0]['startSeconds'] = 11
                else: self.direction['tracks'][0]['sections'].append(copy.deepcopy(self.direction['tracks'][0]['sections'][0]))
                with self.assertRaises(ValueError): self.compile()
                self.direction = saved

    def test_invalid_visual_fields_are_not_silently_ignored(self):
        for field, value in [('style', 'fake-3d'), ('intensity', float('nan')), ('intensity', True), ('motif', 'typo'), ('palette', {'background': 'red'})]:
            with self.subTest(field=field, value=value):
                saved = copy.deepcopy(self.direction)
                self.direction['tracks'][0]['sections'][0][field] = value
                with self.assertRaises(ValueError): self.compile()
                self.direction = saved

    def test_silence_has_no_automatic_accents_and_hits_are_spaced(self):
        result = self.compile()
        events = [a for a in result['accents'] if a['origin'] == 'native-hit']
        self.assertTrue(events)
        self.assertTrue(all(b['timeSeconds']-a['timeSeconds'] >= .9 for a,b in zip(events,events[1:])))
        self.analysis['energy'] = [[0, -180], [12, -180]]
        self.assertEqual(self.compile()['accents'], [])

    def test_padding_keeps_last_section_without_retiming_audio(self):
        result = compile_direction(self.direction, self.playlist, self.analysis, 12.033333)
        self.assertEqual(result['sections'][-1]['endSeconds'], 12.033333)
        self.assertEqual(result['audibleDurationSeconds'], 12)
        self.assertTrue(all(a['timeSeconds'] < 12 for a in result['accents']))

    def test_media_references_are_mapped_without_moving_source_clock(self):
        self.direction['media'] = {'images': [{'id': 'night-city', 'path': '/tmp/night-city.png'}], 'thumbnail': {'path': '/tmp/thumbnail.png', 'durationSeconds': .5}}
        self.direction['tracks'][0]['sections'][0].update(imageId='night-city', imageOpacity=.72)
        playlist = copy.deepcopy(self.playlist)
        playlist['tracks'][0]['source']['cutStartSeconds'] = 0
        playlist['tracks'][0]['source']['cutEndSeconds'] = 6
        result = compile_direction(self.direction, playlist, self.analysis, 12)
        self.assertEqual((result['sections'][0]['startSeconds'], result['sections'][0]['endSeconds']), (0, 6))
        self.assertEqual(result['sections'][0]['imageId'], 'night-city')
        self.assertEqual(result['sections'][0]['imageOpacity'], .72)
        self.assertEqual(result['media']['thumbnail']['durationSeconds'], .5)
        self.direction['tracks'][0]['sections'][0]['imageId'] = 'typo'
        with self.assertRaises(ValueError):
            self.compile()

    def test_thumbnail_is_not_mapped_for_a_later_source_clip(self):
        self.direction['media'] = {'images': [], 'thumbnail': {'path': '/tmp/thumbnail.png', 'durationSeconds': .5}}
        self.assertNotIn('thumbnail', self.compile()['media'])


class MotionDirectionApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / 'project'
        (self.project / 'audio/music').mkdir(parents=True)
        (self.project / 'reel').mkdir()
        self.audio = self.project / 'audio/music/music.wav'
        with wave.open(str(self.audio), 'wb') as output:
            output.setnchannels(2); output.setsampwidth(2); output.setframerate(48_000)
            output.writeframes(b'\0' * 48_000 * 4)
        self.audio_hash = hashlib.sha256(self.audio.read_bytes()).hexdigest()
        (self.project / 'reel/direction.js').write_text('window.PLAYLIST_DIRECTION = null;\n', encoding='utf-8')
        self.write('preset.json', {'id': 'rhythm-canvas'})
        self.write('playlist.json', {'durationSeconds': 1, 'tracks': [{'id': 'track-001', 'startSeconds': 0, 'endSeconds': 1, 'source': {'sha256': 'a'*64, 'cutStartSeconds': 10, 'cutEndSeconds': 11}}]})
        self.write('production.json', {'audio': {'sha256': self.audio_hash}, 'renderDurationSeconds': 1})
        self.write('audio/music/analysis.json', {'hits': [.1, .9], 'energy': [[0, -10], [1, -10]]})
        self.direction = Path(self.temp.name) / 'direction.json'
        self.direction.write_text(json.dumps({'schemaVersion': 1, 'type': 'showreel-music-direction', 'tracks': [{'id': 'track-001', 'sourceSha256': 'a'*64, 'interpretation': {'genre': '팝', 'mood': '밝음', 'lyricTheme': '출발', 'rationale': '가사 흐름'}, 'sections': [{'startSeconds': 0, 'endSeconds': 20, 'style': 'orbit', 'palette': {'background': '#010203', 'foreground': '#F0F0F0', 'accent': '#AABBCC', 'secondary': '#112233'}, 'intensity': .7, 'motif': 'stars'}]}]}, ensure_ascii=False), encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, value):
        (self.project / relative).write_text(json.dumps(value), encoding='utf-8')

    def test_apply_is_single_use_and_records_hashes(self):
        (self.project / 'reel/direction.js').write_text('/* 기본값 */\nwindow.PLAYLIST_DIRECTION = null;\n', encoding='utf-8')
        result = apply(str(self.project.resolve()), str(self.direction.resolve()))
        self.assertEqual(result['sections'], 1)
        self.assertTrue((self.project / 'motion-direction.json').is_file())
        production = json.loads((self.project / 'production.json').read_text())
        self.assertEqual(production['motionDirection']['source']['sha256'], hashlib.sha256(self.direction.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            apply(str(self.project.resolve()), str(self.direction.resolve()))

    def test_tampered_audio_is_rejected_without_outputs(self):
        self.audio.write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            apply(str(self.project.resolve()), str(self.direction.resolve()))
        self.assertFalse((self.project / 'motion-direction.json').exists())

    def test_cli_error_is_one_json_line_and_exit_two(self):
        outcome = subprocess.run([sys.executable, str(Path(__file__).with_name('motion_direction.py')), 'apply', '--project', 'relative', '--direction', str(self.direction.resolve())], text=True, capture_output=True)
        self.assertEqual(outcome.returncode, 2)
        self.assertEqual(len(outcome.stdout.splitlines()), 1)
        self.assertIn('error', json.loads(outcome.stdout))

    def test_apply_copies_local_media_and_records_relative_hashes(self):
        city = Path(self.temp.name) / 'city.png'
        thumbnail = Path(self.temp.name) / 'thumbnail.webp'
        Image.new('RGB', (960, 540), '#203050').save(city)
        Image.new('RGB', (960, 540), '#d0a060').save(thumbnail)
        direction = json.loads(self.direction.read_text())
        direction['media'] = {'images': [{'id': 'night-city', 'path': str(city)}], 'thumbnail': {'path': str(thumbnail), 'durationSeconds': .5}}
        direction['tracks'][0]['sections'][0]['imageId'] = 'night-city'
        self.write('playlist.json', {'durationSeconds': 1, 'tracks': [{'id': 'track-001', 'startSeconds': 0, 'endSeconds': 1, 'source': {'sha256': 'a'*64, 'cutStartSeconds': 0, 'cutEndSeconds': 1}}]})
        self.direction.write_text(json.dumps(direction), encoding='utf-8')
        apply(str(self.project.resolve()), str(self.direction.resolve()))
        rendered = json.loads((self.project / 'motion-direction.json').read_text())
        self.assertEqual(rendered['sections'][0]['imageId'], 'night-city')
        self.assertEqual(rendered['media']['images'][0]['src'], 'assets/motion/night-city.png')
        self.assertEqual(rendered['media']['thumbnail']['src'], 'assets/motion/thumbnail.webp')
        self.assertTrue((self.project / rendered['media']['images'][0]['src']).is_file())
        production = json.loads((self.project / 'production.json').read_text())
        self.assertEqual(production['motionDirection']['media'], rendered['media'])

    def test_apply_rejects_invalid_or_small_media_before_writing(self):
        small = Path(self.temp.name) / 'small.jpg'
        Image.new('RGB', (959, 540), '#203050').save(small)
        direction = json.loads(self.direction.read_text())
        direction['media'] = {'images': [{'id': 'night-city', 'path': str(small)}]}
        direction['tracks'][0]['sections'][0]['imageId'] = 'night-city'
        self.direction.write_text(json.dumps(direction), encoding='utf-8')
        with self.assertRaises(ValueError):
            apply(str(self.project.resolve()), str(self.direction.resolve()))
        self.assertFalse((self.project / 'motion-direction.json').exists())
        self.assertFalse((self.project / 'assets/motion/night-city.jpg').exists())


if __name__ == '__main__':
    unittest.main()
