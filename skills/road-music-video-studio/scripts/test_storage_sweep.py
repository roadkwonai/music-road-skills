from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from storage_manager import StorageManager, _atomic_json
from storage_sweep import StorageSweep


class ScanMaintenance:
    calls = 0
    def __init__(self, manager, root): self.manager = manager; self.root = root
    def list(self, params):
        type(self).calls += 1
        return {"scan": {"scanId": "b" * 48, "complete": True}}
    @contextmanager
    def _lock(self): yield


class FakeMV:
    previews = []; cleanups = []
    def __init__(self, manager): pass
    def preview(self, params):
        type(self).previews.append(params)
        return {"planId": "c" * 48, "projects": [{"id": "a" * 64, "title": "MV", "path": "/tmp/mv", "bytes": 9, "fileCount": 2}], "blocked": []}
    def cleanup(self, params):
        type(self).cleanups.append(params)
        return {"removedFiles": 2, "freedBytes": 9, "freedAllocatedBytes": 4096, "skipped": [], "warnings": []}


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "workspace"; self.root.mkdir(); self.data = self.root.parent / "data"; self.manager = StorageManager(self.data)
        self.project = self.root.parent / "project"; self.project.mkdir(); (self.project / "studio-project.json").write_text(json.dumps({"schemaVersion": 1, "media": []})); (self.project / ".roadmusic/cache").mkdir(parents=True)
        self.row = self.manager.dispatch("register", {"project": str(self.project)})
        self.cache = self.project / ".roadmusic/cache/cache.tmp"; self.cache.write_bytes(b"cache")
        self.manager.dispatch("track", {"projectId": self.row["id"], "path": ".roadmusic/cache/cache.tmp", "kind": "cache", "reproducible": True})
        with self.manager._write_lock():
            data = self.manager._read(); project = data["projects"][self.row["id"]]; project.update({"state": "completed", "autoCleanup": True, "retainDays": 0, "completedAt": 0})
            next(iter(project["entries"].values()))["lastUsedAt"] = 0; self.manager._save(data)
        self.patches = [patch("storage_sweep.is_workspace", return_value=True), patch("storage_sweep.StorageMaintenance", ScanMaintenance)]
        for item in self.patches: item.start(); self.addCleanup(item.stop)
        ScanMaintenance.calls = 0; FakeMV.previews = []; FakeMV.cleanups = []
        self.sweep = StorageSweep(self.manager, self.root, mv_storage_factory=FakeMV)

    def test_preview_runs_full_scan_before_creating_one_use_composed_plan(self):
        result = self.sweep.preview({"mvProjectIds": ["a" * 64]})
        self.assertEqual(ScanMaintenance.calls, 1)
        self.assertTrue(result["planId"])
        self.assertTrue(self.cache.exists())
        self.assertEqual(FakeMV.previews, [{"scanId": "b" * 48, "projectIds": ["a" * 64]}])
        self.assertEqual({item["kind"] for item in result["entries"]}, {"ai-mv-project"})

    def test_cleanup_executes_only_frozen_child_plans_and_cannot_be_reused(self):
        preview = self.sweep.preview({"mvProjectIds": ["a" * 64]})
        result = self.sweep.cleanup({"planId": preview["planId"], "confirm": True})
        self.assertTrue(self.cache.exists())
        self.assertEqual(result["removedFiles"], 2)
        self.assertEqual(FakeMV.cleanups, [{"planId": "c" * 48, "confirm": True}])
        with self.assertRaises(Exception): self.sweep.cleanup({"planId": preview["planId"], "confirm": True})

    def test_plain_bulk_cleanup_keeps_mv_out_and_cleans_expired_project_cache(self):
        preview = self.sweep.preview({})
        self.assertEqual({item["kind"] for item in preview["entries"]}, {"project-cache"})
        result = self.sweep.cleanup({"planId": preview["planId"], "confirm": True})
        self.assertFalse(self.cache.exists())
        self.assertEqual(result["removedFiles"], 1)
        self.assertEqual(FakeMV.cleanups, [])

    def test_plain_sweep_excludes_explicit_artifact_history_candidates(self):
        original = ScanMaintenance.list
        def listing(maintenance, params):
            value = original(maintenance, params)
            value['candidates'] = [{'id': 'artifacts-id', 'scope': 'artifacts', 'fileCount': 8, 'bytes': 999}]
            return value
        with patch.object(ScanMaintenance, 'list', listing):
            result = self.sweep.preview({})
        self.assertEqual({item['kind'] for item in result['entries']}, {'project-cache'})
        self.assertTrue(self.cache.exists())

    def test_mv_cleanup_requires_explicit_ids_and_unknown_input_is_rejected(self):
        result = self.sweep.preview({})
        self.assertEqual(FakeMV.previews, [])
        self.assertTrue(result["planId"])
        with self.assertRaises(Exception): self.sweep.preview({"mvProjectIds": ["bad"]})
        with self.assertRaises(Exception): self.sweep.preview({"root": "/"})


if __name__ == "__main__":
    unittest.main()
