import hashlib
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from delivery_store import DeliveryStore
from storage_file_removal import StorageFileRemoval
from storage_manager import StorageManager, StorageError
from work_library import WorkLibrary


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FileRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'workspace'; self.root.mkdir()
        self.data = self.root.parent / 'data'; self.manager = StorageManager(self.data)
        self.workspace = patch('storage_file_removal.is_workspace', return_value=True); self.workspace.start(); self.addCleanup(self.workspace.stop)
        self.source = self.root / 'source.mp3'; self.source.write_bytes(b'source')
        self.video = self.root / 'video.mp4'; self.video.write_bytes(b'video')
        self.lyrics = self.root / 'lyrics.txt'; self.lyrics.write_text('가사', encoding='utf-8')
        self.project = self.root / 'work'; self.project.mkdir()
        self.media = [{'id':'music','kind':'music','path':str(self.source),'name':self.source.name,'sha256':digest(self.source),'size':self.source.stat().st_size}, {'id':'video','kind':'video','path':str(self.video),'name':self.video.name,'sha256':digest(self.video),'size':self.video.stat().st_size}, {'id':'lyrics','kind':'lyrics','path':str(self.lyrics),'name':self.lyrics.name,'sha256':digest(self.lyrics),'size':self.lyrics.stat().st_size}]
        (self.project / 'studio-project.json').write_text(json.dumps({'schemaVersion':1,'name':'노래','media':self.media}), encoding='utf-8')
        self.store = DeliveryStore(self.root); version = self.store.publish(self.project, self.media, source_sha256=digest(self.source), title='노래')
        canonical = [{key:value for key,value in item.items() if key != 'bytes'} | {'size':item['bytes']} for item in version['media']]
        (self.project / 'studio-project.json').write_text(json.dumps({'schemaVersion':1,'name':'노래','media':canonical}), encoding='utf-8')
        self.library = WorkLibrary(self.data / 'video-studio-library.json'); self.group = self.library.register(self.project)
        self.manager.register({'project': str(self.project)})
        self.removal = StorageFileRemoval(self.manager, self.root)

    def test_preview_then_cleanup_removes_one_canonical_file_and_tombstones_it(self):
        item = next(item for item in self.group['files'] if item['kind'] == 'video')
        plan = self.removal.preview({'groupId':self.group['groupId'], 'fileId':item['id']})
        self.assertTrue(plan['eligible']); result = self.removal.cleanup({'planId':plan['planId'], 'confirm':True})
        self.assertEqual(result['removedFiles'], 1); self.assertEqual(result['metadataRemoved'], 1); self.assertFalse(Path(item['path']).exists())
        self.assertNotIn(item['id'], [value['id'] for value in self.library.group(self.group['groupId'])['files']])
        media = json.loads((self.project / 'studio-project.json').read_text())['media']
        self.assertFalse(any(value.get('id') == 'video' for value in media))
        with closing(sqlite3.connect(self.root / '.roadmusic/history.sqlite3')) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM delivery_file_tombstones').fetchone()[0], 1)
        listed = self.store.versions({'groupId': self.group['groupId']})['versions'][0]
        self.assertTrue(next(value for value in listed['files'] if value['kind'] == 'video')['deleted'])
        with self.assertRaisesRegex(ValueError, '제거된'):
            self.store.publish(self.project, self.media, source_sha256=digest(self.source), title='노래')

    def test_source_and_changed_file_are_protected(self):
        source_plan = self.removal.preview({'groupId':self.group['groupId'], 'fileId':self.group['source']['id']})
        self.assertFalse(source_plan['eligible']); self.assertIn('원음', source_plan['file']['protectedReason'])
        item = next(item for item in self.group['files'] if item['kind'] == 'video'); plan = self.removal.preview({'groupId':self.group['groupId'], 'fileId':item['id']})
        Path(item['path']).write_bytes(b'changed')
        with self.assertRaises(StorageError): self.removal.cleanup({'planId':plan['planId'], 'confirm':True})
        self.assertTrue(Path(item['path']).exists())

    def test_registered_project_input_blocks_only_that_referenced_final(self):
        item = next(item for item in self.group['files'] if item['kind'] == 'video')
        dependent = self.root / 'dependent'; dependent.mkdir()
        (dependent / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'media': [{'id': 'music', 'kind': 'music', 'path': item['path'], 'name': item['name'], 'sha256': item['sha256'], 'size': item['size']}]}), encoding='utf-8')
        self.manager.register({'project': str(dependent)})
        result = self.removal.preview({'groupId':self.group['groupId'], 'fileId':item['id']})
        self.assertFalse(result['eligible']); self.assertEqual(result['dependencies'][0]['type'], 'project-input')

    def test_last_final_remains_an_explicit_manual_removal_with_warning(self):
        video = next(item for item in self.group['files'] if item['kind'] == 'video')
        first = self.removal.preview({'groupId':self.group['groupId'], 'fileId':video['id']})
        self.removal.cleanup({'planId':first['planId'], 'confirm':True})
        remaining = self.library.group(self.group['groupId'])['files'][0]
        plan = self.removal.preview({'groupId':self.group['groupId'], 'fileId':remaining['id']})
        self.assertTrue(plan['eligible']); self.assertTrue(plan['warnings'])
        self.removal.cleanup({'planId':plan['planId'], 'confirm':True})
        self.assertEqual(self.library.group(self.group['groupId'])['files'], [])

    def test_database_write_failure_preserves_file_library_and_project_metadata(self):
        item = next(item for item in self.group['files'] if item['kind'] == 'video')
        plan = self.removal.preview({'groupId':self.group['groupId'], 'fileId':item['id']})
        before_library = self.library._read(); before_project = (self.project / 'studio-project.json').read_bytes()
        with patch.object(self.removal, '_begin_tombstones', side_effect=sqlite3.Error('write failed')):
            with self.assertRaisesRegex(StorageError, '복구'):
                self.removal.cleanup({'planId':plan['planId'], 'confirm':True})
        self.assertTrue(Path(item['path']).is_file())
        self.assertEqual(self.library._read(), before_library)
        self.assertEqual((self.project / 'studio-project.json').read_bytes(), before_project)

    def test_late_database_failure_rolls_back_sql_library_and_preserves_physical_files(self):
        item = next(item for item in self.group['files'] if item['kind'] == 'video')
        plan = self.removal.preview({'groupId': self.group['groupId'], 'fileId': item['id']})
        before_library = self.library._read()
        before_project = (self.project / 'studio-project.json').read_bytes()
        with patch.object(self.removal, '_finish_tombstones', side_effect=sqlite3.Error('write failed')):
            with self.assertRaisesRegex(StorageError, '복구'):
                self.removal.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertTrue(Path(item['path']).is_file())
        self.assertEqual(self.library._read(), before_library)
        self.assertEqual((self.project / 'studio-project.json').read_bytes(), before_project)
        self.assertFalse(any(row['action'] == 'file_removed' for row in self.manager.management_db.events()['events']))

    def test_failed_staging_unlink_restores_committed_sql_library_and_ownership(self):
        item = next(item for item in self.group['files'] if item['kind'] == 'video')
        self.manager.management_db.claim_path(item['path'], 'delivery-file', group_id=self.group['groupId'], kind='file')
        before_paths = self.manager.management_db.paths()
        plan = self.removal.preview({'groupId': self.group['groupId'], 'fileId': item['id']})
        before_library = self.library._read()
        unlink = Path.unlink
        def fail_staged(path, *args, **kwargs):
            if 'file-remove-staging' in path.parts:
                raise OSError('unlink failed')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', new=fail_staged):
            with self.assertRaisesRegex(StorageError, '복구'):
                self.removal.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertTrue(Path(item['path']).is_file())
        self.assertEqual(self.library._read(), before_library)
        self.assertEqual(self.manager.management_db.paths(), before_paths)
        self.assertFalse(any(row['action'] == 'file_removed' for row in self.manager.management_db.events()['events']))

    def test_shared_library_final_is_protected_without_an_active_project(self):
        item = next(item for item in self.group['files'] if item['kind'] == 'video')
        source = self.root / 'second-source.mp3'; source.write_bytes(b'second source')
        other = self.root / 'archived-project'; other.mkdir()
        media = json.loads((self.project / 'studio-project.json').read_text())['media']
        media[0] = {'id': 'music', 'kind': 'music', 'path': str(source), 'sha256': digest(source), 'size': source.stat().st_size}
        (other / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'media': media}), encoding='utf-8')
        second_group = self.library.register(other)
        plan = self.removal.preview({'groupId': self.group['groupId'], 'fileId': item['id']})
        self.assertFalse(plan['eligible'])
        self.assertTrue(any(ref.get('groupId') == second_group['groupId'] for ref in plan['dependencies']))
        self.assertTrue(Path(item['path']).is_file())


if __name__ == '__main__': unittest.main()
