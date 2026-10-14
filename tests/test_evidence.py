from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cep.evidence import content_manifest, git, snapshot, verify_snapshot, worktree
from cep import evidence


class EvidenceTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repo / "file.txt").write_text("candidate\n")
        self.git("add", ".")
        self.git("commit", "-m", "chore: candidate fixture")

    def test_snapshot_content_modes_manifest_and_extra_files(self):
        manifest = snapshot(self.repo, self.root / "snapshot")
        self.assertTrue(verify_snapshot(manifest))
        tampered = deepcopy(manifest)
        tampered["files"]["file.txt"]["sha256"] = "fake"
        self.assertFalse(verify_snapshot(tampered))
        path = self.root / "snapshot/file.txt"
        path.chmod(0o555)
        self.assertFalse(verify_snapshot(manifest))
        path.chmod(0o444)
        (self.root / "snapshot/extra.txt").write_text("unexpected")
        self.assertFalse(verify_snapshot(manifest))

    def test_symlinks_and_credentials_rejected(self):
        (self.repo / "file.txt").unlink()
        (self.root / "secret.txt").write_text("private")
        (self.repo / "file.txt").symlink_to(self.root / "secret.txt")
        with self.assertRaises(ValueError):
            content_manifest(self.repo)
        (self.repo / "file.txt").unlink()
        (self.repo / "file.txt").write_text("candidate")
        (self.repo / ".env").write_text("TOKEN=secret")
        with self.assertRaises(ValueError):
            content_manifest(self.repo)

    def test_controller_git_disables_fsmonitor_and_checkout_hooks(self):
        marker = self.root / "executed"
        attack = self.root / "attack.sh"
        attack.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
        attack.chmod(0o755)
        self.git("config", "core.fsmonitor", str(attack))
        hooks = self.root / "hooks"
        hooks.mkdir()
        (hooks / "post-checkout").write_text(attack.read_text())
        (hooks / "post-checkout").chmod(0o755)
        self.git("config", "core.hooksPath", str(hooks))
        git(self.repo, "status", "--porcelain")
        worktree(self.repo, self.root / "worktree", "fixture")
        self.assertFalse(marker.exists())

    def test_executable_filters_and_includes_rejected(self):
        for key in ("filter.attack.smudge", "include.path"):
            with self.subTest(key=key):
                self.git("config", key, "/does/not/exist")
                with self.assertRaises(ValueError):
                    content_manifest(self.repo)
                self.git("config", "--unset", key)

    def test_source_symlink_swap_during_snapshot_cannot_read_secret(self):
        secret = self.root / "secret.txt"
        secret.write_text("private value")
        original = evidence._read_regular
        calls = 0

        def read(repo, relative):
            nonlocal calls
            calls += 1
            if calls == 2:
                (repo / relative).unlink()
                (repo / relative).symlink_to(secret)
            return original(repo, relative)

        with patch("cep.evidence._read_regular", side_effect=read):
            with self.assertRaises((ValueError, OSError)):
                snapshot(self.repo, self.root / "snapshot")
        self.assertFalse((self.root / "snapshot/file.txt").exists())

    def test_case_variant_credentials_are_rejected_and_templates_remain_allowed(self):
        for filename in (".ENV", ".EnV.LoCaL", ".ENV.PRODUCTION"):
            with self.subTest(filename=filename):
                path = self.repo / filename
                path.write_text("TOKEN=private")
                try:
                    with self.assertRaises(ValueError):
                        content_manifest(self.repo)
                finally:
                    path.unlink()
        template = self.repo / ".EnV.ExAmPlE"
        template.write_text("TOKEN=placeholder")
        self.assertIn(template.name, content_manifest(self.repo)["files"])
