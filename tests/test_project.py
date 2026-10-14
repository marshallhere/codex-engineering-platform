"""CEP-SETUP: discovery is bounded, non-executing and workspace-aware."""

from pathlib import Path
import tempfile
import unittest

from cep.project import ProjectError, discover_files, inspect_project


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, data=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def test_eventu_shaped_workspace_preserves_ownership_without_execution(self):
        for name in ("eventu-api", "eventu-frontend", "eventu-tooling"):
            (self.root / name / ".git").mkdir(parents=True)
        self.write("eventu-api/pyproject.toml", "this need not be executed or parsed")
        self.write("eventu-frontend/package.json", "not executable discovery input")
        self.write("eventu-tooling/bin/eventu", "#!/bin/sh\ntouch should-not-exist\n")
        self.write("AGENTS.md", "preserve me")
        self.write("eventu-api/AGENTS.md", "nested instructions")
        report = inspect_project(self.root)
        self.assertTrue(report["multi_repo"])
        self.assertEqual(
            report["repositories"], ["eventu-api", "eventu-frontend", "eventu-tooling"]
        )
        self.assertEqual(report["technology_hints"], ["javascript", "python"])
        self.assertEqual(report["ownership"][0]["path"], "eventu-tooling")
        self.assertIn("eventu-api/AGENTS.md", report["instructions"])
        self.assertFalse((self.root / "should-not-exist").exists())
        self.assertEqual(report["commands_executed"], [])

    def test_symlinks_and_dependency_trees_are_not_scanned(self):
        self.write("node_modules/fake/go.mod")
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, "pyproject.toml").write_text("private")
            (self.root / "external").symlink_to(outside, target_is_directory=True)
            report = inspect_project(self.root)
        self.assertEqual(report["technology_hints"], [])
        self.assertIn("ignored symlink: external", report["warnings"])

    def test_manifest_cannot_point_outside_workspace(self):
        for value in ("../other", "/tmp/other", "a/../../other", "C:\\other"):
            with self.subTest(value=value):
                self.write(
                    "engineering-platform.toml",
                    f"schema_version = 1\nrepositories = [{value!r}]\n",
                )
                with self.assertRaises(ProjectError):
                    inspect_project(self.root)

    def test_explicit_nested_repositories_and_worktree_git_files(self):
        self.write("services/api/.git", "gitdir: /not-read")
        self.write("services/api/go.mod", "module example.invalid/api")
        self.write(
            "engineering-platform.toml",
            'schema_version = 1\nrepositories = ["services/api"]\npacks = ["go"]\n',
        )
        report = inspect_project(self.root)
        self.assertEqual(report["repositories"], ["services/api"])
        self.assertEqual(report["project_manifest"]["packs"], ["go"])

    def test_bounded_discovery_reports_truncation(self):
        for i in range(6):
            self.write(f"file-{i}")
        files, warnings = discover_files(self.root, max_entries=3)
        self.assertEqual(len(files), 3)
        self.assertTrue(any("limit" in warning for warning in warnings))

    def test_symlink_manifest_rejected(self):
        self.write("elsewhere.toml", "schema_version = 1")
        (self.root / "engineering-platform.toml").symlink_to("elsewhere.toml")
        with self.assertRaises(ProjectError):
            inspect_project(self.root)

    def test_unknown_configuration_is_not_echoed_as_discovered_credentials(self):
        self.write(
            "engineering-platform.toml",
            'schema_version=1\nprovider_token="example-token"\n',
        )
        with self.assertRaises(ProjectError) as error:
            inspect_project(self.root)
        self.assertNotIn("example-token", str(error.exception))


if __name__ == "__main__":
    unittest.main()
