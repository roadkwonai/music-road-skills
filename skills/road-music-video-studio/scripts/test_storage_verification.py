import hashlib, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path: sys.path.insert(0, str(SCRIPTS))
from storage_verification import VerificationMaintenance, DMG_BYTES, DMG_SHA256, PROFILES, DMG_ROOTS
from storage_manager import StorageError, StorageManager


class VerificationMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        (self.root / "cli").mkdir(); (self.root / ".git").mkdir(); (self.root / "cli/road-music.js").write_text("x")
        (self.root / "package.json").write_text(json.dumps({"name": "road-music", "bin": {"road-music": "cli/road-music.js"}}))
        self.store = VerificationMaintenance(self.root, active_check=lambda _: False)
        self._profiles()

    def tearDown(self): self.temp.cleanup()

    def _json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value), encoding="utf-8")

    def _profiles(self):
        paths = {name: self.root / relative for name, relative, *_ in PROFILES}
        for path in paths.values(): path.mkdir(parents=True, exist_ok=True); (path / "payload.txt").write_text(path.name)
        forward = self.root / "Output/music-road-skills-publish-20261018/forward-test/release-build/MusicRoad-Skills-0.1.0.zip"; forward.parent.mkdir(parents=True); forward.write_bytes(b"forward")
        self._json(self.root / "Output/music-road-skills-publish-20261018/forward-test/release-build.json", {"version": "0.1.0", "archive": str(forward), "sha256": hashlib.sha256(b"forward").hexdigest()})
        for name, receipt in (("forward-installed", "install-project.json"), ("forward-clean", "clean-install.json")):
            marker = paths[name] / ".agents/skills/.music-road-skills/managed.json"; marker.parent.mkdir(parents=True)
            self._json(marker, {"repository": "roadkwonai/music-road-skills", "version": "0.1.0", "source": "/historic/source"})
            self._json(self.root / "Output/music-road-skills-publish-20261018/forward-test" / receipt, {"ok": True, "result": {"target": str(paths[name] / ".agents/skills"), "version": "0.1.0"}})
        extracted = paths["forward-extracted"] / "MusicRoad-Skills-0.1.0/manifest.json"; extracted.parent.mkdir(parents=True)
        self._json(extracted, {"name": "music-road-skills", "version": "0.1.0"})
        self._json(self.root / "Output/music-road-skills-publish-20261018/forward-test/verification-summary.json", {"verdict": "PASS"})
        cli_archive = self.root / "Output/music-road-skills-publish-20261018/cli-live-release-0.1.1/RoadMusic-CLI-0.1.1.zip"; cli_archive.parent.mkdir(parents=True); cli_archive.write_bytes(b"cli")
        digest = hashlib.sha256(b"cli").hexdigest()
        self._json(paths["cli-e2e"] / "RoadMusic-CLI-0.1.1/package.json", {"name": "road-music"})
        self._json(self.root / "Output/music-road-skills-publish-20261018/cli-kit-e2e-report.json", {"version": {"cliVersion": "0.1.1"}, "sourceMusicPreserved": True})
        (cli_archive.parent / "SHA256SUMS.txt").write_text(f"{digest}  {cli_archive.name}\n", encoding="utf-8")
        installed = paths["cli-installed-skills"] / ".music-road-skills/managed.json"; installed.parent.mkdir(parents=True)
        self._json(installed, {"repository": "roadkwonai/music-road-skills", "version": "0.1.0", "source": str(paths["cli-e2e"] / "RoadMusic-CLI-0.1.1/skills/music-road-skills")})
        live = paths["live-release-skills"] / ".music-road-skills/managed.json"; live.parent.mkdir(parents=True)
        self._json(live, {"repository": "roadkwonai/music-road-skills", "version": "0.1.0", "source": "/historic/extract"})
        for receipt in ("live-skills-install.json", "live-skills-check.json"):
            self._json(self.root / "Output/music-road-skills-publish-20261018" / receipt, {"result": {"target": str(paths["live-release-skills"])}})
        public_archive = self.root / "Output/music-road-skills-publish-20261018/release-final-use-time-check/MusicRoad-Skills-0.1.0.zip"; public_archive.parent.mkdir(parents=True); public_archive.write_bytes(b"public")
        self._json(public_archive.parent / "verification.json", {"archive": str(public_archive), "sha256": hashlib.sha256(b"public").hexdigest()})
        self._json(paths["local-cli-kit"] / "RoadMusic-CLI-0.1.2/package.json", {"name": "road-music"})
        self._json(self.root / "Output/skills-review-20261018/local-kit-e2e.json", {"publicationPerformed": False, "restoredTestTargetClean": True, "archiveSha256": "c" * 64})
        log = self.root / "Output/skills-review-20261018/cli-package.log"; log.parent.mkdir(parents=True, exist_ok=True); log.write_text("RoadMusic-CLI-0.1.2.zip\n")

    def test_only_exact_profiles_are_candidates_and_cleaned(self):
        found = self.store.inspect(); self.assertEqual(len(found["candidates"]), len(PROFILES))
        result = self.store.cleanup(found["candidates"])
        self.assertEqual(result["removedFiles"], len(PROFILES) * 2)
        self.assertTrue(all(not (self.root / profile[1]).exists() for profile in PROFILES))
        self.assertTrue((self.root / "Output/music-road-skills-publish-20261018/forward-test/install-project.json").exists())

    def test_mutation_symlink_or_activity_invalidates_without_deleting(self):
        first = self.store.inspect()["candidates"][0]
        (self.root / first["path"] / "payload.txt").write_text("changed")
        with self.assertRaisesRegex(StorageError, "계획 뒤"): self.store.cleanup([first])
        self.assertTrue((self.root / first["path"] / "payload.txt").exists())
        self.store = VerificationMaintenance(self.root, active_check=lambda _: True)
        self.assertFalse(self.store.inspect()["candidates"])

    def test_mutation_after_first_unlink_reports_only_actual_partial_cleanup(self):
        candidate = self.store.inspect()["candidates"][0]
        original = StorageManager._unlink_verified; calls = 0
        marker = self.root / candidate["path"] / ".agents/skills/.music-road-skills/managed.json"
        def unlink(root, relative, expected):
            nonlocal calls
            original(root, relative, expected); calls += 1
            if calls == 1: marker.write_text("changed", encoding="utf-8")
        with patch.object(StorageManager, "_unlink_verified", side_effect=unlink):
            result = self.store.cleanup([candidate])
        self.assertEqual(result["removedFiles"], 1)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertTrue(marker.exists())

    def test_dmg_requires_exact_receipt_size_and_hash(self):
        root = self.root / DMG_ROOTS[0]; download = root / "dist/.release-verify-HGUiMR/mac-app/updates/RoadMusic-1.4.0-mac-arm64.dmg.download"
        download.parent.mkdir(parents=True); payload = b"fixture"; download.write_bytes(payload)
        import storage_verification
        old = (storage_verification.DMG_BYTES, storage_verification.DMG_SHA256)
        storage_verification.DMG_BYTES, storage_verification.DMG_SHA256 = len(payload), hashlib.sha256(payload).hexdigest()
        try:
            self._json(download.parent / "update-state.json", {"asset": {"name": download.name.removesuffix(".download"), "size": len(payload), "sha256": storage_verification.DMG_SHA256}})
            candidate = self.store.inspect()["candidates"][-1]
            self.assertEqual(candidate["kind"], "installer-download-cache")
            result = self.store.cleanup([candidate]); self.assertEqual(result["freedBytes"], len(payload)); self.assertFalse(download.exists())
        finally:
            storage_verification.DMG_BYTES, storage_verification.DMG_SHA256 = old


    def test_absent_profiles_are_not_reported_as_remaining_protected_files(self):
        import shutil
        for profile in PROFILES: shutil.rmtree(self.root / profile[1])
        self.assertEqual(self.store.inspect(), {'candidates': [], 'blocked': []})

    def test_current_cli_reference_and_lsof_failure_protect_targets(self):
        import subprocess
        path = self.root / PROFILES[0][1]
        with patch('storage_verification.shutil.which', return_value=str(path / 'payload.txt')):
            self.assertTrue(self.store._active(path))
        with patch('storage_verification.shutil.which', return_value=None), patch('storage_verification.subprocess.run', return_value=subprocess.CompletedProcess([], 2, '', '')):
            self.assertTrue(self.store._active(path))
        file = path / 'payload.txt'
        with patch('storage_verification.shutil.which', return_value=None), patch('storage_verification.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', '')) as command:
            self.assertFalse(self.store._active(file))
            self.assertIn('--', command.call_args.args[0]); self.assertNotIn('+D', command.call_args.args[0])


if __name__ == "__main__": unittest.main()
