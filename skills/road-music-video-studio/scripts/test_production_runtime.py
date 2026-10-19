from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import production_runtime


class Result:
    def __init__(self, payload, code=0):
        self.returncode = code
        self.stdout = json.dumps(payload) + "\n"
        self.stderr = ""


class ProductionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "cli").mkdir()
        (self.root / "cli" / "road-music.js").write_text("// fixture\n", encoding="utf-8")
        self.script = self.root / ".agents/skills/road-music-video-studio/scripts/production_runtime.py"
        self.script.parent.mkdir(parents=True)
        self.script.write_text("# fixture\n", encoding="utf-8")
        production_runtime._CACHE.clear()

    def tearDown(self):
        production_runtime._CACHE.clear()
        self.temp.cleanup()

    def test_reads_current_profile_without_starting_and_normalises_queue(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return Result({"ok": True, "result": {"paused": False, "current": {"jobId": "job-1", "productionTaskId": "a" * 48, "title": "현재", "progress": .25, "currentStage": "synth", "plannedSeconds": 36, "elapsedMs": 1234}, "waiting": [{"jobId": "job-2", "taskId": "b" * 48, "title": "대기"}]}})
        value = production_runtime.read_runtime_queue(self.root / "profile", env={"ROADMUSIC_CLI_ROOT": str(self.root)}, runner=runner, now=123, script_path=self.script)
        self.assertEqual(value["state"], "available")
        self.assertEqual([(item["status"], item["position"]) for item in value["items"]], [("running", 0), ("queued", 1)])
        self.assertEqual(value["items"][0]["taskId"], "a" * 48)
        self.assertEqual((value["items"][0]["expectedMediaSeconds"], value["items"][0]["elapsedMs"]), (36.0, 1234))
        self.assertEqual(calls[0][0][-1], "--no-start")
        self.assertEqual(calls[0][1]["env"]["ROADMUSIC_DATA_DIR"], str((self.root / "profile").resolve()))
        self.assertEqual(calls[0][1]["env"]["ROADMUSIC_STUDIO_AUTO_OPEN"], "0")
        self.assertEqual(calls[0][1]["timeout"], 3)

    def test_stopped_service_is_an_offline_empty_queue(self):
        value = production_runtime.read_runtime_queue(self.root / "profile", env={"ROADMUSIC_CLI_ROOT": str(self.root)}, runner=lambda *args, **kwargs: Result({"ok": False, "error": {"code": "SERVICE_STOPPED"}}, 1), now=123, script_path=self.script)
        self.assertEqual(value, {"state": "offline", "paused": None, "items": [], "observedAtMs": 123})

    def test_cache_reuses_short_read_only_snapshot(self):
        calls = []
        def runner(*args, **kwargs):
            calls.append(args)
            return Result({"ok": True, "result": {"paused": True, "items": []}})
        first = production_runtime.read_runtime_queue(self.root / "profile", env={"ROADMUSIC_CLI_ROOT": str(self.root)}, runner=runner, now=123, script_path=self.script)
        second = production_runtime.read_runtime_queue(self.root / "profile", env={"ROADMUSIC_CLI_ROOT": str(self.root)}, runner=runner, now=456, script_path=self.script)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first["observedAtMs"], second["observedAtMs"])


if __name__ == "__main__":
    unittest.main()
