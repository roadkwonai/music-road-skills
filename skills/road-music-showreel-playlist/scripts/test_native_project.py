#!/usr/bin/env python3
"""Observable contracts for the native, non-preset project helper."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave


SCRIPT = Path(__file__).with_name("native_project.py")
SPEC = importlib.util.spec_from_file_location("native_project", SCRIPT)
native = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(native)


class NativeProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.music = self.root / "song.wav"
        self._wav(self.music, 2.1)
        self.display = self.root / "display.json"
        self.display.write_text(json.dumps({"showSpectrum": "SKIP", "showQueue": False, "showNowPlaying": True, "channelName": "SKIP"}), encoding="utf-8")
        self.build_runtime = native._build_runtime
        native._build_runtime = self._fake_runtime

    def tearDown(self):
        native._build_runtime = self.build_runtime
        self.temp.cleanup()

    def _fake_runtime(self, project, duration):
        """The upstream renderer is outside unit scope; FFmpeg preparation remains real."""
        project = Path(project)
        (project / "reel").mkdir(exist_ok=True)
        for name in ("index.html", "film-runtime.js", "scenes.js"):
            (project / "reel" / name).write_text("// fixture\n", encoding="utf-8")
        __import__("shutil").copy2(project / "audio/music/music.wav", project / "audio/mix.wav")
        native.write_json(project / "audio/music/analysis.json", {"hits": [], "energy": []})
        native.write_json(project / "script.json", {"duration": duration, "fps": 30})
        native.write_json(project / "timeline.json", {"duration": duration, "fps": 30, "scenes": []})

    def _wav(self, path, seconds, frequency=220):
        # A tiny valid fixture; helpers must use actual FFmpeg/PCM boundaries.
        import math
        frames = int(seconds * 48_000)
        with wave.open(str(path), "wb") as out:
            out.setparams((2, 2, 48_000, 0, "NONE", "not compressed"))
            out.writeframes(b"".join(int(7000 * math.sin(2 * math.pi * frequency * i / 48_000)).to_bytes(2, "little", signed=True) * 2 for i in range(frames)))

    def test_prepare_instrumental_single_track_preserves_input_and_has_empty_scenes(self):
        before = self.music.read_bytes()
        out = self.root / "native"
        result = native.prepare(music=str(self.music), captions=None, instrumental=True, display=str(self.display), out=str(out), title="무가사")
        self.assertEqual(self.music.read_bytes(), before)
        self.assertEqual(result["mode"], "native-composition")
        self.assertEqual(native.read_json(out / "composition.json")["tracks"], [])
        playlist = native.read_json(out / "playlist.json")
        self.assertEqual(playlist["tracks"][0]["instrumental"], True)
        self.assertEqual(native.read_json(out / "production.json")["mode"], "native-composition")
        self.assertFalse((out / "reel/film-plan.js").read_text(encoding="utf-8").strip().endswith("{};"))

    def test_prepare_preserves_caption_status_original_paths_and_caption_document(self):
        captions = self.root / "captions.json"
        captions.write_text(json.dumps({"schemaVersion": 1, "status": "auto-asr-unreviewed", "source": {"sha256": native.sha256(self.music)}, "cues": [{"id": "line-1", "startSeconds": 0, "endSeconds": 1, "text": "원문"}]}), encoding="utf-8")
        out = self.root / "captions-native"
        native.prepare(music=str(self.music), captions=str(captions), display=str(self.display), out=str(out))
        record = native.read_json(out / "playlist.json")["tracks"][0]
        self.assertEqual(record["captionStatus"], "auto-asr-unreviewed")
        self.assertEqual(record["source"]["originalPath"], str(self.music.resolve()))
        self.assertEqual(record["inputTiming"]["originalPath"], str(captions.resolve()))
        copied = native.read_json(out / "captions/lyrics.json")
        self.assertEqual(copied["status"], "auto-asr-unreviewed")
        self.assertEqual(copied["cues"][0]["id"], "line-1")

    def test_prepare_preserves_two_line_caption_through_frozen_native_inputs(self):
        captions = self.root / "captions.srt"
        captions.write_text("1\n00:00:00,000 --> 00:00:01,000\n첫 줄\n둘째 줄\n", encoding="utf-8")
        out = self.root / "captions-multiline"
        native.prepare(music=str(self.music), captions=str(captions), display=str(self.display), out=str(out))
        expected = "첫 줄\n둘째 줄"
        self.assertEqual(native.read_json(out / "captions/lyrics.json")["cues"][0]["text"], expected)
        self.assertIn(expected, (out / "captions/lyrics.srt").read_text(encoding="utf-8"))
        self.assertEqual(native._read_global(out / "reel/film-input.js", "FILM_INPUT")["captions"]["cues"][0]["text"], expected)

    def test_single_playlist_keeps_prefixed_multiline_caption_clock_for_check(self):
        captions = self.root / "playlist-captions.srt"
        captions.write_text("1\n00:00:00,000 --> 00:00:01,000\n첫 줄\n둘째 줄\n", encoding="utf-8")
        playlist = self.root / "one-playlist.json"
        playlist.write_text(json.dumps({"schemaVersion": 1, "tracks": [{"path": str(self.music), "captions": str(captions), "captionOriginSeconds": .5}]}), encoding="utf-8")
        out = self.root / "one-playlist"
        native.prepare(playlist=str(playlist), display=str(self.display), out=str(out))
        self.assertEqual(native.read_json(out / "captions/lyrics.json")["cues"][0]["id"], "track-001:1")
        plan = native.read_json(self._full_plan(assets=[]))
        plan['tracks'][0]['scenes'][0].update(startSeconds=0, endSeconds=2.1, lyricCueIds=['1'])
        native.write_json(self.root / 'one-plan.json', plan)
        native.apply(project=str(out), composition=str(self.root / 'one-plan.json'), media=None)
        self.assertTrue(native.check(project=str(out))["prepared"])

    def test_check_binds_all_serialized_input_and_media_plan_to_canonical_documents(self):
        project = self._prepared_cut_project()
        native.apply(project=str(project), composition=str(self._full_plan(assets=[])))
        self.assertTrue(native.check(project=str(project))['prepared'])
        input_path = project / 'reel/film-input.js'
        original = native._read_global(input_path, 'FILM_INPUT')
        import copy
        for key, value in [('playlist', {'tracks': []}), ('display', {}), ('spectrum', {'frames': [[17]]}), ('duration', 2.0), ('audio', '../other.wav')]:
            changed = copy.deepcopy(original); changed[key] = value
            native._write_text(input_path, 'window.FILM_INPUT = ' + json.dumps(changed) + ';\n')
            with self.subTest(key=key), self.assertRaises(ValueError): native.check(project=str(project))
        native._write_text(input_path, 'window.FILM_INPUT = ' + json.dumps(original) + ';\n')
        plan_path = project / 'reel/film-plan.js'
        original_plan = native._read_global(plan_path, 'FILM_PLAN')
        for key, value in [('media', [{'id':'unknown','src':'../other.png'}]), ('opening', {'thumbnailId':'unknown','seconds':.5})]:
            changed = copy.deepcopy(original_plan); changed[key] = value
            native._write_text(plan_path, 'window.FILM_PLAN = ' + json.dumps(changed) + ';\n')
            with self.subTest(key=key), self.assertRaises(ValueError): native.check(project=str(project))
        changed = copy.deepcopy(original_plan); changed['scenes'][0]['assets'] = ['unknown']
        native._write_text(plan_path, 'window.FILM_PLAN = ' + json.dumps(changed) + ';\n')
        with self.assertRaises(ValueError): native.check(project=str(project))

    def test_finalize_requires_receipt_and_exact_output_before_accepting_review(self):
        project = self._prepared_cut_project()
        native.apply(project=str(project), composition=str(self._full_plan(assets=[])))
        prepared = native.check(project=str(project))
        files = prepared['files']
        native.write_json(project / 'qa/native-runtime.json', {'pass':True,'files':files,'sceneBindings':prepared['scenes'], 'registeredScenes':[{'id':s['id'],'startSeconds':s['startSeconds'],'endSeconds':s['endSeconds']} for s in prepared['scenes']]})
        evidence = project / 'qa/seen.txt'; evidence.write_text('actually reviewed fixture')
        native.write_json(project / 'qa/creative-review.json', {'schemaVersion':1,'files':files,'scenes':[{'id':s['id'],'decision':'keep','note':'fixture review','evidence':['qa/seen.txt']} for s in prepared['scenes']]})
        (project / 'out').mkdir(); (project / 'out/test.mp4').write_bytes(b'fake old output')
        native.write_json(project / 'qa/test-motion.json', {'issues':[]})
        with self.assertRaises((ValueError,FileNotFoundError)): native.finalize(project=str(project), name='test')
        for suffix in ('_공유용.mp4', '_포스터.jpg', '.srt'):
            (project / ('out/test' + suffix)).write_bytes(b'fixture')
        report = project / 'qa/test-qa-report.md'; report.write_text('## 자동 검사 통과\n')
        receipt = {'schemaVersion':1,'name':'test','draft':False,'files':files,'checks':{'fixture':True},
                   'outputs':{str(p.relative_to(project)):native.sha256(p) for p in (project/'out').iterdir()},
                   'qaReports':{str(p.relative_to(project)):native.sha256(p) for p in (report,project/'qa/test-motion.json')}}
        native.write_json(project / 'qa/test-render.json', receipt)
        self.assertEqual(native.finalize(project=str(project),name='test')['status'], 'finalized')
        video = project/'out/test.mp4'; video.write_bytes(b'changed output')
        with self.assertRaises(ValueError): native.finalize(project=str(project), name='test')
        video.write_bytes(b'fake old output')
        native.write_json(project/'qa/test-motion.json', {'issues':['p90=2.1']})
        report.write_text('## 고칠 것\n- [ ] p90=2.1\n')
        receipt['qaReports']={str(p.relative_to(project)):native.sha256(p) for p in (report,project/'qa/test-motion.json')}
        native.write_json(project/'qa/test-render.json',receipt)
        with self.assertRaises(ValueError): native.finalize(project=str(project),name='test')
        review=native.read_json(project/'qa/creative-review.json')
        review['motionReview']={'issues':['p90=2.1'],'reason':'음악의 잔향에서 의도한 정착','evidence':['qa/seen.txt'],'motionReportSha256':native.sha256(project/'qa/test-motion.json'),'finalOutputSha256':native.sha256(video)}
        native.write_json(project/'qa/creative-review.json',review)
        self.assertTrue(native.finalize(project=str(project),name='test')['motionReviewed'])
        report.write_text('## 고칠 것\n- [ ] 과도한 어두운 구간\n')
        receipt['qaReports']['qa/test-qa-report.md']=native.sha256(report)
        native.write_json(project/'qa/test-render.json',receipt)
        with self.assertRaises(ValueError): native.finalize(project=str(project),name='test')

    def test_check_rejects_changed_mix_pcm_frozen_captions_or_serialized_captions(self):
        project = self._prepared_cut_project()
        for relative in ("audio/mix.wav", "audio/music/music.wav", "inputs/captions/track-001.srt", "captions/lyrics.json"):
            with self.subTest(relative=relative):
                target = project / relative
                target.write_bytes(target.read_bytes() + b"changed")
                with self.assertRaises(ValueError): native.check(project=str(project))
                # Each subtest needs its own prepared project because the mutation is intentional.
                project = self._prepared_cut_project()

    def test_check_rejects_stored_media_hash_dimensions_or_alpha_change(self):
        project = self._prepared_cut_project()
        image = self.root / "asset.png"
        from PIL import Image
        asset = Image.new("RGBA", (16, 16), (20, 30, 40, 255)); asset.putpixel((0, 0), (20, 30, 40, 0)); asset.save(image)
        media = self.root / "media.json"
        media.write_text(json.dumps({"schemaVersion": 1, "assets": [{"id": "ticket", "path": str(image), "roles": ["object"], "requireAlpha": True, "source": {"kind": "provided"}}]}), encoding="utf-8")
        native.apply(project=str(project), composition=str(self._full_plan(assets=["ticket"])), media=str(media))
        Image.new("RGBA", (16, 16), (20, 30, 40, 255)).save(project / "assets/media/ticket.png")
        with self.assertRaises(ValueError): native.check(project=str(project))

    def test_check_rejects_film_plan_or_timeline_scene_binding_mismatch(self):
        project = self._prepared_cut_project()
        native.apply(project=str(project), composition=str(self._full_plan(assets=[])), media=None)
        plan = native._read_global(project / "reel/film-plan.js", "FILM_PLAN")
        plan["scenes"][0]["sourceStartSeconds"] += .1
        native._write_text(project / "reel/film-plan.js", "window.FILM_PLAN = " + json.dumps(plan) + ";\n")
        with self.assertRaises(ValueError): native.check(project=str(project))

    def test_display_requires_all_four_answers_and_never_reuses_existing_output(self):
        incomplete = self.root / "incomplete.json"
        incomplete.write_text('{"showSpectrum": true}', encoding="utf-8")
        out = self.root / "protected"
        out.mkdir()
        marker = out / "keep"
        marker.write_text("preserve", encoding="utf-8")
        with self.assertRaises(ValueError):
            native.prepare(music=str(self.music), captions=None, instrumental=True, display=str(incomplete), out=str(out))
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_apply_maps_source_clock_cut_and_keeps_original_origin(self):
        project = self._prepared_cut_project()
        plan = self.root / "plan.json"
        plan.write_text(json.dumps({"schemaVersion": 1, "concept": "밤의 표", "tracks": [{"id": "track-001", "sourceSha256": native.sha256(self.music), "scenes": [{"id": "first", "startSeconds": 0, "endSeconds": 1, "lyricCueIds": ["1"], "meaning": "첫 문장", "subject": "표", "action": "접힌다", "medium": "종이", "composition": "정면", "transition": "겹친다", "assets": []}, {"id": "last", "startSeconds": 1, "endSeconds": 2.1, "lyricCueIds": ["2"], "meaning": "둘째 문장", "subject": "표", "action": "펴진다", "medium": "종이", "composition": "측면", "transition": "끝", "assets": []}]}]}, ensure_ascii=False), encoding="utf-8")
        native.apply(project=str(project), composition=str(plan), media=None)
        scene = native.read_json(project / "composition.json")["tracks"][0]["scenes"][0]
        self.assertEqual(scene["originStartSeconds"], 0)
        self.assertEqual(scene["originEndSeconds"], 1)
        self.assertEqual(scene["sourceStartSeconds"], 0.5)
        self.assertEqual(scene["startSeconds"], 0)
        self.assertEqual(scene["endSeconds"], 0.5)
        timeline = native.read_json(project / "timeline.json")
        self.assertEqual(timeline["scenes"][0]["id"], "track-001.first")
        self.assertIn("scene.track-001.first", timeline["cues"])

    def test_apply_rejects_bad_hash_gap_unknown_cue_without_mutating_plan(self):
        project = self._prepared_cut_project()
        good = {"schemaVersion": 1, "concept": "x", "tracks": [{"id": "track-001", "sourceSha256": "0" * 64, "scenes": []}]}
        path = self.root / "bad.json"
        path.write_text(json.dumps(good), encoding="utf-8")
        with self.assertRaises(ValueError): native.apply(project=str(project), composition=str(path), media=None)
        self.assertEqual(native.read_json(project / "composition.json")["tracks"], [])

    def test_open_media_roles_same_art_are_allowed_but_decode_alpha_and_reference_are_checked(self):
        project = self._prepared_cut_project()
        image = self.root / "asset.png"
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow unavailable")
        image_data = Image.new("RGBA", (16, 16), (20, 30, 40, 255))
        image_data.putpixel((0, 0), (20, 30, 40, 0))
        image_data.save(image)
        media = self.root / "media.json"
        media.write_text(json.dumps({"schemaVersion": 1, "assets": [{"id": "ticket", "path": str(image), "roles": ["scene-object", "fold-surface"], "requireAlpha": True, "source": {"kind": "provided"}}]}), encoding="utf-8")
        plan = self._full_plan(assets=["ticket"])
        native.apply(project=str(project), composition=str(plan), media=str(media))
        self.assertTrue((project / "assets/media/ticket.png").is_file())
        self.assertIn("ticket", native.read_json(project / "assets/media.json")["assets"])

    def test_media_rejects_bad_decode_missing_reference_and_opaque_alpha(self):
        project = self._prepared_cut_project()
        broken = self.root / "broken.png"
        broken.write_bytes(b"not an image")
        manifest = self.root / "broken-media.json"
        manifest.write_text(json.dumps({"schemaVersion": 1, "assets": [{"id": "bad", "path": str(broken), "roles": ["unrestricted-role"], "source": {"kind": "reuse"}}]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            native._read_media(manifest, project)
        plan = self._full_plan(assets=["missing"])
        with self.assertRaises(ValueError):
            native.apply(project=str(project), composition=str(plan), media=None)

    def test_require_alpha_is_a_real_bool_and_scene_assets_are_safe(self):
        project = self._prepared_cut_project()
        image = self.root / "alpha.png"
        from PIL import Image
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(image)
        manifest = self.root / "bad-alpha.json"
        manifest.write_text(json.dumps({"schemaVersion": 1, "assets": [{"id": "ticket", "path": str(image), "roles": ["object"], "requireAlpha": 1, "source": {"kind": "provided"}}]}), encoding="utf-8")
        with self.assertRaises(ValueError): native._read_media(manifest, project)
        plan = native.read_json(self._full_plan(assets=[]))
        plan["tracks"][0]["scenes"][0]["assets"] = [["unhashable"]]
        bad = self.root / "unhashable.json"; bad.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaises(ValueError): native.apply(project=str(project), composition=str(bad), media=None)

    def test_fingerprint_excludes_qa_and_out_and_render_requires_fresh_runtime(self):
        project = self._prepared_cut_project()
        (project / "qa").mkdir(exist_ok=True); (project / "out").mkdir(exist_ok=True)
        initial = native.fingerprint(str(project))
        (project / "qa/ignore").write_text("x", encoding="utf-8")
        (project / "out/ignore").write_text("x", encoding="utf-8")
        self.assertEqual(initial, native.fingerprint(str(project)))
        with self.assertRaises(ValueError): native.render(project=str(project), draft=True, name="preview")

    def test_two_non_integer_pcm_tracks_keep_sample_boundary_and_input_clocks(self):
        second = self.root / "second.wav"
        self._wav(second, 1.027, 330)
        playlist = self.root / "playlist.json"
        playlist.write_text(json.dumps({"schemaVersion": 1, "tracks": [{"path": str(self.music), "instrumental": True}, {"path": str(second), "instrumental": True}]}), encoding="utf-8")
        out = self.root / "two"
        native.prepare(playlist=str(playlist), display=str(self.display), out=str(out))
        tracks = native.read_json(out / "playlist.json")["tracks"]
        self.assertEqual(tracks[0]["endSample"], tracks[1]["startSample"])
        self.assertEqual(tracks[0]["source"]["cutStartSeconds"], 0)
        self.assertEqual(tracks[1]["source"]["cutStartSeconds"], 0)

    def test_gap_and_unknown_cue_are_rejected(self):
        project = self._prepared_cut_project()
        for mutation in ("gap", "cue"):
            plan = {"schemaVersion": 1, "concept": "x", "tracks": [{"id": "track-001", "sourceSha256": native.sha256(self.music), "scenes": [{"id": "one", "startSeconds": .5, "endSeconds": 1.5, "lyricCueIds": ["1"], "meaning": "x", "subject": "x", "action": "x", "medium": "same", "composition": "x", "transition": "x", "assets": []}]}]}
            if mutation == "gap": plan["tracks"][0]["scenes"][0]["startSeconds"] = .6
            else: plan["tracks"][0]["scenes"][0]["lyricCueIds"] = ["missing"]
            path = self.root / (mutation + ".json")
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                native.apply(project=str(project), composition=str(path), media=None)

    def test_final_rejects_prepared_blank_scenes_and_stale_creative_evidence(self):
        project = self._prepared_cut_project()
        fp = native.fingerprint(str(project))
        qa = project / "qa"; qa.mkdir(exist_ok=True)
        native.write_json(qa / "native-runtime.json", {"pass": True, "files": fp})
        with self.assertRaises(ValueError): native.render(project=str(project), draft=False, name="final")

    def test_final_rejects_stale_creative_evidence_after_scene_apply(self):
        project = self._prepared_cut_project()
        native.apply(project=str(project), composition=str(self._full_plan(assets=[])), media=None)
        qa = project / "qa"; qa.mkdir(exist_ok=True)
        fp = native.fingerprint(str(project))
        native.write_json(qa / "native-runtime.json", {"pass": True, "files": fp})
        native.write_json(qa / "creative-review.json", {"schemaVersion": 1, "files": {}, "scenes": [], "limitations": []})
        with self.assertRaises(ValueError): native.render(project=str(project), draft=False, name="final")

    def test_preview_padding_keeps_original_scene_span(self):
        project = self._prepared_cut_project()
        production = native.read_json(project / "production.json")
        production["renderDurationSeconds"] = 1.02
        production["expectedFrames"] = 31
        native.write_json(project / "production.json", production)
        native.apply(project=str(project), composition=str(self._full_plan(assets=[])), media=None)
        scene = native.read_json(project / "composition.json")["scenes"][0]
        self.assertEqual(scene["originStartSeconds"], .5)
        self.assertEqual(scene["originEndSeconds"], 1.5)
        self.assertAlmostEqual(scene["endSeconds"], 1.02)

    def test_apply_can_replace_plan_without_touching_existing_output_or_scenes(self):
        project = self._prepared_cut_project()
        scenes = project / "reel/scenes.js"; scenes.write_text("// authored\n", encoding="utf-8")
        out = project / "out"; out.mkdir(exist_ok=True); finished = out / "final.mp4"; finished.write_bytes(b"keep")
        first = self._full_plan(assets=[])
        native.apply(project=str(project), composition=str(first), media=None)
        replacement = native.read_json(first)
        replacement["concept"] = "changed"
        second = self.root / "second-plan.json"; second.write_text(json.dumps(replacement), encoding="utf-8")
        native.apply(project=str(project), composition=str(second), media=None)
        self.assertEqual(native.read_json(project / "composition.json")["concept"], "changed")
        self.assertEqual(scenes.read_text(encoding="utf-8"), "// authored\n")
        self.assertEqual(finished.read_bytes(), b"keep")

    def test_invalid_reapply_preserves_existing_plan_and_media(self):
        project = self._prepared_cut_project()
        native.apply(project=str(project), composition=str(self._full_plan(assets=[])), media=None)
        before = (project / "composition.json").read_bytes(), (project / "reel/film-plan.js").read_bytes()
        broken = native.read_json(self._full_plan(assets=[]))
        broken["tracks"][0]["sourceSha256"] = "0" * 64
        path = self.root / "broken-reapply.json"; path.write_text(json.dumps(broken), encoding="utf-8")
        with self.assertRaises(ValueError): native.apply(project=str(project), composition=str(path), media=None)
        self.assertEqual(before, ((project / "composition.json").read_bytes(), (project / "reel/film-plan.js").read_bytes()))

    def test_native_qa_report_uses_issue_section_not_human_checklist(self):
        report = "# 자동 검수\n\n## 자동 검사 통과\n\n## 사람이 볼 것\n- [ ] 시트 확인\n"
        self.assertTrue(native._native_qa_passes(report, {"issues": []}))
        self.assertFalse(native._native_qa_passes("# 자동 검수\n\n## 고칠 것\n- [ ] 실제 결함\n", {"issues": []}))

    def test_motion_keeps_flash_and_unknown_issues_hard_but_marks_low_motion_for_review(self):
        self.assertEqual(native._motion_status({"issues": ["still_ratio=0.4"]})[0], "needs-review")
        self.assertEqual(native._motion_status({"issues": ["p90=2.1"]})[0], "needs-review")
        self.assertEqual(native._motion_status({"issues": ["멈춘 화면 32%", "큰 움직임 p90 3.0", "6.0~7.2s 동안 화면이 멈춤"]})[0], "needs-review")
        self.assertTrue(native._native_qa_passes("## 고칠 것\n- [ ] 멈춘 화면 32%\n", {"issues": ["멈춘 화면 32%"]}))
        long_still = '6.0~7.2s 동안 1.2초 멈춤 — 의도한 정적인지 확인'
        self.assertTrue(native._native_qa_passes('## 고칠 것\n- [ ] ' + long_still + ' [장면 track-001.s01]\n', {'issues':[long_still]}))
        self.assertFalse(native._native_qa_passes('## 고칠 것\n- [ ] ' + long_still + ' 추가 결함 [장면 track-001.s01]\n', {'issues':[long_still]}))
        self.assertFalse(native._native_qa_passes('## 고칠 것\n- [ ] 섬광 과다 [장면 track-001.s01]\n', {'issues':[long_still]}))
        self.assertEqual(native._motion_status({"issues": ["flash_ratio=0.2"]})[0], "failed")
        self.assertEqual(native._motion_status({"issues": ["섬광 과다"]})[0], "failed")
        self.assertEqual(native._motion_status({"issues": ["decode failed"]})[0], "failed")

    def test_runtime_accepts_native_half_frame_shutter_boundaries_but_not_scene_drift(self):
        scenes = [{'id':'track-001.one','startSeconds':0,'endSeconds':1}, {'id':'track-001.two','startSeconds':1,'endSeconds':2}]
        report = {'pass':True, 'files':{}, 'sceneBindings':scenes, 'registeredScenes':[{'id':'track-001.one','startSeconds':0,'endSeconds':1-.5/30}, {'id':'track-001.two','startSeconds':1-.5/30,'endSeconds':2}]}
        native.write_json(self.root/'qa/native-runtime.json', report)
        native._current_runtime(self.root, {}, scenes)
        report['registeredScenes'][1]['startSeconds'] = .9
        native.write_json(self.root/'qa/native-runtime.json', report)
        with self.assertRaises(ValueError): native._current_runtime(self.root, {}, scenes)

    def test_native_timeline_millisecond_format_keeps_full_precision_clock(self):
        cap=self.root/'fractional.srt';cap.write_text('1\n00:00:00,000 --> 00:00:02,000\n원문\n')
        project=self.root/'fractional-native'
        native.prepare(music=str(self.music),captions=str(cap),display=str(self.display),out=str(project),start=.5,duration=1.003)
        plan=native.read_json(self._full_plan([]));plan['tracks'][0]['scenes'][0].update(endSeconds=1.503,lyricCueIds=['1'])
        file=self.root/'fractional-plan.json';native.write_json(file,plan)
        native.apply(project=str(project),composition=str(file))
        prepared=native.check(project=str(project))
        self.assertAlmostEqual(prepared['scenes'][0]['endSeconds'],31/30)
        timeline=native.read_json(project/'timeline.json')
        self.assertEqual(timeline['scenes'][0]['end'],1.033)
        timeline['scenes'][0]['end']+=.001;native.write_json(project/'timeline.json',timeline)
        with self.assertRaises(ValueError):native.check(project=str(project))

    def _prepared_cut_project(self):
        captions = self.root / "lyrics.srt"
        captions.write_text("1\n00:00:00,000 --> 00:00:01,000\n첫 문장\n\n2\n00:00:01,000 --> 00:00:02,000\n둘째 문장\n", encoding="utf-8")
        out = self.root / ("cut-" + str(len(list(self.root.glob("cut-*")))))
        native.prepare(music=str(self.music), captions=str(captions), instrumental=False, display=str(self.display), out=str(out), start=.5, duration=1.0)
        return out

    def _full_plan(self, assets):
        project = self._prepared_cut_project()
        plan = self.root / "good.json"
        plan.write_text(json.dumps({"schemaVersion": 1, "concept": "x", "tracks": [{"id": "track-001", "sourceSha256": native.sha256(self.music), "scenes": [{"id": "one", "startSeconds": .5, "endSeconds": 1.5, "lyricCueIds": ["1", "2"], "meaning": "x", "subject": "x", "action": "x", "medium": "same", "composition": "x", "transition": "x", "assets": assets}]}]}), encoding="utf-8")
        # The caller has a sibling prepared project; replace its plan with this source-clock complete plan.
        return plan


if __name__ == "__main__":
    unittest.main(verbosity=2)
