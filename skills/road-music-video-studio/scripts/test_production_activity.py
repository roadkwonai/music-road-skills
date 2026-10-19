from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from production_activity import activity
from production_ledger import ProductionLedger


class ProductionActivityTests(unittest.TestCase):
    def test_activity_attaches_live_queue_without_writing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"; root.mkdir()
            ledger = ProductionLedger(Path(directory) / "profile")
            task = ledger.start_task({"project": str(root), "domain": "music", "taskType": "generation", "engine": "ace", "model": "ace", "taskId": "a" * 48, "status": "queued", "expectedMediaSeconds": 36})
            runtime = {"state": "available", "paused": False, "observedAtMs": 123, "items": [{"taskId": task["taskId"], "status": "running", "position": 0, "progress": .25, "currentStage": "synth", "summary": "실제 엔진 단계"}]}
            result = activity(Path(directory) / "profile", {}, runtime_reader=lambda data_dir: runtime)
            self.assertEqual(result["runtime"]["state"], "available")
            self.assertEqual(result["queue"]["items"][0]["currentStage"], "synth")
            self.assertEqual(result["queue"]["items"][0]["progress"], .25)
            self.assertEqual(ledger.tasks({"taskId": task["taskId"]})["tasks"][0]["progress"], None)

    def test_activity_accepts_rich_runtime_items_and_keeps_unmatched_jobs_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"; root.mkdir()
            ledger = ProductionLedger(Path(directory) / "profile")
            group = "a" * 64
            request = ledger.request({"project": str(root), "domain": "music", "intent": "create", "prompt": "원문", "groupId": group})
            historical = ledger.start_task({"project": str(root), "domain": "music", "taskType": "generation", "engine": "ace", "model": "ace", "requestId": request["requestId"], "groupId": group, "taskId": "b" * 48, "status": "running", "expectedMediaSeconds": 36})
            ledger.finish_task({"taskId": historical["taskId"], "status": "succeeded", "elapsedMs": 1000, "mediaSeconds": 36})
            task = ledger.start_task({"project": str(root), "domain": "music", "taskType": "generation", "engine": "ace", "model": "ace", "requestId": request["requestId"], "groupId": group, "taskId": "a" * 48, "status": "queued", "expectedMediaSeconds": 36})
            runtime = {"state": "available", "paused": False, "observedAtMs": 123, "items": [
                {"jobId": "untracked-job", "project": str(root), "title": "복구된 대기 작업", "domain": "music", "taskType": "generation", "engine": "ace", "model": "ace", "status": "queued", "position": 0, "plannedSeconds": 36, "queuedAt": 1, "ignoredByLedger": {"large": "value"}},
                {"taskId": task["taskId"], "jobId": "tracked-job", "projectId": task["projectId"], "title": "연결 작업", "domain": "music", "taskType": "generation", "engine": "ace", "model": "ace", "status": "queued", "position": 1, "expectedMediaSeconds": 36, "expectedFrameCount": 0, "queuedAt": 2},
            ]}
            result = activity(Path(directory) / "profile", {"groupId": group}, runtime_reader=lambda data_dir: runtime)
            self.assertEqual(result["globalQueue"]["unknownCount"], 1)
            self.assertIsNone(result["globalQueue"]["completionEtaMs"])
            self.assertEqual(result["queue"]["items"][0]["taskId"], task["taskId"])
            self.assertIsNone(result["queue"]["items"][0]["estimatedWaitMs"])
            self.assertTrue(any(item.get("runtimeOnly") and item["jobId"] == "untracked-job" for item in activity(Path(directory) / "profile", {}, runtime_reader=lambda data_dir: runtime)["queue"]["items"]))
            self.assertEqual(ledger.tasks({"taskId": task["taskId"]})["tasks"][0]["status"], "queued")


if __name__ == "__main__":
    unittest.main()
