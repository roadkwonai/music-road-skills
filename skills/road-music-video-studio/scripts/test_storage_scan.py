import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from storage_manager import PLAN_TTL, StorageError, _atomic_json, _id, _json_read
from storage_scan import WorkspaceScan, _classification


class WorkspaceScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.root = base / 'workspace'; self.root.mkdir()
        self.data = base / 'data'
        self.scan = WorkspaceScan(self.root, self.data)

    def test_current_source_and_bundled_assets_are_program_not_unlinked_trash(self):
        for relative in ('.agents/skills/studio/assets/font.woff2', 'renderer/app.js', 'electron/main.js', 'docs/cli.md', 'assets/logo.png', 'package-lock.json'):
            self.assertEqual(_classification(relative)[0], 'program', relative)
        self.assertEqual(_classification('Output/old-render/frame.png')[0], 'output')
        self.assertEqual(_classification('.agents/skills/engine/models/current.safetensors')[0], 'model')

    def test_sql_cache_keeps_source_identity_without_copying_frame_payloads(self):
        path = self.root / 'production.json'
        path.write_text(json.dumps({'source': {'path': '/Music/song.mp3', 'sha256': 'a' * 64}, 'frames': ['frame'] * 1000}))
        self.scan.scan()
        with patch.object(self.scan, '_digest', side_effect=AssertionError('rehash')):
            cached = self.scan.cached_metadata()
            self.assertEqual(cached['production.json']['source']['sha256'], 'a' * 64)
            self.assertNotIn('frames', cached['production.json'])

    def test_full_hidden_workspace_scan_records_metadata_only(self):
        (self.root / '.git').mkdir(); (self.root / '.git' / 'pack').write_bytes(b'git')
        (self.root / '.harness').mkdir(); (self.root / '.harness' / 'history.json').write_bytes(b'log')
        (self.root / 'Output').mkdir(); (self.root / 'Output' / 'draft.bin').write_bytes(b'x' * 21)
        result = self.scan.scan()
        self.assertTrue(result['complete']); self.assertEqual(result['totals']['fileCount'], 3)
        self.assertGreaterEqual(result['totals']['directoryCount'], 4)
        self.assertTrue(Path(result['inventoryPath']).is_file())
        self.assertEqual(result['id'], result['scanId'])
        self.assertEqual(self.scan.load(result['scanId'])['fingerprint'], result['fingerprint'])
        self.assertEqual({value['kind'] for value in result['categories']}, {'git', 'tooling', 'output'})

    def test_external_symlink_is_not_followed_or_counted_as_size(self):
        outside = Path(self.temp.name) / 'outside.bin'; outside.write_bytes(b'z' * 8192)
        (self.root / 'link').symlink_to(outside)
        result = self.scan.scan()
        self.assertTrue(result['complete']); self.assertEqual(result['totals']['fileCount'], 0)
        self.assertEqual(result['totals']['logicalBytes'], 0); self.assertEqual(result['externalLinksCount'], 1)
        self.assertEqual(result['externalLinks'][0]['path'], 'link')

    def test_hardlink_has_two_logical_paths_and_one_allocated_file(self):
        first = self.root / 'a.bin'; first.write_bytes(b'a' * 4097)
        os.link(first, self.root / 'b.bin')
        result = self.scan.scan()
        self.assertEqual(result['totals']['fileCount'], 2); self.assertEqual(result['totals']['uniqueFileCount'], 1)
        self.assertEqual(result['totals']['logicalBytes'], 8194)
        self.assertEqual(result['totals']['allocatedBytes'], first.stat().st_blocks * 512)

    def test_partial_error_is_saved_but_cannot_be_loaded_for_a_plan(self):
        (self.root / 'unreadable').mkdir(); (self.root / 'unreadable' / 'x').write_text('x')
        original = os.scandir
        def failing(path):
            if Path(path).name == 'unreadable': raise PermissionError('denied')
            return original(path)
        with patch('storage_scan.os.scandir', side_effect=failing): result = self.scan.scan()
        self.assertFalse(result['complete']); self.assertTrue(result['errors'])
        with self.assertRaisesRegex(StorageError, '완결되지'): self.scan.load(result['scanId'])

    def test_modified_inventory_and_expired_scan_are_rejected(self):
        (self.root / 'asset').write_text('asset'); result = self.scan.scan()
        inventory = Path(result['inventoryPath']); inventory.write_bytes(inventory.read_bytes() + b'x')
        with self.assertRaises(StorageError): self.scan.load(result['scanId'])
        fresh = self.scan.scan(); meta_path = self.scan.scan_dir / (fresh['scanId'] + '.json')
        meta = _json_read(meta_path, None); meta['createdAtEpoch'] = 0; _atomic_json(meta_path, meta)
        with self.assertRaisesRegex(StorageError, '만료'): self.scan.load(fresh['scanId'])

    def test_latest_complete_is_read_only_display_cache_even_after_plan_expiry(self):
        (self.root / 'asset').write_text('asset')
        result = self.scan.scan()
        meta_path = self.scan.scan_dir / (result['scanId'] + '.json')
        meta = _json_read(meta_path, None)
        meta['createdAtEpoch'] = 0; meta['expiresAt'] = PLAN_TTL
        meta['fingerprint'] = _id(json.dumps({'workspace': str(self.root), 'createdAt': meta['createdAtEpoch'], 'totals': meta['totals'],
                                               'inventorySha256': meta['inventorySha256'], 'inventorySnapshot': meta['inventorySnapshot']}, sort_keys=True, separators=(',', ':')))
        _atomic_json(meta_path, meta)
        cached = self.scan.latest_complete()
        self.assertEqual(cached['scanId'], result['scanId'])
        with self.assertRaisesRegex(StorageError, '만료'):
            self.scan.load(result['scanId'])

    def test_rejects_scan_store_inside_workspace(self):
        with self.assertRaises(StorageError): WorkspaceScan(self.root, self.root / 'data')

    def test_prune_keeps_only_the_three_newest_expired_owned_scan_pairs(self):
        (self.root / 'asset').write_text('asset')
        old = [self.scan.scan()['scanId'] for _ in range(4)]
        for scan_id in old:
            path = self.scan.scan_dir / (scan_id + '.json')
            meta = _json_read(path, None); meta['expiresAt'] = 0; _atomic_json(path, meta)
        newest = self.scan.scan()['scanId']
        pairs = sorted(path.stem for path in self.scan.scan_dir.glob('*.json'))
        self.assertEqual(len(pairs), 3)
        self.assertIn(newest, pairs)


if __name__ == '__main__':
    unittest.main()
