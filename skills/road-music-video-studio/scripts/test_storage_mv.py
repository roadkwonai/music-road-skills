import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from storage_manager import StorageError, StorageManager
from storage_mv import MVStorage


class ScanFixture:
    def __init__(self, root, data_dir): self.root = root
    def load(self, scan_id):
        if scan_id != 'a' * 48: raise StorageError('scan required', 'scan_required')
        return {'scanId': scan_id, 'fingerprint': 'stable', 'complete': True, 'expiresAt': 2 ** 31}


class MVStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name, 'repo'); self.root.mkdir()
        self.work = self.root / '.harness' / 'work'; self.work.mkdir(parents=True)
        self.source = Path(self.tmp.name, 'source.flac'); self.source.write_bytes(b'original-audio')
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.manager = StorageManager(Path(self.tmp.name, 'data'))
        self.patches = [patch('storage_mv.is_workspace', return_value=True), patch('storage_maintenance.is_workspace', return_value=True), patch('storage_mv.WorkspaceScan', ScanFixture),
                        patch('storage_mv.subprocess.run', return_value=type('L', (), {'returncode': 1, 'stdout': '', 'stderr': ''})())]
        for value in self.patches: value.start(); self.addCleanup(value.stop)
        self.storage = MVStorage(self.manager, self.root)

    def project(self, name='mv'):
        root = self.work / name; root.mkdir()
        (root / 'input.json').write_text(json.dumps({'source_audio': {'audio': str(self.source), 'sha256': self.digest, 'title': '원곡'}}))
        (root / 'production-plan.json').write_text(json.dumps({'objective': 'MV 제작', 'tasks': ['animatic']}))
        (root / 'preproduction').mkdir(); (root / 'preproduction' / 'animatic.mov').write_bytes(b'animatic')
        (root / 'render').mkdir(); (root / 'render' / 'master.mp4').write_bytes(b'master')
        return root

    def showreel(self, name='showreel-lumi4-prism-20261017'):
        root = self.root / 'Output' / name; root.mkdir(parents=True)
        meta = {'width': 1920, 'height': 1080, 'fps': 30, 'duration': 12.0, 'title': '쇼릴 원곡'}
        (root / 'project.json').write_text(json.dumps(meta)); (root / 'timeline.json').write_text(json.dumps(meta))
        (root / 'audio').mkdir(); (root / 'audio' / 'source-verification.json').write_text(json.dumps({'sourceAudio': str(self.source), 'sourceSha256': self.digest}))
        (root / 'assets').mkdir(); (root / 'assets' / 'provenance.json').write_text(json.dumps([{'sha256': 'a' * 64}]))
        (root / 'assets' / 'generation-sources.json').write_text(json.dumps([{'source': '/generated/source.png'}]))
        (root / 'final.mp4').write_bytes(b'showreel-render')
        return root

    def scan(self): return 'a' * 48

    def test_lists_only_nested_source_with_production_marker(self):
        valid = self.project()
        invalid = self.work / 'lookdev'; invalid.mkdir(); (invalid / 'large.mov').write_bytes(b'x')
        values = self.storage.list({})['projects']
        self.assertEqual([value['path'] for value in values], [str(valid.resolve())])
        self.assertFalse(values[0]['blocked'])
        self.assertEqual(values[0]['title'], '원곡')

    def test_exact_showreel_profile_is_listed_and_can_be_removed_without_source(self):
        root = self.showreel(); values = self.storage.list({})['projects']
        self.assertEqual(len(values), 1); self.assertEqual(values[0]['kind'], 'ai-showreel-mv')
        plan = self.storage.preview({'scanId': self.scan(), 'projectIds': [values[0]['id']]})
        result = self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(result['removedProjects'], 1); self.assertFalse(root.exists()); self.assertTrue(self.source.exists())

    def test_unknown_output_and_changed_showreel_source_are_protected(self):
        unknown = self.root / 'Output' / 'other'; unknown.mkdir(parents=True)
        (unknown / 'project.json').write_text(json.dumps({'width': 1, 'height': 1, 'fps': 1, 'duration': 1}))
        root = self.showreel(); self.source.write_bytes(b'changed-source')
        values = self.storage.list({})['projects']
        self.assertEqual(len(values), 1); self.assertTrue(values[0]['blocked']); self.assertTrue(root.exists())

    def test_preview_and_cleanup_removes_mv_root_but_keeps_source_and_external_target(self):
        project = self.project()
        external = Path(self.tmp.name, 'external.txt'); external.write_text('keep')
        os.symlink(external, project / 'reference-link')
        value = self.storage.list({})['projects'][0]
        plan = self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id']]})
        result = self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertFalse(project.exists())
        self.assertTrue(self.source.exists())
        self.assertEqual(external.read_text(), 'keep')
        self.assertEqual(result['removedProjects'], 1)
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})

    def test_changed_file_stale_plan_does_not_delete(self):
        project = self.project(); value = self.storage.list({})['projects'][0]
        plan = self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id']]})
        (project / 'render' / 'master.mp4').write_bytes(b'changed')
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertTrue(project.exists())

    def test_second_selected_project_change_keeps_first_project(self):
        first = self.project('first'); second = self.project('second')
        values = self.storage.list({})['projects']
        plan = self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id'] for value in values]})
        (second / 'render' / 'master.mp4').write_bytes(b'changed')
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertTrue(first.exists())

    def test_source_change_after_first_removal_keeps_later_project(self):
        self.project('first'); second = self.project('second')
        values = self.storage.list({})['projects']
        plan = self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id'] for value in values]})
        original = self.storage._remove_project; calls = 0
        def remove(*args):
            nonlocal calls
            calls += 1; result = original(*args)
            if calls == 1: self.source.write_bytes(b'changed-after-first')
            return result
        with patch.object(self.storage, '_remove_project', side_effect=remove):
            result = self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['removedProjects'], 1)
        self.assertTrue(second.exists())

    def test_cross_project_hardlink_is_protected_at_preview(self):
        first = self.project('first'); second = self.project('second')
        (first / 'render' / 'shared.bin').write_bytes(b'shared')
        os.link(first / 'render' / 'shared.bin', second / 'render' / 'shared.bin')
        values = self.storage.list({})['projects']
        with self.assertRaises(StorageError) as caught:
            self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id'] for value in values]})
        self.assertEqual(caught.exception.code, 'shared_hardlink')

    def test_partial_failure_reports_actual_deleted_prefix(self):
        self.project(); value = self.storage.list({})['projects'][0]
        plan = self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id']]})
        original = self.storage._unlink; calls = 0
        def unlink(*args):
            nonlocal calls
            calls += 1
            if calls == 2: raise StorageError('forced failure')
            return original(*args)
        with patch.object(self.storage, '_unlink', side_effect=unlink):
            partial = self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(partial['status'], 'partial')
        self.assertGreater(partial['removedFiles'], 0)
        self.assertGreater(partial['freedBytes'], 0)

    def test_root_replacement_is_rejected_by_dirfd_check(self):
        project = self.project(); candidate = self.storage._candidate(project)
        item = next(value for value in candidate['entries'] if value['relativePath'] == 'input.json')
        moved = self.work / 'old'; project.rename(moved); project.mkdir()
        (project / 'input.json').write_text('{}')
        with self.assertRaises(StorageError): self.storage._unlink(project, candidate['root'], 'input.json', item)

    def test_plan_directory_symlink_is_rejected(self):
        self.project(); self.manager.data_dir.mkdir(parents=True)
        outside = Path(self.tmp.name, 'outside'); outside.mkdir()
        os.symlink(outside, self.storage.plan_dir)
        value = self.storage.list({})['projects'][0]
        with self.assertRaises(StorageError): self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id']]})

    def test_generic_plan_json_is_not_an_mv_roadmap(self):
        project = self.project(); (project / 'production-plan.json').unlink()
        (project / 'plan.json').write_text(json.dumps({'objective': 'generic', 'tasks': ['x']}))
        value = self.storage.list({})['projects'][0]
        self.assertTrue(value['blocked'])
        self.assertIn('로드맵', ' '.join(value['reasons']))

    def test_completion_audit_failure_returns_completed_warning(self):
        self.project(); value = self.storage.list({})['projects'][0]
        plan = self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id']]})
        original = self.manager._audit
        def audit(root, action, detail):
            if action == 'mv-project-cleanup': raise OSError('audit full')
            return original(root, action, detail)
        with patch.object(self.manager, '_audit', side_effect=audit):
            result = self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(result['removedProjects'], 1)
        self.assertTrue(result['warnings'])

    def test_source_change_blocks_project(self):
        self.project(); self.source.write_bytes(b'changed-source')
        value = self.storage.list({})['projects'][0]
        self.assertTrue(value['blocked'])
        self.assertIn('원본 음원', ' '.join(value['reasons']))

    def test_active_lsof_or_registered_lease_blocks_project(self):
        project = self.project()
        with patch('storage_mv.subprocess.run', return_value=type('L', (), {'returncode': 0, 'stdout': 'p1\n', 'stderr': ''})()):
            self.assertTrue(self.storage.list({})['projects'][0]['blocked'])
        project_id = self.manager._project_id(project)
        data = self.manager._empty(); data['projects'][project_id] = {'path': str(project)}; data['leases'][project_id] = {'pid': os.getpid()}
        with patch.object(self.manager, '_read', return_value=data):
            self.assertTrue(self.storage.list({})['projects'][0]['blocked'])

    def test_root_escape_models_and_plan_shape_are_rejected(self):
        project = self.project(); (project / 'models').mkdir(); (project / 'models' / 'x.gguf').write_bytes(b'x')
        value = self.storage.list({})['projects'][0]
        self.assertTrue(value['blocked'])
        with self.assertRaises(StorageError): self.storage.preview({'scanId': self.scan(), 'projectIds': ['b' * 64]})
        with self.assertRaises(StorageError): self.storage.preview({'scanId': self.scan(), 'projectIds': [value['id']], 'root': '/tmp'})


if __name__ == '__main__': unittest.main()
