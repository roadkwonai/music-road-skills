import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from storage_manager import StorageManager
from storage_overview import StorageOverview, _synthetic_group
from storage_scan import WorkspaceScan
from work_library import WorkLibrary


def digest(value):
    return hashlib.sha256(value).hexdigest()


class FakeMV:
    def __init__(self, manager): pass
    def list(self, params):
        return {"projects": [{"id": "a" * 64, "title": "AI 영상", "sourceSha256": self.source, "sourcePath": "/tmp/music.mp3", "path": "/tmp/mv", "bytes": 7, "allocatedBytes": 8, "fileCount": 2, "reclaimableBytes": 0, "blocked": False}], "blocked": []}


class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.root = base / "workspace"; self.root.mkdir()
        self.data = base / "data"; self.manager = StorageManager(self.data)
        self.source = self.root / "music.mp3"; self.source.write_bytes(b"source"); self.sha = digest(b"source"); FakeMV.source = self.sha
        self.project = self._project("known", self.source, self.sha, with_video=True)
        self.other_source = self.root / "other.mp3"; self.other_source.write_bytes(b"other")
        self.other = self._project("other", self.other_source, digest(b"other"), with_video=False)
        self.generic = self.root / "project-refined"; self.generic.mkdir(); (self.generic / "preview.mp3").write_bytes(b"preview")
        (self.generic / "meta.json").write_text(json.dumps({"title": "검증 프로젝트"}), encoding="utf-8")
        self.known_row = self.manager.dispatch("register", {"project": str(self.project)})
        self.manager.dispatch("register", {"project": str(self.other)})
        self.manager.dispatch("register", {"project": str(self.generic)})
        cache = self.project / ".roadmusic/cache/render.tmp"; cache.write_bytes(b"cache")
        self.manager.dispatch("track", {"projectId": self.known_row["id"], "path": ".roadmusic/cache/render.tmp", "kind": "cache", "reproducible": True})
        WorkLibrary(self.data / "video-studio-library.json").register(self.project)

    def overview(self):
        return StorageOverview(self.manager, mv_storage_factory=FakeMV, workspace_root=self.root)

    def _project(self, name, source, source_sha, *, with_video):
        project = self.root / name; project.mkdir(); media = [{"id": "music", "kind": "music", "path": str(source), "name": source.name, "size": source.stat().st_size, "sha256": source_sha, "source": "external"}]
        if with_video:
            video = self.root / f"{name}.mp4"; video.write_bytes(b"video")
            media.append({"id": "video-0", "kind": "video", "path": str(video), "name": video.name, "size": video.stat().st_size, "sha256": digest(b"video"), "sourceMusicSha256": source_sha})
        (project / "studio-project.json").write_text(json.dumps({"schemaVersion": 1, "name": name, "media": media}), encoding="utf-8")
        (project / "selection.json").write_text(json.dumps({"schemaVersion": 1, "mode": "showreel-motion", "host": "codex", "styleId": None, "display": {"showSpectrum": None, "showQueue": None, "showNowPlaying": None, "channelName": None}}), encoding="utf-8")
        (project / "feedback.json").write_text(json.dumps({}), encoding="utf-8")
        (project / ".roadmusic/cache").mkdir(parents=True)
        return project

    def test_unknown_private_work_is_not_hidden_by_management_root_claim(self):
        orphan = self.root / '.roadmusic/work/orphan'; orphan.mkdir(parents=True)
        (orphan / 'media.mp4').write_bytes(b'orphan media')
        (orphan / 'archive.zip').write_bytes(b'orphan archive')
        pending = self.root / '.roadmusic/work/pending'; pending.mkdir()
        (pending / 'media.mp4').write_bytes(b'pending media')
        self.manager.management_db.claim_path(str(pending), 'producer-work', project_id='p' * 64, workspace=str(self.root))
        WorkspaceScan(self.root, self.data).scan()
        workspace = self.overview().list({})['overall']['workspace']
        folders = {item['path'] for item in workspace['unattributedFolders']}
        self.assertIn('.roadmusic/work/orphan', folders)
        self.assertNotIn('.roadmusic/work/pending', folders)
        self.assertTrue(any(item['kind'] == 'pending-production' for item in workspace['categories']))
        self.assertTrue((orphan / 'media.mp4').is_file())

    def test_management_tooling_and_program_paths_are_owned_but_unknown_stays_visible(self):
        for folder in (".roadmusic", ".harness", ".omx", ".omc", "_workspace", "docs", "releases", "mystery"):
            path = self.root / folder; path.mkdir(exist_ok=True); (path / "state.bin").write_bytes(b"state")
        WorkspaceScan(self.root, self.data).scan()
        with patch("storage_scan.WorkspaceScan._digest", side_effect=AssertionError("rehash")), patch("storage_overview.gzip.open", side_effect=AssertionError("inventory reread")):
            result = self.overview().list({})
        folders = {item["path"] for item in result["overall"]["workspace"]["unattributedFolders"]}
        self.assertIn("mystery", folders)
        self.assertFalse(folders & {".roadmusic", ".harness", ".omx", ".omc", "_workspace", "docs", "releases"})

    def test_known_music_merges_registered_and_mv_projects(self):
        result = self.overview().list({})
        group = next(item for item in result["groups"] if item["groupId"] == self.sha)
        self.assertEqual(group["groupId"], self.sha)
        self.assertEqual(group["sourcePath"], str(self.source))
        self.assertEqual(len(group["projects"]), 1)
        self.assertEqual(len(group["mvProjects"]), 1)
        self.assertGreater(group["totalBytes"], 0)
        self.assertTrue(any(item.get("path") == str(self.generic) for item in result["otherProjects"]))

    def test_known_music_includes_only_registered_work_files(self):
        group = next(item for item in self.overview().list({})["groups"] if item["groupId"] == self.sha)
        self.assertEqual({item["kind"] for item in group["files"]}, {"source", "video"})
        self.assertEqual({item["name"] for item in group["files"]}, {self.source.name, "known.mp4"})
        self.assertTrue(all(item["id"] and item["sha256"] for item in group["files"]))

    def test_recorded_studio_source_creates_a_named_music_group_without_rehashing(self):
        result = self.overview().list({})
        group = next(item for item in result["groups"] if item["groupId"] == digest(b"other"))
        self.assertEqual(group["sourcePath"], str(self.other_source))
        self.assertEqual([item["id"] for item in group["projects"]], [self.manager.dispatch("register", {"project": str(self.other)})["id"]])

    def test_ambiguous_library_origin_uses_the_project_recorded_source_hash(self):
        first, second = "1" * 64, "2" * 64
        known, paths = StorageOverview._group_sources([
            {"groupId": first, "sourceSha256": first, "title": "하나", "source": {"name": "하나.mp3", "path": str(self.source), "project": str(self.project), "origins": []}, "files": [], "artifacts": []},
            {"groupId": second, "sourceSha256": second, "title": "둘", "source": {"name": "둘.mp3", "path": str(self.other_source), "project": str(self.project), "origins": []}, "files": [], "artifacts": []},
        ])
        self.assertNotIn(str(self.project), paths)
        self.assertIn(first, known)

    def test_project_without_a_recorded_music_identity_stays_in_other_projects(self):
        result = self.overview().list({})
        row = next(item for item in result["otherProjects"] if item.get("path") == str(self.generic))
        self.assertEqual(row["kind"], "project")

    def test_synthetic_source_is_kept_out_of_music_groups_without_deleting_it(self):
        source = self.root / "시험 신호.mp3"; source.write_bytes(b"tone")
        project = self._project("signal", source, digest(b"tone"), with_video=False)
        self.manager.dispatch("register", {"project": str(project)})
        result = self.overview().list({})
        self.assertNotIn(digest(b"tone"), [item["groupId"] for item in result["groups"]])
        self.assertTrue(any(item.get("kind") == "synthetic-input" and item.get("path") == str(project) for item in result["otherProjects"]))

    def test_demo_assets_and_project_folder_names_do_not_hide_a_real_music_source(self):
        group = {"title": "내 음악", "sourcePath": "/Music/내 음악.wav", "projects": [{"path": "/tmp/custom-smoke/project"}], "mvProjects": [{"sourcePath": "/Music/내 음악.wav"}]}
        self.assertIsNone(_synthetic_group(group))
        self.assertEqual(_synthetic_group({**group, "sourcePath": "/Music/test-tone.wav"}), "검증·테스트 입력음원")

    def test_no_params_are_accepted(self):
        with self.assertRaises(Exception):
            self.overview().list({"path": "/tmp"})
        with self.assertRaises(Exception):
            self.overview().list({"refreshWorkspace": "yes"})

    def test_default_overview_reuses_cached_scan_without_running_a_new_scan(self):
        WorkspaceScan(self.root, self.data).scan()
        with patch("storage_overview.WorkspaceScan.scan", side_effect=AssertionError("unexpected scan")):
            result = self.overview().list({"refreshWorkspace": False})
        self.assertTrue(result["overall"]["workspace"]["available"])

    def test_nested_profile_skips_workspace_scan_but_keeps_registered_groups(self):
        manager = StorageManager(self.root / ".roadmusic" / "maintenance" / "profile")
        manager.dispatch("register", {"project": str(self.project)})
        overview = StorageOverview(manager, mv_storage_factory=FakeMV, workspace_root=self.root)
        with patch("storage_overview.WorkspaceScan", side_effect=AssertionError("workspace scan")):
            result = overview.list({"refreshWorkspace": True})
        workspace = result["overall"]["workspace"]
        self.assertEqual(workspace["cacheState"], "scan-skipped-profile-inside-workspace")
        self.assertIn("전체 스캔을 생략", workspace["warning"])
        self.assertTrue(any(item["groupId"] == self.sha for item in result["groups"]))

    def test_refresh_workspace_scans_metadata_and_includes_new_unmanaged_file(self):
        output = self.root / "Output" / "refresh"; output.mkdir(parents=True)
        (output / "production.json").write_text(json.dumps({"source": {"sha256": self.sha, "path": str(self.source)}}), encoding="utf-8")
        first = WorkspaceScan(self.root, self.data).scan()
        before = next(item for item in self.overview().list({})["groups"] if item["groupId"] == self.sha)
        new_file = output / "motion-cache.mov"; new_file.write_bytes(b"new render" * 1000)
        result = self.overview().list({"refreshWorkspace": True})
        workspace = result["overall"]["workspace"]
        after = next(item for item in result["groups"] if item["groupId"] == self.sha)
        self.assertEqual(workspace["cacheState"], "refreshed")
        self.assertNotEqual(workspace["scanId"], first["scanId"])
        self.assertGreaterEqual(after["unmanagedBytes"], before["unmanagedBytes"] + new_file.stat().st_blocks * 512)

    def test_incomplete_refresh_falls_back_to_cached_inventory_without_cleanup_authority(self):
        WorkspaceScan(self.root, self.data).scan()
        with patch("storage_overview.WorkspaceScan.scan", return_value={"complete": False}):
            result = self.overview().list({"refreshWorkspace": True})
        workspace = result["overall"]["workspace"]
        self.assertFalse(workspace["available"])
        self.assertEqual(workspace["cacheState"], "refresh-incomplete-cache")
        self.assertIn("이전 완결 스캔", workspace["warning"])

    def test_cached_workspace_usage_groups_metadata_files_once_and_accounts_for_every_inode(self):
        output = self.root / "Output" / "producer"; output.mkdir(parents=True)
        (output / "production.json").write_text(json.dumps({"source": {"sha256": self.sha, "path": str(self.source)}}), encoding="utf-8")
        render = output / "render.mov"; render.write_bytes(b"render" * 1000)
        render_copy = output / "render-copy.mov"; render_copy.hardlink_to(render)
        (self.root / "models").mkdir(); (self.root / "models" / "keep.safetensors").write_bytes(b"model")
        (self.root / ".git").mkdir(); (self.root / ".git" / "objects").write_bytes(b"git")
        (self.root / "bundle.zip").write_bytes(b"zip")
        scan = WorkspaceScan(self.root, self.data).scan()
        result = self.overview().list({})
        workspace = result["overall"]["workspace"]
        group = next(item for item in result["groups"] if item["groupId"] == self.sha)
        self.assertEqual(workspace["scanId"], scan["scanId"])
        self.assertEqual(sum(item["bytes"] for item in group["producerProjects"]), group["workspaceBytes"])
        producer = next(item for item in group["producerProjects"] if item["path"] == str(output))
        self.assertEqual(producer["fileCount"], len({item["inode"] for item in self._producer_records(scan)}))
        self.assertEqual(workspace["allocatedBytes"], workspace["groupBytes"] + workspace["systemBytes"] + workspace["unattributedBytes"] + workspace["testInputBytes"])
        self.assertEqual({item["kind"] for item in workspace["categories"]}, {"model", "git", "package"})

    def _producer_records(self, scan):
        import gzip
        with gzip.open(scan["inventoryPath"], "rt", encoding="utf-8") as stream:
            return [item for item in (json.loads(line) for line in stream) if item.get("type") == "file" and item["relativePath"].startswith("Output/producer/")]

    def test_conflicting_nested_source_metadata_is_not_assigned_to_either_music_group(self):
        output = self.root / "Output" / "mixed"; nested = output / "native"; nested.mkdir(parents=True)
        other = "e" * 64
        (output / "production.json").write_text(json.dumps({"source": {"sha256": self.sha, "path": str(self.source)}}), encoding="utf-8")
        (nested / "native-production.json").write_text(json.dumps({"source": {"sha256": other, "path": str(self.other_source)}}), encoding="utf-8")
        mixed = nested / "intermediate.mp4"; mixed.write_bytes(b"mixed" * 100)
        scan = WorkspaceScan(self.root, self.data).scan()
        result = self.overview().list({})
        workspace = result["overall"]["workspace"]
        self.assertEqual(workspace["allocatedBytes"], workspace["groupBytes"] + workspace["systemBytes"] + workspace["unattributedBytes"] + workspace["testInputBytes"])
        self.assertGreater(workspace["unattributedBytes"], 0)
        self.assertTrue(any(item["kind"] == "output" for item in workspace["unattributedCategories"]))

    def test_multi_song_owner_uses_deep_metadata_roots_and_keeps_shared_parent_unattributed(self):
        parent = self.root / "Output" / "multi"; left = parent / "left"; right = parent / "right"
        left.mkdir(parents=True); right.mkdir()
        second = "d" * 64
        for folder, source, source_path, name in ((left, self.sha, self.source, "left"), (right, second, self.other_source, "right")):
            (folder / "production.json").write_text(json.dumps({"source": {"sha256": source, "path": str(source_path)}}), encoding="utf-8")
            (folder / f"{name}.mp4").write_bytes(name.encode() * 100)
        shared = parent / "shared-qa.png"; shared.write_bytes(b"shared" * 100)
        WorkspaceScan(self.root, self.data).scan()
        result = self.overview().list({})
        first_group = next(item for item in result["groups"] if item["groupId"] == self.sha)
        second_group = next(item for item in result["groups"] if item["groupId"] == second)
        self.assertTrue(any(item["path"] == str(left) for item in first_group["producerProjects"]))
        self.assertTrue(any(item["path"] == str(right) for item in second_group["producerProjects"]))
        self.assertFalse(any(item["path"] == str(parent) for item in first_group["producerProjects"] + second_group["producerProjects"]))
        workspace = result["overall"]["workspace"]
        self.assertTrue(any(item["path"] == "Output/multi" for item in workspace["unattributedFolders"]))

    def test_single_source_owner_expands_to_its_qa_assets(self):
        parent = self.root / "Output" / "single"; producer = parent / "production"; producer.mkdir(parents=True)
        (producer / "production.json").write_text(json.dumps({"source": {"sha256": self.sha, "path": str(self.source)}}), encoding="utf-8")
        qa = parent / "qa"; qa.mkdir(); frame = qa / "frame.png"; frame.write_bytes(b"frame" * 100)
        WorkspaceScan(self.root, self.data).scan()
        result = self.overview().list({})
        group = next(item for item in result["groups"] if item["groupId"] == self.sha)
        self.assertTrue(any(item["path"] == str(parent) and item["bytes"] >= frame.stat().st_blocks * 512 for item in group["producerProjects"]))

    def test_input_metadata_requires_both_recorded_source_path_and_sha(self):
        project = self.root / "Output" / "harness" / "run"; project.mkdir(parents=True)
        (project / "input.json").write_text(json.dumps({"source_audio_path": str(self.source), "source_audio_sha256": self.sha}), encoding="utf-8")
        asset = project / "animatic.mp4"; asset.write_bytes(b"animation" * 100)
        WorkspaceScan(self.root, self.data).scan()
        result = self.overview().list({})
        group = next(item for item in result["groups"] if item["groupId"] == self.sha)
        self.assertTrue(any(item["path"] == str(project) and item["bytes"] >= asset.stat().st_blocks * 512 for item in group["producerProjects"]))

    def test_internal_music_named_source_stays_out_of_user_music_groups(self):
        internal = self.root / "Output" / "preview" / "audio" / "music"; internal.mkdir(parents=True)
        source = internal / "music.wav"; source.write_bytes(b"internal music")
        project = self._project("internal-preview", source, digest(b"internal music"), with_video=False)
        self.manager.dispatch("register", {"project": str(project)})
        WorkspaceScan(self.root, self.data).scan()
        result = self.overview().list({})
        self.assertNotIn(digest(b"internal music"), [item["groupId"] for item in result["groups"]])

    def test_jizura_final_command_requires_matching_provenance_before_owner_attribution(self):
        owner = self.root / "Output" / "jizura"; owner.mkdir(parents=True)
        other_sha = digest(b"other")
        (owner / "final-render-command.json").write_text(json.dumps(["node", "render.mjs", "--audio", str(self.other_source), "--out", str(owner / "render")]), encoding="utf-8")
        (owner / "source-provenance.json").write_text(json.dumps({"userAudio": str(self.other_source), "sha256": other_sha}), encoding="utf-8")
        movie = owner / "final.mp4"; movie.write_bytes(b"final render" * 100)
        WorkspaceScan(self.root, self.data).scan()
        result = self.overview().list({})
        group = next(item for item in result["groups"] if item["groupId"] == other_sha)
        self.assertTrue(any(item["path"] == str(owner) and item["bytes"] >= movie.stat().st_blocks * 512 for item in group["producerProjects"]))
        (owner / "source-provenance.json").write_text(json.dumps({"userAudio": str(self.source), "sha256": self.sha}), encoding="utf-8")
        WorkspaceScan(self.root, self.data).scan()
        result = self.overview().list({})
        self.assertFalse(any(item["path"] == str(owner) for group in result["groups"] for item in group["producerProjects"]))


if __name__ == "__main__":
    unittest.main()
