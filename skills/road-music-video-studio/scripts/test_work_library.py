import concurrent.futures
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from work_library import WorkLibrary


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_project(root, name, source, entries, mode='showreel-motion', style_id=None, feedback=None):
    project = root / name
    project.mkdir()
    source_entry = {'id': 'music', 'kind': 'music', 'path': str(source), 'name': source.name, 'size': source.stat().st_size, 'sha256': digest(source)}
    media = [source_entry]
    for index, (kind, path, extra) in enumerate(entries):
        media.append({'id': f'{kind}-{index}', 'kind': kind, 'path': str(path), 'name': path.name, 'size': path.stat().st_size, 'sha256': digest(path), **extra})
    (project / 'studio-project.json').write_text(json.dumps({'schemaVersion': 1, 'name': name, 'mode': mode, 'media': media}, ensure_ascii=False), encoding='utf-8')
    (project / 'selection.json').write_text(json.dumps({'styleId': style_id}, ensure_ascii=False), encoding='utf-8')
    if feedback is not None:
        (project / 'feedback.json').write_text(json.dumps(feedback, ensure_ascii=False), encoding='utf-8')
    return project


def register_in_process(path, project, barrier):
    barrier.wait()
    WorkLibrary(path).register(project)


class WorkLibraryTests(unittest.TestCase):
    def setUp(self):
        workspace = patch('storage_packaging.TRUSTED_ROOT', None); workspace.start(); self.addCleanup(workspace.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.library = WorkLibrary(self.root / 'state' / 'video-studio-library.json')

    def tearDown(self):
        self.temp.cleanup()

    def file(self, name, body):
        path = self.root / name
        path.write_bytes(body)
        return path

    def test_groups_by_source_hash_deduplicates_and_preserves_old_snapshots(self):
        source = self.file('cafe\u0301.mp3', b'same-source')
        video = self.file('first.mp4', b'video')
        duplicate_video = self.file('second.mp4', b'video')
        lyrics = self.file('lyrics.txt', '첫 줄\n'.encode())
        first = write_project(self.root, '프로젝트 이름 하나', source, [('video', video, {'styleLabel': '시네마틱'})])
        second = write_project(self.root, '프로젝트 이름 둘', source, [('video', duplicate_video, {}), ('lyrics', lyrics, {})], style_id='acid')

        self.library.register(first)
        detail = self.library.register(second)
        self.assertEqual(detail['groupId'], digest(source))
        self.assertEqual(detail['title'], 'café')
        self.assertEqual(detail['fileCount'], 2)
        self.assertEqual(detail['videoCount'], 1)
        self.assertEqual(detail['styles'], ['acid', '시네마틱'])
        self.assertEqual(detail['createdTimes'], sorted(set(item['createdAt'] for item in detail['files'])))
        self.assertTrue(detail['source']['available'])
        self.assertIn(detail['source']['timestampSource'], {'file-created', 'file-modified'})
        self.assertEqual({item['kind'] for item in detail['files']}, {'video', 'lyrics'})
        self.assertEqual(len(self.library.groups()), 1)

        # A later publish replaces the project manifest, but the historical video stays in the library.
        captions = self.file('captions.srt', b'1\n00:00:00,000 --> 00:00:01,000\ntext\n')
        write_project(self.root, 'replacement', source, [('captions', captions, {})])
        replacement = self.root / 'replacement'
        self.library.register(replacement)
        self.assertEqual(self.library.group(digest(source))['fileCount'], 3)

    def test_group_favorite_is_sql_backed_idempotent_and_filterable(self):
        source = self.file('favorite.mp3', b'source'); video = self.file('favorite.mp4', b'video')
        group = self.library.register(write_project(self.root, 'favorite-project', source, [('video', video, {})]))
        self.assertFalse(self.library.group(group['groupId'])['favorite'])
        first = self.library.set_favorite(group['groupId'], True)
        second = self.library.set_favorite(group['groupId'], True)
        self.assertTrue(first['favorite']); self.assertEqual(first['likedAtMs'], second['likedAtMs'])
        self.assertEqual([item['groupId'] for item in self.library.groups(favorites_only=True)], [group['groupId']])
        self.assertFalse(self.library.set_favorite(group['groupId'], False)['favorite'])
        self.assertEqual(self.library.groups(favorites_only=True), [])

    def test_refresh_project_paths_rebases_only_that_projects_verified_files(self):
        source = self.file('source.mp3', b'source')
        video = self.file('old.mp4', b'video')
        project = write_project(self.root, 'delivery-project', source, [('video', video, {})])
        self.library.register(project)
        delivery = self.root / 'Output' / 'song--x' / 'project--y' / '20261019-010203'; delivery.mkdir(parents=True)
        new_source, new_video = delivery / source.name, delivery / video.name
        new_source.write_bytes(source.read_bytes()); new_video.write_bytes(video.read_bytes())
        data = json.loads((project / 'studio-project.json').read_text())
        for item in data['media']:
            target = new_source if item['id'] == 'music' else new_video
            item.update({'path': str(target), 'name': target.name, 'size': target.stat().st_size, 'sha256': digest(target)})
        (project / 'studio-project.json').write_text(json.dumps(data), encoding='utf-8')
        detail = self.library.refresh_project_paths(project)
        self.assertEqual(Path(detail['source']['path']), new_source)
        self.assertEqual(Path(next(item for item in detail['files'] if item['kind'] == 'video')['path']), new_video)

    def test_register_refuses_the_matching_prepared_workspace_migration(self):
        source = self.file('source.mp3', b'source'); video = self.file('video.mp4', b'video')
        project = write_project(self.root, 'prepared-project', source, [('video', video, {})])
        self.library.path.parent.mkdir(parents=True)
        (self.library.path.parent / 'settings.json').write_text(json.dumps({'deliveryRoot': str(self.root)}), encoding='utf-8')
        marker = self.root / '.roadmusic' / 'structure.json'; marker.parent.mkdir()
        marker.write_text(json.dumps({'phase': 'preparing', 'owner': 'road-music', 'workspace': str(self.root)}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '구조 이전'):
            self.library.register(project)

    def test_archive_sanitizes_windows_separators_in_recorded_names(self):
        source = self.file('source.mp3', b'audio')
        video = self.file('video.mp4', b'video')
        project = write_project(self.root, 'portable-zip', source, [('video', video, {'name': '..\\escape.mp4'})])
        group = self.library.register(project)
        with self.library.archive(group['groupId']) as stream, zipfile.ZipFile(stream) as archive:
            self.assertIn('escape.mp4', archive.namelist())
            self.assertTrue(all('/' not in name and '\\' not in name for name in archive.namelist()))
            self.assertEqual(archive.read('escape.mp4'), b'video')

    def test_same_filename_different_source_bytes_creates_distinct_groups(self):
        left = self.file('same-name.mp3', b'left')
        right_dir = self.root / 'right'; right_dir.mkdir()
        right = right_dir / 'same-name.mp3'; right.write_bytes(b'right')
        left_video = self.file('left.mp4', b'left-video')
        right_video = self.file('right.mp4', b'right-video')
        self.library.register(write_project(self.root, 'left-project', left, [('video', left_video, {})]))
        self.library.register(write_project(self.root, 'right-project', right, [('video', right_video, {})]))
        groups = self.library.groups()
        self.assertEqual(len(groups), 2)
        self.assertEqual({group['title'] for group in groups}, {'same-name'})
        self.assertEqual({group['sourceSha256'] for group in groups}, {digest(left), digest(right)})
        self.assertTrue(all(group['styleCount'] == 0 and group['unclassifiedStyleCount'] == 1 for group in groups))

    def test_archive_contains_source_and_excludes_duplicate_audio_bytes(self):
        source = self.file('original.mp3', b'original')
        final_audio = self.file('final.mp3', b'original')
        video = self.file('final.mp4', b'video')
        project = write_project(self.root, 'archive', source, [('music', final_audio, {}), ('video', video, {})])
        group = self.library.register(project)
        with self.library.archive(group['groupId']) as stream:
            with zipfile.ZipFile(io.BytesIO(stream.read())) as archive:
                self.assertEqual(set(archive.namelist()), {'original.mp3', 'final.mp4'})
                self.assertEqual(archive.read('original.mp3'), b'original')
        source_file = self.library.file(group['groupId'], group['source']['id'])
        self.assertEqual(source_file['kind'], 'source')
        self.assertIsInstance(source_file['path'], Path)

    def test_missing_or_changed_files_are_not_served_or_archived(self):
        source = self.file('source.mp3', b'source')
        video = self.file('final.mp4', b'video')
        group = self.library.register(write_project(self.root, 'missing', source, [('video', video, {})]))
        file_id = group['files'][0]['id']
        video.unlink()
        detail = self.library.group(group['groupId'])
        self.assertFalse(detail['files'][0]['available'])
        with self.assertRaisesRegex(ValueError, '파일을 찾을 수 없|일반 파일|등록 뒤'):
            self.library.file(group['groupId'], file_id)
        with self.assertRaisesRegex(ValueError, '파일을 찾을 수 없|일반 파일|등록 뒤'):
            self.library.archive(group['groupId'])
        video.write_bytes(b'changed-video')
        with self.assertRaisesRegex(ValueError, '변경되어 제공하지 않습니다'):
            self.library.file(group['groupId'], file_id)
        with self.assertRaisesRegex(ValueError, '변경되어 제공하지 않습니다'):
            self.library.archive(group['groupId'])

    def test_invalid_snapshot_does_not_write_and_concurrent_registers_merge(self):
        source = self.file('source.mp3', b'source')
        first_video = self.file('one.mp4', b'one')
        second_video = self.file('two.mp4', b'two')
        first = write_project(self.root, 'concurrent-one', source, [('video', first_video, {})])
        second = write_project(self.root, 'concurrent-two', source, [('video', second_video, {})])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(self.library.register, [first, second]))
        group_id = digest(source)
        self.assertEqual(self.library.group(group_id)['fileCount'], 2)
        before = self.library._read()

        bad = write_project(self.root, 'bad', source, [('video', first_video, {})])
        raw = json.loads((bad / 'studio-project.json').read_text())
        raw['media'][1]['sha256'] = '0' * 64
        (bad / 'studio-project.json').write_text(json.dumps(raw), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '변경'):
            self.library.register(bad)
        self.assertEqual(self.library._read(), before)

    def test_rejects_path_traversal_and_noncanonical_ids(self):
        source = self.file('source.mp3', b'source')
        video = self.file('safe.mp4', b'safe-video')
        group = self.library.register(write_project(self.root, 'safe', source, [('video', video, {})]))
        with self.assertRaises(ValueError):
            self.library.group('../' + group['groupId'])
        with self.assertRaises(ValueError):
            self.library.file(group['groupId'], '../../secret')
        with self.assertRaises(ValueError):
            WorkLibrary('relative-library.json')

    def test_cross_process_registers_do_not_lose_updates(self):
        source = self.file('source.mp3', b'source')
        first_video = self.file('first.mp4', b'first')
        second_video = self.file('second.mp4', b'second')
        first = write_project(self.root, 'process-first', source, [('video', first_video, {})])
        second = write_project(self.root, 'process-second', source, [('video', second_video, {})])
        context = multiprocessing.get_context('spawn')
        barrier = context.Barrier(2)
        processes = [context.Process(target=register_in_process, args=(str(self.library.path), str(project), barrier)) for project in (first, second)]
        for process in processes: process.start()
        for process in processes: process.join(15)
        self.assertEqual([process.exitcode for process in processes], [0, 0])
        self.assertEqual(WorkLibrary(self.library.path).group(digest(source))['fileCount'], 2)

    def test_same_deliverable_moves_to_latest_verified_path_and_style(self):
        source = self.file('source.mp3', b'source')
        old = self.file('old.mp4', b'one-video')
        self.library.register(write_project(self.root, 'old-project', source, [('video', old, {'styleLabel': '이전 스타일'})]))
        moved_dir = self.root / 'moved'; moved_dir.mkdir()
        moved = moved_dir / 'new.mp4'; moved.write_bytes(b'one-video')
        old.unlink()
        group = self.library.register(write_project(self.root, 'new-project', source, [('video', moved, {'styleLabel': '새 스타일'})]))
        self.assertEqual(group['fileCount'], 1)
        self.assertEqual(group['files'][0]['path'], str(moved.resolve()))
        self.assertTrue(group['files'][0]['available'])
        self.assertEqual(group['files'][0]['styleLabel'], '새 스타일')

    def test_same_deliverable_keeps_an_available_representative_path_and_prior_explicit_metadata(self):
        source = self.file('source.mp3', b'source')
        old = self.file('old.mp4', b'one-video')
        first = write_project(self.root, 'old-project', source, [('video', old, {'producedAt': '2026-10-19T01:00:00Z'})])
        self.library.register(first)
        moved_dir = self.root / 'moved'; moved_dir.mkdir()
        moved = moved_dir / 'new.mp4'; moved.write_bytes(b'one-video')
        group = self.library.register(write_project(self.root, 'new-project', source, [('video', moved, {'styleLabel': '새 스타일'})]))
        self.assertEqual(group['files'][0]['path'], str(old.resolve()))
        self.assertEqual(group['files'][0]['styleLabel'], '새 스타일')
        self.assertEqual(group['files'][0]['producedAt'], '2026-10-19T01:00:00Z')

    def test_rejects_same_bytes_conflicting_explicit_metadata(self):
        source = self.file('source.mp3', b'source')
        video = self.file('video.mp4', b'one-video')
        self.library.register(write_project(self.root, 'first', source, [('video', video, {'producedAt': '2026-10-19T01:00:00Z'})]))
        second = write_project(self.root, 'second', source, [('video', video, {'producedAt': '2026-10-19T02:00:00Z'})])
        with self.assertRaisesRegex(ValueError, 'producedAt'):
            self.library.register(second)

    def test_file_verifies_sha_even_when_changed_bytes_keep_stat_fingerprint(self):
        source = self.file('source.mp3', b'source')
        video = self.file('video.mp4', b'original')
        group = self.library.register(write_project(self.root, 'fingerprint', source, [('video', video, {})]))
        file_id = group['files'][0]['id']
        before = video.stat()
        video.write_bytes(b'changed!')
        os.utime(video, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, '변경되어 제공하지 않습니다'):
            self.library.file(group['groupId'], file_id)

    def test_touching_artifact_refreshes_observed_state_for_production_archive(self):
        source = self.file('source.mp3', b'source')
        video = self.file('video.mp4', b'video')
        report = self.file('report.json', b'{"ok":true}')
        group = self.library.register(write_project(self.root, 'artifact-touch', source, [
            ('video', video, {}), ('artifact', report, {'artifactType': 'report'}),
        ]))
        artifact_id = group['artifacts'][0]['id']
        before = report.stat()
        os.utime(report, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        self.assertEqual(self.library.file(group['groupId'], artifact_id)['kind'], 'artifact')
        with self.library.archive(group['groupId'], include_artifacts=True) as stream, zipfile.ZipFile(stream) as archive:
            self.assertIn('report.json', archive.namelist())

    def test_duplicate_bytes_keep_all_project_origins_and_legacy_origin_is_readable(self):
        source = self.file('source.mp3', b'source')
        first_video = self.file('first.mp4', b'same-video')
        second_video = self.file('second.mp4', b'same-video')
        first = write_project(self.root, 'first-origin', source, [('video', first_video, {'styleLabel': '첫 스타일'})],
                              style_id='first', feedback={'status': 'review', 'note': '첫 검수'})
        second = write_project(self.root, 'second-origin', source, [('video', second_video, {'styleLabel': '둘째 스타일'})],
                               style_id='second', feedback={'status': 'approved', 'note': '둘째 검수'})
        self.library.register(first)
        group = self.library.register(second)
        origins = group['files'][0]['origins']
        self.assertEqual({Path(origin['project']).name for origin in origins}, {'first-origin', 'second-origin'})
        self.assertEqual({origin['styleId'] for origin in origins}, {'first', 'second'})
        self.assertEqual({origin['feedback']['note'] for origin in origins}, {'첫 검수', '둘째 검수'})
        self.assertTrue(all(origin['registeredAt'] for origin in origins))
        self.assertEqual(set(group['styles']), {'첫 스타일', '둘째 스타일'})
        self.assertEqual(group['registeredAt'], min(origin['registeredAt'] for origin in group['source']['origins'] + origins))
        self.assertEqual(group['files'][0]['registeredAt'], min(origin['registeredAt'] for origin in origins))

        raw = self.library._read()
        raw['groups'][group['groupId']]['files'][0].pop('origins')
        self.library._save(raw)
        legacy = self.library.group(group['groupId'])['files'][0]['origins']
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0]['project'], str(second.resolve()))
        self.assertIsNone(legacy[0]['registeredAt'])
        self.assertIsNone(self.library.group(group['groupId'])['registeredAt'])

    def test_artifacts_are_separate_from_default_archive_and_caption_links_video(self):
        source = self.file('source.mp3', b'source')
        video = self.file('video.mp4', b'video')
        captions = self.file('lyrics.srt', b'1\n00:00:00,000 --> 00:00:01,000\ntext\n')
        report = self.file('validation.json', b'{"checked": true}')
        project = write_project(self.root, 'materials', source, [
            ('video', video, {'producedAt': '2026-10-19T01:02:03Z'}),
            ('captions', captions, {'forVideoSha256': digest(video)}),
            ('artifact', report, {'artifactType': 'validation'}),
        ])
        group = self.library.register(project)
        self.assertEqual(group['files'][1]['forVideoSha256'], digest(video))
        self.assertEqual(group['files'][0]['producedAt'], '2026-10-19T01:02:03Z')
        self.assertEqual(group['artifactCount'], 1)
        with self.library.archive(group['groupId']) as stream, zipfile.ZipFile(stream) as archive:
            self.assertNotIn('validation.json', archive.namelist())
        with self.library.archive(group['groupId'], include_artifacts=True) as stream, zipfile.ZipFile(stream) as archive:
            self.assertIn('validation.json', archive.namelist())
        report.unlink()
        availability = self.library.group(group['groupId'])
        self.assertTrue(availability['available'])
        self.assertFalse(availability['productionAvailable'])
        with self.library.archive(group['groupId']) as stream, zipfile.ZipFile(stream) as archive:
            self.assertIn('video.mp4', archive.namelist())

    def test_rejects_artifact_and_caption_contract_violations(self):
        source = self.file('source.mp3', b'source')
        video = self.file('video.mp4', b'video')
        forbidden = self.file('program.html', b'<html>')
        bad_artifact = write_project(self.root, 'bad-artifact', source, [('artifact', forbidden, {'artifactType': 'validation'})])
        with self.assertRaisesRegex(ValueError, '지원하지 않는 파일 형식'):
            self.library.register(bad_artifact)
        captions = self.file('captions.srt', b'1\n')
        wrong_caption = write_project(self.root, 'wrong-caption', source, [
            ('video', video, {}), ('captions', captions, {'forVideoSha256': 'f' * 64}),
        ])
        with self.assertRaisesRegex(ValueError, '자막'):
            self.library.register(wrong_caption)

    def test_rejects_boolean_technical_metadata(self):
        source = self.file('source.mp3', b'source')
        video = self.file('video.mp4', b'video')
        group = self.library.register(write_project(self.root, 'technical', source, [('video', video, {})]))
        raw = self.library._read()
        raw['groups'][group['groupId']]['files'][0]['technical']['fps'] = True
        self.library.management_db.write_document('work-library', raw)
        with self.assertRaisesRegex(ValueError, '기술 정보'):
            self.library.group(group['groupId'])

    def test_different_source_results_are_skipped_and_unverified_is_labeled(self):
        source = self.file('source.mp3', b'source')
        current = self.file('current.mp4', b'current')
        unverified = self.file('unverified.mp3', b'unverified')
        foreign = self.file('foreign.mp4', b'foreign')
        group = self.library.register(write_project(self.root, 'mixed', source, [
            ('video', current, {'sourceMusicSha256': digest(source)}),
            ('music', unverified, {}),
            ('video', foreign, {'sourceMusicSha256': 'f' * 64}),
        ]))
        self.assertEqual(group['skippedDifferentSource'], 1)
        self.assertEqual({item['sourceStatus'] for item in group['files']}, {'current', 'unverified-source'})
        only_foreign = write_project(self.root, 'foreign-only', source, [('video', foreign, {'sourceMusicSha256': 'f' * 64})])
        with self.assertRaisesRegex(ValueError, '연결된 완성 파일'):
            self.library.register(only_foreign)

    def test_storyboard_only_project_is_grouped_and_archived_with_source(self):
        source = self.file('source.mp3', b'source')
        board = self.file('storyboard.png', b'png-bytes')
        group = self.library.register(write_project(self.root, 'storyboard-only', source, [('storyboard', board, {})]))
        self.assertEqual(group['fileCount'], 1)
        self.assertEqual(group['videoCount'], 0)
        self.assertEqual(group['storyboardCount'], 1)
        self.assertEqual(group['files'][0]['kind'], 'storyboard')
        with self.library.archive(group['groupId']) as stream:
            with zipfile.ZipFile(io.BytesIO(stream.read())) as archive:
                self.assertEqual(set(archive.namelist()), {'source.mp3', 'storyboard.png'})

    def test_archive_rejects_file_changed_after_trusted_lookup(self):
        source = self.file('source.mp3', b'source')
        video = self.file('video.mp4', b'original-video')
        group = self.library.register(write_project(self.root, 'archive-race', source, [('video', video, {})]))
        trusted = self.library._trusted

        def change_after_lookup(group_id, file_id):
            item = trusted(group_id, file_id)
            if item['kind'] == 'video':
                video.write_bytes(b'changed-video')
            return item

        with patch.object(self.library, '_trusted', side_effect=change_after_lookup):
            with self.assertRaisesRegex(ValueError, '묶음 파일'):
                self.library.archive(group['groupId'])


if __name__ == '__main__':
    unittest.main()
