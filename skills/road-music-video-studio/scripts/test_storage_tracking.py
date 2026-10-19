import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage_manager import StorageManager
from storage_tracking import StorageTracking


class StorageTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.root = base / "workspace"; self.root.mkdir()
        self.manager = StorageManager(base / "profile")
        self.tracking = StorageTracking(self.manager, self.root)
        self.workspace = patch("storage_tracking.is_workspace", side_effect=lambda path: Path(path).resolve() == self.root)
        self.workspace.start(); self.addCleanup(self.workspace.stop)

    def test_default_read_requires_an_explicit_first_index(self):
        result = self.tracking.list({})
        self.assertEqual(result["cacheState"], "scan-required")
        self.assertEqual(result["tracking"]["indexedFiles"], 0)

    def test_nested_profile_skips_workspace_scan_without_disabling_tracking(self):
        manager = StorageManager(self.root / ".roadmusic" / "maintenance" / "profile")
        tracking = StorageTracking(manager, self.root)
        with patch("storage_tracking.WorkspaceScan", side_effect=AssertionError("workspace scan")):
            result = tracking.list({"refreshWorkspace": True})
            preview = tracking.preview({})
        scan = next(item for item in result["checks"] if item["id"] == "workspaceScan")
        self.assertTrue(result["ready"])
        self.assertEqual(result["cacheState"], "scan-skipped-profile-inside-workspace")
        self.assertFalse(scan["enabled"])
        self.assertIn("작업 폴더 안", scan["reason"])
        self.assertIn("전체 스캔을 생략", preview["warnings"][0])

    def test_refresh_indexes_tooling_as_owned_and_leaves_unknown_visible(self):
        (self.root / ".roadmusic").mkdir(); (self.root / ".roadmusic" / "state.json").write_text("{}")
        (self.root / ".harness").mkdir(); (self.root / ".harness" / "review.txt").write_text("review")
        (self.root / "loose").mkdir(); (self.root / "loose" / "unexplained.bin").write_bytes(b"x" * 32)
        result = self.tracking.list({"refreshWorkspace": True})
        self.assertEqual(result["cacheState"], "refreshed")
        self.assertGreater(result["tracking"]["knownOwnership"]["paths"], 0)
        self.assertTrue(any(item["path"] == "loose" for item in result["tracking"]["unknown"]["folders"]))
        self.assertTrue(any(item["kind"] == "unclassified" for item in result["tracking"]["protected"]))

    def test_management_claim_does_not_own_unregistered_private_work(self):
        orphan = self.root / '.roadmusic/work/orphan'; orphan.mkdir(parents=True)
        (orphan / 'media.mp4').write_bytes(b'unknown media')
        pending = self.root / '.roadmusic/work/pending'; pending.mkdir()
        (pending / 'media.mp4').write_bytes(b'pending media')
        self.manager.management_db.claim_path(str(pending), 'producer-work', project_id='p' * 64, workspace=str(self.root))
        result = self.tracking.list({'refreshWorkspace': True})
        self.assertTrue(any(item['path'] == '.roadmusic/work/orphan' for item in result['unknown']['folders']))
        self.assertFalse(any(item['path'] == '.roadmusic/work/pending' for item in result['unknown']['folders']))
        claims = self.manager.management_db.paths(workspace=str(self.root))
        self.assertFalse(any(item['path'] == str(orphan) for item in claims))
        self.assertTrue((orphan / 'media.mp4').is_file())

    def test_producer_metadata_claim_links_only_one_source(self):
        import json
        producer = self.root / "Output/song"; producer.mkdir(parents=True)
        (producer / "production.json").write_text(json.dumps({"source": {"path": "/Music/song.mp3", "sha256": "a" * 64}}))
        (producer / "preview.mp4").write_bytes(b"preview")
        result = self.tracking.list({"refreshWorkspace": True})
        claim = next(item for item in self.manager.management_db.paths() if item["path"] == str(producer))
        self.assertEqual(claim["groupId"], "a" * 64)
        self.assertFalse(any(item["path"] == "Output" for item in result["unknown"]["folders"]))

    def test_contract_and_cached_read_do_not_touch_inventory(self):
        (self.root / "docs").mkdir(); (self.root / "docs/guide.md").write_text("guide")
        (self.root / "mystery").mkdir(); (self.root / "mystery/file.bin").write_bytes(b"keep")
        self.tracking.list({"refreshWorkspace": True})
        with patch("storage_scan.WorkspaceScan._digest", side_effect=AssertionError("inventory rehash")), patch("storage_tracking.WorkspaceScan.scan", side_effect=AssertionError("rescan")):
            result = self.tracking.list({})
        self.assertEqual(result["workspace"], str(self.root))
        self.assertIsInstance(result["status"], list)
        self.assertFalse(any(item["path"] == "docs" for item in result["unknown"]["folders"]))
        self.assertTrue(any(item["path"] == "mystery" for item in result["unknown"]["folders"]))
        self.assertIn("blocked", self.tracking.preview({}))
        self.assertIn("warnings", self.tracking.preview({}))

    def test_cleanup_rejects_symlinked_parent_even_if_leaf_inode_is_unchanged(self):
        nested = self.root / "nested"; nested.mkdir()
        finder = nested / ".DS_Store"; finder.write_bytes(b"finder")
        self.tracking.list({"refreshWorkspace": True}); plan = self.tracking.preview({})
        elsewhere = self.root.parent / "elsewhere"; nested.rename(elsewhere)
        nested.symlink_to(elsewhere, target_is_directory=True)
        result = self.tracking.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertEqual(result["removedFiles"], 0)
        self.assertTrue((elsewhere / ".DS_Store").exists())

    def test_only_finder_residue_is_candidate_and_changed_file_is_skipped(self):
        finder = self.root / ".DS_Store"; finder.write_bytes(b"old")
        unknown = self.root / "unknown.tmp"; unknown.write_bytes(b"keep")
        self.tracking.list({"refreshWorkspace": True})
        plan = self.tracking.preview({})
        self.assertEqual([item["relativePath"] for item in plan["candidates"]], [".DS_Store"])
        finder.write_bytes(b"changed")
        result = self.tracking.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertEqual(result["removedFiles"], 0)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertTrue(finder.exists())
        self.assertTrue(unknown.exists())

    def test_cleanup_reports_removed_files_even_if_result_event_write_fails(self):
        from management_db import ManagementDBError
        finder = self.root / '.DS_Store'; finder.write_bytes(b'finder')
        self.tracking.list({'refreshWorkspace': True}); plan = self.tracking.preview({})
        with patch.object(self.tracking.db, 'record_event', side_effect=ManagementDBError('disk full')):
            result = self.tracking.cleanup({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(result['removedFiles'], 1)
        self.assertFalse(finder.exists())
        self.assertTrue(result['warnings'])

    def test_verified_finder_residue_can_be_removed_once(self):
        finder = self.root / "nested" / ".DS_Store"; finder.parent.mkdir(); finder.write_bytes(b"finder")
        self.tracking.list({"refreshWorkspace": True})
        plan = self.tracking.preview({})
        result = self.tracking.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertEqual(result["removedFiles"], 1)
        self.assertFalse(finder.exists())
        with self.assertRaises(Exception):
            self.tracking.cleanup({"planId": plan["planId"], "confirm": True})


if __name__ == "__main__":
    unittest.main()
