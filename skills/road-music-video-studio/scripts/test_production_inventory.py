"""A large producer directory is streamed in small SQLite writes without truncation."""
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from production_ledger import ProductionLedger
from storage_lifecycle import start_production_task, finish_production_task, shared_storage_manager, abandon_failed_project

class ProductionInventoryTests(unittest.TestCase):
    def test_more_than_five_thousand_files_are_all_recorded_in_bounded_batches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); project = root / 'project'; project.mkdir(); profile = root / 'profile'
            with patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': str(profile)}):
                task = start_production_task(project, task_type='verification', engine='fixture')
                self.assertIsNotNone(task['taskId'], task['warning'])
                for index in range(5201): (project / f'{index}.txt').write_text('fixture')
                batches = []
                with patch.object(ProductionLedger, 'record_files', side_effect=lambda params: batches.append(list(params['files']))):
                    warning = finish_production_task(task, status='succeeded')
                self.assertIsNone(warning)
                self.assertEqual(sum(map(len, batches)), 5201)
                self.assertLessEqual(max(map(len, batches)), 200)
                row = ProductionLedger(profile).tasks({})['tasks'][0]
                self.assertTrue(row['fileInventoryComplete'])
                self.assertEqual(row['status'], 'succeeded')

    def test_unchanged_old_assets_are_not_copied_into_each_new_task_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); project = root / 'project'; project.mkdir(); profile = root / 'profile'
            (project / 'previous.txt').write_text('unchanged')
            with patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': str(profile)}):
                task = start_production_task(project, task_type='verification', engine='fixture')
                (project / 'new.txt').write_text('new')
                finish_production_task(task, status='succeeded')
                files = ProductionLedger(profile).files({})['files']
                self.assertEqual([Path(item['path']).name for item in files], ['new.txt'])

    def test_failed_preparation_keeps_minimal_performance_after_removing_empty_work_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); project = root / 'project'; project.mkdir(); profile = root / 'profile'
            with patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': str(profile)}):
                task = start_production_task(project, task_type='prepare', engine='fixture')
                manager = shared_storage_manager(); project_id = manager._project_id(project)
                manager.management_db.claim_path(str(project), 'producer-work', project_id=project_id, workspace=str(root))
                finish_production_task(task, status='failed', error_summary='fixture failed')
                shutil.rmtree(project)
                self.assertTrue(abandon_failed_project(project))
                self.assertEqual(manager.management_db.paths(project_id=project_id), [])
                self.assertEqual(ProductionLedger(profile).tasks({})['tasks'][0]['status'], 'failed')
                manager.management_db.drop_project(project_id)
                self.assertEqual(ProductionLedger(profile).tasks({})['tasks'], [])

    def test_inventory_read_error_still_finishes_task_with_visible_warning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); project = root / 'project'; project.mkdir(); profile = root / 'profile'
            with patch.dict(os.environ, {'ROADMUSIC_DATA_DIR': str(profile)}):
                task = start_production_task(project, task_type='verification', engine='fixture')
                with patch('storage_lifecycle._production_files', side_effect=OSError('unreadable')):
                    warning = finish_production_task(task, status='failed', error_summary='render failed')
                self.assertIn('기록', warning)
                row = ProductionLedger(profile).tasks({})['tasks'][0]
                self.assertEqual(row['status'], 'failed')
                self.assertFalse(row['fileInventoryComplete'])

if __name__ == '__main__': unittest.main()
