import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from result_records import validate_sync_checks, archive_feedback, feedback_history
from management_db import ManagementDB


class ResultRecordTests(unittest.TestCase):
    def test_sync_records_keep_estimates_and_bind_only_registered_files(self):
        video, captions = 'a' * 64, 'b' * 64
        row = {'line': 9, 'start': 12.3, 'end': 14.1, 'status': 'estimated', 'evidence': '발음 근거 부족', 'videoSha256': video, 'captionSha256': captions}
        result = validate_sync_checks([row], [{'kind': 'video', 'sha256': video}, {'kind': 'captions', 'sha256': captions}])
        self.assertEqual(result[0]['status'], 'estimated')
        self.assertEqual(result[0]['evidence'], row['evidence'])
        dated = {**row, 'reviewedAt': '2026-10-19T12:00:00+09:00'}
        self.assertEqual(validate_sync_checks([dated], [{'kind':'video','sha256':video},{'kind':'captions','sha256':captions}])[0]['reviewedAt'], dated['reviewedAt'])
        for changes in ({'end': 12}, {'start': float('nan')}, {'line': True}, {'videoSha256': captions}, {'status': 'approved'}, {'extra': 'x'}):
            with self.assertRaises(ValueError):
                validate_sync_checks([{**row, **changes}], [{'kind': 'video', 'sha256': video}, {'kind': 'captions', 'sha256': captions}])

    def test_history_preserves_the_previous_feedback_without_touching_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = {'status': 'draft', 'note': '기존 의견', 'savedAt': 1, 'unknownLegacyField': '보존'}
            source = root / 'feedback.json'; source.write_text(json.dumps(old))
            archive_feedback(root, old)
            self.assertEqual(feedback_history(root), [old])
            self.assertEqual(json.loads(source.read_text()), old)

    def test_sql_feedback_history_does_not_create_more_project_history_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'project'; root.mkdir()
            management = ManagementDB(Path(folder) / 'profile')
            previous = {'status': 'draft', 'note': '검수 전'}
            project_id = hashlib.sha256(str(root.resolve()).encode()).hexdigest()
            management.record_event('feedback-change', project_id=project_id, before=previous, after={'status': 'approved', 'note': '검수 완료'})
            self.assertEqual(feedback_history(root, management), [previous])
            self.assertFalse((root / 'feedback-history.jsonl').exists())
