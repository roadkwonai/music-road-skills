import json
import shutil
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import storage_lifecycle
from storage_manager import StorageManager
from studio import init_project


class StorageLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "native-project"
        self.root.mkdir(parents=True)
        (self.root / "production.json").write_text(json.dumps({"schemaVersion": 1, "renderDurationSeconds": 2}), encoding="utf-8")
        (self.root / "playlist.json").write_text(json.dumps({"schemaVersion": 1, "tracks": []}), encoding="utf-8")
        self.manager = StorageManager(Path(self.temp.name) / "data")
        self.original_manager = storage_lifecycle.shared_storage_manager
        storage_lifecycle.shared_storage_manager = lambda: self.manager

    def tearDown(self):
        storage_lifecycle.shared_storage_manager = self.original_manager
        self.temp.cleanup()

    def test_failed_new_work_drops_registry_only_after_files_are_removed(self):
        project = storage_lifecycle.prepare_project(self.root)
        self.assertFalse(storage_lifecycle.abandon_failed_project(self.root))
        shutil.rmtree(self.root)
        self.assertTrue(storage_lifecycle.abandon_failed_project(self.root))
        self.assertNotIn(project['id'], self.manager._read()['projects'])
        self.assertEqual(self.manager.management_db.paths(project_id=project['id']), [])
        self.assertEqual(self.manager.management_db.events()['events'][0]['action'], 'production-failed')
        self.assertFalse(storage_lifecycle.abandon_failed_project(self.root))

    def test_stage_history_reuses_unchanged_result_and_compares_with_previous_stage(self):
        storage_lifecycle.record_production_change(self.root, 'video.finalized', after={'sha': 'first'})
        storage_lifecycle.record_production_change(self.root, 'video.finalized', after={'sha': 'first'})
        storage_lifecycle.record_production_change(self.root, 'video.finalized', after={'sha': 'second'})
        rows = self.manager.management_db.events()['events']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['before'], {'sha': 'first'})
        self.assertEqual(rows[0]['after'], {'sha': 'second'})

    def test_production_task_keeps_known_expected_size_and_observed_stage(self):
        from production_ledger import ProductionLedger
        handle = storage_lifecycle.start_production_task(
            self.root, task_type='render', engine='showreel', model='native-composition',
            expected_media_seconds=36, expected_frame_count=1080,
        )
        self.assertIsNone(storage_lifecycle.progress_production_task(handle, current_stage='render', summary='실제 렌더 시작'))
        task = ProductionLedger(self.manager.data_dir).tasks({'taskId': handle['taskId']})['tasks'][0]
        self.assertEqual((task['expectedMediaSeconds'], task['expectedFrameCount']), (36.0, 1080))
        self.assertEqual((task['currentStage'], task['progress']), ('render', None))

    def test_successful_render_tracks_owned_cache_releases_lease_and_keeps_result(self):
        project = storage_lifecycle.prepare_project(self.root)
        self.assertTrue((self.root / ".roadmusic/cache/picture").is_dir())
        lease = storage_lifecycle.acquire_render_lease(self.root)
        picture = self.root / ".roadmusic/cache/picture/final-picture.mp4"
        picture.write_bytes(b"intermediate")
        final = self.root / "out/final.mp4"
        final.parent.mkdir()
        final.write_bytes(b"final")
        self.manager.dispatch("policy", {"projectId": project["id"], "state": "completed", "retainDays": 0})

        warning = storage_lifecycle.finish_render(self.root, lease["token"], succeeded=True)

        self.assertIsNone(warning)
        self.assertFalse(picture.exists())
        self.assertEqual(final.read_bytes(), b"final")
        listed = self.manager.dispatch("list", {"projectId": project["id"]})["projects"][0]
        self.assertFalse(listed["busy"])
        history = self.manager.dispatch("history", {"projectId": project["id"]})["events"]
        self.assertTrue(any(event["action"] == "track" for event in history))

    def test_failed_render_keeps_resumeable_parts_after_releasing_lease(self):
        project = storage_lifecycle.prepare_project(self.root)
        lease = storage_lifecycle.acquire_render_lease(self.root)
        parts = self.root / ".roadmusic/cache/picture/final-picture.parts/frame-0001.png"
        parts.parent.mkdir(parents=True)
        parts.write_bytes(b"resume")

        warning = storage_lifecycle.finish_render(self.root, lease["token"], succeeded=False)

        self.assertIsNone(warning)
        self.assertTrue(parts.exists())
        self.assertFalse(self.manager.dispatch("list", {"projectId": project["id"]})["projects"][0]["busy"])

    def test_failed_render_restores_editing_before_releasing_completed_project_lease(self):
        project = storage_lifecycle.prepare_project(self.root)
        self.manager.dispatch("policy", {"projectId": project["id"], "state": "completed", "retainDays": 0})
        lease = storage_lifecycle.acquire_render_lease(self.root)
        parts = self.root / ".roadmusic/cache/picture/final-picture.parts/frame-0001.png"
        parts.parent.mkdir(parents=True)
        parts.write_bytes(b"resume")

        warning = storage_lifecycle.finish_render(self.root, lease["token"], succeeded=False)

        self.assertIsNone(warning)
        self.assertTrue(parts.exists())
        listed = self.manager.dispatch("list", {"projectId": project["id"]})["projects"][0]
        self.assertEqual(listed["state"], "editing")

    def test_successful_editing_render_over_budget_cleans_only_reproducible_picture_cache(self):
        project = storage_lifecycle.prepare_project(self.root)
        picture = self.root / ".roadmusic/cache/picture/final-picture.mp4"
        picture.write_bytes(b"intermediate-picture")
        source = self.root / "source.wav"; source.write_bytes(b"source")
        final = self.root / "out/final.mp4"; final.parent.mkdir(); final.write_bytes(b"final")
        history = self.root / ".roadmusic/intermediate/review.json"; history.parent.mkdir(exist_ok=True); history.write_bytes(b"history")
        self.manager.dispatch("track", {"projectId": project["id"], "path": ".roadmusic/intermediate/review.json", "kind": "intermediate"})
        self.manager.dispatch("policy", {"projectId": project["id"], "maxCacheBytes": 1, "maxCacheFiles": 0})
        lease = storage_lifecycle.acquire_render_lease(self.root)

        warning = storage_lifecycle.finish_render(self.root, lease["token"], succeeded=True)

        self.assertIsNone(warning)
        self.assertFalse(picture.exists())
        self.assertEqual(source.read_bytes(), b"source")
        self.assertEqual(final.read_bytes(), b"final")
        self.assertEqual(history.read_bytes(), b"history")

    def test_successful_editing_render_below_budget_keeps_picture_cache(self):
        project = storage_lifecycle.prepare_project(self.root)
        picture = self.root / ".roadmusic/cache/picture/final-picture.mp4"
        picture.write_bytes(b"intermediate")
        self.manager.dispatch("policy", {"projectId": project["id"], "maxCacheBytes": 1024, "maxCacheFiles": 2})
        lease = storage_lifecycle.acquire_render_lease(self.root)

        warning = storage_lifecycle.finish_render(self.root, lease["token"], succeeded=True)

        self.assertIsNone(warning)
        self.assertTrue(picture.exists())

    def test_over_budget_cleanup_respects_disabled_automatic_cleanup_and_pin(self):
        project = storage_lifecycle.prepare_project(self.root)
        picture = self.root / ".roadmusic/cache/picture/final-picture.mp4"
        picture.write_bytes(b"intermediate")
        tracked = self.manager.dispatch("track", {"projectId": project["id"], "path": ".roadmusic/cache/picture", "kind": "cache", "reproducible": True})
        self.manager.dispatch("policy", {"projectId": project["id"], "maxCacheBytes": 1, "maxCacheFiles": 0, "autoCleanup": False})
        lease = storage_lifecycle.acquire_render_lease(self.root)
        self.assertIsNone(storage_lifecycle.finish_render(self.root, lease["token"], succeeded=True))
        self.assertTrue(picture.exists())
        self.manager.dispatch("policy", {"projectId": project["id"], "autoCleanup": True})
        self.manager.dispatch("pin", {"projectId": project["id"], "entryId": tracked["id"], "pinned": True})
        lease = storage_lifecycle.acquire_render_lease(self.root)
        self.assertIsNone(storage_lifecycle.finish_render(self.root, lease["token"], succeeded=True))
        self.assertTrue(picture.exists())

    def test_over_budget_cleanup_keeps_picture_when_another_render_acquires_lease(self):
        project = storage_lifecycle.prepare_project(self.root)
        picture = self.root / ".roadmusic/cache/picture/final-picture.mp4"
        picture.write_bytes(b"intermediate")
        self.manager.dispatch("policy", {"projectId": project["id"], "maxCacheBytes": 1, "maxCacheFiles": 0})
        lease = storage_lifecycle.acquire_render_lease(self.root)
        dispatch = self.manager.dispatch
        acquired = {}

        def acquire_before_cleanup(action, params):
            if action == "cleanup" and not acquired:
                acquired.update(dispatch("lease", {"projectId": project["id"], "operation": "acquire", "pid": os.getpid()}))
            return dispatch(action, params)

        with patch.object(self.manager, "dispatch", side_effect=acquire_before_cleanup):
            warning = storage_lifecycle.finish_render(self.root, lease["token"], succeeded=True)

        self.assertIn("보류", warning)
        self.assertTrue(picture.exists())
        self.manager.dispatch("lease", {"projectId": project["id"], "operation": "release", "token": acquired["token"]})

    def test_verified_published_delivery_completes_default_project_and_cleans_owned_cache(self):
        project = storage_lifecycle.prepare_project(self.root)
        source = self.root / "source.mp3"; source.write_bytes(b"source")
        final = self.root / "final.mp4"; final.write_bytes(b"final")
        cache = self.root / ".roadmusic/cache/picture/frame.png"; cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(b"cache")
        self.manager.dispatch("track", {"projectId": project["id"], "path": ".roadmusic/cache/picture", "kind": "cache", "reproducible": True})
        source_hash = storage_lifecycle._sha256(source)
        final_hash = storage_lifecycle._sha256(final)
        def probe(path):
            return {"streams": [{"codec_type": "audio"}] if Path(path) == source else [{"codec_type": "video"}, {"codec_type": "audio"}], "format": {"duration": "2.0"}}

        with patch.object(storage_lifecycle, "_probe_media", side_effect=probe):
            result = storage_lifecycle.complete_published_project(self.manager, self.root, [
                {"id": "music", "kind": "music", "path": str(source), "sha256": source_hash},
                {"id": "video-0", "kind": "video", "path": str(final), "sha256": final_hash},
            ], source_hash.upper())

        self.assertTrue(result["completed"])
        self.assertFalse(cache.exists())
        self.assertEqual(final.read_bytes(), b"final")
        self.assertEqual(self.manager.dispatch("list", {"projectId": project["id"]})["projects"][0]["state"], "completed")
        receipt = json.loads((self.root / ".roadmusic/history/final-delivery.json").read_text())
        self.assertEqual(receipt["source"]["sha256"], source_hash)
        self.assertEqual(receipt["outputs"][0]["sha256"], final_hash)

    def test_unverified_delivery_or_disabled_auto_cleanup_preserves_editing_cache(self):
        project = storage_lifecycle.prepare_project(self.root)
        source = self.root / "source.mp3"; source.write_bytes(b"source")
        final = self.root / "final.mp4"; final.write_bytes(b"final")
        cache = self.root / ".roadmusic/cache/picture/frame.png"; cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(b"cache")
        self.manager.dispatch("track", {"projectId": project["id"], "path": ".roadmusic/cache/picture", "kind": "cache", "reproducible": True})
        source_hash = storage_lifecycle._sha256(source)
        result = storage_lifecycle.complete_published_project(self.manager, self.root, [
            {"id": "music", "kind": "music", "path": str(source), "sha256": source_hash},
            {"id": "video-0", "kind": "video", "path": str(final), "sha256": storage_lifecycle._sha256(final)},
        ], "0" * 64)
        self.assertFalse(result["completed"])
        self.assertTrue(cache.exists())
        self.manager.dispatch("policy", {"projectId": project["id"], "autoCleanup": False})
        result = storage_lifecycle.complete_published_project(self.manager, self.root, [], source_hash)
        self.assertFalse(result["completed"])
        self.assertTrue(cache.exists())
        self.assertEqual(self.manager.dispatch("list", {"projectId": project["id"]})["projects"][0]["state"], "editing")

    def test_partial_or_unbounded_video_cannot_complete_or_clean_cache(self):
        project = storage_lifecycle.prepare_project(self.root)
        source = self.root / "source.mp3"; source.write_bytes(b"source")
        preview = self.root / "preview.mp4"; preview.write_bytes(b"preview")
        cache = self.root / ".roadmusic/cache/picture/frame.png"; cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(b"cache")
        self.manager.dispatch("track", {"projectId": project["id"], "path": ".roadmusic/cache/picture", "kind": "cache", "reproducible": True})
        source_hash, preview_hash = storage_lifecycle._sha256(source), storage_lifecycle._sha256(preview)
        def probe(path):
            seconds = "120" if Path(path) == source else "20"
            return {"streams": [{"codec_type": "audio"}] if Path(path) == source else [{"codec_type": "video"}, {"codec_type": "audio"}], "format": {"duration": seconds}}
        (self.root / "production.json").write_text(json.dumps({"schemaVersion": 1, "renderDurationSeconds": 120}), encoding="utf-8")
        with patch.object(storage_lifecycle, "_probe_media", side_effect=probe):
            result = storage_lifecycle.complete_published_project(self.manager, self.root, [
                {"id": "music", "kind": "music", "path": str(source), "sha256": source_hash},
                {"id": "video-0", "kind": "video", "path": str(preview), "sha256": preview_hash},
            ], source_hash)
        self.assertFalse(result["completed"]); self.assertTrue(cache.exists())
        (self.root / "production.json").write_text(json.dumps({"schemaVersion": 1}), encoding="utf-8")
        with patch.object(storage_lifecycle, "_probe_media", side_effect=probe):
            result = storage_lifecycle.complete_published_project(self.manager, self.root, [
                {"id": "music", "kind": "music", "path": str(source), "sha256": source_hash},
                {"id": "video-0", "kind": "video", "path": str(preview), "sha256": preview_hash},
            ], source_hash)
        self.assertFalse(result["completed"]); self.assertTrue(cache.exists())

    def test_verified_delivery_cleans_only_create_recorded_derived_stems(self):
        project = storage_lifecycle.prepare_project(self.root)
        (self.root / "production.json").write_text(json.dumps({"schemaVersion": 1, "renderDurationSeconds": 2, "audio": {"path": "audio/mix.wav"}}), encoding="utf-8")
        source = self.root / "source.mp3"; source.write_bytes(b"source")
        final = self.root / "final.mp4"; final.write_bytes(b"final")
        primary = self.root / "audio/mix.wav"; primary.parent.mkdir(exist_ok=True); primary.write_bytes(b"primary")
        stale = self.root / "audio/old-mix.wav"; stale.write_bytes(b"old")
        stems = []
        for name in storage_lifecycle.OWNED_RENDER_STEMS:
            path = self.root / name; path.write_bytes(name.encode()); stems.append(path)
        storage_lifecycle.prepare_project(self.root, generated_cache=list(storage_lifecycle.OWNED_RENDER_STEMS))
        source_hash, final_hash = storage_lifecycle._sha256(source), storage_lifecycle._sha256(final)
        def probe(path):
            return {"streams": [{"codec_type": "audio"}] if Path(path) == source else [{"codec_type": "video"}, {"codec_type": "audio"}], "format": {"duration": "2.0"}}

        with patch.object(storage_lifecycle, "_probe_media", side_effect=probe), patch.object(storage_lifecycle, "_is_open", return_value=False):
            result = storage_lifecycle.complete_published_project(self.manager, self.root, [
                {"id": "music", "kind": "music", "path": str(source), "sha256": source_hash},
                {"id": "video-0", "kind": "video", "path": str(final), "sha256": final_hash},
            ], source_hash)

        self.assertTrue(result["completed"])
        self.assertEqual(result["cleanup"]["ownedRenderCache"]["removedFiles"], 3)
        self.assertTrue(all(not path.exists() for path in stems))
        self.assertEqual(source.read_bytes(), b"source")
        self.assertEqual(final.read_bytes(), b"final")
        self.assertEqual(primary.read_bytes(), b"primary")
        self.assertEqual(stale.read_bytes(), b"old")

    def test_owned_stems_stay_when_changed_pinned_busy_or_auto_cleanup_is_disabled(self):
        def setup():
            root = self.root
            (root / "production.json").write_text(json.dumps({"schemaVersion": 1, "renderDurationSeconds": 2}), encoding="utf-8")
            source = root / "source.mp3"; source.write_bytes(b"source")
            final = root / "final.mp4"; final.write_bytes(b"final")
            stem = root / "audio/mix_bed.wav"; stem.parent.mkdir(exist_ok=True); stem.write_bytes(b"stem")
            project = storage_lifecycle.prepare_project(root, generated_cache=["audio/mix_bed.wav"])
            return project, source, final, stem
        project, source, final, stem = setup()
        stem.write_bytes(b"changed")
        source_hash, final_hash = storage_lifecycle._sha256(source), storage_lifecycle._sha256(final)
        def probe(path): return {"streams": [{"codec_type": "audio"}] if Path(path) == source else [{"codec_type": "video"}, {"codec_type": "audio"}], "format": {"duration": "2"}}
        with patch.object(storage_lifecycle, "_probe_media", side_effect=probe), patch.object(storage_lifecycle, "_is_open", return_value=False):
            result = storage_lifecycle.complete_published_project(self.manager, self.root, [{"id": "music", "kind": "music", "path": str(source), "sha256": source_hash}, {"id": "video-0", "kind": "video", "path": str(final), "sha256": final_hash}], source_hash)
        self.assertTrue(result["completed"]); self.assertTrue(stem.exists())
        self.manager.dispatch("policy", {"projectId": project["id"], "state": "editing", "autoCleanup": False})
        with patch.object(storage_lifecycle, "_probe_media", side_effect=probe):
            result = storage_lifecycle.complete_published_project(self.manager, self.root, [{"id": "music", "kind": "music", "path": str(source), "sha256": source_hash}, {"id": "video-0", "kind": "video", "path": str(final), "sha256": final_hash}], source_hash)
        self.assertFalse(result["completed"]); self.assertTrue(stem.exists())
        self.manager.dispatch("policy", {"projectId": project["id"], "autoCleanup": True})
        pin = self.root / ".roadmusic/cache/pinned.tmp"; pin.parent.mkdir(exist_ok=True); pin.write_bytes(b"pin")
        entry = self.manager.dispatch("track", {"projectId": project["id"], "path": ".roadmusic/cache/pinned.tmp", "kind": "cache", "reproducible": True})
        self.manager.dispatch("pin", {"projectId": project["id"], "entryId": entry["id"], "pinned": True})
        with patch.object(storage_lifecycle, "_probe_media", side_effect=probe):
            result = storage_lifecycle.complete_published_project(self.manager, self.root, [{"id": "music", "kind": "music", "path": str(source), "sha256": source_hash}, {"id": "video-0", "kind": "video", "path": str(final), "sha256": final_hash}], source_hash)
        self.assertTrue(result["completed"]); self.assertTrue(stem.exists())
        lease = self.manager.dispatch("lease", {"projectId": project["id"], "operation": "acquire", "pid": os.getpid()})
        result = storage_lifecycle.complete_published_project(self.manager, self.root, [{"id": "music", "kind": "music", "path": str(source), "sha256": source_hash}, {"id": "video-0", "kind": "video", "path": str(final), "sha256": final_hash}], source_hash)
        self.assertFalse(result["completed"]); self.assertTrue(stem.exists())
        self.manager.dispatch("lease", {"projectId": project["id"], "operation": "release", "token": lease["token"]})

    def test_production_change_skips_equal_values_and_links_one_source(self):
        source = "a" * 64
        (self.root / "production.json").write_text(json.dumps({"source": {"sha256": source}}))
        self.assertIsNone(storage_lifecycle.record_production_change(self.root, "title", {"title": "same"}, {"title": "same"}))
        self.assertEqual(self.manager.management_db.events()["events"], [])
        event = storage_lifecycle.record_production_change(self.root, "title", {"title": "old"}, {"title": "new"})
        self.assertEqual(event["groupId"], source)
        self.assertEqual(event["path"], str(self.root.resolve()))

    def test_new_work_path_claim_exists_before_producer_creates_directory(self):
        workspace = Path(self.temp.name) / "workspace"; workspace.mkdir()
        with patch("storage_lifecycle._trusted_workspace", return_value=workspace):
            actual = storage_lifecycle.working_project_path(workspace / "Output/test", "a" * 64)
        self.assertFalse(actual.exists())
        claim = next(item for item in self.manager.management_db.paths() if item["path"] == str(actual))
        self.assertEqual(claim["groupId"], "a" * 64)
        self.assertEqual(claim["workspace"], str(workspace))

    def test_new_output_request_uses_hidden_work_path_and_completed_structure_redirects_existing_output(self):
        workspace = Path(self.temp.name) / "workspace"
        output = workspace / "Output"
        output.mkdir(parents=True)
        requested = output / "showreel" / "spring"
        existing = output / "legacy"; existing.mkdir()
        original = storage_lifecycle._trusted_workspace
        storage_lifecycle._trusted_workspace = lambda: workspace
        try:
            actual = storage_lifecycle.working_project_path(requested, "a" * 64)
            self.assertEqual(actual.parent, workspace / ".roadmusic/work" / ("a" * 12))
            self.assertRegex(actual.name, r"^spring--[0-9a-f]{12}$")
            self.assertEqual(storage_lifecycle.working_project_path(existing, "a" * 64), existing.resolve())
            marker = workspace / ".roadmusic/structure.json"; marker.parent.mkdir()
            marker.write_text(json.dumps({'schemaVersion': 1, 'phase': 'completed', 'owner': 'road-music', 'workspace': str(workspace)}), encoding='utf-8')
            redirected = storage_lifecycle.working_project_path(existing, "a" * 64)
            self.assertTrue(redirected.is_relative_to(workspace / '.roadmusic/work' / ('a' * 12)))
            self.assertNotEqual(redirected, existing.resolve())
            self.assertEqual(storage_lifecycle.working_project_path(self.root / "outside", "not-a-sha"), (self.root / "outside").resolve())
        finally:
            storage_lifecycle._trusted_workspace = original

    def test_studio_init_redirects_existing_output_path_after_completed_structure(self):
        workspace = Path(self.temp.name) / 'studio-workspace'; requested = workspace / 'Output' / 'legacy-project'
        requested.mkdir(parents=True)
        marker = workspace / '.roadmusic/structure.json'; marker.parent.mkdir()
        marker.write_text(json.dumps({'schemaVersion': 1, 'phase': 'completed', 'owner': 'road-music', 'workspace': str(workspace)}), encoding='utf-8')
        source = self.root / 'source.mp3'; source.write_bytes(b'source')
        original = storage_lifecycle._trusted_workspace
        storage_lifecycle._trusted_workspace = lambda: workspace
        try:
            result = init_project(requested, str(source))
        finally:
            storage_lifecycle._trusted_workspace = original
        actual = Path(result['project'])
        self.assertTrue(actual.is_relative_to(workspace / '.roadmusic/work'))
        self.assertTrue((actual / 'studio-project.json').is_file())
        self.assertTrue(requested.is_dir())

    def test_first_output_request_redirects_even_before_the_output_directory_exists(self):
        workspace = Path(self.temp.name) / 'fresh-workspace'; (workspace / 'cli').mkdir(parents=True)
        (workspace / 'cli/road-music.js').write_text('cli', encoding='utf-8')
        requested = workspace / 'Output' / 'first-project'
        original = storage_lifecycle._trusted_workspace
        storage_lifecycle._trusted_workspace = lambda: workspace
        try:
            actual = storage_lifecycle.working_project_path(requested, 'b' * 64)
        finally:
            storage_lifecycle._trusted_workspace = original
        self.assertTrue(actual.is_relative_to(workspace / '.roadmusic/work' / ('b' * 12)))
        self.assertFalse((workspace / 'Output').exists())


if __name__ == "__main__":
    unittest.main()
