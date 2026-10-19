from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import storage_packaging
from delivery_store import DeliveryStore
from work_library import WorkLibrary


class WorkspaceHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.kit, self.workspace, self.profile = [self.root / name for name in ('installed-kit', 'existing-work', 'profile')]
        for root in (self.kit, self.workspace):
            (root / 'cli').mkdir(parents=True)
            (root / 'cli/road-music.js').write_text('// fixture')
            (root / 'AGENTS.md').write_text('fixture')
            (root / 'package.json').write_text(json.dumps({'name': 'road-music', 'bin': {'road-music': 'cli/road-music.js'}}))
        (self.workspace / 'Output').mkdir()
        (self.workspace / '.roadmusic').mkdir()
        self.marker = self.workspace / '.roadmusic/structure.json'
        self.marker.write_text(json.dumps({'schemaVersion': 1, 'owner': 'road-music', 'policy': 'final-only', 'phase': 'completed', 'workspace': str(self.workspace), 'planId': 'a' * 48}))
        self.profile.mkdir()
        self.settings = self.profile / 'settings.json'
        self.settings.write_text(json.dumps({'deliveryRoot': str(self.workspace)}))
        self.env = {'ROADMUSIC_CLI_ROOT': str(self.kit), 'ROADMUSIC_DATA_DIR': str(self.profile)}

    def test_profile_workspace_survives_a_new_program_install_without_moving_history(self):
        self.assertEqual(storage_packaging.discover_trusted_root(env=self.env), self.workspace)
        self.settings.write_text('{}')
        self.assertEqual(storage_packaging.discover_trusted_root(env=self.env), self.kit)
        with patch.object(storage_packaging, 'TRUSTED_ROOT', self.kit):
            self.assertTrue(storage_packaging.is_workspace(self.kit))

    def test_invalid_or_alias_workspace_never_falls_back_to_a_different_installation(self):
        value = json.loads(self.marker.read_text()); value['workspace'] = str(self.kit)
        self.marker.write_text(json.dumps(value))
        self.assertIsNone(storage_packaging.discover_trusted_root(env=self.env))
        self.assertIsNone(storage_packaging.discover_trusted_root(env={**self.env, 'ROADMUSIC_DELIVERY_ROOT': str(self.profile)}))
        self.settings.unlink(); self.settings.symlink_to(self.kit / 'package.json')
        self.assertIsNone(storage_packaging.discover_trusted_root(env=self.env))

    def test_public_status_and_versions_use_the_existing_workspace(self):
        group, project = 'a' * 64, 'b' * 64
        with closing(DeliveryStore(self.workspace)._connect()) as connection, connection:
            connection.execute('INSERT INTO delivery_groups VALUES(?,?,?)', (group, 'kept song', group))
            connection.execute('INSERT INTO delivery_projects VALUES(?,?,?,?)', (project, group, 'c' * 64, 'kept project'))
            connection.execute('INSERT INTO delivery_versions(id,group_id,project_id,created_at,stamp,summary,reason,fingerprint,snapshot_json) VALUES(?,?,?,?,?,?,?,?,?)', ('d' * 64, group, project, '2026-10-20T00:00:00Z', '20261020-090000', 'kept', 'fixture', 'e' * 64, '{}'))
        script = Path(__file__).with_name('storage_manager.py')
        environment = {**os.environ, **self.env}; environment.pop('ROADMUSIC_DELIVERY_ROOT', None)
        def call(action, params):
            value = json.loads(subprocess.check_output([sys.executable, str(script), action, '--json', json.dumps(params)], env=environment, text=True))
            self.assertTrue(value['ok'], value)
            return value['result']
        status = call('status', {})
        self.assertIn(str(self.workspace), json.dumps(status))
        versions = call('versions', {'groupId': group})
        self.assertEqual(versions['total'], 1)
        self.assertEqual(versions['versions'][0]['summary'], 'kept')
        self.assertFalse((self.kit / '.roadmusic/history.sqlite3').exists())

    def test_unavailable_history_preserves_existing_delivery_claims(self):
        library = WorkLibrary(self.profile / 'video-studio-library.json')
        path, group = str(self.workspace / 'Output/kept.mp3'), 'a' * 64
        with library.management_db.transaction(write=True) as connection:
            library.management_db.claim_path(path, 'delivery-final', group_id=group, workspace=str(self.workspace), kind='file', connection=connection)
            for root in (None, self.kit, self.workspace):
                with patch.object(storage_packaging, 'TRUSTED_ROOT', root):
                    library._sync_delivery_ownership({group}, connection)
                self.assertEqual(connection.execute('SELECT count(*) FROM management_paths WHERE path=?', (path,)).fetchone()[0], 1)
            history = self.workspace / '.roadmusic/history.sqlite3'
            with closing(sqlite3.connect(history)) as incompatible, incompatible:
                incompatible.execute('CREATE TABLE unrelated(id)')
            with patch.object(storage_packaging, 'TRUSTED_ROOT', self.workspace):
                library._sync_delivery_ownership({group}, connection)
            self.assertEqual(connection.execute('SELECT count(*) FROM management_paths WHERE path=?', (path,)).fetchone()[0], 1)

    def test_verified_empty_history_can_remove_stale_delivery_claims(self):
        library = WorkLibrary(self.profile / 'video-studio-library.json')
        path, group = str(self.workspace / 'Output/stale.mp3'), 'a' * 64
        with closing(DeliveryStore(self.workspace)._connect()):
            pass
        with library.management_db.transaction(write=True) as connection:
            library.management_db.claim_path(path, 'delivery-final', group_id=group, workspace=str(self.workspace), kind='file', connection=connection)
            foreign = str(self.kit / 'Output/keep.mp3')
            library.management_db.claim_path(foreign, 'delivery-final', group_id=group, workspace=str(self.kit), kind='file', connection=connection)
            other_group = str(self.workspace / 'Output/other-group.mp3')
            library.management_db.claim_path(other_group, 'delivery-final', group_id='b' * 64, workspace=str(self.workspace), kind='file', connection=connection)
            with patch.object(storage_packaging, 'TRUSTED_ROOT', self.workspace):
                library._sync_delivery_ownership({group}, connection)
            self.assertEqual(connection.execute('SELECT count(*) FROM management_paths WHERE path=?', (other_group,)).fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM management_paths WHERE path=?', (path,)).fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM management_paths WHERE path=?', (foreign,)).fetchone()[0], 1)
