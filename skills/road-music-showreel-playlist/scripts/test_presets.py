#!/usr/bin/env python3
"""경계/시계/영구 등록 동작을 실제 임시 파일로 검증한다."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cd_presets as cd


class PresetChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix='cd-preset-check-')
        cls.base = Path(cls.scratch.name)
        cls.original = cd.PRESETS / 'autumn-archive'
        cls.spec = cd.read(cls.original / 'preset.json')
        cls.video = cls.base / 'fixture.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=640x360:r=30', '-t', '12', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video)], check=True)
        cls.poster = cls.base / 'poster.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(cls.video), '-frames:v', '1', str(cls.poster)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_aliases_and_missing_style(self):
        self.assertEqual(cd.select('빈 티 지')[0]['id'], 'autumn-archive')
        self.assertEqual(cd.select('NEON_AFTERHOURS')[0]['id'], 'neon-afterhours')
        with self.assertRaises(ValueError):
            cd.select('없는 스타일')

    def test_relative_caption_clock_and_cut_edges(self):
        original = {'source': {'cutStartSeconds': 79.76}, 'cues': [
            {'id': 1, 'startSeconds': 0, 'endSeconds': 5.76, 'text': '첫 문장'},
            {'id': 2, 'startSeconds': 5.76, 'endSeconds': 11.82, 'text': '둘째 문장'},
            {'id': 3, 'startSeconds': 11.82, 'endSeconds': 18.1, 'text': '셋째 문장'}]}
        saved = copy.deepcopy(original)
        cues, origin = cd.map_captions(original, 85.52, 12.517)
        self.assertEqual(original, saved)
        self.assertEqual(origin, 79.76)
        self.assertEqual([c['text'] for c in cues], ['둘째 문장', '셋째 문장'])
        self.assertEqual(cues[0]['startSeconds'], 0)
        self.assertEqual(cues[0]['endSeconds'], 6.06)
        self.assertEqual(cues[1]['startSeconds'], 6.06)

    def test_caption_clipping_preserves_text(self):
        doc = {'cues': [{'startSeconds': 2, 'endSeconds': 20, 'text': '원문 그대로'}]}
        cues, _ = cd.map_captions(doc, 3, 12)
        self.assertEqual(cues[0]['text'], '원문 그대로')
        self.assertEqual((cues[0]['startSeconds'], cues[0]['endSeconds']), (0, 12))
        self.assertTrue(cues[0]['clippedByPresentation'])

    def test_caption_words_follow_cut_clock_without_inventing_srt_words(self):
        doc = {'source': {'cutStartSeconds': 10}, 'cues': [{
            'startSeconds': 1, 'endSeconds': 5, 'text': '너 없는 계절',
            'words': [
                {'text': '너', 'startSeconds': 1.2, 'endSeconds': 1.8, 'source': 'asr'},
                {'text': '없는', 'startSeconds': 2, 'endSeconds': 3, 'source': 'asr'},
                {'text': '계절', 'startSeconds': 3, 'endSeconds': 4.8, 'source': 'asr'},
            ],
        }]}
        cues, _ = cd.map_captions(doc, 12.5, 2)
        self.assertEqual(cues[0]['text'], '너 없는 계절')
        self.assertEqual([(word['text'], word['startSeconds'], word['endSeconds']) for word in cues[0]['words']], [('없는', 0, .5), ('계절', .5, 2)])
        self.assertTrue(cues[0]['words'][0]['clippedByPresentation'])
        srt_path = self.base / 'line-only.srt'
        srt_path.write_text('1\n00:00:01,000 --> 00:00:02,000\n원문 그대로\n', encoding='utf-8')
        self.assertNotIn('words', cd.load_captions(srt_path)['cues'][0])

    def test_caption_words_reject_bad_timing_or_text(self):
        base = {'startSeconds': 0, 'endSeconds': 3, 'text': '너 없는', 'words': [
            {'text': '너', 'startSeconds': .1, 'endSeconds': 1},
            {'text': '없는', 'startSeconds': 1, 'endSeconds': 2.5},
        ]}
        bad = [
            dict(base, words=[{'text': '너', 'startSeconds': .1, 'endSeconds': 1}, {'text': '없어', 'startSeconds': 1, 'endSeconds': 2}]),
            dict(base, words=[{'text': '너', 'startSeconds': .1, 'endSeconds': 1.5}, {'text': '없는', 'startSeconds': 1.4, 'endSeconds': 2.5}]),
            dict(base, words=[{'text': '너', 'startSeconds': -.1, 'endSeconds': 1}, {'text': '없는', 'startSeconds': 1, 'endSeconds': 2.5}]),
        ]
        for cue in bad:
            with self.subTest(cue=cue), self.assertRaisesRegex(ValueError, '어절'):
                cd.map_captions({'cues': [cue]}, 0, 3)

    def test_caption_failures(self):
        bad = [
            [{'startSeconds': float('nan'), 'endSeconds': 2, 'text': '가'}],
            [{'startSeconds': 3, 'endSeconds': 2, 'text': '가'}],
            [{'startSeconds': 0, 'endSeconds': 3, 'text': '가'}, {'startSeconds': 2, 'endSeconds': 5, 'text': '나'}],
            [{'startSeconds': 0, 'endSeconds': 2, 'text': ' '}],
            [{'startSeconds': 0, 'endSeconds': 2, 'text': '가\n나'}]]
        for cues in bad:
            with self.subTest(cues=cues), self.assertRaises(ValueError):
                cd.map_captions({'cues': cues}, 0, 12)

    def test_srt_clock_roundtrip(self):
        self.assertEqual(cd.srt([]), '')
        self.assertEqual(cd.stamp(59.9996), '00:01:00,000')
        self.assertEqual(cd.stamp(3599.9996), '01:00:00,000')
        path = self.base / 'timing.srt'
        cues = [{'startSeconds': 1.234, 'endSeconds': 3.789, 'text': '가사 원문'}]
        path.write_text(cd.srt(cues), encoding='utf-8')
        self.assertEqual(cd.load_captions(path)['cues'][0]['text'], '가사 원문')
        self.assertEqual(cd.load_captions(path)['cues'][0]['startSeconds'], 1.234)

    def test_invalid_preset(self):
        for changes in [{'id': '../escape'}, {'variant': 'fake'}, {'discPeriodSeconds': 0}, {'caption': {'font': 'sans', 'size': 200, 'effect': 'glow'}}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cd.validate_preset(dict(self.spec, **changes))

    def test_rhythm_cd_genre_planner_accepts_cd_assets_and_motion_mode(self):
        groove = copy.deepcopy(self.spec)
        groove.update({
            'id': 'groove-dial', 'name': '그루브 다이얼', 'aliases': ['그루브'],
            'category': 'rhythm-cd', 'template': 'template', 'requiresArtist': True, 'genrePlanner': 'cd-assets',
            'assetSchema': {role: {'file': cd.NAMES[role], 'minSide': 500, 'alpha': role == 'case'} for role in cd.ASSETS},
            'motionMode': 'balanced', 'caption': {'font': 'sans', 'size': 66, 'effect': 'underline'},
        })
        original_select = cd.select

        def select(name):
            return (groove, self.base) if cd.key(name) == 'groovedial' else original_select(name)

        with patch.object(cd, 'select', side_effect=select):
            plan = cd.genre_plan('발라드', style='groove-dial')
            self.assertEqual(plan['effectivePreset']['motionMode'], 'soft')
            self.assertEqual(plan['effectivePreset']['caption'], groove['caption'])
            self.assertEqual(set(plan['imageGeneration']['assets']), set(cd.ASSETS))
            override = cd.genre_plan('발라드', style='groove-dial', look={'motionMode': 'drive', 'caption': {'size': 70}})
            self.assertEqual(override['effectivePreset']['motionMode'], 'drive')
            self.assertEqual(override['effectivePreset']['caption'], {'font': 'sans', 'size': 70, 'effect': 'underline'})
            kpop = cd.genre_plan('K-POP', style='groove-dial')
            self.assertEqual(kpop['effectivePreset']['variant'], 'prism')
            self.assertIn('factory-new crystal-clear', kpop['imageGeneration']['assets']['case']['prompt'])
            self.assertNotIn('살짝 닳고', kpop['imageGeneration']['assets']['case']['prompt'])
            self.assertNotIn('worn square', kpop['imageGeneration']['assets']['case']['prompt'])
            prism = cd.genre_plan('발라드', style='groove-dial', look={'variant': 'prism'})
            self.assertIn('factory-new crystal-clear', prism['imageGeneration']['assets']['case']['prompt'])
            self.assertNotIn('살짝 닳고', prism['imageGeneration']['assets']['case']['prompt'])
        broken = copy.deepcopy(groove)
        broken['assetSchema'].pop('paper')
        with self.assertRaisesRegex(ValueError, 'genrePlanner'):
            cd.validate_preset(broken)
        broken = copy.deepcopy(groove)
        broken['caption']['effect'] = 'glow'
        with self.assertRaisesRegex(ValueError, 'Paperlogy'):
            cd.validate_preset(broken)

    def test_core_genres_and_english_aliases(self):
        for genre in ['트로트', '트롯', '발라드', '락발라드', 'R & B', 'RnB', '재즈', '팝']:
            with self.subTest(genre=genre):
                plan = cd.genre_plan(genre)
                self.assertTrue(plan['genre']['matched'])
                self.assertEqual(plan['imageGeneration']['requiredTool'], 'image_gen')
                self.assertEqual(set(plan['imageGeneration']['assets']), set(cd.ASSETS))
        self.assertEqual(cd.genre_plan('락발라드')['genre']['matched'][0]['id'], 'rock-ballad')
        self.assertNotEqual(cd.genre_plan('funk')['genre']['matched'], cd.genre_plan('punk rock')['genre']['matched'])

    def test_all_profile_aliases_resolve_to_their_own_family(self):
        profiles = cd.load_genres()
        for profile in profiles:
            for name in [profile['id'], profile['name'], *profile['aliases']]:
                with self.subTest(name=name):
                    matched, unknown = cd.resolve_genres(name, profiles)
                    self.assertEqual([p['id'] for p in matched], [profile['id']])
                    self.assertEqual(unknown, [])

    def test_creation_rejects_plan_or_caption_conflicts_before_writing(self):
        args = cd.argparse.Namespace(plan=None, style='가을', instrumental=False, captions=None)
        with self.assertRaisesRegex(ValueError, '보컬 곡'):
            cd.create(args)
        args.instrumental, args.captions = True, 'some-captions.json'
        with self.assertRaisesRegex(ValueError, '연주곡'):
            cd.create(args)
        plan = cd.genre_plan('트로트')
        path = self.base / 'conflict-plan.json'
        cd.write(path, plan)
        args.plan, args.style, args.instrumental, args.captions = str(path), '네온', False, None
        with self.assertRaisesRegex(ValueError, '스타일 불일치'):
            cd.create(args)
        plan['instrumental'] = 'false'
        cd.write(path, plan)
        with self.assertRaisesRegex(ValueError, '장르 계획'):
            cd.create(args)

    def test_mixed_and_unlisted_genres_preserve_request(self):
        plan = cd.genre_plan('트로트 + R&B', brief='차분한 밤, 무대 조명은 청록색', artist='가상의 성인 듀오')
        self.assertEqual(len(plan['genre']['matched']), 2)
        self.assertIn('차분한 밤', plan['imageGeneration']['assets']['photoA']['prompt'])
        self.assertIn('가상의 성인 듀오', plan['imageGeneration']['assets']['photoA']['prompt'])
        custom = cd.genre_plan('미분류 우주 폴카', brief='손으로 접은 은빛 종이, 부드러운 공연 사진')
        self.assertEqual(custom['genre']['input'], '미분류 우주 폴카')
        self.assertEqual(custom['genre']['mode'], 'custom')
        self.assertIn('은빛 종이', custom['imageGeneration']['assets']['paper']['prompt'])

    def test_genre_settings_apply_and_explicit_style_wins(self):
        plan = cd.genre_plan('트로트')
        primary = next(p for p in cd.load_genres() if p['id'] == plan['genre']['matched'][0]['id'])
        self.assertEqual(plan['effectivePreset']['palette'], primary['visual']['palette'])
        explicit = cd.genre_plan('트로트', style='누아르')
        self.assertEqual(explicit['effectivePreset']['palette'], cd.select('누아르')[0]['palette'])
        self.assertTrue(explicit['selection']['explicitStyle'])
        prompts = ' '.join(a['prompt'] for a in explicit['imageGeneration']['assets'].values())
        self.assertIn('Black-and-white', prompts)
        self.assertNotIn('35mm 컬러', prompts)
        mixed = cd.genre_plan('트로트 + R&B', style='누아르')
        mixed_prompts = ' '.join(a['prompt'] for a in mixed['imageGeneration']['assets'].values())
        self.assertNotIn('보라·시안', mixed_prompts)

    def test_custom_material_changes_prompt_and_render_palette_together(self):
        look = {'palette': {'paper': '#E5E6E8', 'ink': '#25303A', 'accent': '#8A949C'}, 'paperDirection': '구겨진 은빛 종이와 무광 은박'}
        plan = cd.genre_plan('미등록 장르 XYZ-77', brief='은빛 종이', style='로파이', look=look)
        self.assertEqual(plan['effectivePreset']['palette']['paper'], '#E5E6E8')
        self.assertIn('무광 은박', plan['imageGeneration']['assets']['paper']['prompt'])
        for asset in plan['imageGeneration']['assets'].values():
            self.assertIn('#E5E6E8', asset['prompt'])
        self.assertEqual(cd.select('로파이')[0]['palette']['paper'], '#e9e5df')
        with self.assertRaises(ValueError):
            cd.genre_plan('팝', look={'palette': {'paper': 'bad-color'}})
        with self.assertRaises(ValueError):
            cd.genre_plan('팝', look=[])

    def test_instrumental_plan_and_invalid_genre(self):
        plan = cd.genre_plan('클래식', instrumental=True, artist='가상의 성인 현악 연주자 네 명')
        self.assertTrue(plan['instrumental'])
        self.assertFalse(plan['captions']['required'])
        self.assertIn('No singer', plan['imageGeneration']['assets']['photoA']['prompt'])
        with self.assertRaises(ValueError):
            cd.genre_plan(' ')

    def test_genre_catalog_uses_existing_previews(self):
        path = self.base / 'genre-catalog.html'
        cd.catalog(path)
        page = path.read_text()
        self.assertIn('genre-select', page)
        self.assertIn('트로트', page)
        self.assertIn('data-road-music-ui', page)
        self.assertIn('road-music-design/styles.css', page)
        self.assertTrue((path.parent / 'road-music-design' / 'fonts' / 'Paperlogy-4Regular.ttf').is_file())
        self.assertEqual(page.count('<video '), sum(s.get('preview', {}).get('status') == 'ready' for s, _ in cd.registry()))

    def test_rhythm_cd_catalog_uses_early_cd_button_and_escaped_audio_note(self):
        groove = copy.deepcopy(self.spec)
        groove.update({
            'id': 'groove-dial', 'name': '그루브 다이얼', 'aliases': ['그루브'],
            'category': 'rhythm-cd', 'template': 'template', 'requiresArtist': True, 'genrePlanner': 'cd-assets',
            'assetSchema': {role: {'file': cd.NAMES[role], 'minSide': 500, 'alpha': role == 'case'} for role in cd.ASSETS},
            'motionMode': 'balanced', 'caption': {'font': 'sans', 'size': 66, 'effect': 'underline'},
            'genres': ['K-POP'],
            'preview': {'status': 'pending', 'audioNote': '같은 곡 <DEMO & CHANNEL> 15초 두 구간'},
        })
        path = self.base / 'groove-catalog.html'
        entries = cd.registry()
        with patch.object(cd, 'registry', return_value=[*entries, (groove, self.base)]):
            cd.catalog(path)
        page = path.read_text()
        self.assertIn('data-time="6.5"', page)
        self.assertIn('같은 곡 &lt;DEMO &amp; CHANNEL&gt; 15초 두 구간', page)
        self.assertNotIn('같은 곡 <DEMO & CHANNEL> 15초 두 구간', page)
        self.assertIn('search.value=e.target.value||\'\';', page)
        self.assertIn('음악 장르별 제작 방향', page)
        self.assertIn('id="genre-request" role="status" aria-live="polite"', page)
        for name in ('크롬 프리즘', '그루브 다이얼'):
            end = page.index(f'<h2>{name}</h2>')
            start = page.rfind('<article data-search="', 0, end)
            self.assertIn('K-POP', page[start:end])

    def test_modern_kpop_plan_and_explicit_vintage_override(self):
        modern = cd.genre_plan('K-POP', vocal='female', act='solo')
        self.assertEqual(modern['basePresetId'], 'chrome-prism')
        self.assertEqual(modern['effectivePreset']['variant'], 'prism')
        self.assertIn('factory-new', modern['imageGeneration']['assets']['case']['prompt'])
        self.assertIn('pearl-acrylic', modern['imageGeneration']['assets']['paper']['prompt'])
        self.assertNotIn('worn square', modern['imageGeneration']['assets']['case']['prompt'])
        self.assertNotIn('analog grain', modern['imageGeneration']['assets']['photoA']['prompt'])
        self.assertEqual(cd.select('샤이니')[0]['id'], 'chrome-prism')
        vintage = cd.genre_plan('케이팝', vocal='male', act='band', style='가을')
        self.assertEqual(vintage['effectivePreset']['variant'], 'archive')
        self.assertIn('a worn square', vintage['imageGeneration']['assets']['case']['prompt'])

    def test_registration_persists_and_collisions_do_not_mutate(self):
        library = self.base / 'library'
        library.mkdir()
        spec = copy.deepcopy(self.spec)
        spec.update(id='dawn-tape', name='새벽 테이프', aliases=['새벽'], referenceAssets={role: str(self.original / cd.NAMES[role]) for role in cd.ASSETS})
        spec['preview'] = {'status': 'ready', 'video': str(self.video), 'poster': str(self.poster), 'captionStatus': 'test-fixture'}
        input_path = self.base / 'new.json'
        cd.write(input_path, spec)
        with patch.object(cd, 'PRESETS', library), patch.object(cd, 'catalog', return_value={'catalog': 'test'}):
            result = cd.add(type('Args', (), {'spec': str(input_path)})())
            self.assertEqual(result['registered'], 'dawn-tape')
            self.assertEqual(cd.select('새벽')[0]['name'], '새벽 테이프')
            self.assertTrue((library / 'dawn-tape/preview.mp4').is_file())
            before = cd.digest(library / 'dawn-tape/preset.json')
            with self.assertRaises(ValueError):
                cd.add(type('Args', (), {'spec': str(input_path)})())
            self.assertEqual(before, cd.digest(library / 'dawn-tape/preset.json'))
            spec.update(id='another-dawn', name='다른 새벽', aliases=['새 벽'])
            cd.write(input_path, spec)
            with self.assertRaises(ValueError):
                cd.add(type('Args', (), {'spec': str(input_path)})())
            self.assertFalse((library / 'another-dawn').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
