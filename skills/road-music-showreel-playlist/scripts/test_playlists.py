#!/usr/bin/env python3
"""실제 PCM/자막으로 여러 곡의 시계와 표시 선택 보존을 검사한다."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import cd_presets as cd


class PlaylistChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from storage_manager import StorageManager
        cls.scratch = tempfile.TemporaryDirectory(prefix='cd-playlist-input-')
        cls.root = Path(cls.scratch.name)
        cls.storage_manager = StorageManager(cls.root / 'storage-data')
        cls.storage_manager_factory = cd.storage_lifecycle.shared_storage_manager
        cls.storage_manager_factory.cache_clear()
        cd.storage_lifecycle.shared_storage_manager = lambda: cls.storage_manager
        cls.paths = []
        for i, duration in enumerate([6.001, 6.002]):
            audio = cls.root / f'song-{i}.wav'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', f'sine=frequency={220 + i * 880}:sample_rate=48000:duration={duration}', '-ac', '2', '-c:a', 'pcm_s16le', str(audio)], check=True)
            captions = cls.root / f'song-{i}.json'
            cd.write(captions, {'schemaVersion': 1, 'status': 'auto-asr-unreviewed', 'source': {'sha256': cd.digest(audio), 'cutStartSeconds': 0}, 'cues': [{'id': 1, 'startSeconds': .1 + i * .1, 'endSeconds': .6 + i * .1, 'text': f'원문 {i}'}]})
            cls.paths.append((audio, captions))
        cls.art = {}
        for vocal, preset in [('female', 'neon-afterhours'), ('male', 'noir-contact')]:
            folder = cd.PRESETS / preset
            manifest = cls.root / f'{vocal}-images.json'
            cd.write(manifest, {**{role: str(folder / cd.NAMES[role]) for role in cd.ASSETS}, 'casting': {'vocal': vocal, 'act': 'solo', 'reviewed': True, 'evidence': 'existing fictional QA fixture'}})
            cls.art[vocal] = manifest

    @classmethod
    def tearDownClass(cls):
        cd.storage_lifecycle.shared_storage_manager = cls.storage_manager_factory
        cls.storage_manager_factory.cache_clear()
        cls.scratch.cleanup()

    def items(self):
        return [{'path': a.name, 'title': '같은 제목', 'captions': c.name, 'instrumental': False} for a, c in self.paths]

    def test_sample_clock_and_captions_move_together(self):
        tracks = cd.song_inputs(self.items(), self.root)
        playlist, cues = cd.prepare_playlist(tracks, self.root / 'prepared', True)
        first, second = playlist['tracks']
        self.assertEqual(first['endSample'], 288048)
        self.assertEqual(second['startSample'], first['endSample'])
        self.assertEqual(second['endSample'], 576144)
        self.assertAlmostEqual(playlist['durationSeconds'], 12.003)
        self.assertAlmostEqual(cues[1]['startSeconds'], 6.201)
        self.assertEqual(cues[1]['text'], '원문 1')
        self.assertNotEqual(cues[0]['id'], cues[1]['id'])
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['title'], second['title'])
        self.assertEqual(second['captionStatus'], 'auto-asr-unreviewed')

    def test_word_cues_keep_cut_and_playlist_offsets(self):
        doc = cd.read(self.paths[1][1])
        doc['cues'][0].update(text='원문 1', words=[
            {'text': '원문', 'startSeconds': .2, 'endSeconds': .4},
            {'text': '1', 'startSeconds': .4, 'endSeconds': .7},
        ])
        cd.write(self.paths[1][1], doc)
        tracks = cd.song_inputs(self.items(), self.root)
        _, cues = cd.prepare_playlist(tracks, self.root / 'prepared-words', True)
        words = cues[1]['words']
        self.assertEqual([(word['text'], word['startSeconds'], word['endSeconds']) for word in words], [('원문', 6.201, 6.401), ('1', 6.401, 6.701)])

    def test_all_tracks_validate_before_output(self):
        items = self.items()
        items[1]['captions'] = None
        with self.assertRaisesRegex(ValueError, '보컬 곡'):
            cd.song_inputs(items, self.root)
        items[1]['captions'] = 123
        with self.assertRaisesRegex(ValueError, '경로 문자열'):
            cd.song_inputs(items, self.root)
        with self.assertRaises(ValueError):
            cd.song_inputs([], self.root)

    def test_source_hash_and_boolean_validation(self):
        items = self.items(); items[1]['instrumental'] = 'false'
        with self.assertRaises(ValueError):
            cd.song_inputs(items, self.root)
        wrong = self.root / 'wrong-source.json'
        doc = cd.read(self.paths[0][1]);doc['source']['sha256'] = 'bad';cd.write(wrong, doc)
        items = self.items();items[0]['captions'] = wrong.name
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            cd.song_inputs(items, self.root)

    def test_plan_saves_skip_options_and_refuses_overwrite(self):
        options = self.root / 'display.json'
        cd.write(options, {'showSpectrum': 'SKIP', 'showQueue': True, 'showNowPlaying': False, 'channelName': 'SKIP'})
        target = self.root / 'plan.json'
        args = argparse.Namespace(genre='팝', brief='차분한 음악', artist='가상 아티스트', instrumental=False, style=None, look=None, display=str(options), out=str(target))
        cd.plan_command(args)
        self.assertEqual(cd.read(target)['display'], {'showSpectrum': False, 'showQueue': True, 'showNowPlaying': False, 'channelName': ''})
        before = cd.digest(target)
        with self.assertRaises(FileExistsError):
            cd.plan_command(args)
        self.assertEqual(before, cd.digest(target))

    def test_female_band_plan_preserves_vocal_and_arrangement(self):
        plan = cd.genre_plan('록 발라드', brief='기타 베이스 드럼의 라이브 밴드', artist='가상의 성인 4인 밴드', vocal='여성', act='band')
        self.assertEqual(plan['casting']['vocal'], 'female')
        self.assertEqual(plan['casting']['act'], 'band')
        for role in ['photoA', 'photoB', 'photoC', 'case']:
            prompt = plan['imageGeneration']['assets'][role]['prompt']
            self.assertIn('adult female lead vocalist', prompt)
            self.assertIn('가상의 성인 4인 밴드', prompt)
            self.assertIn('기타 베이스 드럼', prompt)
        self.assertFalse(plan['casting']['needsConfirmation'])
        self.assertTrue(cd.genre_plan('록 발라드')['casting']['needsConfirmation'])

    def test_track_plan_and_explicit_cast_override_album_cast(self):
        plan_path = self.root / 'female-track-plan.json'
        cd.write(plan_path, cd.genre_plan('R&B', vocal='female', act='solo', style='가을'))
        items = self.items();items[0]['plan'] = plan_path.name
        items[1].update(vocal='mixed', act='duo')
        tracks = cd.song_inputs(items, self.root, default_casting={'vocal': 'male', 'act': 'band'})
        self.assertEqual([(t['casting']['vocal'], t['casting']['act']) for t in tracks], [('female', 'solo'), ('mixed', 'duo')])
        invalid = self.root / 'invalid-plan.json';cd.write(invalid, ['wrong'])
        items[0]['plan'] = invalid.name
        with self.assertRaisesRegex(ValueError, '계획 JSON'):
            cd.song_inputs(items, self.root)

    def test_wrong_cast_rejected_before_project_mutation(self):
        plan = self.root / 'wrong-cast-plan.json'
        cd.write(plan, cd.genre_plan('발라드', vocal='female', act='solo'))
        output = self.root / 'must-not-create'
        result = subprocess.run([sys.executable, str(cd.ROOT / 'scripts/cd_presets.py'), 'create', '--plan', str(plan), '--music', str(self.paths[0][0]), '--captions', str(self.paths[0][1]), '--assets', str(self.art['male']), '--out', str(output)], capture_output=True, text=True, env={**os.environ, 'ROADMUSIC_DATA_DIR': str(self.root / 'storage-data')})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('보컬 성별', result.stdout)
        self.assertFalse(output.exists())

    def test_per_track_assets_and_casting_reach_render_config(self):
        plans = {}
        for vocal, genre in [('female', 'R&B'), ('male', '재즈')]:
            path = self.root / f'{vocal}-render-plan.json'
            cd.write(path, cd.genre_plan(genre, vocal=vocal, act='solo', style='가을'))
            plans[vocal] = path
        items = self.items()
        for item, vocal in zip(items, ['female', 'male']):
            item.update(plan=str(plans[vocal]), assets=str(self.art[vocal]))
        playlist_path = self.root / 'cast-playlist.json';cd.write(playlist_path, {'schemaVersion': 1, 'tracks': items})
        output = self.root / 'cast-project'
        result = subprocess.run([sys.executable, str(cd.ROOT / 'scripts/cd_presets.py'), 'create', '--plan', str(plans['female']), '--playlist', str(playlist_path), '--assets', str(self.art['female']), '--out', str(output)], capture_output=True, text=True, env={**os.environ, 'ROADMUSIC_DATA_DIR': str(self.root / 'storage-data')})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        playlist = cd.read(output / 'playlist.json')
        self.assertAlmostEqual(playlist['durationSeconds'], 12.003)
        self.assertEqual([t['casting']['vocal'] for t in playlist['tracks']], ['female', 'male'])
        self.assertEqual([t['castingReview']['status'] for t in playlist['tracks']], ['matched', 'matched'])
        config_text = (output / 'reel/config.js').read_text()
        config = json.loads(config_text.removeprefix('window.CD_CONFIG=').strip().removesuffix(';'))
        for track in config['playlist']['tracks']:
            self.assertIn('assets', track)
            for path in track['assets'].values():
                self.assertTrue((output / 'reel' / path).is_file())
        copied = output / 'assets/tracks/track-002/images.json'
        self.assertEqual(cd.read(copied)['casting']['vocal'], 'male')
        self.assertEqual(cd.asset_paths(cd.read(copied), copied.parent)['photoA'].name, 'photo-a.png')
        self.assertEqual(playlist['tracks'][1]['assetManifestSource']['sha256'], cd.digest(self.art['male']))

    def test_cli_stdout_is_one_json_and_skip_stays_off(self):
        playlist = self.root / 'cli-playlist.json'
        options = self.root / 'cli-display.json'
        cd.write(playlist, {'schemaVersion': 1, 'tracks': self.items()})
        cd.write(options, {key: 'SKIP' for key in ['showSpectrum', 'showQueue', 'showNowPlaying', 'channelName']})
        result = subprocess.run([sys.executable, str(cd.ROOT / 'scripts/cd_presets.py'), 'create', '--style', '가을', '--playlist', str(playlist), '--display', str(options), '--demo-assets', '--out', str(self.root / 'cli-project')], capture_output=True, text=True, env={**os.environ, 'ROADMUSIC_DATA_DIR': str(self.root / 'storage-data')})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        response = json.loads(result.stdout)
        self.assertEqual(response['trackCount'], 2)
        self.assertEqual(response['display'], {'showSpectrum': False, 'showQueue': False, 'showNowPlaying': False, 'channelName': ''})
        self.assertIn('마스터', result.stderr)
        self.assertTrue((self.root / 'cli-project/reel/config.js').read_text().startswith('window.CD_CONFIG='))
        self.assertTrue((self.root / 'cli-project/reel/lyrics.js').read_text().startswith('window.ARCHIVE_LYRICS='))
        self.assertEqual((self.root / 'cli-project/reel/spectrum.js').read_text(), 'window.CD_SPECTRUM=null;\n')
        joined_audio = self.root / 'cli-project/audio/music/music.wav'
        global_captions = self.root / 'cli-project/captions/lyrics.json'
        self.assertEqual(cd.read(global_captions)['source']['sha256'], cd.digest(joined_audio))
        self.assertEqual(cd.read(global_captions)['playlistInput']['sha256'], cd.digest(playlist))
        reused = cd.song_inputs([{'path': str(joined_audio), 'captions': str(global_captions)}], self.root)
        self.assertEqual(len(reused), 1)

    def test_create_redirects_a_new_output_request_to_hidden_work(self):
        (self.root / 'Output').mkdir(exist_ok=True)
        playlist = self.root / 'output-playlist.json'
        cd.write(playlist, {'schemaVersion': 1, 'tracks': self.items()})
        original = cd.storage_lifecycle._trusted_workspace
        cd.storage_lifecycle._trusted_workspace = lambda: self.root
        try:
            result = cd.create(argparse.Namespace(
                plan=None, selection=None, style='크롬', require_word_timing=False,
                allow_multiline=False, playlist=str(playlist), instrumental=False,
                captions=None, out=str(self.root / 'Output' / 'old-style'),
                demo_assets=True, assets=None, display=None, music=None, start=0,
                duration=None, caption_origin=None, title=None,
            ))
        finally:
            cd.storage_lifecycle._trusted_workspace = original
        actual = Path(result['project'])
        self.assertTrue(actual.is_relative_to(self.root / '.roadmusic/work'))
        self.assertFalse((self.root / 'Output' / 'old-style').exists())

    def test_silent_style_preview_preserves_silence(self):
        import wave
        silent = self.root / 'silent.wav'
        with wave.open(str(silent), 'wb') as audio:
            audio.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            audio.writeframes(bytes(12 * 48000 * 4))
        output = self.root / 'silent-project'
        result = subprocess.run([sys.executable, str(cd.ROOT / 'scripts/cd_presets.py'), 'create', '--style', '크롬', '--music', str(silent), '--instrumental', '--demo-assets', '--out', str(output)], capture_output=True, text=True, env={**os.environ, 'ROADMUSIC_DATA_DIR': str(self.root / 'storage-data')})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        media = cd.probe(output / 'audio/mix.wav')
        self.assertEqual(float(media['format']['duration']), 12)
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output / 'audio/mix.wav'), '-f', 's16le', '-'], check=True, capture_output=True).stdout
        self.assertFalse(any(raw))
        self.assertEqual(cd.read(output / 'production.json')['expectedFrames'], 360)
        self.assertEqual(cd.read(output / '.roadmusic/history/owned-render-cache.json')['files'], [])

    def test_render_preserves_final_output_when_storage_postprocessing_warns(self):
        project = self.root / 'render-storage'
        project.mkdir()
        cd.write(project / 'production.json', {'schemaVersion': 1, 'durationSeconds': 1, 'expectedFrames': 30})
        cd.write(project / 'playlist.json', {'schemaVersion': 1, 'tracks': []})
        cd.write(project / 'preset.json', {'category': 'cd'})
        (project / 'captions').mkdir()
        (project / 'qa').mkdir()
        (project / 'captions/lyrics.srt').write_text('fixture', encoding='utf-8')
        registered = cd.storage_lifecycle.prepare_project(project)
        self.storage_manager.dispatch('policy', {'projectId': registered['id'], 'state': 'completed', 'retainDays': 0})

        def fake_run(args):
            if args[0] == 'node':
                picture = Path(args[args.index('--out') + 1]); picture.parent.mkdir(parents=True, exist_ok=True); picture.write_bytes(b'picture')
            elif Path(args[1]).name == 'finish.py':
                out = Path(args[args.index('--outdir') + 1]); out.mkdir(exist_ok=True); (out / 'cd-video.mp4').write_bytes(b'final'); (out / 'cd-video_포스터.jpg').write_bytes(b'poster')

        media = {'streams': [
            {'codec_type': 'video', 'width': 1920, 'height': 1080, 'r_frame_rate': '30/1', 'nb_frames': '30', 'pix_fmt': 'yuv420p', 'color_range': 'tv'},
            {'codec_type': 'audio', 'sample_rate': '48000', 'channels': 2},
        ]}
        finish_render = cd.storage_lifecycle.finish_render
        def warning_after_finish(*args, **kwargs):
            finish_render(*args, **kwargs)
            raise OSError('fixture cleanup warning')

        with patch.object(cd, 'run', side_effect=fake_run), patch.object(cd, 'probe', return_value=media), patch.object(cd.storage_lifecycle, 'finish_render', side_effect=warning_after_finish):
            result = cd.render(argparse.Namespace(project=str(project), preview=False))

        self.assertEqual((project / 'out/cd-video.mp4').read_bytes(), b'final')
        self.assertFalse((project / '.roadmusic/cache/picture/cd-video-picture.mp4').exists())
        self.assertFalse(self.storage_manager.dispatch('list', {'projectId': registered['id']})['projects'][0]['busy'])
        self.assertEqual(result['video'], str((project / 'out/cd-video.mp4').resolve()))
        self.assertIn('저장공간 후처리 실패', result['storageWarning'])
        from production_ledger import ProductionLedger
        task = ProductionLedger(self.storage_manager.data_dir).tasks({'limit': 1})['tasks'][0]
        self.assertEqual((task['taskType'], task['status'], task['engine'], task['model']), ('render', 'succeeded', 'showreel', 'preset-cd'))
        self.assertEqual(task['frameCount'], 30)


if __name__ == '__main__':
    unittest.main(verbosity=2)
