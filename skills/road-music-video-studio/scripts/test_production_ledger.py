import hashlib
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager

from management_db import ManagementDB
from production_ledger import ProductionLedger, ProductionLedgerError


class ProductionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.profile = self.root / "profile"
        self.project = self.root / "work"; self.project.mkdir()
        self.output = self.project / "song.mp3"; self.output.write_bytes(b"song")
        self.ledger = ProductionLedger(self.profile)

    def request(self, **extra):
        return self.ledger.request({"project": str(self.project), "domain": "music", "intent": "first", "prompt": "original prompt", **extra})

    def start(self, **extra):
        return self.ledger.start_task({"project": str(self.project), "domain": "music", "taskType": "generate", **extra})

    def test_read_methods_do_not_create_a_profile(self):
        self.assertEqual(self.ledger.projects(), {"projects": [], "nextCursor": None})
        self.assertEqual(self.ledger.prompts()["prompts"], [])
        self.assertEqual(self.ledger.dashboard()["summary"]["totalTasks"], 0)
        self.assertFalse(self.profile.exists())

    def test_old_schema_reads_without_migration_or_file_mutation(self):
        self.profile.mkdir(); database = self.profile / "storage.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.executescript("""
                CREATE TABLE production_tasks (seq INTEGER PRIMARY KEY,task_id TEXT UNIQUE,project_id TEXT,group_id TEXT,request_id TEXT,parent_task_id TEXT,domain TEXT,task_type TEXT,engine TEXT,model TEXT,status TEXT,started_at INTEGER,finished_at INTEGER,elapsed_ms REAL,media_seconds REAL,frame_count INTEGER,ai_summary TEXT,result_summary TEXT,error_summary TEXT);
                CREATE TABLE production_files (seq INTEGER PRIMARY KEY,task_id TEXT UNIQUE,project_id TEXT,group_id TEXT,path TEXT,role TEXT,bytes INTEGER,mtime_ns INTEGER,exists_at_finish INTEGER,recorded_at INTEGER);
                INSERT INTO production_tasks VALUES(1,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','p',NULL,NULL,NULL,'music','generate',NULL,NULL,'success',1000,2000,100,NULL,NULL,NULL,NULL,NULL);
                INSERT INTO production_files VALUES(1,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','p',NULL,'/tmp/old.mp3','final',4,1,1,2000);
            """)
        before = (database.stat().st_size, database.stat().st_mtime_ns)
        task = self.ledger.tasks()["tasks"][0]; file = self.ledger.files()["files"][0]
        self.assertIsNone(task["queuedAt"]); self.assertIsNone(task["fileInventoryComplete"]); self.assertTrue(file["existsAtFinish"])
        self.assertEqual((database.stat().st_size, database.stat().st_mtime_ns), before)

    def test_main_prompt_is_first_user_request_per_project_and_domain(self):
        engine = self.request(source="engine", intent="caption", prompt="engine caption")
        main = self.request()
        changed = self.request(intent="lyrics revise", prompt="new prompt")
        self.assertFalse(engine["main"]); self.assertTrue(main["main"]); self.assertFalse(changed["main"])
        prompts = self.ledger.prompts({"projectId": main["projectId"]})
        self.assertEqual([item["requestId"] for item in prompts["mainPrompts"]], [main["requestId"]])
        self.assertEqual(prompts["counts"], {"requests": 2, "enginePrompts": 1, "requestedRevisions": 1, "revisions": 0, "generations": 0})

    def test_engine_prompt_gets_linked_task_summary_without_replacing_user_request(self):
        user = self.request(prompt="user original")
        engine = self.request(source="engine", intent="caption", prompt="engine caption")
        task = self.start(requestId=user["requestId"], engineRequestId=engine["requestId"])
        self.ledger.finish_task({"taskId": task["taskId"], "status": "succeeded", "elapsedMs": 1, "aiSummary": "processed user request", "resultSummary": "created output"})
        prompts = {item["requestId"]: item for item in self.ledger.prompts()["prompts"]}
        self.assertEqual(prompts[user["requestId"]]["taskSummary"]["latest"]["summary"], "created output")
        self.assertEqual(prompts[user["requestId"]]["taskSummary"]["latest"]["aiSummary"], "processed user request")
        self.assertEqual(prompts[engine["requestId"]]["taskSummary"]["latest"]["taskId"], task["taskId"])
        with self.assertRaises(ProductionLedgerError): self.start(requestId=user["requestId"], engineRequestId=user["requestId"])

    def test_task_finish_idempotence_conflict_cancel_and_file_metadata(self):
        request = self.request(); task = self.start(requestId=request["requestId"], taskId="a" * 48)
        self.assertEqual(self.start(taskId=task["taskId"], requestId=request["requestId"], status="running")["taskId"], task["taskId"])
        done = self.ledger.finish_task({"taskId": task["taskId"], "status": "success", "elapsedMs": 12, "mediaSeconds": 2.0, "files": [{"path": str(self.output), "role": "final"}]})
        self.assertEqual(done["files"][0]["bytes"], 4)
        self.assertEqual(self.ledger.finish_task({"taskId": task["taskId"], "status": "success", "elapsedMs": 12})["status"], "succeeded")
        with self.assertRaises(ProductionLedgerError): self.ledger.finish_task({"taskId": task["taskId"], "status": "failed"})
        with self.assertRaises(ProductionLedgerError): self.start(taskId=task["taskId"], requestId=request["requestId"], status="running")
        cancelled = self.start(taskId="b" * 48)
        self.assertEqual(self.ledger.finish_task({"taskId": cancelled["taskId"], "status": "cancelled"})["status"], "cancelled")

    def test_file_snapshot_retains_last_known_size_after_cleanup(self):
        task = self.start()
        self.ledger.record_files({"taskId": task["taskId"], "files": [{"path": str(self.output), "role": "intermediate"}], "fileInventoryComplete": True})
        self.output.unlink()
        self.ledger.record_files({"taskId": task["taskId"], "files": [{"path": str(self.output), "role": "intermediate"}], "fileInventoryComplete": False, "fileInventoryWarning": "cleanup observed"})
        row = self.ledger.files({"taskId": task["taskId"]})["files"][0]
        self.assertEqual(row["bytes"], 4); self.assertIsNone(row["existsAtFinish"])

    def test_pagination_project_counts_and_child_steps_do_not_double_count(self):
        first = self.request(); parent = self.start(requestId=first["requestId"])
        child = self.start(taskId="c" * 48, requestId=first["requestId"], parentTaskId=parent["taskId"], taskType="render")
        self.ledger.finish_task({"taskId": child["taskId"], "status": "success", "elapsedMs": 7})
        self.ledger.finish_task({"taskId": parent["taskId"], "status": "success", "elapsedMs": 10})
        for index in range(3): self.request(intent=f"title revise {index}", prompt=f"p{index}")
        page = self.ledger.prompts({"limit": 2})
        self.assertEqual(len(page["prompts"]), 2); self.assertIsNotNone(page["nextCursor"])
        self.assertEqual(len(self.ledger.prompts({"limit": 2, "cursor": page["nextCursor"]})["prompts"]), 2)
        project = self.ledger.projects()["projects"][0]
        self.assertEqual(project["requestCount"], 4); self.assertEqual(project["generationCount"], 1); self.assertEqual(project["revisionCount"], 0); self.assertEqual(project["taskCount"], 2)
        dashboard = self.ledger.dashboard()
        self.assertEqual(dashboard["summary"]["totalTasks"], 1); self.assertEqual(dashboard["summary"]["totalElapsedMs"], 10)

    def test_successful_revision_task_is_separate_from_requested_revision(self):
        request = self.request(intent="revision", prompt="make chorus clearer")
        task = self.ledger.start_task({"project": str(self.project), "domain": "music", "taskType": "revision", "requestId": request["requestId"]})
        self.ledger.finish_task({"taskId": task["taskId"], "status": "succeeded", "elapsedMs": 4})
        self.assertEqual(self.ledger.prompts()["counts"]["revisions"], 1)
        self.assertEqual(self.ledger.projects()["projects"][0]["revisionCount"], 1)
        self.assertEqual(self.ledger.dashboard()["summary"]["revisionCount"], 1)

    def test_dashboard_quantiles_realtime_and_leave_one_out_slow_metric(self):
        request = self.request()
        for elapsed in (300, 1000, 3000):
            task = self.ledger.start_task({"project": str(self.project), "domain": "music", "taskType": "generate", "engine": "ace", "requestId": request["requestId"]})
            self.ledger.finish_task({"taskId": task["taskId"], "status": "succeeded", "elapsedMs": elapsed, "mediaSeconds": 1})
        item = self.ledger.dashboard()["byTask"][0]
        self.assertEqual((item["medianElapsedMs"], item["p95ElapsedMs"]), (1000.0, 3000))
        self.assertAlmostEqual(item["avgRealtimeFactor"], (0.3 + 1 + 3) / 3)
        slow = self.ledger.dashboard()["slowTasks"][0]
        self.assertEqual((slow["elapsedMs"], slow["basis"], slow["sampleCount"]), (3000, "realtimeFactor", 3))

    def test_queue_timing_and_dashboard_output_obey_task_filter(self):
        request = self.request(); queued = self.start(taskId="d" * 48, requestId=request["requestId"], status="queued")
        running = self.start(taskId=queued["taskId"], requestId=request["requestId"], status="running")
        self.assertEqual(running["queuedAtMs"], queued["queuedAtMs"]); self.assertGreaterEqual(running["waitMs"], 0)
        self.ledger.finish_task({"taskId": running["taskId"], "status": "succeeded", "elapsedMs": 1, "files": [{"path": str(self.output), "role": "final"}]})
        other = self.project / "render.mp4"; other.write_bytes(b"render")
        task = self.ledger.start_task({"project": str(self.project), "domain": "music", "taskType": "render", "requestId": request["requestId"]})
        self.ledger.finish_task({"taskId": task["taskId"], "status": "succeeded", "elapsedMs": 1, "files": [{"path": str(other), "role": "final"}]})
        self.assertEqual(self.ledger.dashboard({"taskType": "generate"})["summary"]["outputBytes"], 4)

    def test_expected_work_and_live_progress_are_bounded_and_terminal_safe(self):
        task = self.start(taskId="e" * 48, expectedMediaSeconds=36, expectedFrameCount=1080)
        self.assertEqual((task["expectedMediaSeconds"], task["expectedFrameCount"]), (36, 1080))
        progress = self.ledger.progress_task({"taskId": task["taskId"], "progress": 0.25, "currentStage": "synth", "summary": "diffusion"})
        self.assertEqual((progress["progress"], progress["currentStage"], progress["progressSummary"]), (0.25, "synth", "diffusion"))
        with self.assertRaisesRegex(ProductionLedgerError, "뒤로 갈 수 없습니다"):
            self.ledger.progress_task({"taskId": task["taskId"], "progress": 0.2})
        self.ledger.finish_task({"taskId": task["taskId"], "status": "succeeded", "elapsedMs": 1})
        done = self.ledger.tasks({"taskId": task["taskId"]})["tasks"][0]
        self.assertEqual(done["progress"], 1.0)
        with self.assertRaisesRegex(ProductionLedgerError, "종료된 작업"):
            self.ledger.progress_task({"taskId": task["taskId"], "progress": 1})

    def test_indexed_request_and_file_queries_have_no_full_scan(self):
        request = self.request(); task = self.start(requestId=request["requestId"])
        self.ledger.record_files({"taskId": task["taskId"], "files": [{"path": str(self.output), "role": "artifact"}]})
        with ManagementDB(self.profile).transaction() as connection:
            task_plan = " ".join(row[3] for row in connection.execute("EXPLAIN QUERY PLAN SELECT * FROM production_tasks WHERE request_id=? ORDER BY seq DESC", (request["requestId"],)))
            file_plan = " ".join(row[3] for row in connection.execute("EXPLAIN QUERY PLAN SELECT * FROM production_files WHERE group_id=? ORDER BY seq DESC", ("a" * 64,)))
        self.assertIn("INDEX", task_plan.upper()); self.assertIn("INDEX", file_plan.upper())

    def test_group_binding_and_project_drop_remove_production_rows(self):
        request = self.request(); self.start(requestId=request["requestId"])
        group = "b" * 64
        db = ManagementDB(self.profile)
        db.record_event("song-published", project_id=request["projectId"], group_id=group)
        self.assertEqual(self.ledger.projects()["projects"][0]["groupId"], group)
        self.assertTrue(self.ledger.projects()["projects"][0]["updatedAt"].startswith(str(datetime.now(timezone.utc).year) + "-"))
        result = db.drop_project(request["projectId"])
        self.assertEqual(result["removedProductionProjects"], 1)
        self.assertEqual(self.ledger.projects()["projects"], [])
        with db.transaction() as connection: self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_bound_project_rejects_a_different_group_without_reassigning_history(self):
        first = self.request(groupId="a" * 64)
        with self.assertRaisesRegex(ProductionLedgerError, "다른 음악 그룹.*새 프로젝트"):
            self.request(groupId="b" * 64)
        self.assertEqual(self.ledger.projects()["projects"][0]["groupId"], "a" * 64)
        self.assertEqual(self.ledger.prompts()["prompts"][0]["requestId"], first["requestId"])
        self.assertEqual(self.ledger.prompts()["prompts"][0]["groupId"], "a" * 64)

    def test_unbound_project_first_group_backfills_existing_history(self):
        original = self.request()
        task = self.start(requestId=original["requestId"])
        self.ledger.record_files({"taskId": task["taskId"], "files": [{"path": str(self.output), "role": "final"}]})
        bound = self.request(intent="revision", prompt="bind group", groupId="a" * 64)
        prompts = {item["requestId"]: item for item in self.ledger.prompts()["prompts"]}
        self.assertEqual(self.ledger.projects()["projects"][0]["groupId"], "a" * 64)
        self.assertEqual(bound["groupId"], "a" * 64)
        self.assertEqual(prompts[original["requestId"]]["groupId"], "a" * 64)
        self.assertEqual(self.ledger.tasks()["tasks"][0]["groupId"], "a" * 64)
        self.assertEqual(self.ledger.files()["files"][0]["groupId"], "a" * 64)

    def test_unbound_project_rejects_conflicting_child_group_before_binding_or_title_update(self):
        original = self.request(title="원래 제목")
        task = self.start(requestId=original["requestId"])
        self.ledger.record_files({"taskId": task["taskId"], "files": [{"path": str(self.output), "role": "final"}]})
        checks = (
            ("production_prompts", "request_id", original["requestId"]),
            ("production_tasks", "task_id", task["taskId"]),
            ("production_files", "task_id", task["taskId"]),
        )
        for index, (table, column, identifier) in enumerate(checks):
            with ManagementDB(self.profile).transaction(write=True) as connection:
                connection.execute(f"UPDATE {table} SET group_id=? WHERE {column}=?", ("a" * 64, identifier))
            with self.assertRaisesRegex(ProductionLedgerError, "다른 음악 그룹.*새 프로젝트"):
                self.request(requestId=(str(index + 3) * 48), title="새 그룹 제목", groupId="b" * 64)
            project = self.ledger.projects()["projects"][0]
            self.assertIsNone(project["groupId"])
            self.assertEqual(project["title"], "원래 제목")
            self.assertEqual(len(self.ledger.prompts()["prompts"]), 1)
            with ManagementDB(self.profile).transaction(write=True) as connection:
                connection.execute(f"UPDATE {table} SET group_id=NULL WHERE {column}=?", (identifier,))

    def test_group_prompts_include_only_their_project_titles(self):
        group = "a" * 64
        first = self.ledger.request({"project": str(self.root / "music"), "domain": "music", "intent": "generation", "prompt": "음악 원문", "groupId": group, "title": "음악 생성"})
        second = self.ledger.request({"project": str(self.root / "images"), "domain": "motion", "intent": "prepare", "prompt": "이미지 원문", "groupId": group})
        self.ledger.request({"project": str(self.root / "showreel"), "domain": "motion", "intent": "render", "prompt": "숨겨진 원문", "groupId": "b" * 64, "title": "Showreel Native"})
        prompts = {item["requestId"]: item for item in self.ledger.prompts({"groupId": group})["prompts"]}
        self.assertEqual(prompts[first["requestId"]]["projectTitle"], "음악 생성")
        self.assertEqual(prompts[second["requestId"]]["projectTitle"], "images")
        self.assertNotIn("Showreel Native", {item.get("projectTitle") for item in prompts.values()})
        self.assertEqual(prompts[first["requestId"]]["prompt"], "음악 원문")

    def test_request_id_reuse_validates_its_group_and_rolls_back_initial_binding(self):
        first = self.request(requestId="a" * 48, groupId="a" * 64)
        with ManagementDB(self.profile).transaction(write=True) as connection:
            connection.execute("UPDATE production_projects SET group_id=NULL WHERE project_id=?", (first["projectId"],))
        with self.assertRaisesRegex(ProductionLedgerError, "다른 음악 그룹.*새 프로젝트"):
            self.request(requestId=first["requestId"], groupId="b" * 64)
        self.assertIsNone(self.ledger.projects()["projects"][0]["groupId"])
        self.assertEqual(self.ledger.prompts()["prompts"][0]["groupId"], "a" * 64)

    def test_task_links_reject_mismatched_bound_groups(self):
        group = "a" * 64
        request = self.request(groupId=group)
        engine = self.request(source="engine", intent="caption", prompt="engine", groupId=group)
        parent = self.start(taskId="a" * 48, requestId=request["requestId"], groupId=group)
        cases = (
            ("production_prompts", "request_id", request["requestId"], lambda: self.start(taskId="b" * 48, requestId=request["requestId"], groupId=group)),
            ("production_prompts", "request_id", engine["requestId"], lambda: self.start(taskId="c" * 48, engineRequestId=engine["requestId"], groupId=group)),
            ("production_tasks", "task_id", parent["taskId"], lambda: self.start(taskId="d" * 48, parentTaskId=parent["taskId"], groupId=group)),
        )
        for table, column, identifier, start in cases:
            with ManagementDB(self.profile).transaction(write=True) as connection:
                connection.execute(f"UPDATE {table} SET group_id=? WHERE {column}=?", ("b" * 64, identifier))
            with self.assertRaisesRegex(ProductionLedgerError, "다른 음악 그룹.*새 프로젝트"):
                start()
            with ManagementDB(self.profile).transaction(write=True) as connection:
                connection.execute(f"UPDATE {table} SET group_id=? WHERE {column}=?", (group, identifier))
        self.assertEqual(len(self.ledger.tasks()["tasks"]), 1)

    def test_reused_task_id_rejects_a_mismatched_stored_group(self):
        group = "a" * 64
        request = self.request(groupId=group)
        task = self.start(taskId="a" * 48, requestId=request["requestId"], groupId=group)
        with ManagementDB(self.profile).transaction(write=True) as connection:
            connection.execute("UPDATE production_tasks SET group_id=? WHERE task_id=?", ("b" * 64, task["taskId"]))
        with self.assertRaisesRegex(ProductionLedgerError, "다른 음악 그룹.*새 프로젝트"):
            self.start(taskId=task["taskId"], requestId=request["requestId"], groupId=group)

    def test_dashboard_request_period_and_engine_filters_are_consistent(self):
        request = self.request()
        task = self.start(requestId=request["requestId"], engine="ace")
        self.ledger.finish_task({"taskId": task["taskId"], "status": "succeeded", "elapsedMs": 10})
        future = request["requestedAtMs"] + 86400000
        self.assertEqual(self.ledger.dashboard({"since": future})["summary"]["requestCount"], 0)
        self.assertEqual(self.ledger.dashboard({"engine": "other"})["summary"]["requestCount"], 0)
        self.assertEqual(self.ledger.dashboard({"engine": "ace"})["summary"]["requestCount"], 1)

    def test_new_writer_never_downgrades_a_future_schema_version(self):
        self.request()
        with ManagementDB(self.profile).transaction(write=True) as connection:
            connection.execute("PRAGMA user_version=3")
        self.request(prompt="another")
        with ManagementDB(self.profile).transaction() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_component_observation_defaults_to_installed(self):
        item = self.ledger.record_component({"componentId": "cli", "kind": "cli", "name": "CLI", "installedVersion": "0.1.0"})
        self.assertEqual(item["checkStatus"], "installed")

    def test_total_elapsed_includes_failed_cost_but_average_uses_successes(self):
        first = self.start()
        self.ledger.finish_task({"taskId": first["taskId"], "status": "succeeded", "elapsedMs": 10})
        second = self.start()
        self.ledger.finish_task({"taskId": second["taskId"], "status": "failed", "elapsedMs": 30})
        summary = self.ledger.dashboard()["summary"]
        self.assertEqual(summary["totalElapsedMs"], 40)
        self.assertEqual(summary["avgElapsedMs"], 10)

    def test_project_and_group_performance_exclude_child_steps_and_preserve_unmeasured(self):
        group = "a" * 64
        music_request = self.request(groupId=group)
        music = self.start(requestId=music_request["requestId"], taskId="1" * 48, groupId=group, engine="ace")
        child = self.start(requestId=music_request["requestId"], taskId="2" * 48, groupId=group, parentTaskId=music["taskId"], taskType="decode", engine="ace")
        self.ledger.finish_task({"taskId": child["taskId"], "status": "succeeded", "elapsedMs": 1000})
        self.ledger.finish_task({"taskId": music["taskId"], "status": "succeeded", "elapsedMs": 100, "mediaSeconds": 10})
        motion_project = self.root / "motion"; motion_project.mkdir()
        motion_request = self.ledger.request({"project": str(motion_project), "domain": "motion", "intent": "render", "prompt": "render", "groupId": group})
        motion = self.ledger.start_task({"project": str(motion_project), "domain": "motion", "taskType": "render", "requestId": motion_request["requestId"], "taskId": "3" * 48, "groupId": group})
        unmeasured = self.ledger.start_task({"project": str(motion_project), "domain": "motion", "taskType": "prepare", "requestId": motion_request["requestId"], "taskId": "4" * 48, "groupId": group})
        self.ledger.finish_task({"taskId": motion["taskId"], "status": "failed", "elapsedMs": 300})
        self.ledger.finish_task({"taskId": unmeasured["taskId"], "status": "cancelled"})

        projects = self.ledger.projects()["projects"]
        music_performance = next(item["performance"] for item in projects if item["projectId"] == music["projectId"])
        self.assertEqual(music_performance["totalElapsedMs"], 100)
        self.assertEqual(music_performance["music"]["realtimeFactor"], 0.01)
        self.assertIsNone(music_performance["motion"]["totalElapsedMs"])
        group_performance = self.ledger.group_summaries([group, "b" * 64])
        self.assertEqual(group_performance[0]["performance"]["totalElapsedMs"], 400)
        self.assertEqual(group_performance[0]["performance"]["motion"]["failedCount"], 1)
        self.assertEqual(group_performance[0]["performance"]["missingElapsedCount"], 1)
        self.assertIsNone(group_performance[1]["performance"]["totalElapsedMs"])

        dashboard = self.ledger.dashboard({"groupId": group})
        stages = {(item["domain"], item["taskType"]): item for item in dashboard["stageBreakdown"]}
        self.assertEqual(stages[("music", "generate")]["elapsedMs"], 100)
        self.assertEqual(stages[("motion", "render")]["elapsedMs"], 300)
        self.assertNotIn(("music", "decode"), stages)
        self.assertEqual(self.ledger.dashboard({"groupIds": [group, "b" * 64]})["groupSummaries"][1]["groupId"], "b" * 64)

    def test_project_performance_obeys_task_domain_filter(self):
        music = self.start(taskId="1" * 48)
        self.ledger.finish_task({"taskId": music["taskId"], "status": "succeeded", "elapsedMs": 10})
        project = self.ledger.projects({"domain": "music"})["projects"][0]
        self.assertEqual(project["performance"]["totalElapsedMs"], 10)
        self.assertEqual(project["performance"]["music"]["succeededCount"], 1)
        self.assertIsNone(project["performance"]["motion"]["totalElapsedMs"])

    def test_dashboard_only_returns_stage_breakdown_for_an_explicit_single_group(self):
        grouped = self.request(groupId="a" * 64)
        grouped_task = self.start(requestId=grouped["requestId"], groupId="a" * 64)
        self.ledger.finish_task({"taskId": grouped_task["taskId"], "status": "succeeded", "elapsedMs": 10})
        unbound_project = self.root / "unbound"; unbound_project.mkdir()
        unbound_task = self.ledger.start_task({"project": str(unbound_project), "domain": "music", "taskType": "generate"})
        self.ledger.finish_task({"taskId": unbound_task["taskId"], "status": "succeeded", "elapsedMs": 20})
        self.assertEqual(self.ledger.dashboard()["stageBreakdown"], [])
        self.assertEqual(self.ledger.dashboard({"groupId": "a" * 64})["stageBreakdown"][0]["elapsedMs"], 10)

    def test_legacy_project_first_edit_is_not_presented_as_original_creation_prompt(self):
        revision = self.request(intent="title", prompt="이전 곡 제목을 바꿔줘")
        self.assertFalse(revision["main"])
        self.assertEqual(self.ledger.prompts()["mainPrompts"], [])
        creation = self.request(intent="generation", prompt="새 제작의 최초 요청")
        self.assertTrue(creation["main"])
        self.request(intent="revision", prompt="가사를 보완해줘")
        self.assertEqual(self.ledger.prompts()["mainPrompts"][0]["prompt"], "새 제작의 최초 요청")

    def test_engine_only_task_is_linked_and_latest_completed_parent_wins(self):
        request = self.request(source="engine", prompt="engine settings")
        parent = self.start(engineRequestId=request["requestId"])
        child = self.start(engineRequestId=request["requestId"], parentTaskId=parent["taskId"], taskType="stage:decode")
        self.ledger.finish_task({"taskId": child["taskId"], "status": "succeeded", "elapsedMs": 1, "resultSummary": "decode"})
        self.ledger.finish_task({"taskId": parent["taskId"], "status": "succeeded", "elapsedMs": 2, "resultSummary": "final audio"})
        summary = self.ledger.prompts()["prompts"][0]["taskSummary"]
        self.assertEqual(summary["taskCount"], 2)
        self.assertEqual(summary["latest"]["summary"], "final audio")

    def test_writer_upgrades_old_task_columns_before_creating_new_indexes(self):
        self.profile.mkdir()
        with sqlite3.connect(self.profile / "storage.sqlite3") as connection:
            connection.execute("CREATE TABLE production_tasks (seq INTEGER PRIMARY KEY,task_id TEXT UNIQUE,project_id TEXT,group_id TEXT,request_id TEXT,parent_task_id TEXT,domain TEXT,task_type TEXT,engine TEXT,model TEXT,status TEXT,started_at INTEGER,finished_at INTEGER,elapsed_ms REAL,media_seconds REAL,frame_count INTEGER,ai_summary TEXT,result_summary TEXT,error_summary TEXT)")
            connection.execute("INSERT INTO production_tasks VALUES(1,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','old',NULL,NULL,NULL,'music','generate',NULL,NULL,'success',1000,2000,100,NULL,NULL,NULL,NULL,NULL)")
        self.ledger.record_component({"componentId": "cli", "kind": "cli", "name": "CLI", "installedVersion": "0.1.0"})
        self.assertIsNone(self.ledger.tasks()["tasks"][0]["engineRequestId"])
        with ManagementDB(self.profile).transaction() as connection:
            self.assertIsNotNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='production_tasks_engine_request_idx'").fetchone())

    def test_activity_reads_an_old_active_schema_without_mutating_it(self):
        self.profile.mkdir()
        database = self.profile / "storage.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE production_tasks (seq INTEGER PRIMARY KEY,task_id TEXT UNIQUE,project_id TEXT,group_id TEXT,request_id TEXT,parent_task_id TEXT,domain TEXT,task_type TEXT,engine TEXT,model TEXT,status TEXT,started_at INTEGER,finished_at INTEGER,elapsed_ms REAL,media_seconds REAL,frame_count INTEGER,ai_summary TEXT,result_summary TEXT,error_summary TEXT)")
            connection.execute("INSERT INTO production_tasks VALUES(1,?, 'old',NULL,NULL,NULL,'music','generate','ace','small','queued',1000,NULL,NULL,NULL,NULL,NULL,NULL,NULL)", ("a" * 48,))
        before = (database.stat().st_size, database.stat().st_mtime_ns)
        activity = self.ledger.activity()
        self.assertEqual(activity["queue"]["items"][0]["taskId"], "a" * 48)
        self.assertEqual((database.stat().st_size, database.stat().st_mtime_ns), before)

    def test_activity_uses_only_the_same_model_measurements_and_global_queue_order(self):
        group = "a" * 64
        first = self.request(groupId=group)
        historical = self.start(taskId="1" * 48, requestId=first["requestId"], groupId=group, engine="ace", model="small", expectedMediaSeconds=10)
        self.ledger.finish_task({"taskId": historical["taskId"], "status": "succeeded", "elapsedMs": 1000, "mediaSeconds": 10})
        different = self.start(taskId="2" * 48, requestId=first["requestId"], groupId=group, engine="ace", model="large", expectedMediaSeconds=10)
        self.ledger.finish_task({"taskId": different["taskId"], "status": "succeeded", "elapsedMs": 999999, "mediaSeconds": 10})
        other_project = self.root / "other"
        other_project.mkdir()
        other_request = self.ledger.request({"project": str(other_project), "domain": "music", "intent": "create", "prompt": "other"})
        before = self.ledger.start_task({"project": str(other_project), "domain": "music", "taskType": "generate", "requestId": other_request["requestId"], "taskId": "3" * 48, "engine": "ace", "model": "small", "status": "queued", "expectedMediaSeconds": 10})
        queued = self.start(taskId="4" * 48, requestId=first["requestId"], groupId=group, engine="ace", model="small", status="queued", expectedMediaSeconds=20)
        activity = self.ledger.activity({"groupId": group}, {"state": "available", "paused": False, "observedAtMs": 1, "items": [{"taskId": before["taskId"], "status": "queued", "position": 0}, {"taskId": queued["taskId"], "status": "queued", "position": 1}]})
        item = activity["queue"]["items"][0]
        self.assertEqual((item["estimate"]["estimatedMs"], item["estimate"]["sampleCount"], item["estimatedWaitMs"], item["position"]), (2000, 1, 1000, 1))
        self.assertEqual(activity["globalQueue"]["knownWorkMs"], 3000)

    def test_activity_keeps_parent_and_child_from_double_counting_and_offline_eta_unknown(self):
        request = self.request()
        historical = self.start(taskId="5" * 48, requestId=request["requestId"], engine="ace", model="small")
        self.ledger.finish_task({"taskId": historical["taskId"], "status": "succeeded", "elapsedMs": 1000})
        parent = self.start(taskId="6" * 48, requestId=request["requestId"], engine="ace", model="small", status="running")
        child = self.start(taskId="7" * 48, requestId=request["requestId"], parentTaskId=parent["taskId"], engine="ace", model="small", taskType="decode", status="queued")
        self.ledger.progress_task({"taskId": parent["taskId"], "progress": .5, "currentStage": "합성 중"})
        with patch("production_ledger._now_ms", return_value=parent["startedAtMs"]):
            activity = self.ledger.activity({}, {"state": "offline", "paused": None, "items": []})
        self.assertEqual([item["taskId"] for item in activity["queue"]["items"]], [parent["taskId"]])
        self.assertIsNone(activity["globalQueue"]["completionEtaMs"])
        self.assertTrue(activity["projects"][0]["progress"]["estimated"])
        self.assertEqual(activity["projects"][0]["progress"]["ratio"], 0)

    def test_task_progress_is_monotonic_and_coalesces_rapid_same_stage_updates(self):
        task = self.start(taskId="8" * 48)
        first = self.ledger.progress_task({"taskId": task["taskId"], "progress": .1, "currentStage": "준비"})
        coalesced = self.ledger.progress_task({"taskId": task["taskId"], "progress": .2})
        advanced = self.ledger.progress_task({"taskId": task["taskId"], "progress": .2, "currentStage": "합성"})
        self.assertEqual((first["progress"], coalesced["progress"], advanced["progress"], advanced["currentStage"]), (.1, .1, .2, "합성"))
        with self.assertRaises(ProductionLedgerError):
            self.ledger.progress_task({"taskId": task["taskId"], "progress": .1})

    def test_activity_marks_overrun_unknown_without_inventing_a_tail_eta(self):
        request = self.request()
        historical = self.start(taskId="a" * 48, requestId=request["requestId"], engine="ace", model="small")
        self.ledger.finish_task({"taskId": historical["taskId"], "status": "succeeded", "elapsedMs": 1000})
        running = self.start(taskId="b" * 48, requestId=request["requestId"], engine="ace", model="small", status="running")
        with patch("production_ledger._now_ms", return_value=running["startedAtMs"] + 2000):
            activity = self.ledger.activity({}, {"state": "available", "paused": False, "observedAtMs": 1, "items": [{"taskId": running["taskId"], "status": "running", "position": 0, "progress": 1}]})
        item = activity["queue"]["items"][0]
        self.assertTrue(item["estimate"]["overrun"])
        self.assertIsNone(item["estimate"]["remainingMs"])
        self.assertIsNone(activity["globalQueue"]["completionEtaMs"])

    def test_activity_batches_active_request_and_transition_queries(self):
        historical = self.start(taskId="9" * 48, engine="ace", model="small")
        self.ledger.finish_task({"taskId": historical["taskId"], "status": "succeeded", "elapsedMs": 1000})
        runtime_items = []
        for index in range(50):
            project = self.root / f"queue-{index}"; project.mkdir()
            request = self.ledger.request({"project": str(project), "domain": "music", "intent": "create", "prompt": f"request {index}"})
            task = self.ledger.start_task({"project": str(project), "domain": "music", "taskType": "generate", "requestId": request["requestId"], "taskId": f"{index + 100:048x}", "engine": "ace", "model": "small", "status": "queued"})
            runtime_items.append({"taskId": task["taskId"], "status": "queued", "position": index})
        original = self.ledger.db.transaction
        statements = []
        @contextmanager
        def traced(*args, **kwargs):
            with original(*args, **kwargs) as connection:
                if connection is not None:
                    connection.set_trace_callback(statements.append)
                yield connection
        self.ledger.db.transaction = traced
        activity = self.ledger.activity({}, {"state": "available", "paused": False, "observedAtMs": 1, "items": runtime_items})
        selects = [statement for statement in statements if statement.lstrip().upper().startswith(("SELECT", "WITH"))]
        self.assertEqual(len(activity["projects"]), 50)
        self.assertLess(len(selects), 20)

    def test_invalid_inputs_are_bounded(self):
        with self.assertRaises(ProductionLedgerError): self.request(prompt="x" * (64 * 1024 + 1))
        with self.assertRaises(ProductionLedgerError): self.ledger.request({"project": "relative", "domain": "music", "intent": "x", "prompt": "x"})
        self.request()
        with self.assertRaises(ProductionLedgerError): self.ledger.tasks({"limit": 101})
        with self.assertRaises(ProductionLedgerError): self.ledger.files({"domain": "music"})


if __name__ == "__main__":
    unittest.main()
