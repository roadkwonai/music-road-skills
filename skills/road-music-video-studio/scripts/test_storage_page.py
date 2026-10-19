#!/usr/bin/env python3
"""HTTP integration tests for the token-protected storage-management page."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from storage_manager import StorageManager
from studio import Session, init_project, maintenance_storage, make_handler, shared_video_cache


class StoragePageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.cli_root = self.root / 'road-music'
        (self.cli_root / 'cli').mkdir(parents=True)
        (self.cli_root / 'package.json').write_text(json.dumps({'name': 'road-music', 'bin': {'road-music': 'cli/road-music.js'}}), encoding='utf-8')
        (self.cli_root / 'cli' / 'road-music.js').write_text('#!/usr/bin/env node\n', encoding='utf-8')
        (self.cli_root / 'AGENTS.md').write_text('test fixture\n', encoding='utf-8')
        self.environment = patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': str(self.root / 'state'), 'ROADMUSIC_CLI_ROOT': str(self.cli_root)})
        self.environment.start()
        import storage_overview
        import storage_packaging
        import storage_tracking
        self.trusted_roots = [patch.object(module, 'TRUSTED_ROOT', self.cli_root) for module in (storage_packaging, storage_overview, storage_tracking)]
        for item in self.trusted_roots:
            item.start()
        self.project = self.root / 'storage-project'
        init_project(self.project)
        cache = self.project / '.roadmusic' / 'cache'
        cache.mkdir(parents=True, exist_ok=True)
        (cache / 'preview.tmp').write_bytes(b'cache')
        self.session = Session(self.project)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.session))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        for item in reversed(self.trusted_roots):
            item.stop()
        self.environment.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, *, auth=True, origin=False):
        headers = {'Host': f'127.0.0.1:{self.server.server_port}'}
        if auth:
            path += ('&' if '?' in path else '?') + 'token=' + self.session.token
        if origin:
            headers.update({'Origin': self.origin, 'X-Studio-Token': self.session.token, 'Content-Type': 'application/json'})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_storage_page_lists_current_project_and_requires_token(self):
        self.assertEqual(self.request('GET', '/storage/', auth=False)[0], 403)
        status, _headers, page = self.request('GET', '/storage/')
        self.assertEqual(status, 200)
        self.assertIn('Road Music 저장공간 관리'.encode(), page)
        self.assertIn(b'/storage.js?token=', page)
        self.assertIn(b'data-road-music-nav', page)
        status, headers, script = self.request('GET', '/storage.js')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/javascript; charset=utf-8')
        self.assertIn(b'previewAllStorage', script)
        status, _headers, body = self.request('GET', '/api/storage')
        self.assertEqual(status, 200)
        current = next(project for project in json.loads(body)['projects'] if project['path'] == str(self.project))
        self.assertEqual(current['state'], 'editing')
        self.assertIn('maxCacheBytes', current)
        self.assertIn('maxCacheFiles', current)
        self.assertTrue(any(item['relativePath'] == '.roadmusic/cache/preview.tmp' for item in current['unmanagedEntries']))
        status, _headers, body = self.request('GET', '/api/storage/tracking')
        self.assertEqual(status, 200)
        self.assertIn('status', json.loads(body))
        self.assertEqual(self.request('GET', '/api/storage/tracking?refreshWorkspace=no')[0], 422)
        status, _headers, body = self.request('POST', '/api/storage/reconcile-preview', b'{}', origin=True)
        self.assertEqual(status, 200)
        self.assertIn('planId', json.loads(body))

    def test_storage_page_accepts_only_registered_initial_project(self):
        project_id = json.loads(self.request('GET', '/api/storage')[2])['projects'][0]['id']
        status, _headers, page = self.request('GET', '/storage/?projectId=' + project_id)
        self.assertEqual(status, 200)
        self.assertIn(f'"currentProjectId":"{project_id}"'.encode(), page)
        self.assertEqual(self.request('GET', '/storage/?projectId=' + '0' * 64)[0], 422)

    def test_storage_posts_reject_arbitrary_registration_and_keep_lease_read_only(self):
        status, _headers, body = self.request('GET', '/api/storage')
        self.assertEqual(status, 200)
        project_id = json.loads(body)['projects'][0]['id']
        payload = json.dumps({'project': str(self.root / 'outside')}).encode()
        self.assertEqual(self.request('POST', '/api/storage/register', payload, origin=True)[0], 404)
        payload = json.dumps({'projectId': project_id, 'path': '../outside', 'kind': 'cache', 'reproducible': True}).encode()
        self.assertEqual(self.request('POST', '/api/storage/track', payload, origin=True)[0], 422)
        payload = json.dumps({'projectId': project_id, 'path': '.roadmusic/cache/preview.tmp', 'kind': 'cache', 'reproducible': True}).encode()
        status, _headers, body = self.request('POST', '/api/storage/track', payload, origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['relativePath'], '.roadmusic/cache/preview.tmp')
        self.assertEqual(self.request('POST', '/api/storage/lease', b'{}', origin=True)[0], 404)

    def test_storage_policy_preview_and_history_require_real_current_project(self):
        project_id = json.loads(self.request('GET', '/api/storage')[2])['projects'][0]['id']
        policy = json.dumps({'projectId': project_id, 'state': 'completed', 'preserveHistory': False,
                             'autoCleanup': True, 'retainDays': 7, 'maxCacheBytes': 2 * 1024 ** 3,
                             'maxCacheFiles': 20_000}).encode()
        status, _headers, body = self.request('POST', '/api/storage/policy', policy, origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['state'], 'completed')
        preview = json.dumps({'projectId': project_id, 'kinds': ['cache']}).encode()
        status, _headers, body = self.request('POST', '/api/storage/preview', preview, origin=True)
        self.assertEqual(status, 200)
        self.assertIn('planId', json.loads(body))
        self.assertEqual(self.request('GET', '/api/storage/history?projectId=' + '0' * 64)[0], 422)

    def test_entity_removal_preview_is_session_bound_and_current_project_is_blocked(self):
        current_id = json.loads(self.request('GET', '/api/storage')[2])['currentProjectId']
        payload = json.dumps({'projectId': current_id}).encode()
        status, _headers, body = self.request('POST', '/api/storage/project-remove-preview', payload, origin=True)
        self.assertEqual(status, 200)
        blocked = json.loads(body)
        self.assertFalse(blocked['eligible'])
        self.assertIsNone(blocked['planId'])
        other_id, plan_id = 'a' * 64, 'b' * 48
        preview = {'eligible': True, 'planId': plan_id, 'scope': 'project', 'projectIds': [other_id], 'groupIds': [], 'targets': [], 'preserved': [], 'blocked': [], 'warnings': [], 'summary': {}}
        removed = {'removedProjects': 1, 'removedGroups': 0, 'removedFiles': 0, 'freedBytes': 0, 'freedAllocatedBytes': 0, 'remaining': {}}
        with patch.object(self.session.storage, 'dispatch', side_effect=[preview, removed]) as command:
            status, _headers, body = self.request('POST', '/api/storage/project-remove-preview', json.dumps({'projectId': other_id}).encode(), origin=True)
            self.assertEqual(status, 200); self.assertEqual(json.loads(body)['planId'], plan_id)
            self.assertEqual(self.request('POST', '/api/storage/entity-remove', json.dumps({'planId': plan_id, 'confirm': False}).encode(), origin=True)[0], 422)
            status, _headers, body = self.request('POST', '/api/storage/entity-remove', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True)
            self.assertEqual(status, 200); self.assertEqual(json.loads(body)['removedProjects'], 1)
            self.assertEqual(command.call_args_list[0].args, ('project-remove-preview', {'projectId': other_id}))
            self.assertEqual(command.call_args_list[1].args, ('entity-remove', {'planId': plan_id, 'confirm': True}))
        self.assertEqual(self.request('POST', '/api/storage/entity-remove', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True)[0], 422)

    def test_shared_cache_requires_a_session_bound_plan_and_public_cli_confirmation(self):
        preview = {'planId': 'shared-plan', 'cacheDir': '/safe/video-cache', 'files': [{'name': 'frame.bin', 'bytes': 12}], 'blocked': [], 'fileCount': 1, 'bytes': 12}
        cleaned = {'removedFiles': 1, 'freedBytes': 12, 'skipped': [], 'warnings': []}
        with patch('studio.shared_video_cache', side_effect=[preview, cleaned]) as command:
            self.assertEqual(self.request('POST', '/api/storage/shared-preview', b'{}', origin=True)[0], 200)
            self.assertEqual(self.request('POST', '/api/storage/shared-preview', b'{"path":"ignored"}', origin=True)[0], 422)
            self.assertEqual(self.request('POST', '/api/storage/shared-cleanup', json.dumps({'planId': 'wrong', 'confirm': True}).encode(), origin=True)[0], 422)
            self.assertEqual(self.request('POST', '/api/storage/shared-cleanup', json.dumps({'planId': 'shared-plan', 'confirm': False}).encode(), origin=True)[0], 422)
            status, _headers, body = self.request('POST', '/api/storage/shared-cleanup', json.dumps({'planId': 'shared-plan', 'confirm': True}).encode(), origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['freedBytes'], 12)
        self.assertEqual(command.call_args_list[0].args[1:], ('video:cache',))
        self.assertEqual(command.call_args_list[1].args[1:], ('video:cache-clear', 'shared-plan'))
        self.assertEqual(self.request('POST', '/api/storage/shared-cleanup', json.dumps({'planId': 'shared-plan', 'confirm': True}).encode(), origin=True)[0], 422)

    def test_shared_cache_cli_never_starts_an_app(self):
        response = {'ok': True, 'result': {'planId': 'preview', 'files': [], 'blocked': [], 'fileCount': 0, 'bytes': 0}}
        with patch('studio.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(response) + '\n', '')) as command:
            self.assertEqual(shared_video_cache(self.session.storage.data_dir, 'video:cache')['planId'], 'preview')
        args = command.call_args.args[0]
        self.assertEqual(Path(args[1]), self.cli_root / 'cli' / 'road-music.js')
        self.assertIn('--no-start', args)
        self.assertNotIn('--confirm', args)
        self.assertEqual(command.call_args.kwargs['env']['ROADMUSIC_DATA_DIR'], str(self.session.storage.data_dir))

    def test_maintenance_page_uses_fixed_public_cli_and_one_session_plan(self):
        listed = {'workspace': str(self.root), 'scan': {'scanId': 'scan-plan', 'complete': True, 'totals': {'fileCount': 2, 'directoryCount': 1, 'logicalBytes': 12, 'allocatedBytes': 16, 'symlinkCount': 0}, 'folders': [], 'largestFiles': [], 'categories': [], 'errors': [], 'externalLinksCount': 0}, 'git': {'estimatedReclaimableLogicalBytes': 12},
                  'candidates': [{'id': 'git-candidate', 'kind': 'git-unreachable', 'path': '.git/objects/pack/old.pack', 'description': '24시간 지난 미참조 객체', 'fileCount': 1, 'bytes': 12, 'allocatedBytes': 16, 'evidence': 'refs·reflog·worktree 보존'}],
                  'blocked': [], 'summary': {}}
        preview = {'planId': 'maintenance-plan', 'scope': 'git', 'fileCount': 1, 'bytes': 12,
                   'estimatedReclaimableBytes': 12, 'entries': [], 'blocked': []}
        cleaned = {'scope': 'git', 'removedFiles': 1, 'freedBytes': 12, 'freedAllocatedBytes': 16,
                   'diskFreeDeltaBytes': 16, 'skipped': [], 'warnings': [], 'auditPath': '/safe/audit.json'}
        with patch('studio.maintenance_storage', side_effect=[listed, listed, preview, cleaned]) as command:
            status, _headers, body = self.request('GET', '/api/storage/maintenance')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['candidates'][0]['id'], 'git-candidate')
            self.assertEqual(self.request('GET', '/api/storage/maintenance?scope=git')[0], 200)
            invalid = json.dumps({'scanId': 'scan-plan', 'scope': 'git', 'extra': True}).encode()
            self.assertEqual(self.request('POST', '/api/storage/maintenance-preview', invalid, origin=True)[0], 422)
            self.assertEqual(self.request('POST', '/api/storage/maintenance-preview', json.dumps({'scanId': 'wrong', 'scope': 'git'}).encode(), origin=True)[0], 422)
            payload = json.dumps({'scanId': 'scan-plan', 'scope': 'git'}).encode()
            status, _headers, body = self.request('POST', '/api/storage/maintenance-preview', payload, origin=True)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['planId'], 'maintenance-plan')
            self.assertEqual(self.request('POST', '/api/storage/maintenance-cleanup', json.dumps({'planId': 'wrong', 'confirm': True}).encode(), origin=True)[0], 422)
            self.assertEqual(self.request('POST', '/api/storage/maintenance-cleanup', json.dumps({'planId': 'maintenance-plan', 'confirm': False}).encode(), origin=True)[0], 422)
            status, _headers, body = self.request('POST', '/api/storage/maintenance-cleanup', json.dumps({'planId': 'maintenance-plan', 'confirm': True}).encode(), origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['diskFreeDeltaBytes'], 16)
        self.assertEqual(command.call_args_list[0].args[1:], ('maintenance-list', {'includeRetirement': True}))
        self.assertEqual(command.call_args_list[1].args[1:], ('maintenance-list', {'includeRetirement': True, 'scope': 'git'}))
        self.assertEqual(command.call_args_list[2].args[1:], ('maintenance-preview', {'scanId': 'scan-plan', 'scope': 'git'}))
        self.assertEqual(command.call_args_list[3].args[1:], ('maintenance-cleanup', {'planId': 'maintenance-plan'}))
        self.assertTrue(command.call_args_list[3].kwargs['confirm'])
        self.assertEqual(self.request('POST', '/api/storage/maintenance-cleanup', json.dumps({'planId': 'maintenance-plan', 'confirm': True}).encode(), origin=True)[0], 422)

    def test_maintenance_cli_never_starts_an_app_and_needs_confirmation_only_for_cleanup(self):
        response = {'ok': True, 'result': {'workspace': '/safe', 'candidates': [], 'blocked': [], 'summary': {}}}
        with patch('studio.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(response) + '\n', '')) as command:
            self.assertEqual(maintenance_storage(self.session.storage.data_dir, 'maintenance-list', {})['workspace'], '/safe')
        args = command.call_args.args[0]
        self.assertEqual(Path(args[1]), self.cli_root / 'cli' / 'road-music.js')
        self.assertIn('storage:maintenance-list', args)
        self.assertIn('--no-start', args)
        self.assertNotIn('--confirm', args)
        self.assertEqual(command.call_args.kwargs['env']['ROADMUSIC_DATA_DIR'], str(self.session.storage.data_dir))

    def test_restructure_uses_fixed_cli_and_one_session_bound_plan(self):
        plan_id = 'a' * 48
        status = {'state': 'ready', 'legacyBytes': 12}
        preview = {'planId': plan_id, 'fileCount': 1, 'bytes': 12, 'entries': []}
        cleaned = {'planId': plan_id, 'removedFiles': 1, 'freedBytes': 12}
        with patch('studio.maintenance_storage', side_effect=[status, preview, cleaned]) as command:
            response, _headers, body = self.request('GET', '/api/storage/restructure-status')
            self.assertEqual(response, 200)
            self.assertEqual(json.loads(body)['state'], 'ready')
            self.assertEqual(self.request('GET', '/api/storage/restructure-status?extra=1')[0], 422)
            self.assertEqual(self.request('POST', '/api/storage/restructure-preview', b'{"extra":true}', origin=True)[0], 422)
            response, _headers, body = self.request('POST', '/api/storage/restructure-preview', b'{}', origin=True)
            self.assertEqual(response, 200)
            self.assertEqual(json.loads(body)['planId'], plan_id)
            self.assertEqual(self.request('POST', '/api/storage/restructure-cleanup', json.dumps({'planId': plan_id, 'confirm': False}).encode(), origin=True)[0], 422)
            response, _headers, body = self.request('POST', '/api/storage/restructure-cleanup', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True)
        self.assertEqual(response, 200)
        self.assertEqual(json.loads(body)['freedBytes'], 12)
        self.assertEqual(command.call_args_list[0].args[1:], ('restructure-status', {}))
        self.assertEqual(command.call_args_list[1].args[1:], ('restructure-preview', {}))
        self.assertEqual(command.call_args_list[2].args[1:], ('restructure-cleanup', {'planId': plan_id}))
        self.assertTrue(command.call_args_list[2].kwargs['confirm'])
        self.assertEqual(self.request('POST', '/api/storage/restructure-cleanup', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True)[0], 422)

    def test_project_finish_requires_a_session_bound_public_plan(self):
        project_id = json.loads(self.request('GET', '/api/storage')[2])['projects'][0]['id']
        plan_id = 'b' * 48
        preview = {'planId': plan_id, 'summary': {'fileCount': 2, 'allocatedBytes': 4096, 'canonicalFiles': 2}, 'retainedHistoryPath': '/safe/history.json', 'blocked': []}
        cleaned = {'removedFiles': 2, 'freedAllocatedBytes': 4096, 'canonicalFiles': 2, 'retainedHistoryPath': '/safe/history.json'}
        with patch.object(self.session.storage, 'dispatch', side_effect=[preview, cleaned]) as command:
            status, _headers, body = self.request('POST', '/api/storage/project-finish-preview', json.dumps({'projectId': project_id}).encode(), origin=True)
            self.assertEqual(status, 200); self.assertEqual(json.loads(body)['planId'], plan_id)
            self.assertEqual(self.request('POST', '/api/storage/project-finish', json.dumps({'planId': plan_id, 'confirm': False}).encode(), origin=True)[0], 422)
            status, _headers, body = self.request('POST', '/api/storage/project-finish', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True)
        self.assertEqual(status, 200); self.assertEqual(json.loads(body)['removedFiles'], 2)
        self.assertEqual(command.call_args_list[0].args, ('project-finish-preview', {'projectId': project_id}))
        self.assertEqual(command.call_args_list[1].args, ('project-finish', {'planId': plan_id, 'confirm': True}))

    def test_finished_project_preview_returns_noop_without_creating_a_cleanup_plan(self):
        project_id = json.loads(self.request('GET', '/api/storage')[2])['projects'][0]['id']
        self.session.storage_project_finish_plans = {'b' * 48}
        result = {'planId': None, 'alreadyFinished': True, 'summary': {'fileCount': 0}, 'message': '추가 정리가 필요하지 않습니다.'}
        with patch.object(self.session.storage, 'dispatch', return_value=result) as command:
            status, _headers, body = self.request('POST', '/api/storage/project-finish-preview', json.dumps({'projectId': project_id}).encode(), origin=True)
            self.assertEqual(status, 200); self.assertEqual(json.loads(body), result)
            self.assertFalse(self.session.storage_project_finish_plans)
            self.assertEqual(self.request('POST', '/api/storage/project-finish', json.dumps({'planId': 'b' * 48, 'confirm': True}).encode(), origin=True)[0], 422)
            self.assertEqual(command.call_count, 1)

    def test_artifact_maintenance_requires_a_current_scan_and_session_plan(self):
        listed = {'workspace': str(self.root), 'scan': {'scanId': 'artifact-scan', 'complete': True}, 'git': {}, 'candidates': [], 'blocked': [], 'summary': {}}
        preview = {'planId': 'artifact-plan', 'scope': 'artifacts', 'fileCount': 2, 'bytes': 24, 'entries': [], 'blocked': []}
        with patch('studio.maintenance_storage', side_effect=[listed, preview]) as command:
            self.assertEqual(self.request('GET', '/api/storage/maintenance')[0], 200)
            payload = json.dumps({'scanId': 'artifact-scan', 'scope': 'artifacts', 'candidateIds': ['reference-frames']}).encode()
            status, _headers, body = self.request('POST', '/api/storage/maintenance-preview', payload, origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['scope'], 'artifacts')
        self.assertEqual(command.call_args_list[1].args[1:], ('maintenance-preview', {'scanId': 'artifact-scan', 'scope': 'artifacts', 'candidateIds': ['reference-frames']}))

    def test_retirement_maintenance_requires_explicit_candidates(self):
        listed = {'workspace': str(self.root), 'scan': {'scanId': 'retirement-scan', 'complete': True}, 'git': {}, 'candidates': [], 'blocked': [],
                  'retirementReview': [{'label': '과거 렌더', 'fileCount': 4, 'allocatedBytes': 40, 'eligibleFiles': 2, 'eligibleAllocatedBytes': 20, 'protectedFiles': 2, 'protectedAllocatedBytes': 20, 'reason': '최종본 보존'}], 'summary': {}}
        preview = {'planId': 'retirement-plan', 'scope': 'retirement', 'fileCount': 2, 'bytes': 20, 'entries': [], 'blocked': []}
        with patch('studio.maintenance_storage', side_effect=[listed, preview]) as command:
            self.assertEqual(self.request('GET', '/api/storage/maintenance')[0], 200)
            missing = json.dumps({'scanId': 'retirement-scan', 'scope': 'retirement'}).encode()
            self.assertEqual(self.request('POST', '/api/storage/maintenance-preview', missing, origin=True)[0], 422)
            payload = json.dumps({'scanId': 'retirement-scan', 'scope': 'retirement', 'candidateIds': ['old-render']}).encode()
            status, _headers, body = self.request('POST', '/api/storage/maintenance-preview', payload, origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['scope'], 'retirement')
        self.assertEqual(command.call_args_list[1].args[1:], ('maintenance-preview', {'scanId': 'retirement-scan', 'scope': 'retirement', 'candidateIds': ['old-render']}))

    def test_music_overview_and_sweep_use_public_cli_with_session_confirmation(self):
        preview = {'planId': 'a' * 48, 'scanId': 'b' * 48, 'entries': [], 'bytes': 0, 'fileCount': 0}
        overview = {'groups': [{'groupId': 'c' * 64, 'title': '내 음악', 'projects': [], 'mvProjects': []}], 'otherProjects': []}
        with patch('studio.maintenance_storage', side_effect=[overview, overview, preview, {'freedBytes': 12}]) as command:
            status, _, body = self.request('GET', '/api/storage/overview')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['groups'][0]['title'], '내 음악')
            self.assertEqual(self.request('GET', '/api/storage/overview?refreshWorkspace=1')[0], 200)
            self.assertEqual(self.request('GET', '/api/storage/overview?path=/tmp')[0], 422)
            self.assertEqual(self.request('POST', '/api/storage/sweep-preview', b'{"root":"/tmp"}', origin=True)[0], 422)
            self.assertEqual(self.request('POST', '/api/storage/sweep-preview', b'{"mvProjectIds":["../x"]}', origin=True)[0], 422)
            self.assertEqual(self.request('POST', '/api/storage/sweep-preview', b'{}', origin=True)[0], 200)
            payload = json.dumps({'planId': 'a' * 48, 'confirm': False}).encode()
            self.assertEqual(self.request('POST', '/api/storage/sweep-cleanup', payload, origin=True)[0], 422)
            payload = json.dumps({'planId': 'a' * 48, 'confirm': True}).encode()
            self.assertEqual(self.request('POST', '/api/storage/sweep-cleanup', payload, origin=True)[0], 200)
        self.assertEqual(command.call_args_list[0].args[1:], ('overview', {'refreshWorkspace': False}))
        self.assertEqual(command.call_args_list[1].args[1:], ('overview', {'refreshWorkspace': True}))
        self.assertEqual(command.call_args_list[-1].args[1:], ('sweep-cleanup', {'planId': 'a' * 48}))
        self.assertTrue(command.call_args_list[-1].kwargs['confirm'])
        self.assertEqual(self.request('POST', '/api/storage/sweep-cleanup', payload, origin=True)[0], 422)
        self.assertEqual(self.request('POST', '/api/storage/sweep-preview', b'{}')[0], 403)

    def test_clean_workspace_returns_an_empty_sweep_without_a_deletion_plan(self):
        self.session.storage_sweep_plans = {'old-plan'}
        empty = {'planId': None, 'entries': [], 'fileCount': 0, 'bytes': 0, 'blocked': []}
        with patch('studio.maintenance_storage', return_value=empty):
            status, _, body = self.request('POST', '/api/storage/sweep-preview', b'{}', origin=True)
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(body)['planId'])
        self.assertFalse(self.session.storage_sweep_plans)

    def test_storage_list_refreshes_verified_cli_registered_projects(self):
        project = self.root / 'past-cli-project'
        init_project(project)
        StorageManager().dispatch('register', {'project': str(project)})
        status, _headers, body = self.request('GET', '/api/storage')
        self.assertEqual(status, 200)
        self.assertEqual({item['path'] for item in json.loads(body)['projects']}, {str(self.project), str(project)})

    def test_storage_policy_preserves_zero_budgets(self):
        project_id = json.loads(self.request('GET', '/api/storage')[2])['projects'][0]['id']
        payload = json.dumps({'projectId': project_id, 'maxCacheBytes': 0, 'maxCacheFiles': 0}).encode()
        status, _headers, body = self.request('POST', '/api/storage/policy', payload, origin=True)
        self.assertEqual(status, 200)
        project = json.loads(body)
        self.assertEqual(project['maxCacheBytes'], 0)
        self.assertEqual(project['maxCacheFiles'], 0)

    def test_global_preview_skips_missing_projects_without_blocking_current_project(self):
        missing = self.root / 'missing-project'
        init_project(missing)
        registered = self.session.storage.dispatch('register', {'project': str(missing)})
        self.session.storage_projects.add(registered['id'])
        missing.rename(self.root / 'offline-project')
        result = self.session.storage_preview({'kinds': ['cache']})
        self.assertTrue(result['planId'])
        self.assertTrue(any(item['projectId'] == registered['id'] for item in result['blocked']))

    def test_explicit_intermediate_cleanup_needs_history_opt_out_and_confirmation(self):
        intermediate = self.project / '.roadmusic' / 'intermediate' / 'frame.tmp'
        intermediate.parent.mkdir(parents=True, exist_ok=True)
        intermediate.write_bytes(b'intermediate')
        project_id = json.loads(self.request('GET', '/api/storage')[2])['projects'][0]['id']
        track = json.dumps({'projectId': project_id, 'path': '.roadmusic/intermediate/frame.tmp', 'kind': 'intermediate'}).encode()
        status, _headers, body = self.request('POST', '/api/storage/track', track, origin=True)
        self.assertEqual(status, 200)
        entry_id = json.loads(body)['id']
        blocked = json.dumps({'projectId': project_id, 'entryIds': [entry_id]}).encode()
        status, _headers, body = self.request('POST', '/api/storage/preview', blocked, origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['fileCount'], 0)
        policy = json.dumps({'projectId': project_id, 'preserveHistory': False}).encode()
        self.assertEqual(self.request('POST', '/api/storage/policy', policy, origin=True)[0], 200)
        status, _headers, body = self.request('POST', '/api/storage/preview', blocked, origin=True)
        self.assertEqual(status, 200)
        plan_id = json.loads(body)['planId']
        self.assertTrue(intermediate.exists())
        self.assertEqual(self.request('POST', '/api/storage/cleanup', json.dumps({'planId': plan_id, 'confirm': False}).encode(), origin=True)[0], 422)
        status, _headers, body = self.request('POST', '/api/storage/cleanup', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['removedFiles'], 1)
        self.assertFalse(intermediate.exists())

    def test_composite_cleanup_reports_partial_success_when_one_plan_becomes_invalid(self):
        first = self.project / '.roadmusic' / 'cache' / 'first.tmp'
        first.write_bytes(b'first cache')
        second_project = self.root / 'second-storage-project'
        init_project(second_project)
        second = second_project / '.roadmusic' / 'cache' / 'second.tmp'
        final = second_project / 'final.mp4'
        second.write_bytes(b'second cache')
        final.write_bytes(b'published final')
        StorageManager().dispatch('register', {'project': str(second_project)})
        projects = {item['path']: item['id'] for item in json.loads(self.request('GET', '/api/storage')[2])['projects']}
        for project, relative in ((self.project, '.roadmusic/cache/first.tmp'), (second_project, '.roadmusic/cache/second.tmp')):
            payload = json.dumps({'projectId': projects[str(project)], 'path': relative, 'kind': 'cache', 'reproducible': True}).encode()
            self.assertEqual(self.request('POST', '/api/storage/track', payload, origin=True)[0], 200)
        status, _headers, body = self.request('POST', '/api/storage/preview', json.dumps({'kinds': ['cache']}).encode(), origin=True)
        self.assertEqual(status, 200)
        plan_id = json.loads(body)['planId']
        for core_plan in self.session.storage_plans[plan_id]:
            plan = json.loads((self.session.storage.plan_dir / f'{core_plan}.json').read_text())
            if plan['files'][0]['projectId'] == projects[str(second_project)]:
                (self.session.storage.plan_dir / f'{core_plan}.json').unlink()
        status, _headers, body = self.request('POST', '/api/storage/cleanup', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['removedFiles'], 1)
        self.assertTrue(result['errors'])
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(final.read_bytes(), b'published final')

    def test_cleanup_forwards_core_audit_warning(self):
        cache = self.project / '.roadmusic' / 'cache' / 'warning.tmp'
        cache.write_bytes(b'warning cache')
        project_id = json.loads(self.request('GET', '/api/storage')[2])['projects'][0]['id']
        track = json.dumps({'projectId': project_id, 'path': '.roadmusic/cache/warning.tmp', 'kind': 'cache', 'reproducible': True}).encode()
        self.assertEqual(self.request('POST', '/api/storage/track', track, origin=True)[0], 200)
        plan_id = json.loads(self.request('POST', '/api/storage/preview', json.dumps({'projectId': project_id, 'kinds': ['cache']}).encode(), origin=True)[2])['planId']
        dispatch = self.session.storage.dispatch
        def warning_dispatch(action, params):
            result = dispatch(action, params)
            if action == 'cleanup': result['warnings'] = ['감사 이력 저장 실패']
            return result
        self.session.storage.dispatch = warning_dispatch
        status, _headers, body = self.request('POST', '/api/storage/cleanup', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['warnings'], ['감사 이력 저장 실패'])

    def test_legacy_adoption_keeps_preview_session_bound_and_forwards_partial_warnings(self):
        project_id = json.loads(self.request('GET', '/api/storage')[2])['projects'][0]['id']
        original = self.session.storage.dispatch
        candidate = {'id': 'legacy-candidate', 'relativePath': 'out/song-picture.parts', 'bytes': 42, 'fileCount': 1, 'description': '검증된 기존 picture 렌더 캐시', 'evidence': {}}
        def dispatch(action, params):
            if action == 'legacy':
                self.assertEqual(params, {'projectId': project_id})
                return {'candidates': [candidate], 'blocked': [{'relativePath': 'out/song-picture.mp4', 'reason': '완성본 보호'}]}
            if action == 'adopt-preview':
                self.assertEqual(params, {'projectId': project_id, 'candidateIds': ['legacy-candidate']})
                return {'planId': 'a' * 48, 'entries': [{'source': candidate['relativePath'], 'target': '.roadmusic/cache/legacy/x'}], 'bytes': 42, 'fileCount': 1, 'blocked': []}
            if action == 'adopt':
                self.assertEqual(params, {'planId': 'a' * 48, 'confirm': True})
                return {'movedFiles': 1, 'entries': [], 'skipped': [{'relativePath': 'out/changed.parts', 'reason': '변경됨'}], 'warnings': ['감사 기록 저장 실패'], 'auditPath': None}
            return original(action, params)
        self.session.storage.dispatch = dispatch
        status, _headers, body = self.request('GET', '/api/storage/legacy?projectId=' + project_id)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['candidates'][0]['id'], 'legacy-candidate')
        self.assertEqual(self.request('GET', '/api/storage/legacy?projectId=' + '0' * 64)[0], 422)
        preview = json.dumps({'projectId': project_id, 'candidateIds': ['legacy-candidate']}).encode()
        status, _headers, body = self.request('POST', '/api/storage/adopt-preview', preview, origin=True)
        self.assertEqual(status, 200)
        self.assertEqual(self.request('POST', '/api/storage/adopt', json.dumps({'planId': 'a' * 48, 'confirm': False}).encode(), origin=True)[0], 422)
        status, _headers, body = self.request('POST', '/api/storage/adopt', json.dumps({'planId': 'a' * 48, 'confirm': True}).encode(), origin=True)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['movedFiles'], 1)
        self.assertEqual(result['warnings'], ['감사 기록 저장 실패'])
        self.assertEqual(self.request('POST', '/api/storage/adopt', json.dumps({'planId': 'a' * 48, 'confirm': True}).encode(), origin=True)[0], 422)


if __name__ == '__main__':
    unittest.main()
