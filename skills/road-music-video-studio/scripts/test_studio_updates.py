import tempfile
import time
import unittest
from pathlib import Path

from studio_updates import StudioUpdates


class Process:
    returncode = 0
    stderr = ''
    def __init__(self, result): self.stdout = '{"ok":true,"result":' + result + '}\n'


class StudioUpdatesTests(unittest.TestCase):
    def test_only_allowlisted_components_start_and_finish(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'cli').mkdir(); (root / 'cli' / 'road-music.js').write_text('', encoding='utf-8')
            skills = root / 'skills'; (skills / 'road-music-skills-update' / 'scripts').mkdir(parents=True); (skills / 'road-music-skills-update' / 'scripts' / 'manage.cjs').write_text('', encoding='utf-8')
            (root / 'manifest.json').write_text('{"skills":[]}', encoding='utf-8')
            def runner(argv, **kwargs):
                self.assertEqual(kwargs['env']['ROADMUSIC_DATA_DIR'], str((root / 'profile').resolve()))
                self.assertEqual(kwargs['env']['ROADMUSIC_STUDIO_AUTO_OPEN'], '0')
                return Process('{"available":false,"installable":false}')
            updates = StudioUpdates(root / 'profile', root=root, skills_parent=skills, runner=runner)
            with self.assertRaises(ValueError): updates.start('check', 'not-allowed')
            job = updates.start('check', 'road-music-cli:current')
            for _ in range(50):
                current = updates.job(job['jobId'])
                if current['status'] != 'queued' and current['status'] != 'running': break
                time.sleep(.01)
            self.assertEqual(current['status'], 'succeeded', current.get('error'))
            with self.assertRaises(ValueError): updates.job('bad')
            with self.assertRaises(ValueError): updates.job('0' * 48)

    def test_restart_required_is_not_reported_as_completed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'cli').mkdir(); (root / 'cli' / 'road-music.js').write_text('', encoding='utf-8')
            def runner(argv, **_):
                command = argv[2]
                if command == 'update:check': return Process('{"installable":true}')
                return Process('{"status":"installing"}')
            updates = StudioUpdates(root / 'profile', root=root, skills_parent=root / 'skills', runner=runner)
            job = updates.start('update', 'road-music-app')
            for _ in range(50):
                current = updates.job(job['jobId'])
                if current['status'] not in {'queued', 'running'}: break
                time.sleep(.01)
            self.assertEqual(current['status'], 'restart-required')
            self.assertEqual(current['phase'], 'restart-required')
            self.assertIsNone(current['progress'])

    def test_dead_install_is_verification_required_and_blocks_only_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'cli').mkdir(); (root / 'cli' / 'road-music.js').write_text('', encoding='utf-8')
            updates = StudioUpdates(root / 'profile', root=root, skills_parent=root / 'skills', runner=lambda *_a, **_k: Process('{"available":false}'))
            job = {'jobId': 'a' * 48, 'componentId': 'road-music-cli:current', 'action': 'update', 'status': 'running', 'phase': 'installing', 'progress': None, 'result': None, 'error': None, 'createdAt': 1, 'finishedAt': None, 'ownerPid': 999999}
            updates._save(job); updates._mark_stale()
            self.assertEqual(updates.job(job['jobId'])['status'], 'verification-required')
            capability = next(item for item in updates.capabilities()['components'] if item['componentId'] == job['componentId'])
            self.assertTrue(capability['canCheck']); self.assertFalse(capability['canUpdate'])
            with self.assertRaises(ValueError): updates.start('update', job['componentId'])

    def test_verified_app_version_releases_restart_required_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'cli').mkdir(); (root / 'cli' / 'road-music.js').write_text('', encoding='utf-8')
            updates = StudioUpdates(root / 'profile', root=root, skills_parent=root / 'skills', runner=lambda *_a, **_k: Process('{"current":"1.2.0"}'))
            job = {'jobId': 'b' * 48, 'componentId': 'road-music-app', 'action': 'update', 'status': 'restart-required', 'phase': 'restart-required', 'progress': None, 'result': None, 'error': None, 'createdAt': 1, 'finishedAt': 2, 'ownerPid': 999999, 'targetVersion': '1.2.0'}
            updates._save(job); updates._verify_prior('road-music-app', '1.2.0')
            self.assertEqual(updates.job(job['jobId'])['phase'], 'verified')
            self.assertEqual(updates.job(job['jobId'])['status'], 'succeeded')

    def wait_done(self, updates, job):
        for _ in range(100):
            current=updates.job(job['jobId'])
            if current['status'] not in {'queued','running'}:return current
            time.sleep(.01)
        self.fail('update fixture did not finish')

    def test_skills_family_blocks_both_directions_and_verified_install_releases_it(self):
        import json
        for component,other in [('music-road-skills','skill:example'),('skill:example','music-road-skills')]:
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temp:
                root=Path(temp);skills=root/'skills';script=skills/'road-music-skills-update/scripts/manage.cjs';script.parent.mkdir(parents=True);script.write_text('')
                (root/'manifest.json').write_text(json.dumps({'skills':[{'id':'example'}]}));state=skills/'.music-road-skills/managed.json';state.parent.mkdir();state.write_text('{}')
                updates=StudioUpdates(root/'profile',root=root,skills_parent=skills,runner=lambda *_a,**_k:Process('{"installed":true,"version":"1.2.0","locallyModified":[],"currentVersion":"1.2.0"}'))
                self.addCleanup(updates.executor.shutdown,wait=True)
                prior={'jobId':'c'*48,'componentId':component,'status':'verification-required','phase':'verification-required','action':'update','targetVersion':'1.2.0','ownerPid':999999,'createdAt':1}
                updates._save(prior)
                capabilities={v['componentId']:v for v in updates.capabilities()['components']}
                self.assertFalse(capabilities[component]['canUpdate']);self.assertFalse(capabilities[other]['canUpdate'])
                with self.assertRaises(ValueError):updates.start('update',other)
                self.assertEqual(self.wait_done(updates,updates.start('check',other))['status'],'succeeded')
                self.assertEqual(updates.job(prior['jobId'])['phase'],'verified')
                self.assertTrue(next(v for v in updates.capabilities()['components'] if v['componentId']==other)['canUpdate'])

    def test_unresolved_jobs_survive_start_and_stale_compaction(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'cli').mkdir();(root/'cli/road-music.js').write_text('')
            updates=StudioUpdates(root/'profile',root=root,runner=lambda *_a,**_k:Process('{"current":"0.0.1"}'))
            self.addCleanup(updates.executor.shutdown,wait=True)
            for i in range(41):updates._save({'jobId':format(i,'048x'),'componentId':'road-music-app','action':'update','status':'verification-required','phase':'verification-required','targetVersion':'1.2.0','ownerPid':999999,'createdAt':i})
            updates._mark_stale();self.wait_done(updates,updates.start('check','road-music-app'))
            self.assertEqual(updates.job('0'*48)['status'],'verification-required')
            self.assertEqual(sum(v['status']=='verification-required' for v in updates.db.read_document('studio-update-jobs')),41)
            self.assertFalse(next(v for v in updates.capabilities()['components'] if v['componentId']=='road-music-app')['canUpdate'])

    def test_cli_recovery_checks_the_verified_side_by_side_install_version(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'cli').mkdir();(root/'cli/road-music.js').write_text('')
            home=root/'cli-home';new=home/'1.2.0';script=new/'cli/road-music.js';script.parent.mkdir(parents=True);script.write_text('')
            (new/'.road-music-cli-install.json').write_text(json.dumps({'cliVersion':'1.2.0'}));(home/'current.json').write_text(json.dumps({'cliVersion':'1.2.0','cliPath':str(script)}))
            def runner(argv,**_):return Process('{"cliVersion":"1.2.0"}' if Path(argv[1]).resolve()==script.resolve() else '{"current":"1.0.0","version":"1.2.0"}')
            updates=StudioUpdates(root/'profile',root=root,runner=runner,env={'ROADMUSIC_CLI_HOME':str(home)})
            self.addCleanup(updates.executor.shutdown,wait=True)
            prior={'jobId':'e'*48,'componentId':'road-music-cli:current','action':'update','status':'verification-required','phase':'verification-required','targetVersion':'1.2.0','ownerPid':999999,'createdAt':1};updates._save(prior)
            self.wait_done(updates,updates.start('check','road-music-cli:current'))
            self.assertEqual(updates.job(prior['jobId'])['phase'],'verified')

    def test_installer_response_loss_never_claims_failure_or_allows_duplicate_update(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'cli').mkdir();(root/'cli/road-music.js').write_text('')
            def runner(argv,**_):
                if argv[2]=='update:check':return Process('{"current":"1.0.0","version":"1.2.0","installable":true}')
                if argv[2]=='update:download':return Process('{"status":"downloaded"}')
                raise subprocess.TimeoutExpired(argv,1)
            updates=StudioUpdates(root/'profile',root=root,runner=runner);self.addCleanup(updates.executor.shutdown,wait=True)
            job=self.wait_done(updates,updates.start('update','road-music-app'))
            self.assertEqual(job['status'],'verification-required')
            with self.assertRaises(ValueError):updates.start('update','road-music-app')

    def test_opening_update_status_does_not_initialize_an_existing_unrelated_database(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            profile=Path(temp)/'profile';profile.mkdir();database=profile/'storage.sqlite3'
            with sqlite3.connect(database) as connection:connection.execute('CREATE TABLE sentinel (value TEXT)')
            before=database.stat().st_mtime_ns
            updates=StudioUpdates(profile,root=Path(temp));self.addCleanup(updates.executor.shutdown,wait=True)
            updates.capabilities()
            self.assertEqual(database.stat().st_mtime_ns,before)
            with sqlite3.connect(database) as connection:self.assertEqual(connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0],1)

    def test_managed_skills_install_does_not_require_a_source_manifest(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);skills=root/'installed-skills';script=skills/'road-music-skills-update/scripts/manage.cjs';script.parent.mkdir(parents=True);script.write_text('')
            state=skills/'.music-road-skills/managed.json';state.parent.mkdir();state.write_text(json.dumps({'skills':{'example':{'path':'example'}}}))
            updates=StudioUpdates(root/'profile',root=root,skills_parent=skills);self.addCleanup(updates.executor.shutdown,wait=True)
            self.assertEqual(updates._skill_script(),script.resolve())
            self.assertTrue(next(row for row in updates.capabilities()['components'] if row['componentId']=='skill:example')['canUpdate'])

    def test_explicit_check_blocks_locally_modified_skills_without_rehashing_each_page(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);skills=root/'skills';script=skills/'road-music-skills-update/scripts/manage.cjs';script.parent.mkdir(parents=True);script.write_text('')
            state=skills/'.music-road-skills/managed.json';state.parent.mkdir();state.write_text(json.dumps({'skills':{'example':{}}}))
            updates=StudioUpdates(root/'profile',root=root,skills_parent=skills,runner=lambda *_a,**_k:Process('{"installed":true,"version":"1.0.0","locallyModified":["example"]}'));self.addCleanup(updates.executor.shutdown,wait=True)
            self.wait_done(updates,updates.start('check','music-road-skills'))
            cap=next(v for v in updates.capabilities()['components'] if v['componentId']=='music-road-skills')
            self.assertFalse(cap['canUpdate']);self.assertIn('로컬 수정',cap['reason'])
            with self.assertRaises(ValueError):updates.start('update','skill:example')

if __name__ == '__main__':
    unittest.main()
