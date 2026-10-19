import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
from storage_manager import StorageError, StorageManager
from storage_artifacts import ArtifactMaintenance, FRAME_ROOTS, BEFORE_ROOTS, ARCHIVE, HIGHRES, QA


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.manager = StorageManager(self.root / 'data')
        self.store = ArtifactMaintenance(self.root, self.manager, active_check=lambda _: False)
        self.frames = self.root / FRAME_ROOTS[0] / 'frames'
        self.frames.mkdir(parents=True)
        self.source = self.root / FRAME_ROOTS[0] / '../source.mp4'
        self.source.write_bytes(b'original reference')
        for i in range(7): (self.frames / f'frame-{i:08d}.jpg').write_bytes(bytes([i]) * 10)
        self.manifest = self.frames.parent / 'manifest.json'
        self.write(self.manifest, {'source': {'path': str(self.source.resolve()), 'sha256': sha(self.source)}, 'extraction_complete': True, 'extracted_frames': 7})
        (self.frames.parent / 'frame-index.jsonl').write_text(''.join(json.dumps({'frame_index': i, 'thumbnail': f'frames/frame-{i:08d}.jpg', 'thumbnail_sha256': sha(self.frames / f'frame-{i:08d}.jpg')}) + '\n' for i in range(7)))
        (self.frames.parent / 'sheet-index.json').write_text('{}')
        (self.frames.parent / 'sheets').mkdir()
        (self.frames.parent / 'sheets/sheet-0001.jpg').write_bytes(b'all contact sheet evidence')

    def tearDown(self): self.tmp.cleanup()
    def write(self, p, value):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))

    def test_frames_keep_source_manifest_all_sheets_and_three_representatives(self):
        candidates = self.store.inspect()['candidates']
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['scope'], 'artifacts')
        self.assertEqual(candidates[0]['fileCount'], 4)
        result = self.store.cleanup(candidates)
        self.assertEqual(result['removedFiles'], 4)
        self.assertEqual(len(list(self.frames.glob('*.jpg'))), 3)
        self.assertTrue(self.source.exists())
        self.assertTrue(self.manifest.exists())
        self.assertTrue((self.frames.parent / 'sheets/sheet-0001.jpg').exists())
        self.assertFalse(self.store.inspect()['candidates'])

    def test_no_new_arbitrary_qa_or_before_profile(self):
        p = self.root / 'Output/unrelated/qa'; p.mkdir(parents=True); (p / 'frame.png').write_bytes(b'not cache')
        self.assertFalse(any('unrelated' in x['path'] for x in self.store.inspect()['candidates']))

    def test_changed_source_missing_proof_unknown_leaf_links_and_active_fail_closed(self):
        for mode in ['source', 'proof', 'unknown', 'symlink', 'hardlink', 'active']:
            with self.subTest(mode=mode):
                if mode == 'source': self.source.write_bytes(b'changed')
                if mode == 'proof': self.manifest.rename(self.manifest.with_suffix('.bak'))
                leaf = self.frames / 'unknown.safetensors'
                if mode == 'unknown': leaf.write_bytes(b'not image')
                if mode == 'symlink': leaf.symlink_to(self.source)
                if mode == 'hardlink': os.link(self.frames / 'frame-00000001.jpg', leaf)
                store = ArtifactMaintenance(self.root, self.manager, active_check=lambda _: mode == 'active')
                self.assertFalse(store.inspect()['candidates'])
                self.assertTrue((self.frames / 'frame-00000001.jpg').exists())
                leaf.unlink(missing_ok=True)
                if mode == 'source': self.source.write_bytes(b'original reference')
                if mode == 'proof': self.manifest.with_suffix('.bak').rename(self.manifest)

    def test_changed_plan_or_new_production_reference_prevents_deletion(self):
        candidates = self.store.inspect()['candidates']
        p = self.root / 'Output/current/studio-project.json'
        self.write(p, {'asset': str(self.frames / 'frame-00000001.jpg')})
        with self.assertRaises(StorageError): self.store.cleanup(candidates)
        self.assertEqual(len(list(self.frames.glob('*.jpg'))), 7)
        p.unlink()
        (self.frames / 'frame-00000001.jpg').write_bytes(b'changed')
        with self.assertRaises(StorageError): self.store.cleanup(candidates)

    def test_before_removes_only_archive_identical_binary_and_preserves_version_code(self):
        archive = self.root / ARCHIVE; archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('MusicRoad-Skills-0.1.1/manifest.json', json.dumps({'name': 'music-road-skills', 'version': '0.1.1'}))
            z.writestr('MusicRoad-Skills-0.1.1/skills/road-music-showreel-playlist/assets/example.mp4', b'original demo')
        p = self.root / BEFORE_ROOTS[0] / '0/assets'; p.mkdir(parents=True)
        (p / 'example.mp4').write_bytes(b'original demo')
        (p / 'unique.mp4').write_bytes(b'not in archive')
        (p / 'engine.js').write_text('historical version code')
        values = [x for x in self.store.inspect()['candidates'] if x['kind'] == 'history-binary-copy']
        self.assertEqual(len(values), 1)
        self.assertTrue(values[0]['evidence']['recovery'])
        result = self.store.cleanup(values)
        self.assertEqual(result['removedFiles'], 1)
        self.assertFalse((p / 'example.mp4').exists())
        self.assertTrue((p / 'unique.mp4').exists())
        self.assertTrue((p / 'engine.js').exists())
        self.assertTrue(archive.exists())

    def test_only_exact_capture_footer_warning_at_file_end_is_accepted(self):
        path = self.root / 'capture.webm'; path.write_bytes(b'0123456789')
        warning = '[in#0/matroska,webm @ 0xbc8c20000] File ended prematurely at pos. 10 (0xa)'
        output = '0,v,SHA256=' + 'a' * 64 + '\n'
        with patch('storage_artifacts.subprocess.run', return_value=subprocess.CompletedProcess([], 0, output, warning)):
            self.assertEqual(self.store._stream_hash(path, capture=True), output.strip())
            with self.assertRaises(StorageError): self.store._stream_hash(path)
        for stderr, code in [(warning.replace('pos. 10', 'pos. 9'), 0), (warning + '\ninvalid packet', 0), (warning, 1), ('invalid data', 0)]:
            with self.subTest(stderr=stderr, code=code), patch('storage_artifacts.subprocess.run', return_value=subprocess.CompletedProcess([], code, output, stderr)):
                with self.assertRaises(StorageError): self.store._stream_hash(path, capture=True)
        with patch('storage_artifacts.subprocess.run', return_value=subprocess.CompletedProcess([], 0, output, '')):
            self.assertEqual(self.store._stream_hash(path), output.strip())

    def test_symlink_at_frame_root_is_protected(self):
        real = self.frames.with_name('original-frames'); self.frames.rename(real); self.frames.symlink_to(real, target_is_directory=True)
        result = self.store.inspect()
        self.assertFalse(result['candidates'])
        self.assertTrue(result['blocked'])
        self.assertEqual(len(list(real.iterdir())), 7)

    def test_remux_requires_same_all_streams_and_preserves_original(self):
        parent = self.root / HIGHRES / 'itzy-loco'; parent.mkdir(parents=True)
        source = parent / 'source.mkv'; source.write_bytes(b'original')
        captured = parent / 'captured-video.webm'; captured.write_bytes(b'capture container')
        self.write(self.root / HIGHRES / 'catalog.json', {'cases': [{'id': 'itzy-loco', 'source': str(source), 'source_sha256': sha(source), 'source_page': 'https://example.test/source'}]})
        with patch.object(self.store, '_stream_hash', return_value='0,v,SHA256=same'):
            values = [x for x in self.store.inspect()['candidates'] if x['kind'] == 'reference-remux-copy']
            self.assertEqual(len(values), 1)
            result = self.store.cleanup(values)
        self.assertEqual(result['removedFiles'], 1)
        self.assertTrue(source.exists())
        self.assertFalse(captured.exists())
        captured.write_bytes(b'different')
        with patch.object(self.store, '_stream_hash', side_effect=lambda p, **_: str(p)):
            self.assertFalse(any(x['kind'] == 'reference-remux-copy' for x in self.store.inspect()['candidates']))
        self.assertTrue(captured.exists())

    def test_final_qa_proof_and_all_final_outputs_must_remain_unchanged(self):
        qa = self.root / QA; path = qa / 'runtime-v2'; path.mkdir(parents=True)
        for i in range(7): (path / f'frame-{i:03d}.png').write_bytes(bytes([i]))
        final = qa.parent / 'out/final.mp4'; final.parent.mkdir(); final.write_bytes(b'final')
        report = qa / 'final-report.md'; report.write_text('approved report')
        self.write(qa / 'tomorrow-full-final-render.json', {'schemaVersion': 1, 'draft': False, 'outputs': {'out/final.mp4': sha(final)}, 'qaReports': {'qa/final-report.md': sha(report)}})
        values = [x for x in self.store.inspect()['candidates'] if x['kind'] == 'qa-detail-frames']
        self.assertEqual(len(values), 1)
        final.write_bytes(b'changed final')
        with self.assertRaises(StorageError): self.store.cleanup(values)
        self.assertEqual(len(list(path.iterdir())), 7)
        final.write_bytes(b'final')
        result = self.store.cleanup(values)
        self.assertEqual(result['removedFiles'], 4)
        self.assertEqual(len(list(path.iterdir())), 3)
        self.assertTrue(report.exists()); self.assertTrue(final.exists())

    def test_partial_unlink_failure_counts_only_removed_files(self):
        values = self.store.inspect()['candidates']
        original = StorageManager._unlink_verified
        calls = []
        def unlink(root, relative, expected):
            if calls: raise StorageError('changed during deletion')
            original(root, relative, expected); calls.append(relative)
        with patch.object(StorageManager, '_unlink_verified', side_effect=unlink):
            result = self.store.cleanup(values)
        self.assertEqual(result['removedFiles'], 1)
        self.assertEqual(len(result['skipped']), 1)
        self.assertEqual(len(list(self.frames.glob('*.jpg'))), 6)


if __name__ == '__main__': unittest.main()
