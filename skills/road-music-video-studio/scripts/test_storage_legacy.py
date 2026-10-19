import json
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path: sys.path.insert(0, str(SCRIPTS))

from storage_legacy import StorageLegacy
from storage_manager import StorageError, StorageManager
import storage_manager
import storage_legacy


class StorageLegacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'; self.root.mkdir()
        (self.root / 'production.json').write_text(json.dumps({'schemaVersion': 1, 'expectedFrames': 30}), encoding='utf-8')
        (self.root / 'playlist.json').write_text(json.dumps({'schemaVersion': 1, 'tracks': []}), encoding='utf-8')
        self.manager = StorageManager(Path(self.temp.name) / 'data')
        self.project = self.manager.dispatch('register', {'project': str(self.root)})
        self.legacy = StorageLegacy(self.manager, probe=lambda path: {'video': True, 'audio': Path(path).name == 'native.mp4', 'duration': 1}, open_check=lambda _: False)

    def tearDown(self): self.temp.cleanup()

    def test_verified_picture_is_adopted_then_uses_normal_cache_cleanup(self):
        out = self.root / 'out'; out.mkdir()
        final, picture = out / 'native.mp4', out / 'native-picture.mp4'
        final.write_bytes(b'final'); picture.write_bytes(b'legacy-cache')
        inventory = self.legacy.legacy({'projectId': self.project['id']})
        self.assertEqual(inventory['candidates'][0]['relativePath'], 'out/native-picture.mp4')
        preview = self.legacy.adopt_preview({'projectId': self.project['id'], 'candidateIds': [inventory['candidates'][0]['id']]})
        adopted = self.legacy.adopt({'planId': preview['planId'], 'confirm': True})
        self.assertEqual(adopted['movedFiles'], 1)
        self.assertTrue(final.exists()); self.assertFalse(picture.exists())
        managed = self.root / adopted['entries'][0]['path']; self.assertTrue(managed.exists())
        cleanup = self.manager.dispatch('preview', {'projectId': self.project['id']})
        self.assertEqual(self.manager.dispatch('cleanup', {'planId': cleanup['planId'], 'confirm': True})['removedFiles'], 1)

    def test_requires_matching_verified_final_and_never_adopts_generic_draft(self):
        out = self.root / 'out'; out.mkdir()
        (out / 'draft.tmp').write_bytes(b'draft')
        (out / 'orphan-picture.mp4').write_bytes(b'orphan')
        self.assertEqual(self.legacy.legacy({'projectId': self.project['id']})['candidates'], [])

    def test_large_parts_snapshot_is_not_a_legacy_candidate(self):
        out = self.root / 'out'; out.mkdir()
        (out / 'native.mp4').write_bytes(b'final')
        parts = out / 'native-picture.parts'; parts.mkdir()
        (parts / 'one.mp4').write_bytes(b'1'); (parts / 'two.mp4').write_bytes(b'2'); (parts / 'concat.txt').write_text('one.mp4\ntwo.mp4', encoding='utf-8')
        with patch.object(storage_manager, 'MAX_TRACK_FILES', 1):
            self.assertEqual(self.legacy.legacy({'projectId': self.project['id']})['candidates'], [])

    def test_completion_audit_failure_returns_warning_after_adoption(self):
        out = self.root / 'out'; out.mkdir()
        (out / 'native.mp4').write_bytes(b'final'); picture = out / 'native-picture.mp4'; picture.write_bytes(b'cache')
        candidate = self.legacy.legacy({'projectId': self.project['id']})['candidates'][0]
        preview = self.legacy.adopt_preview({'projectId': self.project['id'], 'candidateIds': [candidate['id']]})
        original = self.manager._audit
        def flaky(root, action, detail):
            if action == 'legacy-adopt': raise OSError('audit unavailable')
            return original(root, action, detail)
        with patch.object(self.manager, '_audit', side_effect=flaky):
            result = self.legacy.adopt({'planId': preview['planId'], 'confirm': True})
        self.assertEqual(result['movedFiles'], 1)
        self.assertTrue(result['warnings'])
        self.assertFalse(picture.exists())

    def test_final_replacement_or_oversized_text_reference_blocks_adoption(self):
        out = self.root / 'out'; out.mkdir()
        final, picture = out / 'native.mp4', out / 'native-picture.mp4'
        final.write_bytes(b'final'); picture.write_bytes(b'cache')
        candidate = self.legacy.legacy({'projectId': self.project['id']})['candidates'][0]
        preview = self.legacy.adopt_preview({'projectId': self.project['id'], 'candidateIds': [candidate['id']]})
        final.write_bytes(b'replaced-final')
        result = self.legacy.adopt({'planId': preview['planId'], 'confirm': True})
        self.assertEqual(result['movedFiles'], 0); self.assertTrue(picture.exists())
        final.write_bytes(b'final'); (self.root / 'qa.md').write_text('x' * (1024 * 1024 + 1), encoding='utf-8')
        self.assertTrue(self.legacy.legacy({'projectId': self.project['id']})['candidates'])
        (self.root / 'qa.md').write_text('x' * (1024 * 1024) + 'out/native-picture.mp4', encoding='utf-8')
        self.assertEqual(self.legacy.legacy({'projectId': self.project['id']})['candidates'], [])

    def test_parts_uses_only_aggregate_and_final_probes(self):
        out = self.root / 'out'; out.mkdir()
        (out / 'native.mp4').write_bytes(b'final'); (out / 'native-picture.mp4').write_bytes(b'aggregate')
        parts = out / 'native-picture.parts'; parts.mkdir()
        (parts / 'settings.json').write_text(json.dumps({'scale': 1, 'sub': 4, 'shutter': .5, 'format': 'png', 'crf': '16', 'fps': 30, 'W': 1920, 'H': 1080, 'code': 'x'}), encoding='utf-8')
        names = []
        for index in range(105):
            name = f'seg_{index:06}_{index + 60:06}.mp4'; names.append(name); (parts / name).write_bytes(b'segment')
        (parts / 'concat.txt').write_text('\n'.join(names), encoding='utf-8')
        calls = []
        legacy = StorageLegacy(self.manager, probe=lambda path: calls.append(Path(path).name) or {'video': True, 'audio': Path(path).name == 'native.mp4', 'duration': 1}, open_check=lambda _: False)
        candidates = legacy.legacy({'projectId': self.project['id']})['candidates']
        self.assertTrue(any(item['relativePath'].endswith('.parts') for item in candidates))
        self.assertLessEqual(len(calls), 4)

    def test_adopts_parts_before_its_picture_aggregate_and_then_cleans_both(self):
        out = self.root / 'out'; out.mkdir()
        (out / 'native.mp4').write_bytes(b'final'); (out / 'native-picture.mp4').write_bytes(b'picture')
        parts = out / 'native-picture.parts'; parts.mkdir()
        (parts / 'settings.json').write_text(json.dumps({'scale': 1, 'sub': 4, 'shutter': .5, 'format': 'png', 'crf': '16', 'fps': 30, 'W': 1920, 'H': 1080, 'code': 'x'}), encoding='utf-8')
        (parts / 'seg_000000_000060.mp4').write_bytes(b'segment')
        (parts / 'concat.txt').write_text('seg_000000_000060.mp4\n', encoding='utf-8')
        candidates = self.legacy.legacy({'projectId': self.project['id']})['candidates']
        preview = self.legacy.adopt_preview({'projectId': self.project['id'], 'candidateIds': [item['id'] for item in candidates]})
        adopted = self.legacy.adopt({'planId': preview['planId'], 'confirm': True})
        self.assertEqual(adopted['movedFiles'], 4)
        self.assertFalse((out / 'native-picture.mp4').exists()); self.assertFalse(parts.exists())
        cleanup = self.manager.dispatch('preview', {'projectId': self.project['id']})
        self.assertEqual(self.manager.dispatch('cleanup', {'planId': cleanup['planId'], 'confirm': True})['removedFiles'], 4)

    def test_parts_requires_exact_concat_and_segment_names(self):
        out = self.root / 'out'; out.mkdir()
        (out / 'native.mp4').write_bytes(b'final'); (out / 'native-picture.mp4').write_bytes(b'picture')
        parts = out / 'native-picture.parts'; parts.mkdir()
        (parts / 'seg_wrong.mp4').write_bytes(b'x'); (parts / 'concat.txt').write_text('other.mp4\n', encoding='utf-8')
        self.assertFalse(any(item['relativePath'].endswith('.parts') for item in self.legacy.legacy({'projectId': self.project['id']})['candidates']))

    def test_cd_profile_requires_matching_preset_hash(self):
        root = Path(self.temp.name) / 'cd'; root.mkdir(); out = root / 'out'; out.mkdir()
        preset = {'schemaVersion': 1, 'id': 'noir'}; (root / 'preset.json').write_text(json.dumps(preset), encoding='utf-8')
        digest = hashlib.sha256((root / 'preset.json').read_bytes()).hexdigest()
        (root / 'production.json').write_text(json.dumps({'schemaVersion': 1, 'presetId': 'noir', 'presetSha256': digest}), encoding='utf-8')
        (out / 'native.mp4').write_bytes(b'final'); (out / 'native-picture.mp4').write_bytes(b'picture')
        project = self.manager.dispatch('register', {'project': str(root)})
        legacy = StorageLegacy(self.manager, probe=lambda path: {'video': True, 'audio': Path(path).name == 'native.mp4', 'duration': 1}, open_check=lambda _: False)
        self.assertTrue(legacy.legacy({'projectId': project['id']})['candidates'])
        parts = out / 'native-picture.parts'; parts.mkdir()
        (parts / 'settings.json').write_text(json.dumps({'scale': 1, 'sub': 4, 'shutter': .5, 'format': 'png', 'crf': '16', 'fps': 30, 'W': 1920, 'H': 1080, 'code': 'x'}))
        (parts / 'seg_000000_000060.mp4').write_bytes(b'segment')
        (parts / 'concat.txt').write_text('seg_000000_000060.mp4\n')
        self.assertEqual(len(legacy.legacy({'projectId': project['id']})['candidates']), 1)
        (root / 'production.json').write_text(json.dumps({'schemaVersion': 1, 'presetId': 'wrong', 'presetSha256': digest}), encoding='utf-8')
        with self.assertRaises(StorageError): legacy.legacy({'projectId': project['id']})

    def test_streaming_reference_limits_actual_reads_if_file_grows(self):
        note = self.root / 'note.md'; note.write_bytes(b'x')
        original = Path.open
        def growing(path, *args, **kwargs):
            if path == note and args and args[0] == 'rb': return io.BytesIO(b'x' * 128)
            return original(path, *args, **kwargs)
        with patch.object(storage_legacy, 'MAX_REFERENCE_FILE_BYTES', 64), patch.object(Path, 'open', growing):
            self.assertTrue(self.legacy._text_references(self.root, self.root / 'out/picture.mp4'))

    def test_native_profile_requires_delivery_digest_and_streaming_reference_crosses_chunks(self):
        root = (Path(self.temp.name) / 'native').resolve(); root.mkdir(); out = root / 'out'; out.mkdir(); qa = root / 'qa'; qa.mkdir()
        final, picture = out / 'final.mp4', out / 'final-picture.mp4'; final.write_bytes(b'final'); picture.write_bytes(b'picture')
        delivery2 = out / 'shared.mp4'; delivery2.write_bytes(b'shared-final')
        (root / 'project.json').write_text(json.dumps({'ratio': '16:9', 'width': 1920, 'height': 1080, 'fps': 30, 'duration': 1}), encoding='utf-8')
        (root / 'production-state.json').write_text(json.dumps({'status': 'complete', 'finalQa': 'pass', 'delivery': 'pass', 'pending': []}), encoding='utf-8')
        delivery = {'pass': True, 'sourceUnchanged': True, 'lyricsUnchanged': True, 'decodeXerror': 'pass', 'files': {p.name: {'path': str(p), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (final, delivery2)}}
        (qa / 'delivery-check.json').write_text(json.dumps(delivery), encoding='utf-8')
        parts = out / 'final-picture.parts'; parts.mkdir()
        (parts / 'settings.json').write_text(json.dumps({'scale': 1, 'sub': 4, 'shutter': .5, 'format': 'png', 'crf': '16', 'fps': 30, 'W': 1920, 'H': 1080, 'code': 'x'}))
        (parts / 'seg_000000_000060.mp4').write_bytes(b'segment')
        (parts / 'concat.txt').write_text('seg_000000_000060.mp4\n')
        project = self.manager.dispatch('register', {'project': str(root)})
        legacy = StorageLegacy(self.manager, probe=lambda path: {'video': True, 'audio': Path(path).name in {'final.mp4', 'shared.mp4'}, 'duration': 1}, open_check=lambda _: False)
        candidates = legacy.legacy({'projectId': project['id']})['candidates']
        self.assertEqual([p['relativePath'] for p in candidates], ['out/final-picture.parts'])
        preview = legacy.adopt_preview({'projectId': project['id'], 'candidateIds': [candidates[0]['id']]})
        state = json.loads((root / 'production-state.json').read_text()); state['reviewNote'] = 'updated proof'
        (root / 'production-state.json').write_text(json.dumps(state))
        self.assertEqual(legacy.adopt({'planId': preview['planId'], 'confirm': True})['movedFiles'], 0)
        (root / 'note.md').write_text('x' * 65530 + 'out/final-picture.parts', encoding='utf-8')
        self.assertEqual(legacy.legacy({'projectId': project['id']})['candidates'], [])
        (root / 'note.md').unlink(); delivery2.write_bytes(b'changed')
        self.assertEqual(legacy.legacy({'projectId': project['id']})['candidates'], [])
        delivery2.write_bytes(b'shared-final')
        current = legacy.legacy({'projectId': project['id']})['candidates']
        preview = legacy.adopt_preview({'projectId': project['id'], 'candidateIds': [current[0]['id']]})
        self.assertEqual(legacy.adopt({'planId': preview['planId'], 'confirm': True})['movedFiles'], 3)
        cleanup = self.manager.dispatch('preview', {'projectId': project['id']})
        self.assertEqual(self.manager.dispatch('cleanup', {'planId': cleanup['planId'], 'confirm': True})['removedFiles'], 3)
        self.assertTrue(picture.exists()); self.assertTrue(final.exists()); self.assertTrue(delivery2.exists())


if __name__ == '__main__': unittest.main()
