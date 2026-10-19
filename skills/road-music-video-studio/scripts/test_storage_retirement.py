import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
from storage_manager import StorageManager, StorageError
from storage_retirement import RetirementMaintenance


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.manager = StorageManager(self.root / 'state')
        canonical = self.root / 'Output/skills-release-review-20261018/final-dist/MusicRoad-Skills-0.1.1.zip'; canonical.parent.mkdir(parents=True)
        with zipfile.ZipFile(canonical, 'w') as archive:
            archive.writestr('MusicRoad-Skills-0.1.1/manifest.json', json.dumps({'name': 'music-road-skills', 'version': '0.1.1'}))
        self.project = self.root / 'Output/showreel-fixture/project'
        self.project.mkdir(parents=True)
        self.source = self.root / 'Output/source.mp3'; self.source.write_bytes(b'original song')
        (self.project / 'out').mkdir(); self.final = self.project / 'out/final.mp4'; self.final.write_bytes(b'final delivery')
        (self.project / 'audio').mkdir(); self.mix = self.project / 'audio/mix_bed.wav'; self.mix.write_bytes(b'derived mix')
        (self.project / 'out/draft-proof.mp4').write_bytes(b'old unique draft')
        self.write(self.project / 'production.json', {'schemaVersion': 1, 'source': {'path': str(self.source), 'sha256': sha(self.source)}, 'durationSeconds': 10})
        self.write(self.project / 'playlist.json', {'schemaVersion': 1})
        self.store = RetirementMaintenance(self.root, self.manager, active_check=lambda _: False, probe=lambda _: {'video': True, 'audio': True, 'duration': 10})

    def tearDown(self): self.tmp.cleanup()
    def write(self, p, value): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(value))
    def library(self, files): self.write(self.manager.data_dir / 'video-studio-library.json', {'schemaVersion': 1, 'groups': {'x': {'source': {'path': str(self.source), 'sha256': sha(self.source)}, 'files': files}}})

    def test_keeps_final_original_metadata_and_removes_unique_draft_and_mix(self):
        values = self.store.inspect()['candidates']
        self.assertTrue(values)
        self.assertEqual(sum(x['fileCount'] for x in values), 2)
        result = self.store.cleanup(values)
        self.assertEqual(result['removedFiles'], 2)
        self.assertTrue(self.final.exists()); self.assertTrue(self.source.exists())
        self.assertTrue((self.project / 'production.json').exists())
        self.assertFalse(self.mix.exists())

    def test_newly_registered_final_or_changed_source_invalidates_plan(self):
        values = self.store.inspect()['candidates']
        self.library([{'path': str(self.mix), 'sha256': sha(self.mix), 'kind': 'music'}])
        with self.assertRaises(StorageError): self.store.cleanup(values)
        self.assertTrue(self.mix.exists())
        self.library([]); values = self.store.inspect()['candidates']; self.source.write_bytes(b'changed')
        with self.assertRaises(StorageError): self.store.cleanup(values)
        self.assertTrue(self.mix.exists())

    def test_active_and_pinned_and_links_are_not_retired(self):
        self.assertFalse(RetirementMaintenance(self.root, self.manager, active_check=lambda _: True, probe=self.store.probe).inspect()['candidates'])
        self.mix.unlink(); self.mix.symlink_to(self.final)
        self.assertFalse(any(any(f['relativePath'].endswith('mix_bed.wav') for f in x['files']) for x in self.store.inspect()['candidates']))
        self.assertTrue(self.mix.is_symlink())

    def test_missing_valid_delivery_keeps_all_render_material(self):
        self.final.unlink()
        self.assertFalse(self.store.inspect()['candidates'])
        self.assertTrue(self.mix.exists())

    def test_empty_directory_pruning_never_removes_unselected_appledouble_files(self):
        directory=self.root/'Output/metadata-only';directory.mkdir()
        metadata=directory/'._unselected';metadata.write_bytes(b'unselected metadata')
        self.store._remove_empty('Output/metadata-only')
        self.assertEqual(metadata.read_bytes(), b'unselected metadata')

    def test_qa_representatives_stay_stable_after_cleanup_with_named_final_images(self):
        qa=self.project/'qa';qa.mkdir()
        for name in ['a.png','b.png','c.png','d.png','final-1.png','final-2.png','z.png']:(qa/name).write_bytes(name.encode())
        self.store.cleanup(self.store.inspect()['candidates'])
        self.assertFalse(self.store.inspect()['candidates'])
        self.assertTrue((qa/'final-1.png').is_file())

    def test_all_review_categories_present_and_current_program_models_preserved(self):
        (self.root / 'cli').mkdir(); (self.root / 'cli/app.js').write_text('program')
        (self.root / 'Output/model.safetensors').write_bytes(b'current weights')
        result = self.store.inspect()
        self.assertEqual({x['label'] for x in result['review']}, {'음악·오디오', '영상', '이미지·프레임', '압축·설치 파일', '프로그램·문서·기타', '모델', 'Git'})
        selected = {f['relativePath'] for x in result['candidates'] for f in x['files']}
        self.assertNotIn('cli/app.js', selected); self.assertNotIn('Output/model.safetensors', selected)

    def test_registered_artifact_and_new_hash_or_missing_delivery_protects_its_owner(self):
        before = self.store.inspect()['candidates']
        self.write(self.manager.data_dir / 'video-studio-library.json', {'schemaVersion':1,'groups':{'g':{'artifacts':[{'path':str(self.mix),'sha256':sha(self.mix),'kind':'project-input'}]}}})
        with self.assertRaises(StorageError): self.store.cleanup(before)
        self.mix.write_bytes(b'changed registered input')
        with self.assertRaises(StorageError): self.store.inspect()
        self.write(self.manager.data_dir / 'video-studio-library.json', {'schemaVersion':1,'groups':{'g':{'files':[{'path':str(self.final),'sha256':sha(self.final),'kind':'video'}]}}})
        before=self.store.inspect()['candidates'];self.final.unlink()
        with self.assertRaises(StorageError): self.store.cleanup(before)
        self.assertTrue(self.mix.exists())

    def test_hardlinks_and_live_registry_lease_are_preserved(self):
        os.link(self.mix,self.project/'audio/copy.wav')
        self.assertFalse(any(any(x['relativePath'].endswith('mix_bed.wav') for x in c['files']) for c in self.store.inspect()['candidates']))
        self.write(self.project/'studio-project.json',{'schemaVersion':1,'media':[]})
        project=self.manager.register({'project':str(self.project)})
        self.manager.lease({'projectId':project['id'],'operation':'acquire','pid':os.getpid()})
        self.assertFalse(self.store.inspect()['candidates'])

    def test_small_model_files_and_zip_members_are_never_candidates(self):
        for suffix in ['.bin','.pth','.onnx','.safetensors']:
            target=self.root/'Output/skills-review-20261018/runtime-upgrade-target/road-music-demo/assets'/('model'+suffix)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'model')
            canonical=self.root/'.agents/skills/road-music-demo/assets'/target.name
            canonical.parent.mkdir(parents=True,exist_ok=True);canonical.write_bytes(b'model')
            archive=self.root/'Output/packages'/suffix[1:]/'RoadMusic-CLI-0.1.0.zip'
            archive.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('RoadMusic-CLI-0.1.0/package.json',json.dumps({'name':'road-music','version':'0.1.0'}));z.writestr('models/model'+suffix,b'model')
        selected={x['relativePath'] for c in self.store.inspect()['candidates'] for x in c['files']}
        self.assertFalse(any('/model.' in x or x.endswith('.zip') for x in selected))

    def test_native_frozen_source_hash_is_required_and_preserved(self):
        frozen=self.project/'inputs/music/track.mp3'; frozen.parent.mkdir(parents=True); frozen.write_bytes(b'frozen track')
        self.write(self.project/'playlist.json', {'schemaVersion':1,'tracks':[{'source':{'path':'inputs/music/track.mp3','sha256':sha(frozen)}}]})
        self.write(self.project/'production.json', {'schemaVersion':1,'mode':'native-composition','durationSeconds':10})
        values=self.store.inspect()['candidates'];self.assertTrue(values)
        self.assertFalse(any(x['relativePath'].endswith('track.mp3') for c in values for x in c['files']))
        frozen.write_bytes(b'changed frozen source')
        with self.assertRaises(StorageError): self.store.cleanup(values)
        self.assertTrue(self.mix.exists())

    def reference_case(self,name,page=True):
        case=self.root/'Output/kpop-mainstream-mv-research-20261016'/name;frame=case/'frames-v2';(frame/'sheets').mkdir(parents=True)
        source=case/'source.mp4';source.write_bytes(b'reference-'+name.encode())
        self.write(frame/'manifest.json',{'source':{'path':str(source),'sha256':sha(source)},'extraction_complete':True})
        if page:self.write(case/'provenance.json',{'official_page':'https://example.test/'+name})
        rows=[]
        for i in range(5):
            p=frame/'sheets'/f'sheet-{i:04d}.jpg';p.write_bytes(bytes([i]));rows.append({'sheet':'sheets/'+p.name,'sha256':sha(p)})
        self.write(frame/'sheet-index.json',rows)
        return case,source,frame

    def test_reference_needs_case_bound_url_and_hash_and_verified_representatives(self):
        a,source_a,frame_a=self.reference_case('case-a')
        b,source_b,frame_b=self.reference_case('case-b',page=False)
        self.write(b/'scope.json',{})
        values=self.store.inspect()['candidates'];selected={x['relativePath'] for c in values for x in c['files']}
        self.assertIn(str(source_a.relative_to(self.root)),selected)
        self.assertNotIn(str(source_b.relative_to(self.root)),selected)
        self.assertEqual(len(selected),len([x for c in values for x in c['files']]))
        (frame_a/'sheets/sheet-0000.jpg').write_bytes(b'corrupt representative')
        with self.assertRaises(StorageError): self.store.cleanup(values)
        self.assertTrue(source_a.exists())

    def test_empty_or_url_only_reference_does_not_retire_unverified_media(self):
        path=self.root/'Output/kpop-mainstream-mv-highres-20261016/case/source.mp4';path.parent.mkdir(parents=True);path.write_bytes(b'unknown')
        self.write(path.parent/'scope.json',{})
        selected=lambda:{x['relativePath'] for c in self.store.inspect()['candidates'] for x in c['files']}
        self.assertNotIn(str(path.relative_to(self.root)),selected())
        self.write(path.parent/'provenance.json',{'source_page':'https://example.test/only-url'})
        self.assertNotIn(str(path.relative_to(self.root)),selected())

    def test_product_zip_is_retirable_but_user_zip_and_required_recovery_zip_stay(self):
        path = self.root / 'Output/packages/RoadMusic-CLI-0.1.0.zip'; path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, 'w') as z: z.writestr('RoadMusic-CLI-0.1.0/package.json', json.dumps({'name': 'road-music', 'version': '0.1.0'}))
        user = path.with_name('music-final.zip')
        with zipfile.ZipFile(user, 'w') as z: z.writestr('final.mp4', b'final')
        values = self.store.inspect()['candidates']; archive = [x for x in values if x['kind'] == 'retired-distribution']
        self.assertEqual(sum(x['fileCount'] for x in archive), 1)
        result = self.store.cleanup(archive); self.assertFalse(path.exists()); self.assertTrue(user.exists())
        self.assertEqual(len(result['manifests']), 1)
        self.assertGreaterEqual(result['retainedHistoryAllocatedBytes'], 0)
        self.assertEqual(result['allocationDeltaBytes'], result['freedAllocatedBytes'] - result['retainedHistoryAllocatedBytes'])
        self.assertEqual(self.store.archive_history.verify(result['manifests'][0])['memberCount'], 1)

    def test_archive_history_prepare_failure_keeps_product_zip(self):
        path = self.root / 'Output/packages/RoadMusic-CLI-0.1.0.zip'; path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('RoadMusic-CLI-0.1.0/package.json', json.dumps({'name': 'road-music', 'version': '0.1.0'}))
        archive = [item for item in self.store.inspect()['candidates'] if item['kind'] == 'retired-distribution']
        with patch.object(self.store.archive_history, 'prepare', side_effect=StorageError('fixture history failure')):
            with self.assertRaises(StorageError): self.store.cleanup(archive)
        self.assertTrue(path.exists())

    def test_jizura_full_render_versions_require_current_final_source_and_project_proof(self):
        root = self.root / 'Output/jizura-belluna-20261017'; root.mkdir(parents=True)
        source = self.root / 'belluna.mp3'; source.write_bytes(b'original')
        current = root / '벨루나-오늘도-수고했어-JIZURA-1080p.mp4'; current.write_bytes(b'current final')
        project = root / 'production-project-v3/project.jizura.json'; project.parent.mkdir(); project.write_text('{}')
        versions = []
        for version in ('v2', 'v3'):
            video = root / f'full-render-{version}/jizura.mp4'; video.parent.mkdir(); video.write_bytes(version.encode())
            result = video.parent / 'result.json'; self.write(result, {'ok': True, 'output': str(video), 'bytes': video.stat().st_size, 'duration': 10, 'sourceDuration': 10})
            versions.append(video)
        self.write(root / 'source-provenance.json', {'userAudio': str(source), 'sha256': sha(source), 'byteIdentical': True})
        self.write(root / 'final-render-command.json', ['node', '--project', str(project), '--audio', str(source), '--out', str(root / 'full-render-v3')])
        self.write(root / 'final-assembly.json', {'output': str(current), 'sourceDuration': 10, 'chapters': [{'audio': str(source), 'sha256': sha(source), 'video': str(versions[1])}]})
        store = RetirementMaintenance(self.root, self.manager, active_check=lambda _: False, probe=lambda _: {'video': True, 'audio': True, 'duration': 10})
        candidates = [item for item in store.inspect()['candidates'] if item['kind'] == 'retired-jizura-render']
        self.assertEqual({file['relativePath'] for item in candidates for file in item['files']}, {str(video.relative_to(self.root)) for video in versions})
        result = store.cleanup(candidates)
        self.assertEqual(result['removedFiles'], 2)
        self.assertTrue(current.exists()); self.assertTrue(source.exists()); self.assertTrue(project.exists())
        self.assertTrue(all(not video.exists() for video in versions))

    def test_jizura_versions_are_protected_without_current_final_binding(self):
        root = self.root / 'Output/jizura-belluna-20261017'; root.mkdir(parents=True)
        for version in ('v2', 'v3'):
            video = root / f'full-render-{version}/jizura.mp4'; video.parent.mkdir(); video.write_bytes(version.encode())
            self.write(video.parent / 'result.json', {'ok': True, 'output': str(video), 'bytes': video.stat().st_size, 'duration': 10, 'sourceDuration': 10})
        self.assertFalse(any(item['kind'] == 'retired-jizura-render' for item in self.store.inspect()['candidates']))


if __name__ == '__main__': unittest.main()
