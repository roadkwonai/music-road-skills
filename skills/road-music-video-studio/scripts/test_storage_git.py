import os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path

SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path: sys.path.insert(0, str(SCRIPTS))
import storage_git
from storage_git import GitMaintenance
from storage_manager import StorageError


def git(root, *args, input=None):
    return subprocess.run(['git', '-C', str(root), *args], input=input, capture_output=True, text=True, check=True).stdout.strip()


class GitMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name) / 'repo'; self.root.mkdir()
        git(self.root, 'init', '-q'); git(self.root, 'config', 'user.email', 'test@example.invalid'); git(self.root, 'config', 'user.name', 'Storage test')
        (self.root / 'keep.txt').write_text('keep\n'); git(self.root, 'add', 'keep.txt'); git(self.root, 'commit', '-qm', 'initial')

    def tearDown(self): self.temp.cleanup()

    def old_unreachable(self, data=b'old unreachable'):
        oid = git(self.root, 'hash-object', '-w', '--stdin', input=data.decode())
        path = self.root / '.git/objects' / oid[:2] / oid[2:]
        then = time.time() - 3 * 86400; os.utime(path, (then, then))
        return oid

    def test_inspect_and_cleanup_preserve_refs_reflog_indexes_and_recent_object(self):
        old = self.old_unreachable(); recent = git(self.root, 'hash-object', '-w', '--stdin', input='recent object')
        (self.root / 'staged.txt').write_text('staged'); git(self.root, 'add', 'staged.txt')
        other = Path(self.temp.name) / 'other'; git(self.root, 'worktree', 'add', '-q', '-b', 'other', str(other), 'HEAD')
        (other / 'other-staged.txt').write_text('other staged'); git(other, 'add', 'other-staged.txt')
        other_index = Path(git(other, 'rev-parse', '--git-path', 'index'))
        if not other_index.is_absolute(): other_index = other / other_index
        preserved = {'head': git(self.root, 'rev-parse', 'HEAD'), 'reflog': git(self.root, 'reflog', 'show', '--format=%H'), 'mainIndex': (self.root / '.git/index').read_bytes(), 'otherIndex': other_index.read_bytes()}
        manager = GitMaintenance(self.root)
        inspected = manager.inspect()
        self.assertFalse(inspected['blocked'], inspected['reasons'])
        self.assertGreaterEqual(inspected['estimatedReclaimableLogicalBytes'], len(b'old unreachable'))
        result = manager.cleanup(inspected)
        self.assertTrue(result['preservation']['passed'])
        self.assertRaises(subprocess.CalledProcessError, git, self.root, 'cat-file', '-e', old)
        self.assertEqual(git(self.root, 'cat-file', '-e', recent), '')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), preserved['head'])
        self.assertEqual(git(self.root, 'reflog', 'show', '--format=%H'), preserved['reflog'])
        self.assertEqual((self.root / '.git/index').read_bytes(), preserved['mainIndex'])
        self.assertEqual(other_index.read_bytes(), preserved['otherIndex'])

    def test_reflog_and_linked_worktree_index_are_reachability_roots(self):
        other = Path(self.temp.name) / 'other'; git(self.root, 'worktree', 'add', '-q', '-b', 'other', str(other), 'HEAD')
        (other / 'other-staged.txt').write_text('other staged'); git(other, 'add', 'other-staged.txt')
        staged = git(other, 'ls-files', '-s', 'other-staged.txt').split()[1]
        reflog_only = git(self.root, 'commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', 'reflog only')
        git(self.root, 'update-ref', 'refs/heads/reflog-only', reflog_only); git(self.root, 'update-ref', 'refs/heads/reflog-only', 'HEAD')
        reachable = git(other, 'rev-list', '--objects', '--all', '--reflog', '--indexed-objects').splitlines()
        self.assertIn(staged, {line.split(' ', 1)[0] for line in reachable})
        self.assertIn(reflog_only, {line.split(' ', 1)[0] for line in reachable})
        manager = GitMaintenance(self.root); before = manager.inspect()
        git(other, 'commit', '-qm', 'linked reflog')
        after = manager.inspect()
        before_worktree = next(item for item in before['state']['worktrees'] if item['path'] == str(other.resolve()))
        after_worktree = next(item for item in after['state']['worktrees'] if item['path'] == str(other.resolve()))
        self.assertNotEqual(before_worktree['reflogHash'], after_worktree['reflogHash'])
        self.assertNotEqual(before['state']['fingerprint'], after['state']['fingerprint'])

    def test_stale_plan_and_locks_block_cleanup(self):
        manager = GitMaintenance(self.root); inspected = manager.inspect()
        (self.root / 'changed.txt').write_text('changed'); git(self.root, 'add', 'changed.txt')
        with self.assertRaisesRegex(StorageError, '변경'):
            manager.cleanup(inspected)
        lock = self.root / '.git/packed-refs.lock'; lock.write_text('busy')
        blocked = manager.inspect(); self.assertTrue(blocked['blocked']); self.assertTrue(blocked['locks'])
        lock.unlink()

    def test_unsupported_storage_and_missing_worktree_are_blocked(self):
        alternate = self.root / '.git/objects/info/alternates'; alternate.parent.mkdir(exist_ok=True); alternate.write_text('/tmp/objects\n')
        self.assertTrue(GitMaintenance(self.root).inspect()['blocked'])
        alternate.unlink()
        other = Path(self.temp.name) / 'gone'; git(self.root, 'worktree', 'add', '-q', '-b', 'gone', str(other), 'HEAD')
        shutil.rmtree(other)
        self.assertTrue(GitMaintenance(self.root).inspect()['blocked'])

    def test_gitlink_cannot_hide_a_genuinely_reachable_local_object(self):
        head = git(self.root, 'rev-parse', 'HEAD')
        git(self.root, 'update-index', '--add', '--cacheinfo', f'160000,{head},external-submodule')
        manager = GitMaintenance(self.root); inspected = manager.inspect()
        self.assertFalse(inspected['blocked'], inspected['reasons'])
        self.assertEqual(inspected['objects']['unreachableCount'], 0)

    def test_gc_timeout_terminates_its_process_group(self):
        fake = Path(self.temp.name) / 'sleeping-git'; fake.write_text('#!/bin/sh\nsleep 60\n'); fake.chmod(0o700)
        manager = GitMaintenance(self.root); manager.git = str(fake)
        original = storage_git._GC_TIMEOUT; storage_git._GC_TIMEOUT = 0.1
        try:
            started = time.monotonic()
            with self.assertRaisesRegex(StorageError, '시간 제한'): manager._gc(['gc'])
            self.assertLess(time.monotonic() - started, 8)
        finally:
            storage_git._GC_TIMEOUT = original


if __name__ == '__main__': unittest.main()
