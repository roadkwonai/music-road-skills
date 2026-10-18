import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from studio import MAX_LYRICS_TEXT, Session, init_project, make_handler, publish, sha256


class DeliverableTests(unittest.TestCase):
    def make_project(self):
        folder = tempfile.TemporaryDirectory()
        root = Path(folder.name).resolve()
        source = root / '원음.mp3'
        source.write_bytes(b'original-audio')
        project = root / 'desk'
        init_project(project, music=str(source))
        return folder, root, project, source

    def publish_all(self, project, source, root):
        video = root / '완성 영상.mp4'
        audio = root / '완성 음원.mp3'
        captions = root / '자막.srt'
        lyrics = root / '원가사.txt'
        video.write_bytes(b'video')
        audio.write_bytes(b'finished-audio')
        captions.write_text('1\n00:00:00,000 --> 00:00:01,000\n자막\n', encoding='utf-8')
        lyrics.write_bytes('첫 줄\n둘째 줄\n'.encode('utf-8-sig'))
        manifest = root / 'publish.json'
        manifest.write_text(json.dumps({
            'title': '완성된 곡', 'sourceMusicSha256': sha256(source),
            'video': [str(video)], 'audio': [str(audio)],
            'captions': [str(captions)], 'lyrics': [str(lyrics)],
        }, ensure_ascii=False), encoding='utf-8')
        publish(project, str(manifest))
        return video, audio, captions, lyrics

    def server(self, session):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(session))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        return server

    @staticmethod
    def get(server, path, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', server.server_port)
        client.request('GET', path, headers=headers or {})
        response = client.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        client.close()
        return result

    def test_publish_exposes_finished_media_and_original_lyrics(self):
        folder, root, project, source = self.make_project()
        self.addCleanup(folder.cleanup)
        _, _, _, lyrics = self.publish_all(project, source, root)
        state = Session(project, review=True).state()

        self.assertEqual(state['media']['music']['name'], source.name)
        self.assertEqual(state['media']['music']['size'], source.stat().st_size)
        self.assertIn('download=1', state['media']['music']['downloadUrl'])
        self.assertEqual(len(state['media']['review']['videos']), 1)
        self.assertEqual(len(state['media']['review']['audios']), 1)
        self.assertEqual(len(state['media']['review']['captions']), 1)
        self.assertEqual(len(state['media']['review']['lyrics']), 1)
        entry = state['media']['review']['lyrics'][0]
        self.assertEqual(entry['name'], lyrics.name)
        self.assertEqual(entry['text'], '첫 줄\n둘째 줄\n')
        self.assertEqual(entry['size'], lyrics.stat().st_size)
        self.assertEqual(entry['sourceStatus'], 'current')
        self.assertIn('download=1', entry['downloadUrl'])
        self.assertNotIn('text', state['media']['review']['captions'][0])

    def test_lyrics_validation_rejects_unsupported_large_and_invalid_text(self):
        folder, root, project, source = self.make_project()
        self.addCleanup(folder.cleanup)
        for name, content, expected in (
            ('not-lyrics.srt', b'1\n', '지원하지 않는 파일 형식'),
            ('too-large.txt', b'a' * (MAX_LYRICS_TEXT + 1), '가사 파일이 너무 큽니다'),
            ('invalid.txt', b'\xff\xfe', 'UTF-8'),
        ):
            candidate = root / name
            candidate.write_bytes(content)
            manifest = root / f'{name}.json'
            manifest.write_text(json.dumps({'sourceMusicSha256': sha256(source), 'lyrics': [str(candidate)]}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, expected):
                publish(project, str(manifest))

    def test_download_preserves_bom_and_uses_safe_attachment_headers(self):
        folder, root, project, source = self.make_project()
        self.addCleanup(folder.cleanup)
        _, _, _, lyrics = self.publish_all(project, source, root)
        session = Session(project, review=True)
        server = self.server(session)
        item = session.state()['media']['review']['lyrics'][0]

        status, headers, _ = self.get(server, item['url'])
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/plain; charset=utf-8')
        status, headers, body = self.get(server, item['downloadUrl'])
        self.assertEqual(status, 200)
        self.assertEqual(body, lyrics.read_bytes())
        self.assertEqual(headers['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('attachment; filename="download"', headers['Content-Disposition'])
        self.assertIn("filename*=UTF-8''%EC%9B%90%EA%B0%80%EC%82%AC.txt", headers['Content-Disposition'])

    def test_media_auth_and_range_remain_available(self):
        folder, root, project, source = self.make_project()
        self.addCleanup(folder.cleanup)
        self.publish_all(project, source, root)
        session = Session(project, review=True)
        server = self.server(session)
        music = session.state()['media']['music']

        self.assertEqual(self.get(server, '/media/music')[0], 403)
        status, headers, body = self.get(server, music['url'], {'Range': 'bytes=0-3'})
        self.assertEqual(status, 206)
        self.assertEqual(headers['Content-Range'], f'bytes 0-3/{source.stat().st_size}')
        self.assertEqual(body, b'orig')

    def test_native_motion_saves_without_forcing_a_registered_preset(self):
        folder, root, project, source = self.make_project()
        self.addCleanup(folder.cleanup)
        session = Session(project, review=True)
        request = {'host':'codex','mode':'showreel-motion','styleId':None,'display':{'showSpectrum':None,'showQueue':None,'showNowPlaying':None,'channelName':None}}
        result = session.save_selection(request)
        self.assertEqual(result['status'],'saved')
        self.assertNotIn('showreelRequest',result)
        self.assertFalse((project/'showreel-request.json').exists())
        self.assertIsNone(json.loads((project/'production-request.json').read_text())['selection']['styleId'])
        if session.card_ids:
            session.save_selection({**request,'styleId':sorted(session.card_ids)[0]})
            self.assertTrue((project/'showreel-request.json').exists())
            self.assertNotIn('showreelRequest',session.save_selection(request))
            self.assertFalse((project/'showreel-request.json').exists())
        with self.assertRaisesRegex(ValueError,'스타일'):
            session.save_selection({**request,'mode':'showreel-cd'})

    def test_existing_manifest_without_lyrics_remains_compatible(self):
        folder, root, project, source = self.make_project()
        self.addCleanup(folder.cleanup)
        video = root / 'final.mp4'
        video.write_bytes(b'video')
        manifest = root / 'existing.json'
        manifest.write_text(json.dumps({'video': [str(video)], 'sourceMusicSha256': sha256(source)}), encoding='utf-8')
        self.assertEqual(publish(project, str(manifest))['status'], 'published')
        self.assertEqual(Session(project, review=True).state()['media']['review']['lyrics'], [])


if __name__ == '__main__':
    unittest.main()
