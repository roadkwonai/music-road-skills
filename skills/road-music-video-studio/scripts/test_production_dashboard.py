#!/usr/bin/env python3
"""HTTP checks for the bounded production-record dashboard."""
from __future__ import annotations

import http.client
import json
import os
import re
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from studio import Session, init_project, make_handler


class ProductionDashboardTest(unittest.TestCase):
    def test_user_guides_default_to_yue_and_download_only_the_selected_model(self):
        for engine, expected in [('YuE', {'yue-mlx'}), ('ACE', {'ace'})]:
            status, headers, raw = self.request('GET', '/guide/ccm-library.md?engine=' + engine)
            self.assertEqual(status,200)
            markdown=raw.decode()
            examples=[json.loads(block) for block in re.findall(r'```json\n(.*?)\n```',markdown,re.S)]
            self.assertEqual({item['engine'] for item in examples if isinstance(item,dict) and 'engine' in item},expected)
            self.assertIn(engine.lower(),headers['Content-Disposition'])
            status, _, page = self.request('GET','/guide/ccm/?engine='+engine)
            self.assertEqual(status,200)
            self.assertIn(('<h1>'+engine+' CCM').encode(),page)
        status, _, default=self.request('GET','/guide/ccm-library.md')
        self.assertEqual(status,200)
        self.assertNotIn(b'"engine": "ace"',default)
        for query in ['engine=Other','engine=ACE&engine=YuE','engine=']:
            self.assertEqual(self.request('GET','/guide/ccm/?'+query)[0],422)
        status, _, fallback=self.request('GET','/guide/yue-advanced/?engine=ACE')
        self.assertEqual(status,200)
        self.assertNotIn('YuE2 고급 활용 프롬프트'.encode(),fallback)

    def test_activity_page_assets_and_read_only_projection(self):
        status, _, page = self.request('GET', '/dashboard/')
        self.assertEqual(status, 200)
        self.assertIn(b'data-production-activity', page)
        self.assertIn(b'/production-activity.js?token=', page)
        self.assertEqual(self.request('GET', '/production-activity.js')[0], 200)
        with patch('studio.read_runtime_queue', return_value={'state': 'offline', 'paused': None, 'items': [], 'observedAtMs': 1}):
            status, _, raw = self.request('GET', '/api/production/activity?limit=1&offset=0')
            self.assertEqual(status, 200)
            data = json.loads(raw)
            self.assertEqual(data['queue']['items'], [])
            self.assertEqual(data['globalQueue']['queuedCount'], 0)
            self.assertEqual(data['runtime']['state'], 'offline')
        self.assertEqual(self.request('GET', '/api/production/activity?offset=-1')[0], 422)
        self.assertEqual(self.request('GET', '/api/production/activity?groupId=bad')[0], 422)

    def test_recipe_and_ccm_pages_share_authenticated_read_only_library(self):
        studio_status, _, studio_page = self.request('GET','/')
        self.assertEqual(studio_status,200)
        self.assertIn(b'id="studioCcmLink"',studio_page)
        self.assertIn(b"pageUrl('/ccm/')",studio_page)
        for path, collection in [('/recipes/', 'general'), ('/ccm/', 'ccm')]:
            status, _, raw = self.request('GET', path)
            self.assertEqual(status, 200)
            self.assertIn(b'recipe-library.js?token=', raw)
            self.assertIn(collection.encode(), raw)
        self.assertEqual(self.request('GET', '/recipe-library.js')[0], 200)
        for endpoint in ['/api/recipes', '/api/ccm']:
            with patch('studio.recipe_snapshot', return_value={'state':'ready','readOnly':True,'guides':[],'styles':[]}):
                status, _, raw = self.request('GET', endpoint)
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(raw)['readOnly'])
        status, _, guide = self.request('GET', '/guide/ccm/')
        self.assertEqual(status, 200)
        self.assertIn(b'/ccm/?token=', guide)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.previous = os.environ.get("ROADMUSIC_DATA_DIR")
        os.environ["ROADMUSIC_DATA_DIR"] = str(self.root / "profile")
        self.project = self.root / "project"
        init_project(self.project)
        self.session = Session(self.project)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.session))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        if self.previous is None: os.environ.pop("ROADMUSIC_DATA_DIR", None)
        else: os.environ["ROADMUSIC_DATA_DIR"] = self.previous
        self.temp.cleanup()

    def request(self, method, path, body=None, *, origin=False):
        separator = '&' if '?' in path else '?'
        path += separator + 'token=' + self.session.token
        headers = {"Host": f"127.0.0.1:{self.server.server_port}"}
        if origin:
            headers.update({"Origin": self.origin, "X-Studio-Token": self.session.token, "Content-Type": "application/json"})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse(); value = (response.status, dict(response.getheaders()), response.read()); connection.close()
        return value

    def test_dashboard_page_uses_group_scope_and_bounded_api(self):
        group = 'a' * 64
        response = self.session.production.dispatch('request', {'project': str(self.project), 'domain': 'music', 'intent': '초기 음악 요청', 'prompt': '따뜻한 어쿠스틱 곡', 'groupId': group})
        task = self.session.production.dispatch('task-start', {'project': str(self.project), 'domain': 'music', 'taskType': 'generation', 'requestId': response['requestId']})
        self.session.production.dispatch('task-finish', {'taskId': task['taskId'], 'status': 'success', 'elapsedMs': 1250, 'resultSummary': '샘플 음원 생성'})
        status, _headers, page = self.request('GET', '/dashboard/?groupId=' + group)
        self.assertEqual(status, 200)
        self.assertIn(b'Road Music', page); self.assertIn(b'/dashboard.js?token=', page)
        self.assertIn(group.encode(), page)
        status, _headers, body = self.request('GET', '/api/production/dashboard?groupId=' + group)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['summary']['totalTasks'], 1)
        status, _headers, body = self.request('GET', '/api/production/prompts?groupId=' + group + '&limit=1')
        self.assertEqual(status, 200)
        prompts = json.loads(body)
        self.assertEqual(prompts['counts']['requests'], 1); self.assertEqual(prompts['mainPrompts'][0]['prompt'], '따뜻한 어쿠스틱 곡')
        self.assertEqual(prompts['prompts'][0]['taskSummary']['latest']['summary'], '샘플 음원 생성')
        self.assertEqual(self.request('GET', '/api/production/dashboard?cursor=1')[0], 422)
        self.assertEqual(self.request('GET', '/api/production/projects?path=/tmp')[0], 422)

    def test_manual_request_is_bound_to_current_studio_project(self):
        payload = json.dumps({'domain': 'motion', 'intent': '영상 수정 요청', 'prompt': '리듬을 빠르게'}).encode()
        status, _headers, body = self.request('POST', '/api/production/request', payload, origin=True)
        self.assertEqual(status, 201)
        result = json.loads(body)
        self.assertIn('requestId', result)
        projects = json.loads(self.request('GET', '/api/production/projects')[2])['projects']
        self.assertEqual(projects[0]['path'], str(self.project))
        rejected = json.dumps({'domain': 'motion', 'intent': 'x', 'prompt': 'x', 'project': '/tmp'}).encode()
        self.assertEqual(self.request('POST', '/api/production/request', rejected, origin=True)[0], 422)

    def test_group_favorites_and_prompt_queries_stay_in_the_selected_group(self):
        from test_work_library import write_project
        group_ids=[]
        for index in range(2):
            source=self.root / f'source-{index}.mp3';source.write_bytes(f'fixture audio {index}'.encode())
            lyrics=self.root / f'lyrics-{index}.txt';lyrics.write_text(f'가사 {index}',encoding='utf-8')
            project=write_project(self.root,f'published-{index}',source,[('lyrics',lyrics,{})])
            group=self.session.library.register(project);group_ids.append(group['groupId'])
            self.session.production.request({'project':str(project),'groupId':group['groupId'],'domain':'music','prompt':f'group-{index}-only'})
        favorite='/api/works/'+group_ids[0]+'/favorite'
        self.assertEqual(self.request('POST',favorite,json.dumps({'favorite':True}))[0],403)
        self.assertEqual(self.request('POST',favorite,json.dumps({'favorite':'true'}),origin=True)[0],422)
        self.assertEqual(self.request('POST',favorite,json.dumps({'favorite':True}),origin=True)[0],200)
        status,_,body=self.request('GET','/api/works?favoritesOnly=true')
        self.assertEqual(status,200);self.assertEqual([g['groupId'] for g in json.loads(body)['groups']],[group_ids[0]])
        status,_,body=self.request('GET','/api/production/prompts?groupId='+group_ids[0])
        self.assertEqual(status,200);self.assertIn('group-0-only',body.decode());self.assertNotIn('group-1-only',body.decode())
        self.assertEqual(self.request('GET','/work-production.js')[0],200)
        status,headers,shared=self.request('GET','/production-ui.js')
        self.assertEqual(status,200);self.assertIn('text/javascript',headers['Content-Type'])
        self.assertIn(b'RoadMusicProductionUI',shared)
        self.assertEqual(self.request('GET','/production-ui.js/../../studio.py')[0],404)
        self.assertEqual(self.request('GET','/api/works?favoritesOnly=bad')[0],422)
        self.assertEqual(self.request('POST',favorite,json.dumps({'favorite':False}),origin=True)[0],200)
        self.assertEqual(json.loads(self.request('GET','/api/works?favoritesOnly=true')[2])['groups'],[])

    def test_update_routes_require_explicit_confirmation_and_protected_origin(self):
        class Updates:
            def capabilities(self):return {'components':[]}
            def start(self,action,component_id):return {'jobId':'a'*48,'status':'queued','action':action,'componentId':component_id}
            def job(self,job_id):return {'jobId':job_id,'status':'succeeded'}
        self.session._updates=Updates()
        self.assertEqual(self.request('GET','/api/updates/capabilities')[0],200)
        self.assertEqual(self.request('POST','/api/updates/check',json.dumps({'componentId':'road-music-app'}))[0],403)
        self.assertEqual(self.request('POST','/api/updates/update',json.dumps({'componentId':'road-music-app'}),origin=True)[0],422)
        self.assertEqual(self.request('POST','/api/updates/update',json.dumps({'componentId':'road-music-app','confirm':False}),origin=True)[0],422)
        status,_,body=self.request('POST','/api/updates/update',json.dumps({'componentId':'road-music-app','confirm':True}),origin=True)
        self.assertEqual(status,202);self.assertEqual(json.loads(body)['status'],'queued')
        self.assertEqual(self.request('GET','/api/updates/jobs/'+'a'*48)[0],200)


if __name__ == '__main__':
    unittest.main()
