import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from delivery_store import DeliveryStore, record_song


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class DeliveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / 'work' / 'project'; self.project.mkdir(parents=True)
        self.source = self.root / 'source.mp3'; self.source.write_bytes(b'source')
        self.video = self.root / 'video.mp4'; self.video.write_bytes(b'video-a')
        self.lyrics = self.root / 'lyrics.txt'; self.lyrics.write_text('첫 줄\n', encoding='utf-8')
        (self.project / 'plan.json').write_text('{}', encoding='utf-8')
        (self.project / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'name': '첫 노래', 'mode': 'showreel-motion', 'media': []}), encoding='utf-8')
        (self.project / 'selection.json').write_text(json.dumps({'styleId': 'neon'}), encoding='utf-8')
        (self.project / 'feedback.json').write_text(json.dumps({'status': 'approved', 'note': '색감 보완'}), encoding='utf-8')
        self.store = DeliveryStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def media(self, video=None):
        video = video or self.video
        return [
            {'id': 'music', 'kind': 'music', 'path': str(self.source), 'name': self.source.name, 'sha256': digest(self.source), 'size': self.source.stat().st_size},
            {'id': 'video-0', 'kind': 'video', 'path': str(video), 'name': video.name, 'sha256': digest(video), 'size': video.stat().st_size},
            {'id': 'lyrics-0', 'kind': 'lyrics', 'path': str(self.lyrics), 'name': self.lyrics.name, 'sha256': digest(self.lyrics), 'size': self.lyrics.stat().st_size},
            {'id': 'artifact-0', 'kind': 'artifact', 'path': str(self.project / 'plan.json'), 'name': 'plan.json', 'sha256': hashlib.sha256(b'{}').hexdigest(), 'size': 2, 'artifactType': 'plan'},
        ]

    def test_publish_keeps_only_delivery_files_and_artifact_metadata(self):
        result = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래', reason='색감 보완', created_at='2026-10-19T03:04:05+09:00')
        self.assertEqual(result['stamp'], '20261019-030405')
        self.assertEqual({item['kind'] for item in result['files']}, {'music', 'video', 'lyrics'})
        self.assertTrue(all(Path(item['path']).is_file() for item in result['files']))
        self.assertTrue(all('Output' in Path(item['path']).parts for item in result['files']))
        self.assertFalse(any(path.name == 'plan.json' for path in self.root.rglob('*') if path.is_file() and 'Output' in path.parts))
        self.assertEqual(self.store.versions({'groupId': digest(self.source)})['total'], 1)

    def test_same_payload_is_idempotent_and_same_second_uses_sequence(self):
        created = '2026-10-19T03:04:05+09:00'
        first = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래', created_at=created)
        again = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래', created_at=created)
        self.assertEqual(first['id'], again['id'])
        self.assertEqual(sorted(first['media'], key=lambda item: item['path']), sorted(again['media'], key=lambda item: item['path']))
        second_video = self.root / 'video-b.mp4'; second_video.write_bytes(b'video-b')
        second = self.store.publish(self.project, self.media(second_video), source_sha256=digest(self.source), title='첫 노래', created_at=created)
        self.assertEqual(second['stamp'], '20261019-030405-2')
        diff = self.store.diff({'fromId': first['id'], 'toId': second['id']})
        self.assertTrue(diff['fileChanges'])
        listed = self.store.versions({'groupId': digest(self.source), 'projectId': second['projectId']})['versions']
        self.assertEqual(listed[0]['id'], second['id'])
        self.assertEqual(listed[0]['changes'], diff['changes'])

    def test_bad_or_linked_source_never_creates_delivery(self):
        linked = self.root / 'linked.mp4'; linked.symlink_to(self.video)
        before = list((self.root / 'Output').glob('**/*')) if (self.root / 'Output').exists() else []
        bad = self.media(); bad[1] = {**bad[1], 'path': str(linked)}
        with self.assertRaisesRegex(ValueError, '심볼릭'):
            self.store.publish(self.project, bad, source_sha256=digest(self.source), title='첫 노래')
        self.assertEqual(before, list((self.root / 'Output').glob('**/*')) if (self.root / 'Output').exists() else [])

    def test_diffs_include_reason_and_text_snapshot(self):
        first = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래', reason='')
        self.lyrics.write_text('첫 줄\n둘째 줄\n', encoding='utf-8')
        second = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래', reason='가사 보완')
        diff = self.store.diff({'fromId': first['id'], 'toId': second['id']})
        self.assertTrue(any('reason' in item['field'] or 'lyrics' in item['field'] for item in diff['changes']))

    def test_authored_motion_and_composition_changes_are_kept_in_sql_version_diffs(self):
        (self.project / 'reel').mkdir()
        scene = self.project / 'reel/scenes.js'; scene.write_text('drawWindow();')
        composition = self.project / 'composition.json'; composition.write_text(json.dumps({'concept': '창'}))
        first = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래')
        scene.write_text('drawRoad();'); composition.write_text(json.dumps({'concept': '길'}))
        second = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래', reason='영상 연출 변경')
        changes = self.store.diff({'fromId': first['id'], 'toId': second['id']})['changes']
        self.assertTrue(any(item['before'] == 'drawWindow();' and item['after'] == 'drawRoad();' for item in changes))
        self.assertTrue(any(item['before'] == '창' and item['after'] == '길' for item in changes))

    def test_history_link_and_unverified_song_metadata_are_rejected(self):
        self.store.history.parent.mkdir(parents=True)
        self.store.history.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, '심볼릭'):
            self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래')
        self.store.history.unlink()
        (self.project / 'meta.json').write_text(json.dumps({'status': 'running', 'audio': str(self.source)}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '완료된'):
            record_song(self.root, self.project)

    def test_record_song_keeps_only_the_verified_primary_audio(self):
        song = self.root / 'song'; song.mkdir()
        primary, stale = song / 'final.mp3', song / 'older.wav'
        primary.write_bytes(b'final'); stale.write_bytes(b'older')
        (song / 'meta.json').write_text(json.dumps({'status': 'done', 'audio': str(primary), 'mp3': str(stale), 'title': '완성 음악'}), encoding='utf-8')
        result = record_song(self.root, song)
        self.assertEqual([(item['kind'], Path(item['path']).read_bytes()) for item in result['files']], [('music', b'final')])

    def test_new_source_keeps_prior_project_versions_in_their_original_group(self):
        old = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래')
        logical = old['logicalProjectId']
        self.source.write_bytes(b'new-source')
        new = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='새 원음')
        self.assertNotEqual(old['groupId'], new['groupId'])
        self.assertNotEqual(old['projectId'], new['projectId'])
        self.assertEqual(new['logicalProjectId'], logical)
        self.assertEqual(self.store.versions({'groupId': old['groupId']})['total'], 1)
        self.assertEqual(self.store.versions({'groupId': new['groupId']})['total'], 1)

    def test_idempotent_retry_rejects_a_missing_or_changed_canonical_copy(self):
        first = self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래')
        Path(first['files'][0]['path']).unlink()
        with self.assertRaisesRegex(ValueError, '기존 완성본'):
            self.store.publish(self.project, self.media(), source_sha256=digest(self.source), title='첫 노래')
        self.assertTrue(self.source.is_file())
        self.assertTrue(self.video.is_file())


if __name__ == '__main__':
    unittest.main()
