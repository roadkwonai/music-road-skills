import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path: sys.path.insert(0, str(SCRIPTS))

from delivery_store import DeliveryStore
from storage_manager import StorageError, StorageManager
from storage_project_finish import ProjectFinish
import storage_packaging
from work_library import WorkLibrary


class ProjectFinishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve() / "music-road"; (self.workspace / "Output").mkdir(parents=True)
        (self.workspace / "cli").mkdir(); (self.workspace / "cli/road-music.js").write_text("#!/usr/bin/env node\n")
        (self.workspace / "AGENTS.md").write_text("rules\n")
        (self.workspace / "package.json").write_text(json.dumps({"name":"road-music","bin":{"road-music":"cli/road-music.js"}}))
        self.original_root = storage_packaging.TRUSTED_ROOT; storage_packaging.TRUSTED_ROOT = self.workspace; self.addCleanup(setattr, storage_packaging, "TRUSTED_ROOT", self.original_root)
        self.project = self.workspace / ".roadmusic/work/song/project"; self.project.mkdir(parents=True)
        self.music = self.project / "song.mp3"; self.music.write_bytes(b"music")
        self.video = self.project / "final.mp4"; self.video.write_bytes(b"video")
        self.cache = self.project / ".roadmusic/cache/frame.png"; self.cache.parent.mkdir(parents=True); self.cache.write_bytes(b"cache")
        self.report = self.workspace / ".roadmusic/control/history/production-validation.json"; self.report.parent.mkdir(parents=True); self.report.write_text(json.dumps({"pass": True}))
        (self.project / "selection.json").write_text(json.dumps({"style":"warm"}))
        (self.project / "feedback.json").write_text(json.dumps({"note":"keep"}))
        self.project.joinpath("studio-project.json").write_text(json.dumps({"schemaVersion":1,"name":"Song","media":[{"id":"music","kind":"music","path":str(self.music),"sha256":self._sha(self.music),"size":self.music.stat().st_size},{"id":"video","kind":"video","path":str(self.video),"sha256":self._sha(self.video),"size":self.video.stat().st_size},{"id":"report","kind":"artifact","artifactType":"report","path":str(self.report),"sha256":self._sha(self.report),"size":self.report.stat().st_size}]}))
        DeliveryStore(self.workspace).publish(self.project, [{"id":"music","kind":"music","path":str(self.music)},{"id":"video","kind":"video","path":str(self.video)}], source_sha256=self._sha(self.music), title="Song", _allow_source_only=False)
        self.manager = StorageManager(self.workspace / ".appdata"); self.project_id = self.manager.dispatch("register", {"project":str(self.project)})["id"]
        WorkLibrary(self.manager.data_dir / "video-studio-library.json").register(self.project)
        self.manager.dispatch("policy", {"projectId":self.project_id,"state":"completed"}); self.finish = ProjectFinish(self.manager)

    @staticmethod
    def _sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def test_preview_then_finish_removes_only_private_work_after_canonical_verification(self):
        entry = self.manager.dispatch("track", {"projectId": self.project_id, "path": ".roadmusic/cache/frame.png", "kind": "cache", "reproducible": True})
        preview = self.finish.preview({"projectId":self.project_id})
        self.assertGreater(preview["summary"]["fileCount"], 2)
        result = self.finish.cleanup({"planId":preview["planId"],"confirm":True})
        self.assertTrue(self.project.exists()); self.assertGreater(result["removedFiles"], 2)
        self.assertEqual(sorted(path.relative_to(self.project).as_posix() for path in self.project.rglob("*") if path.is_file()), ["feedback.json", "selection.json", "studio-project.json"])
        self.assertTrue(self.report.is_file())
        self.assertTrue(Path(result["retainedHistoryPath"]).is_file())
        self.assertTrue(any((self.workspace / "Output").rglob("song.mp3")))
        self.assertEqual(self.manager.dispatch("list", {"projectId": self.project_id})["projects"][0]["entries"], [])
        again = self.finish.preview({"projectId": self.project_id})
        self.assertTrue(again["alreadyFinished"]); self.assertIsNone(again["planId"])
        self.assertEqual(again["retainedHistoryPath"], result["retainedHistoryPath"])
        (self.project / "new-work.tmp").write_bytes(b"new")
        with self.assertRaises(StorageError) as changed:
            self.finish.preview({"projectId": self.project_id})
        self.assertEqual(changed.exception.code, "already_finished_changed")

    def test_editing_pinned_changed_or_missing_delivery_is_rejected(self):
        self.manager.dispatch("policy", {"projectId":self.project_id,"state":"editing"})
        with self.assertRaises(StorageError): self.finish.preview({"projectId":self.project_id})
        self.manager.dispatch("policy", {"projectId":self.project_id,"state":"completed"})
        entry = self.manager.dispatch("track", {"projectId":self.project_id,"path":".roadmusic/cache/frame.png","kind":"cache","reproducible":True})
        self.manager.dispatch("pin", {"projectId":self.project_id,"entryId":entry["id"],"pinned":True})
        with self.assertRaises(StorageError): self.finish.preview({"projectId":self.project_id})
        self.manager.dispatch("pin", {"projectId":self.project_id,"entryId":entry["id"],"pinned":False})
        preview = self.finish.preview({"projectId":self.project_id}); self.cache.write_bytes(b"changed")
        with self.assertRaises(StorageError): self.finish.cleanup({"planId":preview["planId"],"confirm":True})

    def test_external_symlink_and_unpublished_media_are_protected(self):
        outside = self.workspace.parent / "outside.wav"; outside.write_bytes(b"outside")
        (self.project / "bad").symlink_to(outside)
        with self.assertRaises(StorageError): self.finish.preview({"projectId":self.project_id})

    def test_canonicalized_studio_media_paths_are_accepted(self):
        database = self.workspace / ".roadmusic/history.sqlite3"
        with __import__("sqlite3").connect(database) as connection:
            rows = list(connection.execute("SELECT kind,path,sha256,bytes FROM delivery_files"))
        studio = json.loads((self.project / "studio-project.json").read_text())
        for item in studio["media"]:
            if item["kind"] == "artifact":
                continue
            row = next(row for row in rows if row[0] == item["kind"] and row[2] == item["sha256"])
            item.update({"path": row[1], "size": row[3]})
        (self.project / "studio-project.json").write_text(json.dumps(studio))
        preview = self.finish.preview({"projectId": self.project_id})
        self.assertGreater(preview["summary"]["canonicalFiles"], 0)
        self.finish.cleanup({"planId": preview["planId"], "confirm": True})
        saved = json.loads((self.project / "studio-project.json").read_text())
        self.assertTrue(all(Path(item["path"]).is_relative_to(self.workspace / "Output") for item in saved["media"] if item["kind"] != "artifact"))
        self.assertTrue(any(item["kind"] == "artifact" and Path(item["path"]) == self.report for item in saved["media"]))

    def test_finish_preserves_verified_media_metadata_for_library_reregistration(self):
        captions = self.project / "final.srt"; captions.write_text("1\n00:00:00,000 --> 00:00:01,000\nSong\n")
        source_sha, video_sha = self._sha(self.music), self._sha(self.video)
        studio_path = self.project / "studio-project.json"
        studio = json.loads(studio_path.read_text())
        video = next(item for item in studio["media"] if item["kind"] == "video")
        video.update({"styleLabel": "종이배의 항해", "styleId": "paper-boat", "sourceMusicSha256": source_sha, "producedAt": "2026-10-19T12:34:56+09:00"})
        studio["media"].append({"id": "captions", "kind": "captions", "path": str(captions), "sha256": self._sha(captions), "size": captions.stat().st_size, "sourceMusicSha256": source_sha, "forVideoSha256": video_sha, "producedAt": "2026-10-19T12:34:56+09:00"})
        studio_path.write_text(json.dumps(studio))
        DeliveryStore(self.workspace).publish(self.project, [{"id": "music", "kind": "music", "path": str(self.music)}, {"id": "video", "kind": "video", "path": str(self.video)}, {"id": "captions", "kind": "captions", "path": str(captions)}], source_sha256=source_sha, title="Song", _allow_source_only=False)
        library_path = self.manager.data_dir / "video-studio-library.json"
        WorkLibrary(library_path).register(self.project)

        preview = self.finish.preview({"projectId": self.project_id})
        self.finish.cleanup({"planId": preview["planId"], "confirm": True})
        retained = json.loads(studio_path.read_text())
        retained_video = next(item for item in retained["media"] if item["kind"] == "video")
        retained_captions = next(item for item in retained["media"] if item["kind"] == "captions")
        self.assertEqual(retained_video["styleLabel"], "종이배의 항해")
        self.assertEqual(retained_video["styleId"], "paper-boat")
        self.assertEqual(retained_video["sourceMusicSha256"], source_sha)
        self.assertEqual(retained_video["producedAt"], "2026-10-19T12:34:56+09:00")
        self.assertEqual(retained_captions["forVideoSha256"], video_sha)
        self.assertTrue(Path(retained_video["path"]).is_relative_to(self.workspace / "Output"))
        self.assertEqual(retained_video["sha256"], video_sha)
        self.assertEqual(retained_video["size"], (Path(retained_video["path"])).stat().st_size)

        group = WorkLibrary(self.workspace / ".reregister" / "video-studio-library.json").register(self.project)
        files = {item["kind"]: item for item in group["files"]}
        self.assertEqual(files["video"]["styleLabel"], "종이배의 항해")
        self.assertEqual(files["video"]["styleId"], "paper-boat")
        self.assertEqual(files["video"]["producedAt"], "2026-10-19T12:34:56+09:00")
        self.assertEqual(files["captions"]["forVideoSha256"], video_sha)


if __name__ == "__main__": unittest.main()
