from pathlib import Path
import tempfile
import unittest
from cep.specs import load_change, validate_task_graph


class SpecsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.change = self.root / "openspec/changes/demo"
        (self.change / "specs/tasks").mkdir(parents=True)
        (self.change / "proposal.md").write_text("Task CLI\n")
        (self.change / "tasks.md").write_text("- [ ] DEMO-LIST: implement\n")
        self.spec = self.change / "specs/tasks/spec.md"
        self.spec.write_text(
            "## ADDED Requirements\n### Requirement: DEMO-LIST unfinished tasks\n#### Scenario: Normal input\n- WHEN valid\n- THEN list\n"
        )

    def test_frozen_content_and_checkboxes_not_proof(self):
        first = load_change(self.root, "demo")
        self.assertEqual(first["requirement_ids"], ["DEMO-LIST"])
        self.assertNotIn("accepted", first)
        (self.change / "tasks.md").write_text("- [x] DEMO-LIST: implement\n")
        second = load_change(self.root, "demo")
        self.assertEqual(second["task_ids"], first["task_ids"])
        self.assertNotEqual(second["digest"], first["digest"])

    def test_escape_rejected(self):
        for slug in ("../demo", "/tmp/demo", "demo/other"):
            with self.assertRaises(ValueError):
                load_change(self.root, slug)
        self.spec.unlink()
        self.spec.symlink_to(self.root / "outside.md")
        (self.root / "outside.md").write_text("outside")
        with self.assertRaises(ValueError):
            load_change(self.root, "demo")

    def test_requirements_need_scenarios_and_tasks(self):
        self.spec.write_text("### Requirement: DEMO-LIST unfinished\n")
        with self.assertRaises(ValueError):
            load_change(self.root, "demo")
        self.spec.write_text(
            "### Requirement: DEMO-OTHER unfinished\n#### Scenario: Example\n"
        )
        with self.assertRaises(ValueError):
            load_change(self.root, "demo")

    def test_task_graph(self):
        tasks = [{"id": "review", "depends_on": ["implement"]}, {"id": "implement"}]
        self.assertEqual(validate_task_graph(tasks), ["implement", "review"])
        for invalid in (
            [{"id": "a", "depends_on": ["a"]}],
            [{"id": "a", "depends_on": ["missing"]}],
            [{"id": "a"}, {"id": "a"}],
        ):
            with self.assertRaises(ValueError):
                validate_task_graph(invalid)
