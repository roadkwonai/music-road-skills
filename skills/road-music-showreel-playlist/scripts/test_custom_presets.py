#!/usr/bin/env python3
"""비CD 템플릿 프리셋의 등록과 플레이리스트 프로젝트 경계 검사."""
import argparse
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
import shutil
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import cd_presets as cd
from vocal_cast import casting_spec, check_asset_casting


class CustomPresetChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix='playlist-custom-')
        cls.root = Path(cls.scratch.name)
        cls.library = cls.root / 'library'; cls.library.mkdir()
        cls.source = cls.root / 'source'; cls.source.mkdir()
        cls.template = cls.source / 'collage-template'; cls.template.mkdir()
        (cls.template / 'index.html').write_text('<!doctype html><title>fixture</title>', encoding='utf-8')
        for name, color in [('portrait.png', '#8866aa'), ('background.png', '#26374e')]:
            Image.new('RGB', (640, 640), color).save(cls.source / name)
        cls.video = cls.source / 'preview.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=640x360:r=30', '-t', '12', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video)], check=True)
        cls.poster = cls.source / 'poster.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(cls.video), '-frames:v', '1', str(cls.poster)], check=True)
        cd.write(cls.source / 'verification.json', {'status': 'fixture-media-checked'})

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def spec(self, **changes):
        value = {
            'schemaVersion': 1, 'id': 'motion-collage', 'name': '모션 콜라주', 'aliases': ['콜라주'],
            'genres': ['앰비언트'], 'description': '사진 레이어가 움직이는 비CD 플레이리스트.',
            'artDirection': '차분한 사진 콜라주와 절제된 타이포그래피.', 'category': 'motion-collage',
            'template': 'collage-template', 'assetSchema': {
                'portrait': {'file': 'portrait.png', 'minSide': 500},
                'background': {'file': 'background.png', 'minSide': 500},
            }, 'requiresArtist': False,
            # 독립 fixture의 실제 12초 회색 영상이며, CD 데모를 재사용하지 않는다.
            'preview': {'status': 'ready', 'video': 'preview.mp4', 'poster': 'poster.jpg', 'captionStatus': 'fixture'},
        }
        value.update(changes)
        return value

    def add_custom(self):
        path = self.source / 'preset.json'; cd.write(path, self.spec())
        with patch.object(cd, 'PRESETS', self.library), patch.object(cd, 'catalog', return_value={'catalog': 'fixture'}):
            return cd.add(argparse.Namespace(spec=str(path)))

    def call(self, *args):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['playlist_presets.py', *args]), contextlib.redirect_stdout(output):
            self.assertEqual(cd.main(), 0)
        return cd.json.loads(output.getvalue())

    def test_add_show_and_two_song_create_uses_generic_contract(self):
        self.add_custom()
        with patch.object(cd, 'PRESETS', self.library):
            shown = self.call('show', '콜라주')
            self.assertEqual((shown['category'], shown['template']), ('motion-collage', 'collage-template'))
            listed = self.call('list')
            self.assertEqual(listed[0]['category'], 'motion-collage')
            self.assertTrue((self.library / 'motion-collage/collage-template/index.html').is_file())
            self.assertEqual(cd.read(self.library / 'motion-collage/verification.json'), {'status': 'fixture-media-checked'})

            tracks = []
            for index, duration in enumerate((6.001, 6.002)):
                audio = self.root / f'song-{index}.wav'
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'sine=frequency={440 + index * 110}:sample_rate=48000:duration={duration}', '-ac', '2', '-c:a', 'pcm_s16le', str(audio)], check=True)
                captions = self.root / f'song-{index}.json'
                cue = {'id': 1, 'startSeconds': .1, 'endSeconds': .6, 'text': f'가사 {index}'}
                if index == 0:
                    cue['words'] = [{'text': '가사', 'startSeconds': .1, 'endSeconds': .3}, {'text': '0', 'startSeconds': .3, 'endSeconds': .6}]
                cd.write(captions, {'schemaVersion': 1, 'status': 'fixture', 'source': {'sha256': cd.digest(audio)}, 'cues': [cue]})
                tracks.append({'path': audio.name, 'title': f'곡 {index}', 'captions': captions.name})
            playlist = self.root / 'playlist.json'; cd.write(playlist, {'schemaVersion': 1, 'tracks': tracks})
            output = self.root / 'project'
            result = cd.create(argparse.Namespace(plan=None, style='motion-collage', playlist=str(playlist), music=None, captions=None, instrumental=False, display=None, title=None, assets=None, demo_assets=True, start=0, duration=None, caption_origin=None, out=str(output)))
            self.assertEqual(result['trackCount'], 2)
            self.assertEqual(result['wordTiming'], {'cueCount': 2, 'timedCueCount': 1, 'timedUnitCount': 2})
            self.assertEqual(cd.read(output / 'production.json')['wordTiming'], result['wordTiming'])
            self.assertEqual([t['castingReview']['status'] for t in cd.read(output / 'playlist.json')['tracks']], ['not-applicable', 'not-applicable'])
            self.assertEqual(cd.read(output / 'script.json')['scenes'], [{'id': 'playlist', 'start': 0, 'end': 12.033333333333333}])
            config = (output / 'reel/config.js').read_text(encoding='utf-8')
            self.assertTrue(config.startswith('window.PLAYLIST_CONFIG='))
            self.assertTrue((output / 'reel/lyrics.js').read_text().startswith('window.PLAYLIST_LYRICS='))
            self.assertTrue((output / 'reel/spectrum.js').read_text().startswith('window.PLAYLIST_SPECTRUM='))
            self.assertEqual(set(cd.json.loads(config.removeprefix('window.PLAYLIST_CONFIG=').strip().removesuffix(';'))['assets']), {'portrait', 'background'})
            with self.assertRaisesRegex(ValueError, '비CD 프리셋'):
                cd.genre_plan('팝', style='motion-collage')

    def test_traversal_symlink_and_collision_leave_library_unchanged(self):
        path = self.source / 'preset.json'
        invalid = {'id': 'invalid-motion', 'name': '잘못된 콜라주', 'aliases': ['잘못됨']}
        cd.write(path, self.spec(template='../collage-template', **invalid))
        with patch.object(cd, 'PRESETS', self.library), patch.object(cd, 'catalog', return_value={}):
            with self.assertRaises(ValueError):
                cd.add(argparse.Namespace(spec=str(path)))
            self.assertFalse((self.library / 'invalid-motion').exists())
            linked = self.source / 'linked-template'; linked.symlink_to(self.template, target_is_directory=True)
            cd.write(path, self.spec(template='linked-template', **invalid))
            with self.assertRaisesRegex(ValueError, 'symlink'):
                cd.add(argparse.Namespace(spec=str(path)))
            self.assertFalse((self.library / 'invalid-motion').exists())
        if not (self.library / 'motion-collage').exists():
            cd.write(path, self.spec())
            self.add_custom()
        before = cd.digest(self.library / 'motion-collage/preset.json')
        with patch.object(cd, 'PRESETS', self.library), patch.object(cd, 'catalog', return_value={}):
            cd.write(path, self.spec())
            with self.assertRaisesRegex(ValueError, '충돌'):
                cd.add(argparse.Namespace(spec=str(path)))
        self.assertEqual(before, cd.digest(self.library / 'motion-collage/preset.json'))

    def test_custom_artist_check_uses_its_own_roles(self):
        schema = self.spec()['assetSchema']
        manifest = {'portrait': 'portrait.png', 'background': 'background.png', 'casting': {'vocal': 'female', 'act': 'solo', 'reviewed': True}}
        self.assertEqual(check_asset_casting(casting_spec('female', 'solo'), manifest, required_assets=tuple(schema))['status'], 'matched')
        with self.assertRaisesRegex(ValueError, 'assetSchema 역할'):
            cd.validate_preset(self.spec(requiresArtist=True, assetSchema={}))

    def test_rhythm_cd_track_motion_modes_reach_playlist_config(self):
        groove = cd.read(cd.PRESETS / 'autumn-archive/preset.json')
        groove.update({
            'id': 'groove-dial', 'name': '그루브 다이얼', 'aliases': ['그루브'],
            'category': 'rhythm-cd', 'template': 'groove-template', 'requiresArtist': True,
            'genrePlanner': 'cd-assets', 'motionMode': 'balanced', 'caption': {'font': 'sans', 'size': 66, 'effect': 'underline'},
            'assetSchema': {role: {'file': cd.NAMES[role], 'minSide': 500, 'alpha': role == 'case'} for role in cd.ASSETS},
        })
        source = self.root / 'groove-source'; source.mkdir()
        for role, name in cd.NAMES.items():
            if role == 'case':
                image = Image.new('RGBA', (640, 640), (0, 0, 0, 0))
                image.paste((68, 102, 136, 255), (64, 64, 576, 576))
            else:
                image = Image.new('RGB', (640, 640), '#446688')
            image.save(source / name)
        shutil.copytree(self.template, source / 'groove-template')
        original_select = cd.select

        def select(name):
            return (groove, source) if cd.key(name) == 'groovedial' else original_select(name)

        audio = self.root / 'groove-song.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=12.01', '-ac', '2', '-c:a', 'pcm_s16le', str(audio)], check=True)
        captions = self.root / 'groove-captions.json'
        cd.write(captions, {'schemaVersion': 1, 'source': {'sha256': cd.digest(audio)}, 'cues': [{'id': 1, 'startSeconds': .1, 'endSeconds': .9, 'text': '가사'}]})
        with patch.object(cd, 'select', side_effect=select):
            soft = cd.genre_plan('발라드', style='groove-dial')
            drive = cd.genre_plan('발라드', style='groove-dial', look={'motionMode': 'drive'})
            soft_path, drive_path = self.root / 'soft-plan.json', self.root / 'drive-plan.json'
            cd.write(soft_path, soft); cd.write(drive_path, drive)
            playlist = self.root / 'groove-playlist.json'
            cd.write(playlist, {'schemaVersion': 1, 'tracks': [
                {'path': audio.name, 'captions': captions.name, 'plan': soft_path.name},
                {'path': audio.name, 'captions': captions.name, 'plan': drive_path.name},
            ]})
            output = self.root / 'groove-project'
            cd.create(argparse.Namespace(plan=str(soft_path), style=None, playlist=str(playlist), music=None, captions=None, instrumental=False, display=None, title=None, assets=None, demo_assets=True, start=0, duration=None, caption_origin=None, out=str(output)))
        config = cd.json.loads((output / 'reel/config.js').read_text().removeprefix('window.PLAYLIST_CONFIG=').strip().removesuffix(';'))
        self.assertEqual([track['motionMode'] for track in config['playlist']['tracks']], ['soft', 'drive'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
