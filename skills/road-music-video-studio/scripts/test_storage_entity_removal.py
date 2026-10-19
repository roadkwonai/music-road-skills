from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from delivery_store import DeliveryStore
from production_ledger import ProductionLedger
from storage_entity_removal import StorageEntityRemoval
from storage_manager import StorageError, StorageManager
from work_library import WorkLibrary


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class EntityRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "workspace"; self.root.mkdir()
        self.manager = StorageManager(self.root.parent / "profile")
        self.library = WorkLibrary(self.manager.data_dir / "video-studio-library.json")
        self.store = DeliveryStore(self.root)
        self.workspace_patch = patch("storage_entity_removal.is_workspace", return_value=True)
        self.workspace_patch.start(); self.addCleanup(self.workspace_patch.stop)
        self.removal = StorageEntityRemoval(self.manager, self.root)

    def make_project(self, label, source=None):
        source = source or self.root / (label + ".mp3")
        if not source.exists(): source.write_bytes(("source-" + label).encode())
        project = self.root / ".roadmusic" / "work" / label; project.mkdir(parents=True)
        video = project / "final.mp4"; video.write_bytes(("video-" + label).encode())
        media = [{"id": "music", "kind": "music", "path": str(source)}, {"id": "video", "kind": "video", "path": str(video), "sourceMusicSha256": digest(source)}]
        marker = project / "studio-project.json"
        marker.write_text(json.dumps({"schemaVersion": 1, "name": label, "media": media}))
        registration = self.manager.register({"project": str(project)})
        version = self.store.publish(project, media, source_sha256=digest(source), title=label, project_id=registration["id"])
        media = [{key: value for key, value in item.items() if key != "bytes"} | {"size": item["bytes"], "sourceMusicSha256": digest(source)} for item in version["media"]]
        marker.write_text(json.dumps({"schemaVersion": 1, "name": label, "media": media}))
        group = self.library.register(project)
        self.manager.management_db.record_event("fixture", project_id=registration["id"], group_id=group["groupId"], path=str(project))
        self.manager.management_db.claim_path(str(project), "project", project_id=registration["id"], group_id=group["groupId"], workspace=str(self.root))
        return {"project": project, "id": registration["id"], "group": group["groupId"], "source": source, "media": media}

    def test_group_removes_selected_files_and_sql_but_preserves_other_group_and_external_source(self):
        selected, other = self.make_project("first"), self.make_project("second")
        before_other = {Path(item["path"]): digest(item["path"]) for item in other["media"]}
        other_plan = self.removal.preview_group({"groupId": other["group"]})
        with self.manager.management_db.transaction(write=True) as connection:
            for project in (selected, other):
                relative = str((project["project"] / "studio-project.json").relative_to(self.root))
                connection.execute("INSERT INTO storage_tracking_files(workspace,relative_path,size,allocated_bytes,file_type,classification,label,protection_reason,indexed_at,scan_id) VALUES(?,?,?,?,?,?,?,?,?,?)", (str(self.root), relative, 1, 512, "file", "project", "fixture", "", 1, "fixture"))
        plan = self.removal.preview_group({"groupId": selected["group"]})
        self.assertTrue(plan["eligible"], plan)
        self.library.set_favorite(selected["group"], True)
        self.assertGreater(plan["summary"]["allocatedBytes"], 0)
        result = self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertFalse(selected["project"].exists()); self.assertTrue(selected["source"].exists())
        self.assertEqual(set(result["remaining"].values()), {0})
        self.assertEqual(result["removedProjects"], 1); self.assertEqual(result["removedGroups"], 1)
        for path, expected in before_other.items(): self.assertEqual(digest(path), expected)
        self.assertIn(other["group"], self.library._read()["groups"])
        self.assertEqual(self.library.management_db.favorites({selected["group"]}), {})
        self.assertIn(other["id"], self.manager._read()["projects"])
        self.assertIsNone(self.manager.management_db.read_document("entity-removal:" + other_plan["planId"]))
        with self.manager.management_db.transaction() as connection:
            rows = connection.execute("SELECT relative_path FROM storage_tracking_files WHERE workspace=?", (str(self.root),)).fetchall()
        self.assertEqual(rows, [(str((other["project"] / "studio-project.json").relative_to(self.root)),)])
        with self.assertRaises(StorageError): self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        compact = self.manager.management_db.read_document("entity-removal:" + plan["planId"])
        self.assertNotIn(str(selected["project"]), json.dumps(compact))

    def test_project_removal_preserves_same_group_other_project_and_shared_file(self):
        selected = self.make_project("one")
        other = self.make_project("two", selected["source"])
        group = self.library._read()["groups"][selected["group"]]
        shared = next(item for item in group["files"] if any(origin["project"] == str(selected["project"]) for origin in item["origins"]))
        # A valid second origin makes this physical canonical file shared.
        other_origin = next(origin for item in group["files"] for origin in item["origins"] if origin["project"] == str(other["project"]))
        shared["origins"].append(other_origin)
        library = self.library._read(); library["groups"][selected["group"]] = group; self.library._save(library)
        plan = self.removal.preview_project({"projectId": selected["id"]})
        self.assertTrue(plan["eligible"], plan)
        self.assertTrue(any(item["path"] == shared["path"] for item in plan["preserved"]))
        self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertTrue(Path(shared["path"]).exists()); self.assertTrue(other["project"].exists())
        self.assertIn(selected["group"], self.library._read()["groups"])
        kept = next(item for item in self.library._read()["groups"][selected["group"]]["files"] if item["id"] == shared["id"])
        self.assertEqual(kept["project"], str(other["project"]))

    def test_busy_pin_symlink_and_model_are_blocked(self):
        project = self.make_project("protected")
        lease = self.manager.lease({"projectId": project["id"], "operation": "acquire", "pid": os.getpid()})
        self.assertFalse(self.removal.preview_project({"projectId": project["id"]})["eligible"])
        self.manager.lease({"projectId": project["id"], "operation": "release", "token": lease["token"]})
        registry = self.manager._read(); registry["projects"][project["id"]]["entries"]["pin"] = {"pinned": True}; self.manager._save(registry)
        self.assertFalse(self.removal.preview_project({"projectId": project["id"]})["eligible"])
        registry["projects"][project["id"]]["entries"] = {}; self.manager._save(registry)
        link = project["project"] / "link"; link.symlink_to(project["source"])
        self.assertFalse(self.removal.preview_project({"projectId": project["id"]})["eligible"])
        link.unlink(); model = project["project"] / "model.gguf"; model.write_bytes(b"model")
        self.assertFalse(self.removal.preview_project({"projectId": project["id"]})["eligible"])
        self.assertTrue(model.exists())

    def test_active_production_task_blocks_entity_removal_until_explicit_finish(self):
        selected = self.make_project("active-production")
        ledger = ProductionLedger(self.manager.data_dir)
        request = ledger.request({"project": str(selected["project"]), "domain": "motion", "intent": "render", "prompt": "keep working", "groupId": selected["group"]})
        task = ledger.start_task({"project": str(selected["project"]), "domain": "motion", "taskType": "render", "requestId": request["requestId"], "groupId": selected["group"]})
        blocked = self.removal.preview_project({"projectId": selected["id"]})
        self.assertFalse(blocked["eligible"])
        self.assertTrue(any(item.get("taskId") == task["taskId"] for item in blocked["blocked"]))
        ledger.finish_task({"taskId": task["taskId"], "status": "cancelled"})
        self.assertTrue(self.removal.preview_project({"projectId": selected["id"]})["eligible"])

    def test_external_active_task_with_selected_group_blocks_group_removal(self):
        selected = self.make_project("group-active")
        external = self.root / ".roadmusic" / "work" / "external-active"; external.mkdir(parents=True)
        ledger = ProductionLedger(self.manager.data_dir)
        request = ledger.request({"project": str(external), "domain": "motion", "intent": "render", "prompt": "external", "groupId": selected["group"]})
        task = ledger.start_task({"project": str(external), "domain": "motion", "taskType": "render", "requestId": request["requestId"], "groupId": selected["group"]})
        plan = self.removal.preview_group({"groupId": selected["group"]})
        self.assertFalse(plan["eligible"]); self.assertIn(task["taskId"], {item.get("taskId") for item in plan["blocked"]})

    def test_changed_file_and_missing_confirm_leave_all_files(self):
        selected = self.make_project("changed")
        plan = self.removal.preview_project({"projectId": selected["id"]})
        with self.assertRaises(StorageError): self.removal.cleanup({"planId": plan["planId"]})
        path = Path(selected["media"][1]["path"]); path.write_bytes(b"changed")
        with self.assertRaises(StorageError): self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertTrue(selected["project"].exists()); self.assertTrue(path.exists())

    def test_delivery_sql_failure_rolls_back_profile_and_all_files(self):
        selected = self.make_project("rollback")
        before_registry, before_library, before_delivery = self.manager._read(), self.library._read(), self.removal._delivery()
        plan = self.removal.preview_group({"groupId": selected["group"]})
        original_delete = self.removal._delivery_delete
        def fail_after_delivery_commit(value):
            original_delete(value)
            raise sqlite3.OperationalError("fixture failure after delivery commit")
        with patch.object(self.removal, "_delivery_delete", side_effect=fail_after_delivery_commit):
            with self.assertRaisesRegex(StorageError, "복구"):
                self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertTrue(selected["project"].exists())
        self.assertEqual(self.manager._read(), before_registry); self.assertEqual(self.library._read(), before_library)
        self.assertEqual(self.removal._delivery(), before_delivery)
        for item in selected["media"]: self.assertTrue(Path(item["path"]).exists())

    def test_process_interrupt_preserves_isolation_and_requires_recovery(self):
        selected = self.make_project("interrupt")
        plan = self.removal.preview_project({"projectId": selected["id"]})
        original_delete = self.removal._delivery_delete
        def interrupt_after_delivery_commit(value):
            original_delete(value)
            raise KeyboardInterrupt
        with patch.object(self.removal, "_delivery_delete", side_effect=interrupt_after_delivery_commit):
            with self.assertRaises(KeyboardInterrupt): self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        stored = self.manager.management_db.read_document("entity-removal:" + plan["planId"])
        self.assertEqual(stored["state"], "applying")
        self.assertEqual(self.removal._delivery()["delivery_versions"], [])
        self.assertTrue(all(Path(move["staging"]).exists() for move in stored["moves"]))
        self.assertIn(selected["id"], self.manager._read()["projects"])
        with self.assertRaisesRegex(StorageError, "복구 점검"):
            self.removal.cleanup({"planId": plan["planId"], "confirm": True})

    def interrupt(self, selected):
        plan = self.removal.preview_project({"projectId": selected["id"]})
        original = self.removal._delivery_delete
        def interrupt_after_commit(value):
            original(value)
            raise KeyboardInterrupt
        with patch.object(self.removal, "_delivery_delete", side_effect=interrupt_after_commit):
            with self.assertRaises(KeyboardInterrupt): self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        return plan

    def test_public_recovery_restores_interrupted_files_and_both_metadata_stores(self):
        selected, other = self.make_project("recover"), self.make_project("untouched")
        registry, library, delivery = self.manager._read(), self.library._read(), self.removal._delivery()
        plan = self.interrupt(selected)
        result = self.removal.recover({"planId": plan["planId"], "confirm": True})
        self.assertTrue(result["recovered"]); self.assertEqual(result["removedFiles"], 0)
        self.assertTrue(selected["project"].exists()); self.assertTrue(other["project"].exists())
        self.assertEqual(self.manager._read(), registry); self.assertEqual(self.library._read(), library)
        self.assertEqual(self.removal._delivery(), delivery)
        for item in selected["media"]: self.assertTrue(Path(item["path"]).exists())
        with self.assertRaises(StorageError): self.removal.recover({"planId": plan["planId"], "confirm": True})

    def test_recovery_rejects_changed_metadata_file_and_injected_destination(self):
        selected = self.make_project("recovery-guard")
        plan = self.interrupt(selected)
        with self.assertRaises(StorageError): self.removal.recover({"planId": plan["planId"]})
        stored = self.manager.management_db.read_document("entity-removal:" + plan["planId"])
        stage = Path(stored["moves"][0]["staging"])
        (stage / "new-file.txt").write_text("changed")
        with self.assertRaisesRegex(StorageError, "격리 자료"):
            self.removal.recover({"planId": plan["planId"], "confirm": True})
        (stage / "new-file.txt").unlink()
        selected["project"].symlink_to(selected["source"])
        with self.assertRaises(StorageError): self.removal.recover({"planId": plan["planId"], "confirm": True})
        selected["project"].unlink()
        held = stage.with_name("held"); stage.rename(held); stage.symlink_to(selected["source"])
        with self.assertRaises(StorageError): self.removal.recover({"planId": plan["planId"], "confirm": True})
        stage.unlink(); held.rename(stage)
        before = self.manager._read(); changed = self.manager._read()
        changed["projects"][selected["id"]]["name"] = "changed"; self.manager._save(changed)
        with self.assertRaisesRegex(StorageError, "등록 정보"):
            self.removal.recover({"planId": plan["planId"], "confirm": True})
        self.manager._save(before)
        self.manager.management_db.record_event("changed-after-interrupt", project_id=selected["id"])
        with self.assertRaisesRegex(StorageError, "소유권·이력"):
            self.removal.recover({"planId": plan["planId"], "confirm": True})
        self.assertTrue(stage.is_dir()); self.assertTrue(selected["source"].is_file())

    def test_recovery_preserves_all_files_if_delivery_history_changed(self):
        selected, other = self.make_project("delivery-guard"), self.make_project("delivery-other")
        plan = self.interrupt(selected)
        with closing(sqlite3.connect(self.removal.database)) as connection:
            connection.execute("UPDATE delivery_groups SET title='changed' WHERE group_id=?", (other["group"],)); connection.commit()
        with self.assertRaisesRegex(StorageError, "납품 이력"):
            self.removal.recover({"planId": plan["planId"], "confirm": True})
        self.assertTrue(other["project"].exists())
        stored = self.manager.management_db.read_document("entity-removal:" + plan["planId"])
        self.assertTrue(all(Path(move["staging"]).exists() for move in stored["moves"]))
        blocked = self.removal.preview_project({"projectId": other["id"]})
        self.assertFalse(blocked["eligible"]); self.assertEqual(blocked["blocked"][0]["planId"], plan["planId"])

    def test_committed_cleanup_can_resume_after_unlink_failure(self):
        selected = self.make_project("unlink-failure")
        plan = self.removal.preview_project({"projectId": selected["id"]})
        with patch("storage_entity_removal.shutil.rmtree", side_effect=OSError("fixture unlink failure")):
            with self.assertRaisesRegex(StorageError, "같은 계획"):
                self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        stored = self.manager.management_db.read_document("entity-removal:" + plan["planId"])
        self.assertEqual(stored["state"], "committed")
        result = self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertEqual(set(result["remaining"].values()), {0})
        self.assertFalse(selected["project"].exists())

    def test_registered_external_project_is_detached_but_preserved(self):
        selected = self.make_project("external")
        external = self.root / "external-project"
        selected["project"].rename(external)
        registry = self.manager._read(); registry["projects"].pop(selected["id"]); self.manager._save(registry)
        selected_id = self.manager.register({"project": str(external)})["id"]
        self.library.register(external)
        # Remove the obsolete origin exactly as a pre-existing external fixture.
        library = self.library._read()
        for entry in [library["groups"][selected["group"]]["source"], *library["groups"][selected["group"]]["files"]]:
            entry["origins"] = [origin for origin in entry["origins"] if origin["project"] == str(external)]
            entry["project"] = str(external)
        self.library._save(library)
        plan = self.removal.preview_project({"projectId": selected_id})
        self.assertTrue(plan["eligible"], plan)
        self.assertTrue(any(item["path"] == str(external) for item in plan["preserved"]))
        self.removal.cleanup({"planId": plan["planId"], "confirm": True})
        self.assertTrue(external.is_dir()); self.assertTrue(selected["source"].exists())

    def test_surviving_producer_markers_protect_absolute_relative_and_asset_inputs(self):
        selected = self.make_project("producer-marker-target")
        source = selected["project"] / "shared-input.wav"; source.write_bytes(b"shared input")
        variants = [
            ("native-production.json", {"source_audio": str(source), "source_audio_sha256": digest(source)}),
            ("native-production.json", {"source": {"path": str(source), "sha256": digest(source)}}),
            ("playlist.json", {"tracks": [{"source": {"path": str(source)}}]}),
            ("native-production.json", {"source_audio": "RELATIVE"}),
            ("native-production.json", {"style": {"assets": [{"file": str(source)}]}}),
            ("input.json", {"sourceAudioPath": str(source)}),
        ]
        for index, (marker_name, fields) in enumerate(variants):
            with self.subTest(marker=marker_name, fields=fields):
                dependent = self.root / ("producer-dependent-" + str(index)); dependent.mkdir()
                if fields.get("source_audio") == "RELATIVE": fields = {"source_audio": os.path.relpath(source, dependent)}
                for name in ("native-production.json", "playlist.json"):
                    (dependent / name).write_text(json.dumps({"schemaVersion": 1}))
                (dependent / marker_name).write_text(json.dumps({"schemaVersion": 1, **fields}))
                dependent_id = self.manager.register({"project": str(dependent)})["id"]
                plan = self.removal.preview_group({"groupId": selected["group"]})
                self.assertFalse(plan["eligible"])
                self.assertTrue(any(item.get("projectId") == dependent_id and item.get("path") == str(source) for item in plan["blocked"]))
                self.assertTrue(source.exists())

    def test_ordinary_lyrics_text_does_not_become_a_file_dependency(self):
        selected, other = self.make_project("lyrics-target"), self.make_project("lyrics-other")
        source = selected["project"] / "source.wav"; source.write_bytes(b"source")
        (other["project"] / "production-request.json").write_text(json.dumps({"lyrics": str(source), "caption": str(source)}))
        plan = self.removal.preview_project({"projectId": selected["id"]})
        self.assertTrue(plan["eligible"], plan)

    def test_surviving_registered_child_is_protected_even_with_external_input_and_active_lease(self):
        selected = self.make_project("parent-target")
        child = selected["project"] / "registered-child"; child.mkdir()
        (child / "studio-project.json").write_text(json.dumps({"schemaVersion": 1, "media": [{"id": "music", "kind": "music", "path": str(selected["source"])}]}))
        child_id = self.manager.register({"project": str(child)})["id"]
        lease = self.manager.lease({"projectId": child_id, "operation": "acquire", "pid": os.getpid()})
        plan = self.removal.preview_project({"projectId": selected["id"]})
        self.assertFalse(plan["eligible"])
        self.assertTrue(any(item.get("projectId") == child_id and "프로젝트" in item["reason"] for item in plan["blocked"]))
        self.assertTrue(child.exists()); self.assertEqual(self.manager._read()["leases"][child_id]["token"], lease["token"])

    def test_unreadable_or_symlinked_surviving_metadata_blocks_removal(self):
        selected, other = self.make_project("marker-target"), self.make_project("marker-other")
        marker = other["project"] / "native-production.json"
        marker.write_text("invalid JSON")
        plan = self.removal.preview_project({"projectId": selected["id"]})
        self.assertFalse(plan["eligible"])
        marker.unlink(); marker.symlink_to(other["project"] / "studio-project.json")
        plan = self.removal.preview_project({"projectId": selected["id"]})
        self.assertFalse(plan["eligible"])
        self.assertTrue(selected["project"].exists())

    def test_remaining_project_input_blocks_removal(self):
        selected, other = self.make_project("input"), self.make_project("dependent")
        marker = other["project"] / "studio-project.json"
        value = json.loads(marker.read_text()); value["media"][0]["path"] = selected["media"][1]["path"]; marker.write_text(json.dumps(value))
        plan = self.removal.preview_group({"groupId": selected["group"]})
        self.assertFalse(plan["eligible"]); self.assertTrue(any("사용하는" in item["reason"] for item in plan["blocked"]))


if __name__ == "__main__": unittest.main()
