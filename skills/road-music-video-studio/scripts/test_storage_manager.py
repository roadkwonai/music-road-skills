import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from storage_manager import StorageError, StorageManager
import storage_manager


def project_id(path):
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()


class StorageManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.data = self.root / 'data'
        self.project = self.root / 'project'
        self.project.mkdir()
        (self.project / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'media': []}), encoding='utf-8')
        self.manager = StorageManager(self.data)
        self.registered = self.manager.dispatch('register', {'project': str(self.project)})
        self.project_id = self.registered['id']

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, body=b'cache'):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def track_cache(self, relative='.roadmusic/cache/render.tmp'):
        self.write(relative)
        return self.manager.dispatch('track', {
            'projectId': self.project_id, 'path': relative, 'kind': 'cache', 'reproducible': True,
        })

    def test_mv_production_plan_keeps_master_and_history_while_cleaning_only_stage_cache(self):
        run = self.root / 'mv-run'; run.mkdir()
        source = self.root / 'approved.wav'; source.write_bytes(b'original')
        (run / 'input.json').write_text(json.dumps({'schema_version': 1, 'source_audio': str(source), 'source_audio_sha256': hashlib.sha256(b'original').hexdigest()}))
        (run / 'production-plan.json').write_text(json.dumps({'objective': 'approved MV', 'tasks': []}))
        registered = self.manager.dispatch('register', {'project': str(run)})
        master = run / 'preproduction/animatic.mov'; master.parent.mkdir(); master.write_bytes(b'approved master')
        cache = run / '.roadmusic/cache/animatic/concat.txt'; cache.parent.mkdir(); cache.write_text('reproducible stage')
        self.manager.dispatch('track', {'projectId': registered['id'], 'path': '.roadmusic/cache/animatic', 'kind': 'cache', 'reproducible': True})
        lease = self.manager.dispatch('lease', {'projectId': registered['id'], 'operation': 'acquire', 'pid': os.getpid()})
        self.manager.dispatch('policy', {'projectId': registered['id'], 'state': 'completed', 'retainDays': 0})
        self.assertTrue(cache.exists())
        self.manager.dispatch('lease', {'projectId': registered['id'], 'operation': 'release', 'token': lease['token']})
        self.assertFalse(cache.exists()); self.assertEqual(master.read_bytes(), b'approved master')
        self.assertEqual(source.read_bytes(), b'original'); self.assertTrue((run / 'production-plan.json').exists())

    def test_register_uses_canonical_project_id_and_rejects_unregistered_paths(self):
        self.assertEqual(self.project_id, project_id(self.project))
        self.assertTrue(all((self.project / '.roadmusic' / name).is_dir() for name in ('cache', 'intermediate', 'history')))
        with self.assertRaisesRegex(StorageError, '등록된 프로젝트'):
            self.manager.dispatch('track', {'projectId': '0' * 64, 'path': 'x', 'kind': 'cache', 'reproducible': True})
        outside = self.root / 'outside'; outside.mkdir()
        with self.assertRaisesRegex(StorageError, 'studio-project.json'):
            self.manager.dispatch('register', {'project': str(outside)})

    def test_register_accepts_verified_showreel_or_harness_markers_but_rejects_data_root(self):
        showreel = self.root / 'showreel'; showreel.mkdir()
        (showreel / 'production.json').write_text(json.dumps({'schemaVersion': 1, 'music': 'song.mp3'}), encoding='utf-8')
        (showreel / 'playlist.json').write_text(json.dumps({'schemaVersion': 1, 'items': []}), encoding='utf-8')
        self.assertEqual(self.manager.dispatch('register', {'project': str(showreel)})['path'], str(showreel))
        harness = self.root / 'harness'; harness.mkdir()
        (harness / 'input.json').write_text(json.dumps({'schemaVersion': 1, 'music': {'path': 'song.mp3'}}), encoding='utf-8')
        (harness / 'plan.json').write_text(json.dumps({'schemaVersion': 1, 'shots': []}), encoding='utf-8')
        self.assertEqual(self.manager.dispatch('register', {'project': str(harness)})['path'], str(harness))
        (self.data / 'studio-project.json').parent.mkdir(parents=True, exist_ok=True)
        (self.data / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'media': []}), encoding='utf-8')
        with self.assertRaisesRegex(StorageError, '등록할 수 없습니다'):
            self.manager.dispatch('register', {'project': str(self.data)})

    def test_verified_project_below_home_or_repository_output_is_not_treated_as_the_root(self):
        home_project = self.root / 'home-project'; home_project.mkdir()
        (home_project / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'media': []}), encoding='utf-8')
        repo = self.root / 'repo'; output_project = repo / 'Output' / 'fixture'; output_project.mkdir(parents=True)
        (output_project / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'media': []}), encoding='utf-8')
        fake_module = repo / '.agents/skills/road-music-video-studio/scripts/storage_manager.py'
        with patch('storage_manager.Path.home', return_value=self.root), patch('storage_manager.__file__', str(fake_module)):
            self.assertEqual(self.manager.dispatch('register', {'project': str(home_project)})['path'], str(home_project))
            self.assertEqual(self.manager.dispatch('register', {'project': str(output_project)})['path'], str(output_project))

    def test_registers_existing_song_folder_but_keeps_root_audio_and_score_protected(self):
        song = self.root / 'song'; song.mkdir()
        (song / 'meta.json').write_text(json.dumps({'title': '기존 곡', 'style': 'ballad'}), encoding='utf-8')
        (song / 'song.wav').write_bytes(b'audio')
        registered = self.manager.dispatch('register', {'project': str(song)})
        with self.assertRaisesRegex(StorageError, '내부에서만'):
            self.manager.dispatch('track', {'projectId': registered['id'], 'path': 'song.wav', 'kind': 'cache', 'reproducible': True})
        (song / 'score.abc').write_text('X:1\nK:C\n', encoding='utf-8')
        with self.assertRaisesRegex(StorageError, '내부에서만'):
            self.manager.dispatch('track', {'projectId': registered['id'], 'path': 'score.abc', 'kind': 'history'})

    def test_track_requires_reproducible_cache_and_never_tracks_symlink_or_source(self):
        self.write('cache/a.tmp')
        with self.assertRaisesRegex(StorageError, 'reproducible'):
            self.manager.dispatch('track', {'projectId': self.project_id, 'path': 'cache/a.tmp', 'kind': 'cache'})
        source = self.write('original.wav', b'original')
        with self.assertRaisesRegex(StorageError, '내부에서만'):
            self.manager.dispatch('track', {'projectId': self.project_id, 'path': 'original.wav', 'kind': 'cache', 'reproducible': True})
        link = self.project / 'cache' / 'link.tmp'
        try:
            link.symlink_to(source)
        except OSError as error:
            self.skipTest(f'symlink unavailable: {error}')
        with self.assertRaisesRegex(StorageError, 'symlink'):
            self.manager.dispatch('track', {'projectId': self.project_id, 'path': 'cache/link.tmp', 'kind': 'cache', 'reproducible': True})

    def test_track_rejects_legacy_media_outside_its_managed_kind_root(self):
        self.write('legacy/song.mp4', b'final')
        with self.assertRaisesRegex(StorageError, '내부에서만') as error:
            self.manager.dispatch('track', {'projectId': self.project_id, 'path': 'legacy/song.mp4', 'kind': 'cache', 'reproducible': True})
        self.assertEqual(error.exception.code, 'unsafe_path')

    def test_track_rejects_executable_even_inside_managed_cache(self):
        executable = self.write('.roadmusic/cache/runner', b'#!/bin/sh\n')
        executable.chmod(0o755)
        with self.assertRaisesRegex(StorageError, '프로그램'):
            self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/cache/runner', 'kind': 'cache', 'reproducible': True})

    def test_track_fails_closed_when_directory_snapshot_exceeds_limit(self):
        self.write('.roadmusic/cache/many/one.tmp'); self.write('.roadmusic/cache/many/two.tmp')
        with patch.object(storage_manager, 'MAX_TRACK_FILES', 1), self.assertRaisesRegex(StorageError, '안전 한도'):
            self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/cache/many', 'kind': 'cache', 'reproducible': True})

    def test_track_counts_empty_subdirectories_against_snapshot_limit(self):
        (self.project / '.roadmusic/cache/tree/empty/child').mkdir(parents=True)
        self.write('.roadmusic/cache/tree/file.tmp')
        with patch.object(storage_manager, 'MAX_TRACK_FILES', 1), self.assertRaisesRegex(StorageError, '안전 한도'):
            self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/cache/tree', 'kind': 'cache', 'reproducible': True})

    def test_preview_is_read_only_and_cleanup_requires_confirm_and_unchanged_snapshot(self):
        entry = self.track_cache()
        preview = self.manager.dispatch('preview', {'projectId': self.project_id, 'entryIds': [entry['id']]})
        self.assertEqual(preview['fileCount'], 1)
        self.assertTrue((self.project / '.roadmusic/cache/render.tmp').exists())
        with self.assertRaisesRegex(StorageError, 'confirm'):
            self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': False})
        self.write('.roadmusic/cache/render.tmp', b'changed')
        cleaned = self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})
        self.assertEqual(cleaned['removedFiles'], 0)
        self.assertTrue(cleaned['skipped'])
        self.assertTrue((self.project / '.roadmusic/cache/render.tmp').exists())

    def test_list_reports_changed_tracked_file_as_readonly_unknown_live_usage(self):
        self.track_cache()
        self.write('.roadmusic/cache/render.tmp', b'changed-cache')
        listed = self.manager.dispatch('list', {'projectId': self.project_id})['projects'][0]
        self.assertEqual(listed['managedBytes'], 0)
        self.assertGreaterEqual(listed['totalBytes'], len(b'changed-cache'))
        self.assertGreaterEqual(listed['readonlyUnknownBytes'], len(b'changed-cache'))
        self.assertIn('.roadmusic/cache/render.tmp', [item['relativePath'] for item in listed['unmanagedEntries']])

    def test_unknown_and_protected_files_stay_untouched_when_tracked_directory_is_cleaned(self):
        self.write('.roadmusic/cache/repro.tmp')
        self.write('.roadmusic/cache/unknown.tmp', b'unknown')
        self.track_cache('.roadmusic/cache/repro.tmp')
        self.write('publish/final.mp4', b'final')
        preview = self.manager.dispatch('preview', {'projectId': self.project_id})
        cleaned = self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})
        self.assertFalse((self.project / '.roadmusic/cache/repro.tmp').exists())
        self.assertTrue((self.project / '.roadmusic/cache/unknown.tmp').exists())
        self.assertTrue((self.project / 'publish/final.mp4').exists())
        self.assertEqual(cleaned['removedFiles'], 1)

    def test_empty_selection_and_feedback_values_do_not_protect_project_root(self):
        (self.project / 'selection.json').write_text(json.dumps({'schemaVersion': 1, 'display': {'channelName': ''}}), encoding='utf-8')
        (self.project / 'feedback.json').write_text(json.dumps({'schemaVersion': 1, 'note': ''}), encoding='utf-8')
        entry = self.track_cache()
        preview = self.manager.dispatch('preview', {'projectId': self.project_id, 'entryIds': [entry['id']]})
        cleaned = self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})
        self.assertEqual(cleaned['removedFiles'], 1)
        listed = self.manager.dispatch('list', {'projectId': self.project_id})['projects'][0]
        self.assertEqual(listed['entries'], [])
        self.assertEqual(listed['managedBytes'], 0)
        self.assertGreaterEqual(listed['totalBytes'], listed['readonlyUnknownBytes'])

    def test_completed_ttl_cleanup_only_removes_old_reproducible_cache(self):
        cache = self.write('.roadmusic/cache/ttl.tmp')
        old = time.time() - 9 * 86400
        os.utime(cache, (old, old))
        entry = self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/cache/ttl.tmp', 'kind': 'cache', 'reproducible': True})
        self.assertEqual(entry['relativePath'], '.roadmusic/cache/ttl.tmp')
        # completedAt is also a retention floor, so zero means an explicit immediate cleanup policy.
        changed = self.manager.dispatch('policy', {'projectId': self.project_id, 'state': 'completed', 'retainDays': 0})
        self.assertEqual(changed['cleanup']['removedFiles'], 1)
        result = self.manager.maybe_cleanup(self.project_id)
        self.assertEqual(result['removedFiles'], 0)
        self.assertFalse(cache.exists())

    def test_editing_and_busy_project_do_not_auto_cleanup(self):
        self.track_cache()
        self.assertEqual(self.manager.maybe_cleanup(self.project_id)['removedFiles'], 0)
        self.manager.dispatch('policy', {'projectId': self.project_id, 'state': 'completed', 'retainDays': 0})
        lease = self.manager.dispatch('lease', {'projectId': self.project_id, 'operation': 'acquire', 'pid': os.getpid()})
        self.assertTrue(self.manager.dispatch('list', {'projectId': self.project_id})['projects'][0]['busy'])
        self.assertEqual(self.manager.maybe_cleanup(self.project_id)['removedFiles'], 0)
        self.manager.dispatch('lease', {'projectId': self.project_id, 'operation': 'release', 'token': lease['token']})

    def test_lease_release_applies_completed_cleanup_without_deleting_editing_cache(self):
        self.track_cache()
        lease = self.manager.dispatch('lease', {'projectId': self.project_id, 'operation': 'acquire', 'pid': os.getpid()})
        self.manager.dispatch('policy', {'projectId': self.project_id, 'state': 'completed', 'retainDays': 0})
        released = self.manager.dispatch('lease', {'projectId': self.project_id, 'operation': 'release', 'token': lease['token']})
        self.assertEqual(released['cleanup']['removedFiles'], 1)
        self.track_cache()
        lease = self.manager.dispatch('lease', {'projectId': self.project_id, 'operation': 'acquire', 'pid': os.getpid()})
        self.manager.dispatch('policy', {'projectId': self.project_id, 'state': 'editing'})
        released = self.manager.dispatch('lease', {'projectId': self.project_id, 'operation': 'release', 'token': lease['token']})
        self.assertEqual(released['cleanup']['removedFiles'], 0)
        self.assertTrue((self.project / '.roadmusic/cache/render.tmp').exists())

    def test_lease_release_returns_cleanup_warning_after_successful_release(self):
        lease = self.manager.dispatch('lease', {'projectId': self.project_id, 'operation': 'acquire', 'pid': os.getpid()})
        with patch.object(self.manager, 'maybe_cleanup', side_effect=StorageError('cleanup unavailable')):
            released = self.manager.dispatch('lease', {'projectId': self.project_id, 'operation': 'release', 'token': lease['token']})
        self.assertTrue(released['released'])
        self.assertIn('cleanupWarning', released)

    def test_budget_warns_without_expanding_cleanup_scope(self):
        self.track_cache()
        project = self.manager.dispatch('policy', {'projectId': self.project_id, 'maxCacheBytes': 1, 'maxCacheFiles': 0})
        self.assertEqual(project['maxCacheBytes'], 1)
        listed = self.manager.dispatch('list', {'projectId': self.project_id})['projects'][0]
        self.assertTrue(listed['budgetExceeded'])
        self.assertTrue(listed['warnings'])
        self.assertTrue((self.project / '.roadmusic/cache/render.tmp').exists())

    def test_history_and_pinned_entries_are_preserved_and_hardlink_reclaim_is_not_overstated(self):
        entry = self.track_cache()
        self.manager.dispatch('pin', {'projectId': self.project_id, 'entryId': entry['id'], 'pinned': True})
        preview = self.manager.dispatch('preview', {'projectId': self.project_id})
        self.assertEqual(preview['fileCount'], 0)
        self.assertTrue(preview['blocked'])
        self.manager.dispatch('pin', {'projectId': self.project_id, 'entryId': entry['id'], 'pinned': False})
        other = self.project / '.roadmusic/cache' / 'linked.tmp'
        try:
            os.link(self.project / '.roadmusic/cache/render.tmp', other)
        except OSError as error:
            self.skipTest(f'hardlink unavailable: {error}')
        preview = self.manager.dispatch('preview', {'projectId': self.project_id})
        self.assertEqual(preview['bytes'], 0)
        history = self.manager.dispatch('history', {'projectId': self.project_id})
        self.assertTrue(history['events'])
        self.assertTrue(self.manager.management_db.path.is_file())
        self.assertFalse((self.project / '.roadmusic/history.jsonl').exists())

    def test_unchanged_policy_and_pin_do_not_write_history_or_database(self):
        entry = self.track_cache()
        self.manager.policy({'projectId': self.project_id, 'state': 'completed'})
        self.manager.pin({'projectId': self.project_id, 'entryId': entry['id'], 'pinned': True})
        policy = self.manager._read()['projects'][self.project_id]
        previous_events = self.manager.management_db.events()['events']
        previous_mtime = self.manager.management_db.path.stat().st_mtime_ns
        params = {'projectId': self.project_id, **{key: policy[key] for key in ('state', 'preserveHistory', 'autoCleanup', 'retainDays', 'maxCacheBytes', 'maxCacheFiles')}}
        with patch.object(self.manager, 'maybe_cleanup', side_effect=AssertionError('unchanged policy retriggered cleanup')):
            current = self.manager.policy(params)
            pinned = self.manager.pin({'projectId': self.project_id, 'entryId': entry['id'], 'pinned': True})
        self.assertEqual(current['state'], 'completed'); self.assertTrue(pinned['pinned'])
        self.assertEqual(self.manager._read()['projects'][self.project_id]['completedAt'], policy['completedAt'])
        self.assertEqual(self.manager.management_db.events()['events'], previous_events)
        self.assertEqual(self.manager.management_db.path.stat().st_mtime_ns, previous_mtime)

    def test_retracking_keeps_pin_and_rejects_overlapping_entries(self):
        entry = self.track_cache()
        self.manager.dispatch('pin', {'projectId': self.project_id, 'entryId': entry['id'], 'pinned': True})
        retracked = self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/cache/render.tmp', 'kind': 'cache', 'reproducible': True})
        self.assertTrue(retracked['pinned'])
        self.write('.roadmusic/cache/tree/a.tmp')
        self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/cache/tree', 'kind': 'cache', 'reproducible': True})
        with self.assertRaisesRegex(StorageError, '중복'):
            self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/cache/tree/a.tmp', 'kind': 'cache', 'reproducible': True})

    def test_intermediate_requires_explicit_entry_and_disabled_history_preservation(self):
        self.write('.roadmusic/intermediate/frame.tmp')
        entry = self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/intermediate/frame.tmp', 'kind': 'intermediate'})
        blocked = self.manager.dispatch('preview', {'projectId': self.project_id, 'entryIds': [entry['id']]})
        self.assertEqual(blocked['fileCount'], 0)
        self.manager.dispatch('policy', {'projectId': self.project_id, 'preserveHistory': False})
        preview = self.manager.dispatch('preview', {'projectId': self.project_id, 'entryIds': [entry['id']]})
        self.assertEqual(preview['fileCount'], 1)
        self.assertEqual(self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})['removedFiles'], 1)

    def test_new_child_added_to_a_tracked_folder_invalidates_the_cleanup_plan(self):
        self.write('.roadmusic/cache/tree/old.tmp')
        entry = self.manager.dispatch('track', {'projectId': self.project_id, 'path': '.roadmusic/cache/tree', 'kind': 'cache', 'reproducible': True})
        preview = self.manager.dispatch('preview', {'projectId': self.project_id, 'entryIds': [entry['id']]})
        self.write('.roadmusic/cache/tree/new.tmp')
        result = self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})
        self.assertEqual(result['removedFiles'], 0)
        self.assertTrue(result['skipped'])
        self.assertTrue((self.project / '.roadmusic/cache/tree/old.tmp').exists())
        self.assertTrue((self.project / '.roadmusic/cache/tree/new.tmp').exists())

    def test_stale_registered_project_does_not_break_other_project_listing_or_auto_cleanup(self):
        stale = self.root / 'stale'; stale.mkdir()
        (stale / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'media': []}), encoding='utf-8')
        stale_id = self.manager.dispatch('register', {'project': str(stale)})['id']
        shutil.rmtree(stale)
        self.track_cache()
        listed = self.manager.dispatch('list', {})['projects']
        stale_row = next(item for item in listed if item['id'] == stale_id)
        self.assertFalse(stale_row['availability'])
        self.assertTrue(stale_row['protected'])
        preview = self.manager.dispatch('preview', {})
        self.assertTrue(any(item.get('projectId') == stale_id for item in preview['blocked']))
        result = self.manager.maybe_cleanup()
        self.assertEqual(result['removedFiles'], 0)
        self.assertTrue(any(item.get('projectId') == stale_id for item in result['skipped']))

    def test_empty_automatic_cleanup_does_not_create_a_plan(self):
        result = self.manager.maybe_cleanup(self.project_id)
        self.assertEqual(result['removedFiles'], 0)
        self.assertFalse((self.data / 'storage-plans').exists())

    def test_cli_envelope_is_one_json_line(self):
        import subprocess
        command = [sys.executable, str(SCRIPTS / 'storage_manager.py'), 'list', '--json', json.dumps({'projectId': self.project_id})]
        env = {**os.environ, 'ROADMUSIC_DATA_DIR': str(self.data)}
        output = subprocess.run(command, text=True, capture_output=True, env=env, check=True)
        self.assertEqual(len(output.stdout.splitlines()), 1)
        self.assertTrue(json.loads(output.stdout)['ok'])

    def test_cleanup_rejects_nonopaque_plan_id_and_audit_never_follows_history_symlink(self):
        with self.assertRaisesRegex(StorageError, 'planId'):
            self.manager.dispatch('cleanup', {'planId': '../' + 'a' * 48, 'confirm': True})
        entry = self.track_cache()
        preview = self.manager.dispatch('preview', {'projectId': self.project_id, 'entryIds': [entry['id']]})
        outside = self.root / 'outside-history'; outside.write_bytes(b'keep')
        history = self.project / '.roadmusic/history.jsonl'
        history.unlink(missing_ok=True)
        try:
            history.symlink_to(outside)
        except OSError as error:
            self.skipTest(f'symlink unavailable: {error}')
        result = self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})
        self.assertEqual(result['removedFiles'], 1)
        self.assertEqual(outside.read_bytes(), b'keep')
        self.assertTrue(history.is_symlink())
        self.assertFalse((self.project / '.roadmusic/cache/render.tmp').exists())

    def test_cleanup_records_intent_and_actual_result_after_registry_commit(self):
        entry = self.track_cache()
        preview = self.manager.dispatch('preview', {'projectId': self.project_id, 'entryIds': [entry['id']]})
        result = self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})
        self.assertEqual(result['removedFiles'], 1)
        events = self.manager.dispatch('history', {'projectId': self.project_id})['events']
        intent = next(item for item in reversed(events) if item['action'] == 'cleanup-intent')
        completed = next(item for item in reversed(events) if item['action'] == 'cleanup')
        self.assertEqual(intent['entries'][0]['relativePath'], '.roadmusic/cache/render.tmp')
        self.assertEqual(completed['removedFiles'], 1)
        self.assertEqual(completed['entries'][0]['relativePath'], '.roadmusic/cache/render.tmp')
        with self.assertRaisesRegex(StorageError, '유효한 정리 계획'):
            self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})

    def test_post_cleanup_audit_failure_returns_warning_after_registry_commit(self):
        entry = self.track_cache()
        preview = self.manager.dispatch('preview', {'projectId': self.project_id, 'entryIds': [entry['id']]})
        original = self.manager._audit
        def flaky(root, action, detail):
            if action == 'cleanup': raise OSError('audit write unavailable')
            return original(root, action, detail)
        with patch.object(self.manager, '_audit', side_effect=flaky):
            result = self.manager.dispatch('cleanup', {'planId': preview['planId'], 'confirm': True})
        self.assertEqual(result['removedFiles'], 1)
        self.assertTrue(result['warnings'])
        self.assertEqual(self.manager.dispatch('list', {'projectId': self.project_id})['projects'][0]['entries'], [])


if __name__ == '__main__':
    unittest.main()
