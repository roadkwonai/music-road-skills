import hashlib, json, sys, tempfile, unittest, zipfile
from pathlib import Path
SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path: sys.path.insert(0, str(SCRIPTS))
import storage_packaging
from storage_packaging import PackagingStorage, discover_trusted_root, git_available, is_workspace
from storage_manager import StorageError, StorageManager
from storage_legacy import StorageLegacy

class PackagingStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        (self.root / "cli").mkdir(); (self.root / ".git").mkdir()
        (self.root / "cli/road-music.js").write_text("#!/usr/bin/env node\n"); (self.root / "AGENTS.md").write_text("rules\n")
        (self.root / "package.json").write_text(json.dumps({"name":"road-music","bin":{"road-music":"cli/road-music.js"}}))
        self.old = (storage_packaging.TRUSTED_ROOT, storage_packaging.PLAYLIST_SHA256, storage_packaging.TOMORROW_SHA256); storage_packaging.TRUSTED_ROOT = self.root
        release = self.root / "Output/skills-release-review-20261018"; release.mkdir(parents=True)
        (release / "published-release.json").write_text(json.dumps({"assets":[{"digest":"sha256:" + "a" * 64}]}))
        (release / "github-releases.json").write_text(json.dumps([{"assets":[{"digest":"sha256:" + "b" * 64}]}]))
    def tearDown(self):
        storage_packaging.TRUSTED_ROOT, storage_packaging.PLAYLIST_SHA256, storage_packaging.TOMORROW_SHA256 = self.old; self.temp.cleanup()
    def archive(self, project, folder):
        path = self.root / "Output" / project / folder / "MusicRoad-Skills-0.1.1.zip"; path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as z: z.writestr("MusicRoad-Skills-0.1.1/README.md", "fixture")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        (path.parent / "SHA256SUMS.txt").write_text(f"{digest}  {path.name}\n")
        return path, digest
    def proof(self, project, archive, digest, tomorrow=False):
        base = self.root / "Output" / project
        if tomorrow:
            (base / "qa").mkdir(); (base / "qa/package-audit.json").write_text(json.dumps({"archive":str(archive),"archiveSha256":digest,"pass":True,"finalized":True,"published":False})); (base / "qa/delivery-audit.json").write_text(json.dumps({"published":False}))
        else:
            (base / "package-audit.json").write_text(json.dumps({"archive":str(archive),"sha256":digest,"purpose":"local verification only; not published"})); (base / "validation.json").write_text(json.dumps({"status":"complete-local-not-published"}))
    def test_exact_profiles_and_snapshot_receipts(self):
        playlist, playlist_sha = self.archive("showreel-playlist-rebuild-20261018", "package-check"); tomorrow, tomorrow_sha = self.archive("showreel-tomorrow-full-rebuild-20261018", "package-check-v2")
        storage_packaging.PLAYLIST_SHA256, storage_packaging.TOMORROW_SHA256 = playlist_sha, tomorrow_sha
        self.proof("showreel-playlist-rebuild-20261018", playlist, playlist_sha); self.proof("showreel-tomorrow-full-rebuild-20261018", tomorrow, tomorrow_sha, True)
        store = PackagingStorage(self.root, open_check=lambda _: True)
        self.assertEqual({item[0] for item in store.sources()}, {playlist, tomorrow})
        candidate = store.candidate("p", playlist); self.assertEqual(len(candidate["evidence"]["receipts"]), 3)
        publisher = self.root / 'Output/skills-release-review-20261018/github-releases.json'
        publisher.write_text(json.dumps([[{'assets': [{'digest': 'sha256:' + 'b' * 64}]}]]))
        self.assertNotEqual(store.candidate('p', playlist)['id'], candidate['id'])
    def test_rejects_self_signed_third_and_source_alias(self):
        forged, digest = self.archive("forged", "package-check"); self.proof("forged", forged, digest)
        self.assertEqual(PackagingStorage(self.root, open_check=lambda _: True).sources(), [])
        alias = self.root / "alias.zip"; alias.symlink_to(forged)
        with self.assertRaisesRegex(Exception, "안전한 workspace"): PackagingStorage(self.root, open_check=lambda _: True).candidate("p", alias)
    def test_missing_corrupt_or_published_receipt_denies(self):
        archive, digest = self.archive("showreel-playlist-rebuild-20261018", "package-check"); storage_packaging.PLAYLIST_SHA256 = digest; self.proof("showreel-playlist-rebuild-20261018", archive, digest)
        published = self.root / "Output/skills-release-review-20261018/published-release.json"; published.unlink()
        self.assertEqual(PackagingStorage(self.root, open_check=lambda _: True).sources(), [])
        published.write_text(json.dumps({"assets":[{"digest":"sha256:" + digest}]}))
        self.assertEqual(PackagingStorage(self.root, open_check=lambda _: True).sources(), [])

    def test_receipt_parent_alias_is_rejected(self):
        archive, digest = self.archive('showreel-tomorrow-full-rebuild-20261018', 'package-check-v2')
        storage_packaging.TOMORROW_SHA256 = digest
        self.proof('showreel-tomorrow-full-rebuild-20261018', archive, digest, True)
        qa = archive.parent.parent / 'qa'; real = archive.parent.parent / 'actual-qa'
        qa.rename(real); qa.symlink_to(real, target_is_directory=True)
        self.assertEqual(PackagingStorage(self.root, open_check=lambda _: True).sources(), [])
    def test_workspace_must_be_exact_trusted_root(self):
        self.assertTrue(is_workspace(self.root))
        other = self.root / "other"; other.mkdir(); self.assertFalse(is_workspace(other))

    def test_packaged_kit_without_git_discovers_depth_three_root(self):
        (self.root / ".git").rmdir()
        self.assertTrue(is_workspace(self.root)); self.assertFalse(git_available(self.root))
        module = self.root / "skills/studio/scripts/storage_packaging.py"; module.parent.mkdir(parents=True); module.write_text("# fixture\n")
        self.assertEqual(discover_trusted_root(module), self.root)

    def test_external_skill_uses_only_validated_explicit_cli_root(self):
        outside = self.root.parent / 'external-skill/storage_packaging.py'
        self.assertEqual(discover_trusted_root(outside, {'ROADMUSIC_CLI_ROOT': str(self.root)}), self.root)
        self.assertIsNone(discover_trusted_root(outside, {'ROADMUSIC_CLI_ROOT': str(self.root / 'Output')}))
        self.assertIsNone(discover_trusted_root(outside, {'ROADMUSIC_CLI_ROOT': 'relative-kit'}))
        alias = self.root / 'kit-alias'; alias.symlink_to(self.root, target_is_directory=True)
        self.assertIsNone(discover_trusted_root(outside, {'ROADMUSIC_CLI_ROOT': str(alias)}))

    def test_workspace_adoption_preserves_programs_and_counts_only_managed_storage(self):
        archive, digest = self.archive("showreel-playlist-rebuild-20261018", "package-check")
        storage_packaging.PLAYLIST_SHA256 = digest
        self.proof("showreel-playlist-rebuild-20261018", archive, digest)
        manager = StorageManager(self.root / 'state')
        project = manager.dispatch('register', {'project': str(self.root)})
        self.assertEqual(project['usageScope'], 'managed-cache')
        self.assertFalse(any(item['relativePath'].startswith('Output/') for item in project['unmanagedEntries']))
        legacy = StorageLegacy(manager, open_check=lambda _: False)
        candidates = legacy.legacy({'projectId': project['id']})['candidates']
        self.assertEqual(len(candidates), 1)
        plan = legacy.adopt_preview({'projectId': project['id'], 'candidateIds': [candidates[0]['id']]})
        result = legacy.adopt({'planId': plan['planId'], 'confirm': True})
        self.assertEqual(result['movedFiles'], 1)
        self.assertFalse(archive.exists())
        cleanup = manager.dispatch('preview', {'projectId': project['id']})
        self.assertEqual(manager.dispatch('cleanup', {'planId': cleanup['planId'], 'confirm': True})['removedFiles'], 1)
        self.assertTrue((self.root / 'cli/road-music.js').is_file())
        program = self.root / '.roadmusic/cache/current.py'; program.write_bytes(b'program')
        with self.assertRaises(StorageError): manager.dispatch('track', {'projectId': project['id'], 'path': '.roadmusic/cache/current.py', 'kind': 'cache', 'reproducible': True})

if __name__ == "__main__": unittest.main()
