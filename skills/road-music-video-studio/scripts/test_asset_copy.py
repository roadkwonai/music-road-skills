import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from html_design import apply_design, copy_local_asset


class LocalAssetCopyTests(unittest.TestCase):
    def test_copy_preserves_content_metadata_and_independent_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target = root / 'source.bin', root / 'target.bin'
            source.write_bytes(b'original asset')
            stamp = 1_700_000_000_000_000_000
            os.utime(source, ns=(stamp, stamp))
            copy_local_asset(source, target)
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertEqual(target.stat().st_mtime_ns, source.stat().st_mtime_ns)
            self.assertNotEqual(target.stat().st_ino, source.stat().st_ino)
            target.write_bytes(b'changed copy')
            self.assertEqual(source.read_bytes(), b'original asset')

    def test_falls_back_to_copy2_when_path_copy_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target = root / 'source.bin', root / 'target.bin'
            source.write_bytes(b'fallback')
            copy2 = shutil.copy2
            with patch.object(Path, 'copy', None, create=True), patch('html_design.shutil.copy2', wraps=copy2) as fallback:
                copy_local_asset(source, target)
            fallback.assert_called_once_with(source, target)
            self.assertEqual(target.read_bytes(), b'fallback')

    def test_failed_copy_does_not_leave_target_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target.bin'
            with self.assertRaises(FileNotFoundError):
                copy_local_asset(Path(folder) / 'missing.bin', target)
            self.assertFalse(target.exists())

    def test_repeated_design_materialization_keeps_one_font_set(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'review.html'
            page = '<html><head></head><body>검수</body></html>'
            first = apply_design(page, target, ui=False)
            fonts = target.parent / 'road-music-design' / 'fonts'
            expected = {path.name: path.read_bytes() for path in fonts.glob('*.ttf')}
            second = apply_design(first, target, ui=False)
            self.assertEqual(second, first)
            self.assertEqual({path.name: path.read_bytes() for path in fonts.glob('*.ttf')}, expected)
            self.assertEqual(len(list(fonts.glob('*.ttf'))), len(expected))


if __name__ == '__main__':
    unittest.main()
