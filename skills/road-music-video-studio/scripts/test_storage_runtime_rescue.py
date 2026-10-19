import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote


SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from storage_manager import StorageError
from storage_runtime_rescue import ACTIVATION_FILES, LEGACY_ENGINE, REQUIRED_MODEL_FILES, RuntimeRescue


class RuntimeRescueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_temp = tempfile.TemporaryDirectory(prefix='road music ')
        self.root = Path(self.temp.name).resolve()
        self.data = Path(self.data_temp.name).resolve()
        self.source = self.root / LEGACY_ENGINE
        (self.source / 'models').mkdir(parents=True)
        (self.source / 'vae').mkdir()
        (self.source / 'src/src/lyra').mkdir(parents=True)
        (self.source / 'src/vendor/yue/src').mkdir(parents=True)
        (self.source / 'venv/bin').mkdir(parents=True)
        (self.root / 'Output/female-ballads/runtime/yue').mkdir(parents=True)
        external = self.root / 'Output/female-ballads/runtime/yue/converted.safetensors'
        external.write_bytes(b'model')
        asr = self.root / 'Output/female-ballads-20261016/evaluation/asr/ggml-large-v3-turbo.bin'
        asr.parent.mkdir(parents=True)
        asr.write_bytes(b'asr-model')
        (self.source / 'models/ar-8bit.safetensors').symlink_to(external)
        for name in REQUIRED_MODEL_FILES - {'ar-8bit.safetensors'}:
            (self.source / 'models' / name).write_text('{}')
        (self.source / 'vae/model.safetensors').symlink_to(external)
        (self.source / 'vae/config.json').write_text('{}')
        (self.source / 'src/pyproject.toml').write_text('[project]')
        (self.source / 'src/uv.lock').write_text('lock')
        (self.source / 'src/src/lyra/cli.py').write_text('')
        (self.source / 'src/cache_source.py').write_text('source = 1\n')
        (self.source / 'src/__pycache__').mkdir()
        (self.source / 'src/__pycache__/cache_source.cpython-312.pyc').write_bytes(b'\0' + str(self.source).encode())
        (self.source / 'src/__pycache__/orphan.cpython-312.pyc').write_bytes(b'\0' + str(self.source).encode())
        shared = self.data / 'runtime/python/bin/python3.12'
        shared.parent.mkdir(parents=True)
        shared.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).resolve()}" "$@"\n')
        shared.chmod(0o755)
        (self.source / 'venv/bin/python').symlink_to(shared)
        (self.source / 'venv/bin/python3').symlink_to('python')
        for relative in ACTIVATION_FILES:
            path = self.source / relative
            path.write_text(f'VIRTUAL_ENV={self.source}/venv\n')
        console = self.source / 'venv/bin/hf'
        console.write_text(f'#!{self.source}/venv/bin/python\nprint("console-ok")\n')
        console.chmod(0o755)
        editable = self.source / 'venv/lib/python3.12/site-packages/_editable_impl_mlx_yue.pth'
        editable.parent.mkdir(parents=True)
        editable.write_text(f'{self.source}/src/src\n{self.source}/src/vendor/yue/src\n')
        direct = self.source / 'venv/lib/python3.12/site-packages/mlx_yue-0.1.0.dist-info/direct_url.json'
        direct.parent.mkdir(parents=True)
        direct.write_text(json.dumps({'url': f'file://{self.source}/src', 'dir_info': {'editable': True}}, separators=(',', ':')))
        (self.source / 'hf-cache').mkdir()
        (self.source / 'hf-cache/old').symlink_to(self.root / 'Output/deleted-cache')
        payload = {'schema': 1, 'model': str(self.source / 'models'), 'vae': str(self.source / 'vae'), 'precision': '8bit',
                   'doctor': {'model': {'path': str(self.source / 'models')}, 'vae': {'path': str(self.source / 'vae')}}}
        (self.source / 'paths.json').write_text(json.dumps(payload))
        self.rescue = RuntimeRescue(self.root, self.data)

    def tearDown(self):
        self.temp.cleanup()
        self.data_temp.cleanup()

    def test_plan_is_read_only_and_apply_materializes_workspace_model_links(self):
        plan = self.rescue.plan()
        self.assertTrue(any(item['relativePath'] == 'models/ar-8bit.safetensors' and item['kind'] == 'materialize' for item in plan['items']))
        self.assertEqual(plan['discardedBrokenCacheLinks'], ['hf-cache/old'])
        self.assertEqual(plan['discardedRegenerablePythonCaches'], ['src/__pycache__/cache_source.cpython-312.pyc'])
        self.assertFalse((self.data / 'engines/yue-mlx').exists())
        source_activate = {relative: (self.source / relative).read_bytes() for relative in ACTIVATION_FILES}
        source_console = (self.source / 'venv/bin/hf').read_bytes()
        result = self.rescue.apply(plan)
        target = self.data / 'engines/yue-mlx'
        self.assertTrue((target / 'models/ar-8bit.safetensors').is_file())
        self.assertFalse((target / 'models/ar-8bit.safetensors').is_symlink())
        self.assertTrue((target / 'venv/bin/python').is_symlink())
        self.assertEqual((target / 'venv/bin/python').resolve(), self.data / 'runtime/python/bin/python3.12')
        self.assertTrue((target / 'venv/bin/python3').is_symlink())
        self.assertTrue((target / 'venv/bin/hf').read_text().startswith('#!/bin/sh\n'))
        self.assertEqual(stat.S_IMODE((target / 'venv/bin/hf').stat().st_mode), 0o755)
        self.assertEqual(subprocess.run([str(target / 'venv/bin/hf')], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.strip(), 'console-ok')
        self.assertEqual((target / 'venv/lib/python3.12/site-packages/_editable_impl_mlx_yue.pth').read_text(), f'{target}/src/src\n{target}/src/vendor/yue/src\n')
        self.assertEqual(json.loads((target / 'venv/lib/python3.12/site-packages/mlx_yue-0.1.0.dist-info/direct_url.json').read_text())['url'], f'file://{quote(str(target / "src"))}')
        self.assertFalse((target / 'src/__pycache__/cache_source.cpython-312.pyc').exists())
        self.assertTrue((target / 'src/__pycache__/orphan.cpython-312.pyc').is_file())
        manifest = json.loads((target / 'paths.json').read_text())
        self.assertEqual(manifest['model'], str(target / 'models'))
        self.assertEqual(manifest['doctor']['model']['path'], str(target / 'models'))
        self.assertGreater(result['movedAllocatedBytes'], 0)
        self.assertTrue(result['preservedModels'])
        self.assertTrue((self.data / 'models/asr/ggml-large-v3-turbo.bin').is_file())
        self.assertFalse((self.data / 'models/asr/ggml-large-v3-turbo.bin').is_symlink())
        self.assertTrue(self.source.exists())
        self.assertEqual((self.source / 'venv/bin/hf').read_bytes(), source_console)
        for path in target.rglob('*'):
            if path.is_symlink(): self.assertNotIn(self.root, path.resolve(strict=True).parents)
        for relative in ACTIVATION_FILES:
            self.assertEqual((self.source / relative).read_bytes(), source_activate[relative])
            self.assertEqual(stat.S_IMODE((target / relative).stat().st_mode), stat.S_IMODE((self.source / relative).stat().st_mode))
            self.assertIn(str(self.source / 'venv').replace('\\', '/'), (self.source / relative).read_text())
            self.assertIn(str(target / 'venv').replace('\\', '/'), (target / relative).read_text())

    def test_canonical_runtime_can_be_planned_again_after_legacy_removal(self):
        self.rescue.apply(self.rescue.plan())
        shutil.rmtree(self.source)
        (self.root / 'Output/female-ballads-20261016/evaluation/asr/ggml-large-v3-turbo.bin').unlink()
        plan = self.rescue.plan()
        self.assertTrue(plan['alreadyCanonical'])
        self.assertEqual(plan['moves'], [])
        self.assertEqual(self.rescue.apply(plan)['movedAllocatedBytes'], 0)

    def test_absent_runtime_is_a_noop_but_new_or_partial_runtime_is_rejected(self):
        shutil.rmtree(self.source)
        (self.root / 'Output/female-ballads-20261016/evaluation/asr/ggml-large-v3-turbo.bin').unlink()
        plan = self.rescue.plan()
        self.assertTrue(plan['notRequired'])
        self.assertTrue(self.rescue.apply(plan)['notRequired'])
        self.source.mkdir(parents=True)
        with self.assertRaises(StorageError) as appeared:
            self.rescue.apply(plan)
        self.assertEqual(appeared.exception.code, 'changed_runtime')

    def test_partial_or_symlink_runtime_is_not_silently_skipped(self):
        shutil.rmtree(self.source)
        self.source.symlink_to(self.root / 'missing-engine', target_is_directory=True)
        with self.assertRaises(StorageError) as blocked:
            self.rescue.plan()
        self.assertEqual(blocked.exception.code, 'unsafe_runtime')

    def test_source_and_verified_target_return_a_noop_plan(self):
        self.rescue.apply(self.rescue.plan())
        plan = self.rescue.plan()
        self.assertTrue(plan['alreadyCanonical'])
        self.assertEqual(self.rescue.apply(plan)['mappings'], [])

    def test_canonical_retry_ignores_only_source_backed_python_cache(self):
        self.rescue.apply(self.rescue.plan())
        target = self.data / 'engines/yue-mlx'
        generated = target / 'src/__pycache__/cache_source.cpython-312.pyc'
        generated.parent.mkdir(exist_ok=True)
        generated.write_bytes(b'generated')
        self.assertTrue(self.rescue.plan()['alreadyCanonical'])
        (target / 'src/__pycache__/unexpected.cpython-312.pyc').write_bytes(b'unknown')
        with self.assertRaises(StorageError) as blocked:
            self.rescue.plan()
        self.assertEqual(blocked.exception.code, 'target_conflict')

    def test_tampered_canonical_target_or_failed_post_rename_is_not_accepted(self):
        plan = self.rescue.plan()
        with patch.object(self.rescue, '_verify_target', side_effect=StorageError('fail', 'copy_failed')):
            with self.assertRaises(StorageError):
                self.rescue.apply(plan)
        self.assertTrue(self.source.exists())
        self.assertFalse((self.data / 'engines/yue-mlx').exists())
        self.rescue.apply(self.rescue.plan())
        target_config = self.data / 'engines/yue-mlx/models/config.json'
        replacement = target_config.with_name('.config.replacement')
        replacement.write_text('{"tampered":true}')
        replacement.replace(target_config)
        with self.assertRaises(StorageError) as rejected:
            self.rescue.plan()
        self.assertEqual(rejected.exception.code, 'target_conflict')

    def test_changed_source_or_target_conflict_fails_closed(self):
        plan = self.rescue.plan()
        (self.source / 'models/config.json').write_text('{"changed":true}')
        with self.assertRaises(StorageError) as changed:
            self.rescue.apply(plan)
        self.assertEqual(changed.exception.code, 'changed_runtime')
        self.assertFalse((self.data / 'engines/yue-mlx').exists())
        fresh = self.rescue.plan()
        target = self.data / 'engines/yue-mlx'
        target.mkdir(parents=True)
        with self.assertRaises(StorageError) as conflict:
            self.rescue.apply(fresh)
        self.assertEqual(conflict.exception.code, 'target_exists')

    def test_external_links_outside_app_data_are_rejected(self):
        (self.source / 'bad').symlink_to('/bin/sh')
        with self.assertRaises(StorageError) as rejected:
            self.rescue.plan()
        self.assertEqual(rejected.exception.code, 'unsafe_runtime')

    def test_unrecognised_legacy_absolute_pointer_blocks_install(self):
        (self.source / 'venv/bin/legacy-tool').write_text(f'#!{self.source}/venv/bin/python\n# {self.source}\n')
        with self.assertRaises(StorageError) as blocked:
            self.rescue.apply(self.rescue.plan())
        self.assertEqual(blocked.exception.code, 'copy_failed')
        self.assertFalse((self.data / 'engines/yue-mlx').exists())

    def test_content_check_streams_large_files_without_read_bytes(self):
        large = self.root / 'large-model.bin'
        with large.open('wb') as stream:
            stream.truncate(17 * 1024 * 1024)
        snapshot = self.rescue._snapshot(large)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('whole-file read')):
            self.assertTrue(self.rescue._matches_content(large, snapshot))


if __name__ == '__main__':
    unittest.main()
