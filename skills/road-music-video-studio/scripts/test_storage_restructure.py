import json
import hashlib
import sqlite3
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from storage_manager import StorageManager,StorageError
from storage_restructure import StorageRestructure

class RestructureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()/'repo';self.root.mkdir();self.manager=StorageManager(self.root.parent/'data')
  for name in ('storage_restructure.is_workspace','storage_maintenance.is_workspace'):
   p=patch(name,return_value=True);p.start();self.addCleanup(p.stop)
  self.store=StorageRestructure(self.manager,self.root)
  self.trash=self.root/'Output/legacy-test/render.tmp';self.trash.parent.mkdir(parents=True);self.trash.write_bytes(b'old experiment')
  self.program=self.root/'cli/current.js';self.program.parent.mkdir();self.program.write_bytes(b'current application')
  self.scan=patch('storage_restructure.WorkspaceScan');self.scanmock=self.scan.start();self.addCleanup(self.scan.stop);self.scanmock.return_value.scan.return_value={'complete':True,'scanId':'a'*48,'totals':{'allocatedBytes':4096}}
  self.runtime=patch('storage_runtime_rescue.RuntimeRescue');self.rescue=self.runtime.start();self.addCleanup(self.runtime.stop);self.rescue.return_value.plan.return_value={'moves':[]};self.rescue.return_value.apply.return_value={'mappings':[]}
 def test_explicit_plan_deletes_only_original_legacy_roots_and_keeps_program_and_canonical(self):
  canonical=self.root/'Output/song--0123456789ab/final.mp4';canonical.parent.mkdir();canonical.write_bytes(b'approved final')
  self.store.marker.parent.mkdir(exist_ok=True);self.store.marker.write_text(json.dumps({'schemaVersion':1,'deliveryRoots':['Output/song--0123456789ab']}))
  with sqlite3.connect(self.store.control/'history.sqlite3')as connection:
   connection.execute('CREATE TABLE delivery_files(path TEXT)');connection.execute('INSERT INTO delivery_files VALUES (?)',(str(canonical),))
  connection.close()
  preview=self.store.preview({});self.assertEqual(preview['summary']['legacyFileCount'],1)
  with self.assertRaises(StorageError):self.store.cleanup({'planId':preview['planId']})
  result=self.store.cleanup({'planId':preview['planId'],'confirm':True})
  self.assertFalse(self.trash.exists());self.assertEqual(canonical.read_bytes(),b'approved final');self.assertEqual(self.program.read_bytes(),b'current application');self.assertEqual(result['removedFiles'],1)
  with self.assertRaises(StorageError):self.store.cleanup({'planId':preview['planId'],'confirm':True})
 def test_changed_file_or_added_file_invalidates_without_deleting_anything(self):
  preview=self.store.preview({});self.trash.write_bytes(b'new work')
  with self.assertRaises(StorageError):self.store.cleanup({'planId':preview['planId'],'confirm':True})
  self.assertTrue(self.trash.exists());self.rescue.return_value.apply.assert_not_called()
 def test_failed_runtime_or_delivery_preparation_keeps_legacy_original(self):
  preview=self.store.preview({});self.rescue.return_value.apply.side_effect=StorageError('rescue failed')
  with self.assertRaises(StorageError):self.store.cleanup({'planId':preview['planId'],'confirm':True})
  self.assertTrue(self.trash.exists())
 def test_external_symlink_is_unlinked_without_touching_target(self):
  outside=self.root.parent/'model.bin';outside.write_bytes(b'protected shared model');link=self.trash.parent/'alias';link.symlink_to(outside)
  preview=self.store.preview({});self.store.cleanup({'planId':preview['planId'],'confirm':True});self.assertEqual(outside.read_bytes(),b'protected shared model');self.assertFalse(link.is_symlink())
 def test_preview_rejects_paths_and_output_symlink(self):
  with self.assertRaises(StorageError):self.store.preview({'root':'/'})

 def test_new_canonical_music_after_first_migration_is_not_legacy(self):
  canonical=self.root/'Output/new-song/project/20261019-123456/final.mp3';canonical.parent.mkdir(parents=True);canonical.write_bytes(b'newly published final')
  self.store.control.mkdir(exist_ok=True)
  with sqlite3.connect(self.store.control/'history.sqlite3')as connection:
   connection.execute('CREATE TABLE delivery_files(path TEXT)');connection.execute('INSERT INTO delivery_files VALUES (?)',(str(canonical),))
  connection.close()
  self.assertFalse(any(root==canonical or root in canonical.parents for root in self.store._roots()))

 def test_import_groups_registration_events_without_file_timestamp_duplicates(self):
  audio=self.trash;video=self.trash.parent/'final.mp4';video.write_bytes(b'final')
  group={'source':{'path':str(audio)},'files':[{'path':str(path),'createdAt':date,'origins':[{'project':'/project','registeredAt':None},{'project':'/project','registeredAt':'2026-10-18T12:34:56Z'}]}for path,date in[(audio,'2026-10-17T10:00:00Z'),(video,'2026-10-18T11:00:00Z')]]}
  events=self.store._delivery_events(group);self.assertEqual(len(events),1);self.assertEqual(len(next(iter(events.values()))),2)
  for item in group['files']:item['origins']=[{'project':'/project','registeredAt':None}]
  self.assertEqual(len(self.store._delivery_events(group)),1)

 def test_registered_finals_are_copied_before_retirement_and_library_is_available(self):
  from work_library import WorkLibrary
  project=self.trash.parent/'studio';project.mkdir();music=project/'song.mp3';music.write_bytes(b'approved song');video=project/'final.mp4';video.write_bytes(b'approved video')
  media=[{'id':key,'kind':kind,'path':str(p),'name':p.name,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for key,kind,p in [('music','music',music),('final','video',video)]]
  (project/'studio-project.json').write_text(json.dumps({'schemaVersion':1,'name':'approved song','media':media,'mode':'showreel-motion'}))
  library=WorkLibrary(self.store.library);library.register(project);preview=self.store.preview({});result=self.store.cleanup({'planId':preview['planId'],'confirm':True})
  self.assertEqual(result['deliveryVersions'],1);self.assertFalse(project.exists())
  group=next(iter(library._read()['groups'].values()))
  for item in [group['source'],*group['files']]:
   p=Path(item['path']);self.assertTrue(p.is_relative_to(self.root/'Output'));self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),item['sha256']);self.assertTrue(library._public_file(item)['available'])

 def test_registered_finished_song_can_be_the_same_file_as_its_source(self):
  from work_library import WorkLibrary
  project=self.trash.parent/'music-only';project.mkdir();music=project/'song.flac';music.write_bytes(b'completed recorded song');poster=project/'poster.jpg';poster.write_bytes(b'approved poster')
  media=[{'id':key,'kind':kind,'path':str(p),'name':p.name,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for key,kind,p in [('music','music',music),('poster','storyboard',poster)]]
  (project/'studio-project.json').write_text(json.dumps({'schemaVersion':1,'name':'finished song','media':media,'mode':'showreel-motion'}))
  library=WorkLibrary(self.store.library);library.register(project)
  with self.assertRaisesRegex(ValueError,'완성 음원 또는 영상'):self.store._import_deliveries()
  data=library._read();group=next(iter(data['groups'].values()));group['files'].append({**group['source'],'kind':'music','origins':group['files'][0]['origins']});library._save(data)
  preview=self.store.preview({});result=self.store.cleanup({'planId':preview['planId'],'confirm':True})
  self.assertEqual(result['deliveryVersions'],1);self.assertFalse(project.exists());self.assertEqual(len(list((self.root/'Output').rglob('song.flac'))),1)

 def test_missing_empty_temporary_registration_is_planned_and_pruned_only_if_unchanged(self):
  import shutil
  gone=self.root.parent/'gone-project';gone.mkdir();(gone/'studio-project.json').write_text('{"schemaVersion":1,"media":[]}')
  row=self.manager.register({'project':str(gone)});key=row['id'];shutil.rmtree(gone)
  preview=self.store.preview({});self.assertEqual(preview['summary']['obsoleteRegistrations'],1)
  result=self.store.cleanup({'planId':preview['planId'],'confirm':True});self.assertEqual(result['prunedRegistrations'],1);self.assertNotIn(key,self.manager._read()['projects'])
  gone.mkdir();(gone/'studio-project.json').write_text('{"schemaVersion":1,"media":[]}');self.manager.register({'project':str(gone)});shutil.rmtree(gone)
  preview=self.store.preview({});gone.mkdir()
  result=self.store.cleanup({'planId':preview['planId'],'confirm':True});self.assertEqual(result['prunedRegistrations'],0);self.assertIn(key,self.manager._read()['projects']);self.assertTrue(gone.is_dir())
  import os
  gone.rmdir();data=self.manager._read();data['leases'][key]={'pid':os.getpid(),'token':'active'};self.manager._save(data);self.assertEqual(self.store.preview({})['summary']['obsoleteRegistrations'],0)

 def test_active_script_and_open_file_both_block_the_plan(self):
  command=subprocess.CompletedProcess([],0,stdout='99999 '+str(self.trash.parent/'server.py'),stderr='')
  with patch('storage_restructure.subprocess.run',return_value=command):
   with self.assertRaises(StorageError):self.store.preview({})
  rows=[subprocess.CompletedProcess([],0,stdout='',stderr=''),subprocess.CompletedProcess([],0,stdout='p99999\nn'+str(self.trash)+'\n',stderr='')]
  with patch('storage_restructure.subprocess.run',side_effect=rows):
   with self.assertRaises(StorageError):self.store.preview({})
  self.assertTrue(self.trash.exists())

 def test_noop_runtime_rescue_never_skips_failed_import_on_retry(self):
  self.rescue.return_value.apply.return_value={'mappings':[],'preservedModels':[{'sha256':'a'*64}]}
  with patch.object(self.store,'_idle'),patch('storage_restructure.subprocess.run',side_effect=FileNotFoundError('runtime unavailable'))as probe:
   for attempt in range(2):
    plan=self.store.preview({})
    with self.assertRaises(StorageError):self.store.cleanup({'planId':plan['planId'],'confirm':True})
    self.assertTrue(self.trash.exists())
   self.assertEqual(probe.call_count,2)

 def test_lexical_work_prefix_never_allows_origin_path_traversal(self):
  audio=self.trash;digest=hashlib.sha256(audio.read_bytes()).hexdigest();outside=self.root/'outside';outside.mkdir();marker=outside/'studio-project.json';marker.write_text('{"private":true}')
  bad=str(self.store.control/'work/../../outside')
  group={'title':'song','source':{'path':str(audio),'sha256':digest,'kind':'source'},'files':[{'path':str(audio),'sha256':digest,'kind':'music','createdAt':'2026-10-18T12:00:00Z','origins':[{'project':bad,'registeredAt':'2026-10-18T12:00:00Z'}]}]}
  self.store.library.parent.mkdir(exist_ok=True);self.store.library.write_text(json.dumps({'schemaVersion':1,'groups':{digest:group}}))
  with self.assertRaises(StorageError):self.store._import_deliveries()
  self.assertEqual(marker.read_text(),'{"private":true}')

if __name__=='__main__':unittest.main()
