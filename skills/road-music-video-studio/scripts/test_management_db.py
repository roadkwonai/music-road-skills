import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from management_db import ManagementDB, ManagementDBError
from storage_manager import StorageManager
from work_library import WorkLibrary


class ManagementDBTests(unittest.TestCase):
    def setUp(self):
        workspace = patch('storage_packaging.TRUSTED_ROOT', None); workspace.start(); self.addCleanup(workspace.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.profile = self.root / 'profile'
        self.db = ManagementDB(self.profile)

    def test_read_without_database_does_not_create_profile(self):
        self.assertEqual(self.db.read_document('missing', fallback={'x': 1}), {'x': 1})
        self.assertEqual(self.db.events(), {'events': [], 'nextCursor': None})
        self.assertEqual(self.db.paths(), [])
        self.assertEqual(self.db.favorites(), {})
        self.assertFalse(self.profile.exists())

    def test_known_music_binds_earlier_unassigned_events_without_rewriting_other_groups(self):
        self.db.record_event('created', project_id='project', after={'title': '곡'})
        self.db.record_event('old-version', project_id='project', group_id='old', after={})
        self.db.record_event('other-project', project_id='other', after={})
        self.db.record_event('published', project_id='project', group_id='new', after={})
        rows = {item['action']: item for item in self.db.events()['events']}
        self.assertEqual(rows['created']['groupId'], 'old')
        self.assertEqual(rows['old-version']['groupId'], 'old')
        self.assertEqual(rows['published']['groupId'], 'new')
        self.assertIsNone(rows['other-project']['groupId'])

    def test_existing_database_reads_do_not_run_schema_or_change_files(self):
        self.db.write_document('example', {'x': 1})
        before = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in self.profile.iterdir()}
        with patch.object(self.db, '_schema', side_effect=AssertionError('read ran DDL')):
            self.assertEqual(self.db.read_document('example'), {'x': 1})
            self.db.events(); self.db.paths()
        after = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in self.profile.iterdir()}
        self.assertEqual(after, before)

    def test_migration_preserves_json_and_backup_and_imports_only_once(self):
        self.profile.mkdir(); source = self.profile / 'legacy.json'
        source.write_text('{"value": 1}', encoding='utf-8'); original = source.read_bytes()
        self.assertEqual(self.db.migrate_legacy('legacy', source), {'value': 1})
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(source.with_name('legacy.json.migration-backup').read_bytes(), original)
        source.write_text('{"value": 2}', encoding='utf-8')
        self.assertEqual(self.db.migrate_legacy('legacy', source), {'value': 1})
        with self.db.transaction() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM management_documents').fetchone()[0], 1)

    def test_invalid_legacy_does_not_create_database(self):
        self.profile.mkdir(); source = self.profile / 'legacy.json'; source.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ManagementDBError):
            self.db.migrate_legacy('legacy', source)
        self.assertFalse(self.db.path.exists())
        self.assertFalse(source.with_name('legacy.json.migration-backup').exists())

    def test_failed_migration_keeps_backup_and_can_retry(self):
        self.profile.mkdir(); source = self.profile / 'legacy.json'; source.write_text('{"value": 1}', encoding='utf-8')
        schema = self.db._schema
        def fail_insert(connection):
            schema(connection)
            connection.execute("CREATE TRIGGER fail_import BEFORE INSERT ON management_documents BEGIN SELECT RAISE(ABORT, 'test'); END")
        with patch.object(self.db, '_schema', side_effect=fail_insert):
            with self.assertRaises(ManagementDBError):
                self.db.migrate_legacy('legacy', source)
        self.assertEqual(source.with_name('legacy.json.migration-backup').read_bytes(), source.read_bytes())
        self.assertEqual(self.db.migrate_legacy('legacy', source), {'value': 1})

    def test_profile_transaction_rolls_back_documents_events_and_ownership(self):
        manager = StorageManager(self.profile); library = WorkLibrary(self.profile / 'video-studio-library.json')
        manager._save(manager._empty()); library._save(library._empty())
        original = manager._read()
        with self.assertRaisesRegex(RuntimeError, 'rollback'):
            with self.db.transaction(write=True) as connection:
                registry = manager._read(); registry['leases']['project'] = {'pid': 1}
                manager._save(registry, connection=connection)
                library._save(library._empty(), connection=connection)
                self.db.claim_path(str(self.root / 'project'), 'project', project_id='project', connection=connection)
                self.db.record_event('project_updated', project_id='project', connection=connection)
                raise RuntimeError('rollback')
        self.assertEqual(manager._read(), original)
        self.assertEqual(library._read(), library._empty())
        self.assertEqual(self.db.paths(), [])
        self.assertEqual(self.db.events()['events'], [])

    def test_project_drop_rolls_back_with_caller_transaction(self):
        self.db.claim_path(str(self.root / 'project'), 'project', project_id='project')
        self.db.record_event('project_updated', project_id='project')
        with self.assertRaises(RuntimeError):
            with self.db.transaction(write=True) as connection:
                self.db.drop_project('project', connection=connection)
                raise RuntimeError('rollback')
        self.assertEqual(len(self.db.paths()), 1)
        self.assertEqual(len(self.db.events()['events']), 1)

    def test_storage_list_without_profile_does_not_create_files(self):
        result = StorageManager(self.profile).list({})
        self.assertEqual(result['projects'], [])
        self.assertFalse(self.profile.exists())

    def test_storage_migrate_imports_registry_and_library_with_backups(self):
        self.profile.mkdir()
        manager = StorageManager(self.profile)
        manager.registry_path.write_text(json.dumps(manager._empty()), encoding='utf-8')
        library = self.profile / 'video-studio-library.json'
        library.write_text(json.dumps(WorkLibrary._empty()), encoding='utf-8')
        result = manager.migrate_management_metadata()
        self.assertEqual(result['library']['groups'], 0)
        self.assertEqual(result['registry']['projects'], 0)
        for source in (manager.registry_path, library):
            self.assertEqual(source.with_name(source.name + '.migration-backup').read_bytes(), source.read_bytes())
        self.assertEqual(manager.migrate_management_metadata(), result)

    def test_invalid_library_prevents_partial_registry_migration(self):
        self.profile.mkdir()
        manager = StorageManager(self.profile)
        manager.registry_path.write_text(json.dumps(manager._empty()), encoding='utf-8')
        library = self.profile / 'video-studio-library.json'; library.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError): manager.migrate_management_metadata()
        self.assertFalse(self.db.path.exists())

    def test_project_listing_uses_index_without_walk_or_profile_writes(self):
        manager = StorageManager(self.profile)
        project = self.root / 'project'; project.mkdir()
        (project / 'studio-project.json').write_text('{"schemaVersion":1,"media":[]}', encoding='utf-8')
        unknown = project / 'unknown.txt'; unknown.write_text('unknown', encoding='utf-8')
        project_id = manager.register({'project': str(project)})['id']
        before = {str(path): (path.stat().st_size, path.stat().st_mtime_ns) for path in self.profile.rglob('*') if path.is_file()}
        with patch('storage_manager.os.walk', side_effect=AssertionError('list walked disk')):
            listed = manager.list({'projectId': project_id})['projects'][0]
            manager.history({'projectId': project_id})
        self.assertFalse(listed['unknownScanRequired'])
        self.assertIn('unknown.txt', [item['relativePath'] for item in listed['unmanagedEntries']])
        after = {str(path): (path.stat().st_size, path.stat().st_mtime_ns) for path in self.profile.rglob('*') if path.is_file()}
        self.assertEqual(after, before)
        with self.db.transaction(write=True) as connection:
            connection.execute("DELETE FROM management_documents WHERE name LIKE 'workspace-scan:%'")
            connection.execute('DELETE FROM storage_tracking_files')
        with patch('storage_manager.os.walk', side_effect=AssertionError('list walked disk')):
            unindexed = manager.list({'projectId': project_id})['projects'][0]
        self.assertTrue(unindexed['unknownScanRequired'])
        self.assertIsNone(unindexed['readonlyUnknownBytes'])

    def test_legacy_history_remains_readable_without_importing_or_changing_it(self):
        manager = StorageManager(self.profile)
        project = self.root / 'project'; project.mkdir()
        (project / 'studio-project.json').write_text('{"schemaVersion":1,"media":[]}', encoding='utf-8')
        project_id = manager.register({'project': str(project)})['id']
        legacy = project / '.roadmusic/history.jsonl'
        legacy.write_text('{"action":"legacy-event","at":"2020-01-01T00:00:00Z"}\n', encoding='utf-8')
        original = legacy.read_bytes()
        history = manager.history({'projectId': project_id})
        self.assertTrue(any(item['action'] == 'legacy-event' for item in history['events']))
        self.assertEqual(legacy.read_bytes(), original)
        self.assertFalse(any(item['action'] == 'legacy-event' for item in self.db.events()['events']))

    def test_project_drop_clears_its_sql_index_but_preserves_shared_workspace(self):
        manager = StorageManager(self.profile)
        project = self.root / 'project'; project.mkdir()
        (project / 'studio-project.json').write_text('{"schemaVersion":1,"media":[]}', encoding='utf-8')
        project_id = manager.register({'project': str(project)})['id']
        self.db.claim_path(str(self.root), 'program', workspace=str(self.root))
        self.db.write_document('workspace-scan:' + hashlib.sha256(str(self.root).encode()).hexdigest(), {'shared': True})
        with self.db.transaction() as connection:
            self.assertTrue(connection.execute('SELECT count(*) FROM storage_tracking_files WHERE workspace=?', (str(project),)).fetchone()[0])
        result = self.db.drop_project(project_id)
        self.assertGreater(result['removedIndexFiles'], 0)
        self.assertEqual(result['removedDocuments'], 2)
        with self.db.transaction() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM storage_tracking_files WHERE workspace=?', (str(project),)).fetchone()[0], 0)
        self.assertEqual(len(self.db.paths(workspace=str(self.root))), 1)
        self.assertIsNotNone(self.db.read_document('workspace-scan:' + hashlib.sha256(str(self.root).encode()).hexdigest()))

    def test_migration_repairs_35_registered_final_file_owners_idempotently(self):
        from storage_tracking import StorageTracking
        from test_work_library import write_project
        workspace = self.root / 'workspace'; workspace.mkdir()
        output = workspace / 'Output'; output.mkdir()
        source = self.root / 'external-source.mp3'; source.write_bytes(b'source')
        finals = []
        for index in range(35):
            video = output / f'final-{index}.mp4'; video.write_bytes(f'video-{index}'.encode())
            finals.append(video)
        project = write_project(workspace, 'project', source, [('video', path, {}) for path in finals])
        fixture = WorkLibrary(self.root / 'fixture-profile/library.json'); fixture.register(project)
        self.profile.mkdir()
        manager = StorageManager(self.profile)
        registry = manager._empty(); project_id = manager._project_id(project)
        registry['projects'][project_id] = {'path': str(project)}
        manager.registry_path.write_text(json.dumps(registry), encoding='utf-8')
        (self.profile / 'video-studio-library.json').write_text(json.dumps(fixture._read()), encoding='utf-8')
        with patch('storage_packaging.TRUSTED_ROOT', workspace), patch('storage_tracking.is_workspace', return_value=True):
            manager.migrate_management_metadata()
            tracking = StorageTracking(manager, workspace)
            indexed = tracking.list({'refreshWorkspace': True})
            known = {item['path'] for item in indexed['knownOwnership']['items']}
            self.assertTrue({str(path) for path in finals}.issubset(known))
            self.assertEqual(len([item for item in manager.management_db.paths(workspace=str(workspace)) if item['role'] == 'final']), 35)
            source_claim = next(item for item in manager.management_db.paths() if item['path'] == str(source))
            self.assertEqual(source_claim['role'], 'source'); self.assertIsNone(source_claim['workspace'])
            with manager.management_db.transaction(write=True) as connection:
                documents = connection.execute('SELECT count(*) FROM management_documents').fetchone()[0]
                connection.execute("DELETE FROM management_paths WHERE role IN ('source','final','artifact','project')")
            manager.migrate_management_metadata()
            repaired = {item['path']: item for item in manager.management_db.paths()}
            self.assertTrue({str(path) for path in finals}.issubset(repaired))
            self.assertEqual(repaired[str(project)]['projectId'], project_id)
            self.assertEqual(repaired[str(project)]['groupId'], hashlib.sha256(b'source').hexdigest())
            with manager.management_db.transaction() as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM management_documents').fetchone()[0], documents)
            self.assertTrue({str(path) for path in finals}.issubset({item['path'] for item in tracking.list({})['knownOwnership']['items']}))

    def test_library_save_ownership_is_atomic_and_preserves_shared_source(self):
        from test_work_library import write_project
        workspace = self.root / 'workspace'; workspace.mkdir()
        source = workspace / 'source.mp3'; source.write_bytes(b'source')
        shared = workspace / 'shared.mp3'; shared.write_bytes(b'shared final and input')
        video = workspace / 'video.mp4'; video.write_bytes(b'video')
        first = write_project(workspace, 'first', source, [('music', shared, {})])
        second = write_project(workspace, 'second', shared, [('video', video, {})])
        library = WorkLibrary(self.profile / 'video-studio-library.json')
        with patch('storage_packaging.TRUSTED_ROOT', workspace):
            first_group = library.register(first); second_group = library.register(second)
            before = library._read(); claims = library.management_db.paths()
            changed = library._read(); changed['groups'][second_group['groupId']]['title'] = 'changed title'
            with patch.object(library.management_db, 'claim_path', side_effect=ManagementDBError('claim failed')):
                with self.assertRaisesRegex(ValueError, 'claim failed'): library._save(changed)
            self.assertEqual(library._read(), before)
            self.assertEqual(library.management_db.paths(), claims)
            remaining = library._read(); remaining['groups'].pop(first_group['groupId'])
            library._save(remaining)
            current = {item['path']: item for item in library.management_db.paths()}
            self.assertEqual(current[str(shared)]['role'], 'source')
            self.assertEqual(current[str(shared)]['groupId'], second_group['groupId'])
            self.assertNotIn(str(source), current)

    def test_past_delivery_paths_with_same_hash_remain_owned_after_migration_and_save(self):
        from delivery_store import DeliveryStore
        from storage_tracking import StorageTracking
        from test_work_library import write_project
        workspace = self.root / 'workspace'; workspace.mkdir()
        source = self.root / 'source.mp3'; source.write_bytes(b'source')
        video = self.root / 'video.mp4'; video.write_bytes(b'same video')
        project = write_project(workspace, 'project', source, [('video', video, {})])
        media = json.loads((project / 'studio-project.json').read_text())['media']
        store = DeliveryStore(workspace)
        first = store.publish(project, media, source_sha256=hashlib.sha256(b'source').hexdigest(), title='song')
        (project / 'feedback.json').write_text('{"note":"new review"}', encoding='utf-8')
        second = store.publish(project, media, source_sha256=hashlib.sha256(b'source').hexdigest(), title='song')
        old_video = next(item['path'] for item in first['media'] if item['kind'] == 'video')
        new_video = next(item['path'] for item in second['media'] if item['kind'] == 'video')
        self.assertNotEqual(old_video, new_video)
        foreign_source = self.root / 'foreign-source.mp3'; foreign_source.write_bytes(b'foreign source')
        foreign_project = write_project(workspace, 'foreign-project', foreign_source, [('video', video, {})])
        foreign_media = json.loads((foreign_project / 'studio-project.json').read_text())['media']
        foreign = store.publish(foreign_project, foreign_media, source_sha256=hashlib.sha256(b'foreign source').hexdigest(), title='foreign song')
        foreign_paths = {item['path'] for item in foreign['media']}
        (project / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'media': second['media']}), encoding='utf-8')
        library = WorkLibrary(self.profile / 'video-studio-library.json')
        library.register(project)
        manager = StorageManager(self.profile)
        with patch('storage_packaging.TRUSTED_ROOT', workspace), patch('storage_tracking.is_workspace', return_value=True):
            manager.migrate_management_metadata()
            tracking = StorageTracking(manager, workspace)
            known = {item['path'] for item in tracking.list({'refreshWorkspace': True})['knownOwnership']['items']}
            self.assertTrue({old_video, new_video}.issubset(known))
            library._save(library._read())
            claims = {item['path']: item for item in manager.management_db.paths()}
            self.assertEqual(claims[old_video]['role'], 'delivery-final')
            self.assertEqual(claims[old_video]['projectId'], first['logicalProjectId'])
            self.assertEqual(claims[new_video]['role'], 'final')
            self.assertTrue(foreign_paths.isdisjoint(claims))
            history_mtime = store.history.stat().st_mtime_ns
            with patch('work_library._sha256', side_effect=AssertionError('ownership recalculated media hash')):
                manager.migrate_management_metadata()
            self.assertEqual(store.history.stat().st_mtime_ns, history_mtime)
            self.assertTrue({old_video, new_video}.issubset({item['path'] for item in tracking.list({})['knownOwnership']['items']}))
            missing_source = next(item['path'] for item in first['media'] if item['id'] == 'music')
            Path(missing_source).unlink()
            with sqlite3.connect(store.history) as delivery:
                delivery.execute("CREATE TABLE delivery_file_tombstones(version_id TEXT,kind TEXT,name TEXT,path TEXT,state TEXT)")
                delivery.execute("INSERT INTO delivery_file_tombstones VALUES(?,?,?,?,?)", (first['id'], 'video', Path(old_video).name, old_video, 'applied'))
            delivery.close()
            manager.migrate_management_metadata()
            live_claims = {item['path'] for item in manager.management_db.paths()}
            self.assertNotIn(old_video, live_claims)
            self.assertNotIn(missing_source, live_claims)
            self.assertIn(new_video, live_claims)

    def test_existing_project_registration_does_not_rescan_or_write_index(self):
        manager = StorageManager(self.profile)
        project = self.root / 'project'; project.mkdir()
        (project / 'studio-project.json').write_text('{"schemaVersion":1,"media":[]}', encoding='utf-8')
        first = manager.register({'project': str(project)})
        before = self.db.path.stat().st_mtime_ns
        with patch('storage_scan.WorkspaceScan.scan', side_effect=AssertionError('repeat register rescanned')), patch('storage_manager.os.walk', side_effect=AssertionError('repeat register walked')):
            repeated = manager.register({'project': str(project)})
        self.assertEqual(repeated['id'], first['id'])
        self.assertEqual(self.db.path.stat().st_mtime_ns, before)
        with self.db.transaction(write=True) as connection:
            connection.execute("DELETE FROM management_documents WHERE name LIKE 'workspace-scan:%'")
        before_unindexed = self.db.path.stat().st_mtime_ns
        with patch('storage_scan.WorkspaceScan.scan', side_effect=AssertionError('repeat register rescanned')):
            pending = manager.register({'project': str(project)})
        self.assertTrue(pending['unknownScanRequired'])
        self.assertEqual(self.db.path.stat().st_mtime_ns, before_unindexed)

    def test_empty_profile_library_never_reads_default_delivery_database(self):
        library = WorkLibrary(self.profile / 'video-studio-library.json')
        trusted = self.root / 'trusted-workspace'; trusted.mkdir()
        history = trusted / '.roadmusic/history.sqlite3'
        connect = sqlite3.connect
        def isolated_connection(target, *args, **kwargs):
            if str(target).startswith(history.as_uri()):
                raise AssertionError('empty profile accessed another workspace delivery history')
            return connect(target, *args, **kwargs)
        with patch('storage_packaging.TRUSTED_ROOT', trusted), patch('work_library.sqlite3.connect', side_effect=isolated_connection):
            library._save(library._empty())
            StorageManager(self.profile).migrate_management_metadata()
        self.assertEqual(library.management_db.paths(), [])


if __name__ == '__main__': unittest.main()
