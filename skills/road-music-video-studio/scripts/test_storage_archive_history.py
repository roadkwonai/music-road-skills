import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from storage_manager import StorageError
import storage_archive_history as history
from storage_archive_history import ArchiveHistory


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_zip(path, entries):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries:
            archive.writestr(name, value)


class ArchiveHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.canonical = self.root / 'Output/skills-release-review-20261018/final-dist/MusicRoad-Skills-0.1.1.zip'
        self.canonical.parent.mkdir(parents=True)
        write_zip(self.canonical, [('MusicRoad-Skills-0.1.1/manifest.json', b'{"name":"music-road-skills","version":"0.1.1"}'), ('shared.txt', b'shared')])
        self.source = self.root / 'Output/old/MusicRoad-Skills-0.1.0.zip'
        self.source.parent.mkdir(parents=True)
        write_zip(self.source, [('MusicRoad-Skills-0.1.0/manifest.json', b'{"name":"music-road-skills","version":"0.1.0"}'), ('shared.txt', b'shared'), ('unique.txt', b'unique')])
        self.archive = ArchiveHistory(self.root, canonical_relative=self.canonical.relative_to(self.root))

    def tearDown(self):
        self.temp.cleanup()

    def test_plan_is_read_only_and_prepare_preserves_canonical_and_unique_members(self):
        self.assertFalse((self.root / '.roadmusic').exists())
        plan = self.archive.plan(self.source)
        self.assertFalse((self.root / '.roadmusic').exists())
        shared = next(item for item in plan['members'] if item['name'] == 'shared.txt')
        unique = next(item for item in plan['members'] if item['name'] == 'unique.txt')
        self.assertEqual(shared['canonicalMember'], 'shared.txt')
        self.assertNotIn('canonicalMember', unique)
        result = self.archive.prepare([plan])
        self.assertEqual(len(result['manifests']), 1)
        self.assertGreater(result['storedBytes'], 0)
        self.assertGreater(result['storedAllocatedBytes'], 0)
        manifest = result['manifests'][0]
        checked = self.archive.verify(manifest)
        self.assertEqual(checked['sourceSha256'], plan['source']['sha256'])
        data = json.loads((self.root / manifest['path']).read_text())
        blob = next(item['blob'] for item in data['members'] if item['name'] == 'unique.txt')
        with gzip.open(self.root / blob, 'rb') as stream:
            self.assertEqual(stream.read(), b'unique')
        self.assertTrue(self.canonical.exists())

    def test_prepare_rejects_changed_source_without_writing_history(self):
        plan = self.archive.plan(self.source)
        write_zip(self.source, [('changed.txt', b'changed')])
        with self.assertRaises(StorageError):
            self.archive.prepare([plan])
        self.assertFalse((self.root / '.roadmusic').exists())

    def test_verify_rejects_corrupt_blob(self):
        manifest = self.archive.prepare([self.archive.plan(self.source)])['manifests'][0]
        data = json.loads((self.root / manifest['path']).read_text())
        blob = next(item['blob'] for item in data['members'] if item['name'] == 'unique.txt')
        self.source.unlink()
        self.assertEqual(self.archive.verify(manifest)['memberCount'], 3)
        (self.root / blob).write_bytes(b'broken')
        with self.assertRaises(StorageError):
            self.archive.verify(manifest)

    def test_verify_rejects_changed_canonical(self):
        manifest = self.archive.prepare([self.archive.plan(self.source)])['manifests'][0]
        self.source.unlink()
        self.assertEqual(self.archive.verify(manifest)['memberCount'], 3)
        write_zip(self.canonical, [('shared.txt', b'changed canonical')])
        with self.assertRaises(StorageError):
            self.archive.verify(manifest)

    def test_canonical_archive_is_cached_until_its_snapshot_changes(self):
        original = self.archive._archive
        with patch.object(self.archive, '_archive', wraps=original) as read_archive:
            self.archive.plan(self.source)
            self.archive.plan(self.source)
            canonical_reads = [call for call in read_archive.call_args_list if Path(call.args[0]) == self.canonical]
            self.assertEqual(len(canonical_reads), 1)
            write_zip(self.canonical, [('shared.txt', b'changed canonical')])
            self.archive.plan(self.source)
            canonical_reads = [call for call in read_archive.call_args_list if Path(call.args[0]) == self.canonical]
            self.assertEqual(len(canonical_reads), 2)

    def test_rejects_unsafe_roots_and_unsafe_or_model_archives(self):
        link = self.root.parent / (self.root.name + '-link')
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest(f'symlink unavailable: {error}')
        with self.assertRaises(StorageError):
            ArchiveHistory(link, canonical_relative=self.canonical.relative_to(self.root))
        parent_link = self.root / 'Output/linked'
        parent_link.symlink_to(self.source.parent, target_is_directory=True)
        with self.assertRaises(StorageError):
            self.archive.plan(parent_link / self.source.name)
        bad = self.root / 'Output/bad.zip'
        for entries in [('../escape.txt', b'bad'), ('models/model.safetensors', b'bad')]:
            write_zip(bad, [entries])
            with self.assertRaises(StorageError):
                self.archive.plan(bad)
        model_zip = self.root / 'Output/model-cache.zip'
        write_zip(model_zip, [('notes.txt', b'not a distribution')])
        with self.assertRaises(StorageError):
            self.archive.plan(model_zip)

    def test_rejects_duplicate_encrypted_and_bomb_members(self):
        duplicate = self.root / 'Output/duplicate.zip'
        write_zip(duplicate, [('same.txt', b'a'), ('same.txt', b'b')])
        with self.assertRaises(StorageError):
            self.archive.plan(duplicate)

        encrypted = self.root / 'Output/encrypted.zip'
        write_zip(encrypted, [('secret.txt', b'secret')])
        raw = bytearray(encrypted.read_bytes())
        for marker, offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
            at = raw.find(marker)
            self.assertNotEqual(at, -1)
            raw[at + offset] |= 1
        encrypted.write_bytes(raw)
        with self.assertRaises(StorageError):
            self.archive.plan(encrypted)

        bomb = self.root / 'Output/bomb.zip'
        write_zip(bomb, [('large.txt', b'0123456789')])
        with patch.object(history, 'MAX_UNCOMPRESSED_BYTES', 1), self.assertRaises(StorageError):
            self.archive.plan(bomb)


if __name__ == '__main__':
    unittest.main()
