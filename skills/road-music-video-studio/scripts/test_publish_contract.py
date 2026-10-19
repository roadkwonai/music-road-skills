import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from studio import init_project, publish, Session
from result_records import feedback_history

class PublishContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': str(self.root / 'state'), 'ROADMUSIC_DELIVERY_ROOT': str(self.root)}); self.env.start(); self.addCleanup(self.env.stop)
        self.music = self.root / 'source.mp3'; self.music.write_bytes(b'source')
        self.project = self.root / 'project'; init_project(self.project, str(self.music))
        self.video = self.root / 'video.mp4'; self.video.write_bytes(b'video')
        self.manifest = self.root / 'manifest.json'

    def test_reopening_studio_preserves_existing_project_ownership(self):
        first = Session(self.project)
        first.management.claim_path(str(first.project), 'project', project_id=first.storage_project_id,
                                    group_id='a' * 64, workspace=str(self.root.resolve()))
        before = first.management.paths(project_id=first.storage_project_id)
        Session(self.project)
        self.assertEqual(first.management.paths(project_id=first.storage_project_id), before)

    def test_dry_run_does_not_write_and_reports_replacement(self):
        self.manifest.write_text(json.dumps({'video': [str(self.video)]}))
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = publish(self.project, str(self.manifest), dry_run=True)
        self.assertEqual(result['added'], [self.video.name])
        self.assertEqual(result['status'], 'preview')
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_artifacts_caption_association_and_legacy_feedback_preserve_sync(self):
        captions = self.root / 'captions.srt'; captions.write_text('1\n00:00:00,000 --> 00:00:01,000\n가사\n')
        report = self.root / 'qa.json'; report.write_text('{"result":"estimated"}')
        video_sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps({'sourceMusicSha256': hashlib.sha256(b'source').hexdigest(), 'video': [str(self.video)], 'captions': [{'path': str(captions), 'forVideoSha256': video_sha}], 'artifacts': [{'path': str(report), 'artifactType': 'validation'}]}))
        publish(self.project, str(self.manifest))
        session = Session(self.project)
        row = {'line': 9, 'start': .2, 'end': .8, 'status': 'estimated', 'evidence': '근거 부족', 'videoSha256': video_sha}
        session.save_feedback({'status': 'draft', 'note': '원문 유지', 'syncChecks': [row]})
        session.save_feedback({'status': 'needs-revision', 'note': '수정 요청'})
        self.assertEqual(session.feedback['syncChecks'][0]['status'], 'estimated')
        self.assertFalse((self.project / 'feedback-history.jsonl').exists())
        self.assertEqual(feedback_history(self.project, session.management)[-1]['note'], '원문 유지')
        self.assertEqual(json.loads((self.project / 'publish-diagnostic.json').read_text())['status'], 'published')

    def test_artifact_rejects_executable_and_caption_wrong_video(self):
        script = self.root / 'unsafe.html'; script.write_text('<script>bad</script>')
        for manifest in [{'artifacts': [{'path': str(script), 'artifactType': 'report'}]}, {'captions': [{'path': str(self.music), 'forVideoSha256': 'f'*64}]}]:
            self.manifest.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): publish(self.project, str(self.manifest), dry_run=True)

    def test_publish_links_existing_source_song_history_to_its_music_group_once(self):
        session = Session(self.project)
        source_id = hashlib.sha256(str(self.music.parent.resolve()).encode()).hexdigest()
        session.management.record_event('song-renamed', project_id=source_id, before={'title': '이전'}, after={'title': '현재'})
        self.manifest.write_text(json.dumps({'video': [str(self.video)]}))
        result = publish(self.project, str(self.manifest))
        group_id = result['workGroupId']
        events = session.management.events(group_id=group_id)['events']
        self.assertTrue(any(item['action'] == 'song-renamed' for item in events))
        self.assertEqual(len([item for item in events if item['action'] == 'song-published']), 1)
        publish(self.project, str(self.manifest))
        self.assertEqual(len([item for item in session.management.events(group_id=group_id)['events'] if item['action'] == 'song-published']), 1)

    def test_repeated_publication_with_title_keeps_one_version(self):
        self.manifest.write_text(json.dumps({'title': '최종 음악 제목', 'video': [str(self.video)]}))
        first = publish(self.project, str(self.manifest))
        second = publish(self.project, str(self.manifest))
        self.assertEqual(first['deliveryVersion']['id'], second['deliveryVersion']['id'])
        self.assertEqual(json.loads((self.project / 'studio-project.json').read_text())['name'], '최종 음악 제목')

    def test_explicit_final_audio_matching_source_uses_one_canonical_file_and_keeps_both_roles(self):
        final_audio = self.root / '손바닥의 바다.mp3'; final_audio.write_bytes(self.music.read_bytes())
        self.manifest.write_text(json.dumps({'sourceMusicSha256': hashlib.sha256(b'source').hexdigest(), 'audio': [str(final_audio)], 'video': [str(self.video)]}))

        preview = publish(self.project, str(self.manifest), dry_run=True)
        first = publish(self.project, str(self.manifest))
        second = publish(self.project, str(self.manifest))

        self.assertEqual(preview['mediaCount'], 3)
        self.assertFalse(preview['warnings'])
        self.assertEqual(first['deliveryVersion']['id'], second['deliveryVersion']['id'])
        media = {item['id']: item for item in Session(self.project)._registered()}
        self.assertEqual(media['music']['path'], media['music-0']['path'])
        self.assertEqual(Path(media['music']['path']).name, final_audio.name)
        self.assertEqual(len(list((self.root / 'Output').rglob('*.mp3'))), 1)
        group = Session(self.project).library.group(hashlib.sha256(b'source').hexdigest())
        final = next(item for item in group['files'] if item['kind'] == 'music')
        self.assertEqual(group['source']['path'], final['path'])

    def test_explicit_source_audio_alias_allows_music_only(self):
        self.manifest.write_text(json.dumps({'sourceMusicSha256': hashlib.sha256(b'source').hexdigest(), 'audio': [str(self.music)]}))

        result = publish(self.project, str(self.manifest))

        media = {item['id']: item for item in Session(self.project)._registered()}
        self.assertEqual(result['mediaCount'], 2)
        self.assertEqual(media['music']['path'], media['music-0']['path'])
        self.assertEqual(len(list((self.root / 'Output').rglob('*.mp3'))), 1)

    def test_explicit_audio_with_different_bytes_keeps_duplicate_name_guard(self):
        alternate = self.root / 'alternate'; alternate.mkdir()
        renamed_audio = alternate / 'source.mp3'; renamed_audio.write_bytes(b'different')
        self.manifest.write_text(json.dumps({'sourceMusicSha256': hashlib.sha256(b'source').hexdigest(), 'audio': [str(renamed_audio)]}))

        with self.assertRaisesRegex(ValueError, '같은 종류의 완성본 파일명이 중복됩니다'):
            publish(self.project, str(self.manifest))

    def test_publish_keeps_cache_until_a_real_final_delivery_is_probe_verified(self):
        session = Session(self.project)
        project_id = next(iter(session.storage_projects))
        cache = self.project / '.roadmusic/cache/render.tmp'; cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(b'cache')
        session.storage.dispatch('track', {'projectId': project_id, 'path': '.roadmusic/cache/render.tmp', 'kind': 'cache', 'reproducible': True})
        self.manifest.write_text(json.dumps({'sourceMusicSha256': hashlib.sha256(b'source').hexdigest(), 'video': [str(self.video)]}))

        result = publish(self.project, str(self.manifest))

        self.assertFalse(result['storageCompletion']['completed'])
        self.assertTrue(cache.exists())
        self.assertEqual(session.storage.dispatch('list', {'projectId': project_id})['projects'][0]['state'], 'editing')

    def test_change_reason_is_saved_in_the_delivery_version_and_is_bounded(self):
        self.manifest.write_text(json.dumps({'sourceMusicSha256': hashlib.sha256(b'source').hexdigest(), 'video': [str(self.video)], 'changeReason': '후렴 자막 동기화 보완'}))
        result = publish(self.project, str(self.manifest))
        self.assertEqual(result['deliveryVersion']['summary'], '후렴 자막 동기화 보완')
        self.manifest.write_text(json.dumps({'video': [str(self.video)], 'changeReason': 'x' * 4001}))
        with self.assertRaisesRegex(ValueError, 'changeReason'):
            publish(self.project, str(self.manifest), dry_run=True)

    def test_publish_refuses_while_the_workspace_structure_migration_is_prepared(self):
        marker = self.root / '.roadmusic' / 'structure.json'; marker.parent.mkdir()
        marker.write_text(json.dumps({'schemaVersion': 1, 'phase': 'prepared', 'owner': 'road-music', 'workspace': str(self.root)}), encoding='utf-8')
        self.manifest.write_text(json.dumps({'video': [str(self.video)]}))
        with self.assertRaisesRegex(ValueError, '구조 이전'):
            publish(self.project, str(self.manifest))
        self.assertTrue(self.video.is_file())
