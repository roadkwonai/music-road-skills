#!/usr/bin/env python3
"""End-to-end HTTP checks for source-audio grouped work pages."""
from __future__ import annotations

from datetime import datetime
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote
import zipfile
from zoneinfo import ZoneInfo

from studio import Session, init_project, make_handler, publish, sha256
from management_db import ManagementDBError


class WorkPagesTest(unittest.TestCase):
    def test_work_times_use_one_group_batch_and_exclude_child_stages(self):
        ledger = self.session.production
        for domain, elapsed in [('music', 1000), ('motion', 3000)]:
            task = ledger.start_task({'project': str(self.project), 'groupId': self.media['group'], 'domain': domain, 'taskType': 'generation' if domain == 'music' else 'render'})
            child = ledger.start_task({'project': str(self.project), 'groupId': self.media['group'], 'domain': domain, 'taskType': 'stage:decode', 'parentTaskId': task['taskId']})
            ledger.finish_task({'taskId': child['taskId'], 'status': 'succeeded', 'elapsedMs': 500})
            ledger.finish_task({'taskId': task['taskId'], 'status': 'succeeded', 'elapsedMs': elapsed})
        with patch.object(ledger, 'group_summaries', wraps=ledger.group_summaries) as batch:
            status, _, raw = self.request('GET', '/api/works')
            self.assertEqual(status, 200)
            batch.assert_called_once()
            group = json.loads(raw)['groups'][0]
            self.assertEqual(group['performance']['totalElapsedMs'], 4000)
        status, _, raw = self.request('GET', '/api/works/' + self.media['group'])
        self.assertEqual(status, 200)
        group = json.loads(raw)
        self.assertEqual(group['performance']['music']['totalElapsedMs'], 1000)
        self.assertEqual(group['performance']['motion']['totalElapsedMs'], 3000)
        self.assertEqual(sum(item['elapsedMs'] for item in group['stageBreakdown']), 4000)
        status, _, raw = self.request('GET', '/api/production/dashboard?groupIds=' + quote(json.dumps([self.media['group']])))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['groupSummaries'][0]['performance']['totalElapsedMs'], 4000)
        self.assertEqual(self.request('GET', '/api/production/dashboard?groupIds=' + quote('["not-a-group"]'))[0], 422)
        self.assertEqual(self.request('GET', '/api/production/tasks?groupIds=' + quote(json.dumps([self.media['group']])))[0], 422)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.old_data = os.environ.get('ROADMUSIC_DATA_DIR')
        self.old_delivery_root = os.environ.get('ROADMUSIC_DELIVERY_ROOT')
        os.environ['ROADMUSIC_DATA_DIR'] = str(self.root / 'state')
        os.environ['ROADMUSIC_DELIVERY_ROOT'] = str(self.root)
        self.source = self.file('사용한 음악.mp3', b'original-source')
        self.project, self.media = self.project_with_publish('첫 프로젝트', '첫 영상', '크림슨')
        self.session = Session(self.project, review=True)
        from http.server import ThreadingHTTPServer
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.session))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        if self.old_data is None:
            os.environ.pop('ROADMUSIC_DATA_DIR', None)
        else:
            os.environ['ROADMUSIC_DATA_DIR'] = self.old_data
        if self.old_delivery_root is None:
            os.environ.pop('ROADMUSIC_DELIVERY_ROOT', None)
        else:
            os.environ['ROADMUSIC_DELIVERY_ROOT'] = self.old_delivery_root
        self.temp.cleanup()

    def file(self, name, body):
        path = self.root / name
        path.write_bytes(body)
        return path

    def project_with_publish(self, project_name, video_name, style):
        project = self.root / project_name
        init_project(project, str(self.source), mode='showreel-motion')
        video = self.file(video_name + '.mp4', b'video:' + video_name.encode())
        audio = self.file(video_name + '.m4a', b'audio:' + video_name.encode())
        lyrics = self.file(video_name + '.txt', '첫 줄\n<script>가사 원문</script>\n'.encode())
        captions = self.file(video_name + '.srt', '1\n00:00:00,000 --> 00:00:01,000\n자막 <태그>\n'.encode())
        storyboard = self.file(video_name + '.png', b'not-a-preview-text')
        manifest = self.root / (project_name + '.json')
        manifest.write_text(json.dumps({
            'title': '같은 음악 작업물', 'sourceMusicSha256': sha256(self.source),
            'video': [{'path': str(video), 'styleLabel': style, 'styleId': style.lower()}],
            'audio': [str(audio)], 'lyrics': [str(lyrics)], 'captions': [str(captions)], 'storyboard': [str(storyboard)],
        }, ensure_ascii=False), encoding='utf-8')
        result = publish(project, str(manifest))
        return project, {'video': video, 'audio': audio, 'lyrics': lyrics, 'captions': captions, 'storyboard': storyboard, 'group': result['workGroupId']}

    def request(self, method, path, body=None, *, auth=True, origin=False, content_type=None):
        headers = {'Host': f'127.0.0.1:{self.server.server_port}'}
        query = (('&' if '?' in path else '?') + f'token={self.session.token}') if auth else ''
        if origin:
            headers.update({'Origin': self.origin, 'X-Studio-Token': self.session.token})
        if content_type:
            headers['Content-Type'] = content_type
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path + query, body=body, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def works(self):
        status, _headers, body = self.request('GET', '/api/works')
        self.assertEqual(status, 200)
        return json.loads(body)['groups']

    def detail(self):
        group = self.works()[0]
        status, _headers, body = self.request('GET', '/api/works/' + group['groupId'])
        self.assertEqual(status, 200)
        return json.loads(body)

    def test_publish_preview_has_no_project_side_effect_and_is_authenticated(self):
        before = (self.project / 'studio-project.json').read_bytes()
        value = {'video': [str(self.media['video'])]}
        status, _, body = self.request('POST', '/api/publish-preview', json.dumps(value), origin=True, content_type='application/json')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'preview')
        self.assertTrue(json.loads(body)['removed'])
        self.assertEqual((self.project / 'studio-project.json').read_bytes(), before)
        self.assertEqual(self.request('POST', '/api/publish-preview', '{}', content_type='application/json')[0], 403)

    def test_artifact_preview_and_separate_production_archive(self):
        report = self.file('검증.json', b'{"summary":"explicit evidence"}')
        manifest = self.root / 'artifact-manifest.json'
        manifest.write_text(json.dumps({'sourceMusicSha256': sha256(self.source), 'video': [str(self.media['video'])], 'artifacts': [{'path': str(report), 'artifactType': 'validation'}]}))
        publish(self.project, str(manifest))
        detail = self.detail(); artifact = detail['artifacts'][0]
        self.assertEqual(artifact['summary']['summary'], 'explicit evidence')
        route = '/works/' + detail['groupId'] + '/files/' + artifact['id'] + '/text'
        self.assertEqual(json.loads(self.request('GET', route)[2])['text'], report.read_text())
        for suffix, expected in (('download.zip', False), ('production.zip', True)):
            status, _, body = self.request('GET', '/works/' + detail['groupId'] + '/' + suffix)
            self.assertEqual(status, 200)
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                self.assertEqual(report.name in archive.namelist(), expected)

    def test_same_file_origins_keep_each_project_feedback_visible(self):
        other = self.root / '재사용 프로젝트'
        init_project(other, str(self.source), mode='jizura')
        manifest = self.root / 'same-video.json'; manifest.write_text(json.dumps({'video': [str(self.media['video'])]}))
        publish(other, str(manifest))
        Session(other).save_feedback({'status': 'needs-revision', 'note': '다른 프로젝트 의견'})
        group = self.detail()
        records = json.loads(self.request('GET', '/api/works/' + group['groupId'] + '/records')[2])['records']
        live = [record for record in records if not record.get('historical')]
        self.assertEqual(len(live), 2)
        self.assertIn('다른 프로젝트 의견', [record['feedback']['note'] for record in live])

    def test_sqlite_change_events_are_grouped_and_failed_ledger_rolls_back_metadata(self):
        self.session.save_feedback({'status': 'approved', 'note': 'SQLite 이력 확인'})
        group = self.detail()
        status, _headers, body = self.request('GET', '/api/storage/events?groupId=' + group['groupId'] + '&limit=50')
        self.assertEqual(status, 200)
        events = json.loads(body)['events']
        self.assertTrue(any(event['action'] == 'feedback-change' and event['after']['note'] == 'SQLite 이력 확인' for event in events))
        self.assertEqual(self.request('GET', '/api/storage/events?groupId=' + group['groupId'] + '&limit=101')[0], 422)
        before = (self.project / 'studio-project.json').read_bytes()
        other = self.file('다른 원음.mp3', b'other-source')
        with patch.object(self.session.management, 'record_event', side_effect=ManagementDBError('쓰기 실패')):
            with self.assertRaisesRegex(ValueError, '되돌렸습니다'):
                self.session.set_music(other, external=True)
        self.assertEqual((self.project / 'studio-project.json').read_bytes(), before)
        selection_before = (self.project / 'selection.json').read_bytes()
        saved_selection = json.loads(selection_before)
        selection = {key: saved_selection[key] for key in ('host', 'mode', 'styleId', 'display', 'request') if key in saved_selection}
        selection['display']['showQueue'] = not selection['display']['showQueue']
        with patch.object(self.session.management, 'record_event', side_effect=ManagementDBError('쓰기 실패')):
            with self.assertRaisesRegex(ValueError, '되돌렸습니다'):
                self.session.save_selection(selection)
        self.assertEqual((self.project / 'selection.json').read_bytes(), selection_before)

    def test_pages_and_api_group_source_work_in_korean_time(self):
        status, _headers, page = self.request('GET', '/works/')
        self.assertEqual(status, 200)
        self.assertIn(b'/works.js?token=', page)
        self.assertIn('내 작업물'.encode(), page)
        group = self.detail()
        self.assertEqual(group['groupId'], sha256(self.source))
        self.assertEqual(group['title'], '사용한 음악')
        self.assertEqual({item['kind'] for item in group['files']}, {'video', 'music', 'lyrics', 'captions', 'storyboard'})
        expected_dates = sorted({datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat() for value in group['createdTimes']}, reverse=True)
        self.assertEqual(group['dates'], expected_dates)
        status, _headers, detail_page = self.request('GET', '/works/' + group['groupId'] + '/')
        self.assertEqual(status, 200)
        self.assertIn(group['groupId'].encode(), detail_page)
        self.assertIn(b'data-page="detail"', detail_page)
        self.assertIn(b'work-subnav', detail_page)
        status, headers, script = self.request('GET', '/works.js')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/javascript; charset=utf-8')
        self.assertIn(b'workDraftKey', script)

    def test_source_and_matching_completed_audio_share_one_canonical_playback_file(self):
        final_audio = self.file('완성 원음.mp3', self.source.read_bytes())
        manifest = self.root / 'matching-audio.json'
        manifest.write_text(json.dumps({'sourceMusicSha256': sha256(self.source), 'audio': [str(final_audio)]}), encoding='utf-8')

        publish(self.project, str(manifest))

        group = self.detail()
        final = next(item for item in group['files'] if item['kind'] == 'music' and item['sha256'] == sha256(self.source))
        self.assertEqual(group['source']['path'], final['path'])
        self.assertNotEqual(group['source']['id'], final['id'])
        status, _headers, script = self.request('GET', '/works.js')
        self.assertEqual(status, 200)
        self.assertIn(b"file.kind==='music'&&file.id!==group.source.id", script)
        for item in (group['source'], final):
            status, _headers, body = self.request('GET', f'/works/{group["groupId"]}/files/{item["id"]}')
            self.assertEqual(status, 200)
            self.assertEqual(body, self.source.read_bytes())

    def test_group_files_text_range_and_zip_keep_original_bytes(self):
        group = self.detail()
        files = {item['kind']: item for item in group['files']}
        video = files['video']
        headers = {'Host': f'127.0.0.1:{self.server.server_port}', 'Range': 'bytes=1-4'}
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request('GET', f'/works/{group["groupId"]}/files/{video["id"]}?token={self.session.token}', headers=headers)
        response = connection.getresponse(); body = response.read(); range_headers = dict(response.getheaders()); status = response.status; connection.close()
        self.assertEqual(status, 206)
        self.assertEqual(body, self.media['video'].read_bytes()[1:5])
        self.assertEqual(range_headers['Content-Range'], f'bytes 1-4/{self.media["video"].stat().st_size}')
        for kind, expected in (('lyrics', self.media['lyrics'].read_text()), ('captions', self.media['captions'].read_text())):
            status, _headers, body = self.request('GET', f'/works/{group["groupId"]}/files/{files[kind]["id"]}/text')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['text'], expected)
        status, _headers, _body = self.request('GET', f'/works/{group["groupId"]}/files/{files["storyboard"]["id"]}/text')
        self.assertEqual(status, 404)
        status, headers, archive_bytes = self.request('GET', f'/works/{group["groupId"]}/download.zip')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            expected = [self.source, self.media['video'], self.media['audio'], self.media['lyrics'], self.media['captions'], self.media['storyboard']]
            self.assertEqual(set(archive.namelist()), {path.name for path in expected})
            for path in expected:
                self.assertEqual(archive.read(path.name), path.read_bytes())

    def test_library_routes_require_session_and_reject_invalid_identifiers(self):
        group = self.detail()
        self.assertEqual(self.request('GET', '/works/', auth=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/works/' + '0' * 64)[0], 404)
        self.assertEqual(self.request('GET', '/works/' + group['groupId'] + '/files/' + '0' * 64)[0], 404)
        self.assertEqual(self.request('GET', '/works/%2e%2e/')[0], 404)
        self.assertEqual(self.request('GET', '/works/' + group['groupId'] + '/files/%2e%2e')[0], 404)

    def test_version_routes_accept_only_bound_ids_and_strict_query_values(self):
        group = self.detail()
        from_id, to_id = 'a' * 64, 'b' * 64
        versions = {'versions': [], 'total': 0, 'limit': 2, 'offset': 0}
        diff = {'fromId': from_id, 'toId': to_id, 'groupId': group['groupId'], 'fileChanges': [], 'changes': []}
        foreign = {**diff, 'groupId': 'f' * 64}
        with patch.object(self.session.storage, 'dispatch', side_effect=[versions, diff, foreign]) as command:
            status, _headers, body = self.request('GET', f'/api/works/{group["groupId"]}/versions?limit=2&offset=0&token={self.session.token}', auth=False)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['limit'], 2)
            status, _headers, body = self.request('GET', f'/api/works/{group["groupId"]}/version-diff?fromId={from_id}&toId={to_id}&token={self.session.token}', auth=False)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['fromId'], from_id)
            self.assertEqual(self.request('GET', f'/api/works/{group["groupId"]}/version-diff?fromId={from_id}&toId={to_id}&token={self.session.token}', auth=False)[0], 422)
        self.assertEqual(command.call_args_list[0].args, ('versions', {'groupId': group['groupId'], 'limit': 2, 'offset': 0}))
        self.assertEqual(command.call_args_list[1].args, ('version-diff', {'fromId': from_id, 'toId': to_id}))
        self.assertEqual(self.request('GET', f'/api/works/{group["groupId"]}/versions?limit=101&token={self.session.token}', auth=False)[0], 422)
        self.assertEqual(self.request('GET', f'/api/works/{group["groupId"]}/version-diff?fromId={from_id}&toId=bad&token={self.session.token}', auth=False)[0], 422)

    def test_version_filter_uses_delivery_project_id(self):
        group = self.detail()
        status, _headers, body = self.request('GET', f'/api/works/{group["groupId"]}/versions?token={self.session.token}', auth=False)
        self.assertEqual(status, 200)
        versions = json.loads(body)
        self.assertEqual(versions['total'], 1)
        project_id = versions['projects'][0]['id']
        status, _headers, body = self.request('GET', f'/api/works/{group["groupId"]}/versions?projectId={project_id}&token={self.session.token}', auth=False)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['versions'][0]['projectId'], project_id)
        unknown_project = 'f' * 64
        self.assertEqual(self.request('GET', f'/api/works/{group["groupId"]}/versions?projectId={unknown_project}&token={self.session.token}', auth=False)[0], 422)

    def test_registered_file_removal_requires_a_session_bound_plan(self):
        group = self.detail(); file = next(item for item in group['files'] if item['kind'] == 'video')
        plan_id = 'a' * 48
        preview = {'eligible': True, 'planId': plan_id, 'file': {**file, 'removeDisabled': False}, 'dependencies': [], 'versionReferences': 1}
        cleaned = {'removedFiles': 1, 'freedBytes': file['size'], 'file': {'id': file['id'], 'name': file['name']}, 'tombstonedVersions': 1}
        with patch.object(self.session.storage, 'dispatch', side_effect=[preview, cleaned]) as command:
            payload = json.dumps({'groupId': group['groupId'], 'fileId': file['id']}).encode()
            status, _headers, body = self.request('POST', '/api/storage/file-remove-preview', payload, origin=True, content_type='application/json')
            self.assertEqual(status, 200); self.assertEqual(json.loads(body)['planId'], plan_id)
            self.assertEqual(self.request('POST', '/api/storage/file-remove', json.dumps({'planId': plan_id, 'confirm': False}).encode(), origin=True, content_type='application/json')[0], 422)
            status, _headers, body = self.request('POST', '/api/storage/file-remove', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True, content_type='application/json')
        self.assertEqual(status, 200); self.assertEqual(json.loads(body)['removedFiles'], 1)
        self.assertEqual(command.call_args_list[0].args, ('file-remove-preview', {'groupId': group['groupId'], 'fileId': file['id']}))
        self.assertEqual(command.call_args_list[1].args, ('file-remove', {'planId': plan_id, 'confirm': True}))
        self.assertEqual(self.request('POST', '/api/storage/file-remove', json.dumps({'planId': plan_id, 'confirm': True}).encode(), origin=True, content_type='application/json')[0], 422)

    def test_project_records_and_feedback_are_isolated_per_project(self):
        second, second_media = self.project_with_publish('둘째 프로젝트', '둘째 영상', '민트')
        group_id = second_media['group']
        status, _headers, body = self.request('GET', '/api/works/' + group_id + '/records')
        self.assertEqual(status, 200)
        records = json.loads(body)['records']
        self.assertEqual(len(records), 2)
        wanted = next(record for record in records if record['id'] == hashlib.sha256(str(second.resolve()).encode()).hexdigest())
        payload = json.dumps({'note': '둘째 프로젝트만 수정', 'status': 'needs-revision'}, ensure_ascii=False).encode()
        status, _headers, body = self.request('POST', f'/api/works/{group_id}/records/{wanted["id"]}/feedback', payload, origin=True, content_type='application/json')
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)['note'], '둘째 프로젝트만 수정')
        self.assertEqual(json.loads((second / 'feedback.json').read_text())['note'], '둘째 프로젝트만 수정')
        self.assertEqual(json.loads((self.project / 'feedback.json').read_text())['note'], '')
        status, _headers, _body = self.request('POST', f'/api/works/{group_id}/records/' + '0' * 64 + '/feedback', payload, origin=True, content_type='application/json')
        self.assertEqual(status, 422)
        self.assertEqual(self.request('POST', f'/api/works/{group_id}/records/{wanted["id"]}/feedback', payload, origin=False, content_type='application/json')[0], 403)

    def test_missing_storyboard_is_not_available_as_text_or_partial_zip(self):
        group = self.detail()
        board = next(item for item in group['files'] if item['kind'] == 'storyboard')
        Path(board['path']).unlink()
        refreshed = self.detail()
        refreshed_board = next(item for item in refreshed['files'] if item['kind'] == 'storyboard')
        self.assertFalse(refreshed_board['available'])
        self.assertEqual(self.request('GET', f'/works/{group["groupId"]}/files/{board["id"]}')[0], 404)
        self.assertEqual(self.request('GET', f'/works/{group["groupId"]}/files/{board["id"]}/text')[0], 404)
        self.assertEqual(self.request('GET', f'/works/{group["groupId"]}/download.zip')[0], 409)

    def test_invalid_utf8_caption_is_not_rendered_as_text_but_keeps_original_download(self):
        project = self.root / '손상 자막 프로젝트'
        init_project(project, str(self.source), mode='showreel-motion')
        video = self.file('손상 자막 영상.mp4', b'video-with-bad-caption')
        caption = self.file('손상 자막.srt', b'\xff\xfebroken')
        manifest = self.root / '손상 자막.json'
        manifest.write_text(json.dumps({'sourceMusicSha256': sha256(self.source), 'video': [str(video)], 'captions': [str(caption)]}), encoding='utf-8')
        publish(project, str(manifest))
        group = self.detail()
        item = next(file for file in group['files'] if file['sha256'] == sha256(caption))
        self.assertEqual(self.request('GET', f'/works/{group["groupId"]}/files/{item["id"]}/text')[0], 404)
        with patch('studio.mimetypes.guess_type', return_value=('text/plain', None)):
            status, headers, body = self.request('GET', f'/works/{group["groupId"]}/files/{item["id"]}')
        self.assertEqual(status, 200)
        self.assertTrue(headers['Content-Type'].startswith('application/x-subrip'))
        self.assertEqual(body, caption.read_bytes())


if __name__ == '__main__':
    unittest.main()
