"""CEP-SETUP: reversible integration preserves edits and filesystem boundaries."""

import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from cep.install import (
    InstallError,
    _Tree,
    install_project,
    rollback_project,
    uninstall_project,
)
from cep.project import ProjectError


BUNDLE = Path(__file__).resolve().parents[1] / "plugin"


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.bundle = Path(self.temp.name) / "bundle"
        shutil.copytree(BUNDLE, self.bundle)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_dry_run_is_nonmutating_and_apply_is_idempotent(self):
        self.write("pyproject.toml", "[project]\nname='test'")
        before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        preview = install_project(self.root, self.bundle)
        self.assertEqual(preview["status"], "planned")
        self.assertFalse(preview["applied"])
        self.assertEqual(
            before, sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        )
        applied = install_project(self.root, self.bundle, apply=True)
        self.assertEqual(applied["status"], "installed")
        self.assertEqual(
            install_project(self.root, self.bundle, apply=True)["status"], "unchanged"
        )
        manifest = tomllib.loads((self.root / "engineering-platform.toml").read_text())
        self.assertEqual(manifest["packs"], [])
        self.assertFalse(manifest["autonomy"]["auto_merge"])

    def test_existing_instructions_and_global_independent_project_config_preserved(
        self,
    ):
        instruction = self.write("AGENTS.md", "My project rules\n")
        config = self.write(
            ".codex/config.toml",
            '# personal project settings\nmodel = "configured-model"\n',
        )
        original = config.read_bytes()
        install_project(self.root, self.bundle, apply=True)
        self.assertTrue(config.read_bytes().startswith(original))
        self.assertEqual(instruction.read_text(), "My project rules\n")
        uninstall_project(self.root, apply=True)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(instruction.read_text(), "My project rules\n")
        self.assertFalse((self.root / "engineering-platform.toml").exists())

    def test_unowned_agent_conflict_prevents_all_mutations(self):
        profile = self.write(
            ".codex/agents/code_reviewer.toml", 'name = "my-reviewer"\n'
        )
        result = install_project(self.root, self.bundle, apply=True)
        self.assertEqual(result["status"], "conflict")
        self.assertIn(".codex/agents/code_reviewer.toml", result["conflicts"])
        self.assertEqual(profile.read_text(), 'name = "my-reviewer"\n')
        self.assertFalse((self.root / ".cep").exists())
        self.assertFalse((self.root / "engineering-platform.toml").exists())

    def test_upgrade_and_rollback_restore_previous_owned_version(self):
        install_project(self.root, self.bundle, apply=True)
        target = self.root / ".codex/agents/code_reviewer.toml"
        old = target.read_bytes()
        source = self.bundle / "assets/agents/code_reviewer.toml"
        source.write_bytes(source.read_bytes() + b"\n# new reviewed version\n")
        install_project(self.root, self.bundle, apply=True)
        self.assertNotEqual(target.read_bytes(), old)
        self.assertFalse(rollback_project(self.root)["applied"])
        rollback_project(self.root, apply=True)
        self.assertEqual(target.read_bytes(), old)
        rollback_project(self.root, apply=True)
        self.assertFalse(target.exists())

    def test_uninstall_preserves_user_edits_and_keeps_private_receipts_ignored(self):
        install_project(self.root, self.bundle, apply=True)
        target = self.root / ".codex/agents/code_reviewer.toml"
        target.write_text("# my edits\n")
        result = uninstall_project(self.root, apply=True)
        self.assertEqual(result["status"], "preserved_edits")
        self.assertIn(".codex/agents/code_reviewer.toml", result["preserved"])
        self.assertEqual(target.read_text(), "# my edits\n")
        self.assertIn("/.cep/", (self.root / ".gitignore").read_text())
        self.assertEqual((self.root / ".cep/.gitignore").read_text(), "*\n")

    def test_rollback_with_user_edits_is_atomic_conflict(self):
        install_project(self.root, self.bundle, apply=True)
        target = self.root / ".codex/agents/code_reviewer.toml"
        target.write_text("# keep this\n")
        result = rollback_project(self.root, apply=True)
        self.assertEqual(result["status"], "conflict")
        self.assertTrue((self.root / "engineering-platform.toml").exists())
        self.assertEqual(target.read_text(), "# keep this\n")

    def test_selected_technology_adds_only_its_roles(self):
        self.write(
            "engineering-platform.toml",
            'schema_version=1\npacks=["go"]\nroles=["code_reviewer"]\nrepositories=["."]\n',
        )
        result = install_project(self.root, self.bundle, apply=True)
        self.assertEqual(
            result["roles"], ["code_reviewer", "go_engineer", "test_runner"]
        )
        self.assertFalse((self.root / ".codex/agents/fastapi_engineer.toml").exists())
        self.assertTrue((self.root / ".codex/agents/go_engineer.toml").exists())

    def test_project_disabled_plugin_is_preserved(self):
        config = self.write(
            ".codex/config.toml",
            '[plugins."codex-engineering-platform@codex-engineering-platform"]\nenabled=false\n',
        )
        with self.assertRaises(InstallError):
            install_project(self.root, self.bundle, apply=True)
        self.assertIn("false", config.read_text())
        self.assertFalse((self.root / ".cep").exists())

    def test_noop_removal_does_not_create_project_files(self):
        rollback_project(self.root, apply=True)
        uninstall_project(self.root, apply=True)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_later_ignore_negation_cannot_expose_private_receipts(self):
        self.write(".gitignore", "/.cep/\n!/.cep/\n!/.cep/**\n")
        install_project(self.root, self.bundle, apply=True)
        self.assertTrue(
            (self.root / ".gitignore").read_text().rstrip().endswith("/.cep/")
        )

    def test_invalid_receipt_is_reported_as_install_error(self):
        self.write(".cep/install-state.json", "[]")
        with self.assertRaises(InstallError):
            install_project(self.root, self.bundle)

    def test_external_pack_and_agent_install_without_core_or_bundle_edits(self):
        pack = json.loads((self.bundle / "packs/go/pack.json").read_text())
        pack.update(id="local-go", roles=["local_go_engineer"])
        self.write("technology-packs/local-go/pack.json", json.dumps(pack))
        self.write(
            "technology-packs/local-go/agents/local_go_engineer.toml",
            'name="local_go_engineer"\ndescription="Project Go conventions"\ndeveloper_instructions="Use this project convention."\n',
        )
        self.write(
            "engineering-platform.toml",
            'schema_version=1\npacks=["local-go"]\npack_paths=["technology-packs"]\nroles=[]\nrepositories=["."]\n',
        )
        result = install_project(self.root, self.bundle, apply=True)
        self.assertEqual(result["roles"], ["local_go_engineer"])
        self.assertTrue((self.root / ".codex/agents/local_go_engineer.toml").exists())
        self.assertFalse(
            (self.bundle / "assets/agents/local_go_engineer.toml").exists()
        )

    def test_symlinked_project_control_paths_cannot_escape(self):
        for name in (".codex", ".cep"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as outside:
                link = self.root / name
                link.symlink_to(outside, target_is_directory=True)
                try:
                    with self.assertRaises((InstallError, ProjectError)):
                        install_project(self.root, self.bundle, apply=True)
                    self.assertEqual(list(Path(outside).iterdir()), [])
                finally:
                    link.unlink()

    def test_symlinked_bundle_agent_is_not_copied(self):
        source = self.bundle / "assets/agents/code_reviewer.toml"
        source.unlink()
        source.symlink_to(BUNDLE / "assets/agents/code_reviewer.toml")
        with self.assertRaises((InstallError, ProjectError)):
            install_project(self.root, self.bundle)

    def test_interrupted_install_recovers_without_false_success(self):
        original = _Tree.write
        writes = []

        def fail_after_first_asset(tree, path, data):
            if path.startswith(".codex/agents/"):
                if writes:
                    raise OSError("simulated abrupt write failure")
                writes.append(path)
            return original(tree, path, data)

        with patch.object(_Tree, "write", fail_after_first_asset):
            with self.assertRaises(OSError):
                install_project(self.root, self.bundle, apply=True)
        with self.assertRaisesRegex(InstallError, "interrupted"):
            install_project(self.root, self.bundle)
        result = rollback_project(self.root, apply=True)
        self.assertEqual(result["status"], "rolled_back")
        self.assertFalse((self.root / "engineering-platform.toml").exists())
        self.assertFalse((self.root / writes[0]).exists())
        self.assertEqual(
            install_project(self.root, self.bundle, apply=True)["status"], "installed"
        )

    def test_tampered_receipt_cannot_restore_outside_managed_paths(self):
        install_project(self.root, self.bundle, apply=True)
        path = self.root / ".cep/install-state.json"
        state = json.loads(path.read_text())
        state["history"][-1]["changes"][0]["path"] = "../outside"
        path.write_text(json.dumps(state))
        with self.assertRaises(InstallError):
            rollback_project(self.root, apply=True)


class PluginPackageTests(unittest.TestCase):
    def test_portable_manifest_has_onboarding_and_no_hooks_or_external_accounts(self):
        manifest = json.loads((BUNDLE / "plugin.json").read_text())
        self.assertEqual(
            manifest["$schema"],
            "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        )
        extension = manifest["extensions"]["com.openai"]
        onboarding = BUNDLE / extension["onboardingSkill"]
        self.assertTrue(onboarding.is_file())
        self.assertNotIn("hooks", extension)
        self.assertFalse((BUNDLE / "hooks").exists())
        self.assertFalse((BUNDLE / "mcp.json").exists())
        self.assertEqual(len(list((BUNDLE / "skills").glob("*/SKILL.md"))), 22)

    def test_profiles_use_current_required_fields_without_fake_permission_overrides(
        self,
    ):
        for path in (BUNDLE / "assets/agents").glob("*.toml"):
            with self.subTest(path=path.name):
                profile = tomllib.loads(path.read_text())
                for field in ("name", "description", "developer_instructions"):
                    self.assertTrue(profile[field])
                self.assertEqual(profile["name"], path.stem)
                self.assertFalse(
                    set(profile)
                    & {
                        "sandbox_mode",
                        "approval_policy",
                        "mcp_servers",
                        "model_provider",
                    }
                )


if __name__ == "__main__":
    unittest.main()
