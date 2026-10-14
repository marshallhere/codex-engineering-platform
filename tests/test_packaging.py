"""CEP-SETUP: distributions carry exact assets without local file discovery."""

import json
from pathlib import Path
import runpy
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / "setup.py"))


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "packaging").mkdir()
        (self.root / "plugin").mkdir()
        (self.root / "examples").mkdir()
        (self.root / "plugin/plugin.json").write_text("{}\n")
        (self.root / "examples/demo.py").write_text("print('demo')\n")
        self.manifest = {
            "schema_version": 1,
            "groups": [
                {"source": "plugin", "destination": "bundle", "files": ["plugin.json"]},
                {"source": "examples", "destination": "fixtures", "files": ["demo.py"]},
            ],
        }
        self.save()

    def save(self):
        (self.root / "packaging/assets.json").write_text(json.dumps(self.manifest))

    def test_distribution_manifests_cover_canonical_assets_and_entrypoints(self):
        assets = HELPERS["collect_assets"](ROOT)
        includes = {
            line.removeprefix("include ")
            for line in (ROOT / "MANIFEST.in").read_text().splitlines()
            if line.startswith("include ")
        }
        for source, _ in assets:
            self.assertIn(source.relative_to(ROOT).as_posix(), includes)
        destinations = {target.as_posix() for _, target in assets}
        for required in (
            "cep/bundle/plugin.json",
            "cep/bundle/.codex-plugin/plugin.json",
            "cep/bundle/packs/python/pack.json",
            "cep/bundle/packs/go/pack.json",
            "cep/bundle/skills/setup/SKILL.md",
            "cep/fixtures/python-task-cli/task_cli.py",
            "cep/fixtures/go-pack/go.mod",
        ):
            self.assertIn(required, destinations)
        for directory in ("plugin", "examples"):
            canonical = {
                path.relative_to(ROOT).as_posix()
                for path in (ROOT / directory).rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix not in {".pyc", ".pyo"}
                and path.name != ".DS_Store"
            }
            listed = {
                source.relative_to(ROOT).as_posix()
                for source, _ in assets
                if source.relative_to(ROOT).parts[0] == directory
            }
            self.assertEqual(
                listed,
                canonical,
                "Explicitly review new or removed distribution assets",
            )

    def test_copy_excludes_unlisted_private_files_and_removes_stale_assets(self):
        (self.root / "plugin/private-binding.json").write_text("private fixture\n")
        output = self.root / "build"
        stale = output / "cep/bundle/stale.txt"
        stale.parent.mkdir(parents=True)
        stale.write_text("old fixture\n")
        HELPERS["copy_assets"](self.root, output)
        self.assertFalse(stale.exists())
        self.assertFalse((output / "cep/bundle/private-binding.json").exists())
        self.assertEqual(
            (output / "cep/fixtures/demo.py").read_text(), "print('demo')\n"
        )

    def test_missing_symlinked_and_traversal_assets_fail_closed(self):
        for bad in ("../private", "missing.json", "/absolute.json", "./plugin.json"):
            with self.subTest(path=bad):
                self.manifest["groups"][0]["files"] = [bad]
                self.save()
                with self.assertRaises(ValueError):
                    HELPERS["collect_assets"](self.root)
        self.manifest["groups"][0]["files"] = ["linked.json"]
        self.save()
        (self.root / "plugin/linked.json").symlink_to(self.root / "plugin/plugin.json")
        with self.assertRaises(ValueError):
            HELPERS["collect_assets"](self.root)

    def test_symlinked_asset_parent_is_rejected(self):
        (self.root / "plugin/nested").symlink_to(
            self.root / "examples", target_is_directory=True
        )
        self.manifest["groups"][0]["files"] = ["nested/demo.py"]
        self.save()
        with self.assertRaises(ValueError):
            HELPERS["collect_assets"](self.root)


if __name__ == "__main__":
    unittest.main()
