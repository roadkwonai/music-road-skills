import json
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from storage_manager import StorageManager, StorageError
from storage_maintenance import StorageMaintenance
from storage_verification import PROFILES, DMG_DOWNLOAD
from storage_artifacts import RESEARCH


class ScanFixture:
    complete = True
    def __init__(self, root, data_dir): self.root = root
    def scan(self): return {'scanId': 'a' * 48, 'complete': self.complete, 'workspace': str(self.root), 'totals': {'allocatedBytes': 10000}, 'errors': []}
    def load(self, scan_id):
        if scan_id != 'a' * 48 or not self.complete: raise StorageError('완료된 스캔이 필요합니다', 'scan_required')
        return self.scan()


class GitFixture:
    state = 'stable'
    calls = 0
    def __init__(self, root): self.root = root
    def inspect(self):
        return {'fingerprint': self.state, 'objectsBytesAllocated': 1000, 'estimatedReclaimableLogicalBytes': 500,
                'unreachableObjects': 2, 'blocked': []}
    def cleanup(self, expected):
        if expected['fingerprint'] != self.state: raise StorageError('계획 뒤 Git 상태 변경', 'stale_plan')
        type(self).calls += 1
        return {'freedAllocatedBytes': 400, 'beforeAllocatedBytes': 1000, 'afterAllocatedBytes': 600,
                'diskFreeDeltaBytes': 384, 'removedObjects': 2, 'preservation': {'pass': True}, 'warnings': []}


class VerificationFixture:
    state = 'stable'
    calls = 0
    def __init__(self, root): self.root = root
    def inspect(self):
        return {'candidates': [{'id': 'candidate', 'path': 'Output/verification/copy', 'absolutePath': str(self.root / 'Output/verification/copy'),
                                'kind': 'verification-copy', 'description': '테스트 설치 복제', 'fileCount': 1, 'bytes': 12,
                                'allocatedBytes': 4096, 'fingerprint': self.state, 'evidence': {'archiveSha256': 'a' * 64}}], 'blocked': []}
    def cleanup(self, selected):
        if selected[0]['fingerprint'] != self.state: raise StorageError('복제본 변경', 'stale_plan')
        type(self).calls += 1
        return {'removedFiles': 1, 'freedBytes': 12, 'freedAllocatedBytes': 4096, 'skipped': [], 'warnings': []}


class ArtifactFixture(VerificationFixture):
    def __init__(self, root, manager): super().__init__(root)
    def inspect(self):
        result = super().inspect()
        result['candidates'][0].update({'id': 'artifact', 'scope': 'artifacts', 'files': [{'relativePath': 'Output/research/frame.jpg', 'bytes': 12}]})
        return result


class RetirementFixture(VerificationFixture):
    calls = 0
    def __init__(self, root, manager): super().__init__(root)
    def inspect(self):
        type(self).calls += 1
        result = super().inspect()
        result['candidates'][0].update({'id': 'retirement', 'scope': 'retirement', 'files': [{'relativePath': 'Output/old/render.mp4', 'bytes': 12}]})
        result['review'] = []
        return result


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'repo'; self.root.mkdir()
        (self.root / '.git').mkdir()
        (self.root / PROFILES[0][1]).mkdir(parents=True)
        (self.root / RESEARCH).mkdir(parents=True)
        self.manager = StorageManager(self.root.parent / 'data')
        self.patches = [patch('storage_maintenance.is_workspace', return_value=True),
                        patch('storage_maintenance.WorkspaceScan', ScanFixture),
                        patch('storage_maintenance.GitMaintenance', GitFixture),
                        patch('storage_maintenance.VerificationMaintenance', VerificationFixture),
                        patch('storage_maintenance.ArtifactMaintenance', ArtifactFixture),
                        patch('storage_maintenance.RetirementMaintenance', RetirementFixture)]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        ScanFixture.complete = True
        GitFixture.state = VerificationFixture.state = 'stable'; GitFixture.calls = VerificationFixture.calls = RetirementFixture.calls = 0
        self.storage = StorageMaintenance(self.manager, self.root)

    def test_status_and_missing_targets_never_start_optional_inspectors(self):
        root = self.root.parent / 'installed'; root.mkdir()
        with patch('storage_maintenance.GitMaintenance', side_effect=AssertionError('Git must not run')), patch('storage_maintenance.VerificationMaintenance', side_effect=AssertionError('verification must not run')), patch('storage_maintenance.ArtifactMaintenance', side_effect=AssertionError('artifacts must not run')):
            status = StorageMaintenance.status(self.manager, root)
            for key in ('git', 'verification', 'artifacts', 'retirement'):
                self.assertFalse(status['capabilities'][key]['enabled'])
                self.assertTrue(status['capabilities'][key]['reason'])
            storage = StorageMaintenance(self.manager, root)
            self.assertEqual(storage.list({})['candidates'], [])
            with patch('storage_maintenance.WorkspaceScan', side_effect=AssertionError('disabled scope must not scan')):
                for scope in ('git', 'retirement'):
                    with self.assertRaises(StorageError) as error: storage.list({'scope': scope})
                    self.assertEqual(error.exception.code, 'maintenance_unavailable')
                for scope in ('git', 'verification', 'artifacts'):
                    with self.assertRaises(StorageError): storage.preview({'scope': scope, 'scanId': 'a' * 48})

    def test_status_checks_actual_dmg_file_and_disables_git_symlinks(self):
        root = self.root.parent / 'portable'; root.mkdir()
        (root / '.git').symlink_to(self.root / '.git', target_is_directory=True)
        value = StorageMaintenance.status(self.manager, root)['capabilities']
        self.assertFalse(value['git']['enabled'])
        self.assertFalse(value['verification']['enabled'])
        download = root / DMG_DOWNLOAD; download.parent.mkdir(parents=True); download.write_bytes(b'fixture')
        self.assertTrue(StorageMaintenance.status(self.manager, root)['capabilities']['verification']['enabled'])

    def test_retirement_public_candidate_lists_files_and_marks_archive_recovery_as_upper_bound(self):
        value = {'scope': 'retirement', 'id': 'retirement', 'path': 'Output/old.zip', 'fileCount': 2, 'bytes': 30,
                 'allocatedBytes': 4096, 'files': [{'relativePath': 'Output/old.zip', 'bytes': 20}, {'relativePath': 'Output/old-proof.png', 'bytes': 10}],
                 'evidence': {'archiveRecovery': [{'members': [
                     {'name': 'common/a.txt', 'size': 7, 'sha256': 'a' * 64},
                     {'name': 'copied/a.txt', 'size': 7, 'sha256': 'a' * 64},
                     {'name': 'canonical.txt', 'size': 99, 'sha256': 'c' * 64, 'canonicalMember': True},
                     {'name': 'unique/b.txt', 'size': 11, 'sha256': 'b' * 64}
                 ]}]}}
        public = StorageMaintenance._public_candidate(value)
        self.assertEqual(public['retirementFileList'], [{'path': 'Output/old.zip', 'bytes': 20}, {'path': 'Output/old-proof.png', 'bytes': 10}])
        self.assertEqual(public['grossAllocatedBytes'], 4096)
        self.assertTrue(public['estimateIsUpperBound'])
        self.assertEqual(public['archiveRecovery'], {'uniqueMemberCount': 2, 'uniqueMemberBytes': 18})
        self.assertNotIn('files', StorageMaintenance._public_candidate({'scope': 'verification', 'files': value['files']}))

    def test_artifacts_are_explicit_separate_scope_with_compressed_file_history(self):
        listing = self.storage.list({})
        self.assertEqual([x['scope'] for x in listing['candidates']], ['verification', 'artifacts'])
        with self.assertRaises(StorageError): self.storage.preview({'scanId': 'a' * 48, 'scope': 'verification', 'candidateIds': ['artifact']})
        plan = self.storage.preview({'scanId': 'a' * 48, 'scope': 'artifacts', 'candidateIds': ['artifact']})
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId']})
        result = self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(result['scope'], 'artifacts')
        receipt = json.loads(Path(result['manifestPath']).read_text())
        self.assertNotIn('files', receipt['plan']['candidates'][0])
        with gzip.open(receipt['plan']['fileInventoryPath'], 'rt') as stream:
            item = json.loads(stream.readline())
        self.assertEqual(item['relativePath'], 'Output/research/frame.jpg')
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})

    def test_legacy_workspace_history_remains_visible_without_import_on_read(self):
        path = self.root / '.roadmusic/history.jsonl'; path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'action': 'sweep-cleanup', 'removedFiles': 9}) + '\n')
        before = path.read_bytes()
        self.assertTrue(any(event.get('removedFiles') == 9 for event in self.storage.history({})['events']))
        self.assertEqual(path.read_bytes(), before)

    def test_workspace_history_keeps_mv_and_sweep_summaries_after_project_removal(self):
        self.manager._audit(self.root, 'mv-project-cleanup', {'removedProjects': 2, 'removedFiles': 4})
        self.manager._audit(self.root, 'sweep-cleanup', {'removedFiles': 4})
        actions = [value['action'] for value in self.storage.history({})['events']]
        self.assertIn('mv-project-cleanup', actions)
        self.assertIn('sweep-cleanup', actions)

    def test_preview_never_deletes_and_unknown_candidate_or_mixed_scope_is_rejected(self):
        result = self.storage.list({})
        self.assertEqual(result['candidates'][0]['id'], 'candidate')
        self.assertEqual(GitFixture.calls + VerificationFixture.calls, 0)
        with self.assertRaises(StorageError): self.storage.preview({'scanId': 'a' * 48, 'scope': 'verification', 'candidateIds': ['other']})
        with self.assertRaises(StorageError): self.storage.preview({'scanId': 'a' * 48, 'scope': 'git', 'candidateIds': ['candidate']})
        with self.assertRaises(StorageError): self.storage.preview({'scanId': 'a' * 48, 'scope': 'other'})

    def test_retirement_only_list_scans_workspace_without_git_or_other_maintenance(self):
        class GitMustNotRun:
            def __init__(self, root): raise AssertionError('Git inspection must not run for retirement-only list')
        with patch('storage_maintenance.GitMaintenance', GitMustNotRun):
            result = self.storage.list({'scope': 'retirement'})
        self.assertEqual([item['scope'] for item in result['candidates']], ['retirement'])
        self.assertEqual(RetirementFixture.calls, 1)
        self.assertFalse(result['git']['available'])

    def test_large_evidence_is_stored_once_without_duplicating_public_entries(self):
        inventory = VerificationFixture(self.root).inspect()
        inventory['candidates'][0]['evidence']['proofText'] = 'x' * (9 * 1024 * 1024)
        with patch.object(VerificationFixture, 'inspect', return_value=inventory):
            result = self.storage.preview({'scanId':'a'*48,'scope':'verification','candidateIds':['candidate']})
        saved = json.loads((self.storage.plan_dir / (result['planId']+'.json')).read_text())
        self.assertEqual(len(result['entries']), 1)
        self.assertNotIn('entries', saved['public'])
        self.assertEqual(saved['candidates'], inventory['candidates'])

    def test_git_plan_requires_confirmation_is_one_use_and_records_measured_bytes(self):
        plan = self.storage.preview({'scanId': 'a' * 48, 'scope': 'git'})
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId']})
        self.assertEqual(GitFixture.calls, 0)
        result = self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(result['freedAllocatedBytes'], 400)
        self.assertEqual(result['diskFreeDeltaBytes'], 384)
        self.assertEqual(GitFixture.calls, 1)
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertTrue(self.storage.history({})['events'])
        self.assertTrue(Path(result['auditPath']).is_file())

    def test_stale_git_or_verification_plan_does_not_execute(self):
        plan = self.storage.preview({'scanId': 'a' * 48, 'scope': 'git'}); GitFixture.state = 'changed'
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(GitFixture.calls, 0)
        plan = self.storage.preview({'scanId': 'a' * 48, 'scope': 'verification', 'candidateIds': ['candidate']}); VerificationFixture.state = 'changed'
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(VerificationFixture.calls, 0)

    def test_audit_failure_prevents_cleanup_and_expired_plan_is_rejected(self):
        plan = self.storage.preview({'scanId': 'a' * 48, 'scope': 'git'})
        with patch.object(self.manager, '_audit', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(GitFixture.calls, 0)
        plan = self.storage.preview({'scanId': 'a' * 48, 'scope': 'git'})
        path = self.storage.plan_dir / (plan['planId'] + '.json')
        data = json.loads(path.read_text()); data['expiresAt'] = 0; path.write_text(json.dumps(data))
        with self.assertRaises(StorageError): self.storage.cleanup({'planId': plan['planId'], 'confirm': True})

    def test_scope_parameters_cannot_supply_paths_or_git_options(self):
        for value in [{'scope': 'git', 'root': '/tmp'}, {'scope': 'git', 'prune': 'now'}, {'scope': 'verification', 'candidateIds': []}]:
            with self.assertRaises(StorageError): self.storage.preview(value)

    def test_no_plan_without_complete_fresh_whole_workspace_scan(self):
        with self.assertRaises(StorageError): self.storage.preview({'scope': 'git'})
        ScanFixture.complete = False
        self.assertFalse(self.storage.list({})['scan']['complete'])
        with self.assertRaises(StorageError): self.storage.preview({'scope': 'git', 'scanId': 'a' * 48})
        self.assertEqual(GitFixture.calls + VerificationFixture.calls, 0)

    def test_result_audit_failure_does_not_hide_a_completed_cleanup(self):
        plan = self.storage.preview({'scanId': 'a' * 48, 'scope': 'git'}); original = self.manager._audit
        def audit(root, action, detail):
            if action == 'maintenance-cleanup': raise OSError('post audit full')
            return original(root, action, detail)
        with patch.object(self.manager, '_audit', side_effect=audit):
            result = self.storage.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(result['freedAllocatedBytes'], 400)
        self.assertTrue(result['warnings'])


if __name__ == '__main__': unittest.main()
