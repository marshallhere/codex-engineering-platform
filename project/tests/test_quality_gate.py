import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

P = Path(__file__).resolve().parents[1] / "scripts/quality_gate.py"
spec = importlib.util.spec_from_file_location("qa_gate", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class QualityTests(unittest.TestCase):
    def test_missing_config_fails(self):
        self.assertEqual(mod.run(Path('/tmp/codex-kit-definitely-missing-gates.json'), 'pr'), 2)

    def test_empty_stage_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'gates.json'
            path.write_text(json.dumps({'stages': {'pr': []}}))
            self.assertEqual(mod.run(path, 'pr'), 2)

    def test_simple_success(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'gates.json'
            path.write_text(json.dumps({'stages': {'pr': [{'id': 'pass', 'argv': ['python3', '-c', 'print(1)']}]}}))
            self.assertEqual(mod.run(path, 'pr'), 0)

    def test_failure_not_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'gates.json'
            path.write_text(json.dumps({'stages': {'pr': [{'id': 'fail', 'argv': ['python3', '-c', 'raise SystemExit(12)']}]}}))
            self.assertEqual(mod.run(path, 'pr'), 1)

    def test_cwd_escape_rejected(self):
        with self.assertRaises(ValueError):
            mod.check_within_repo('../../')


if __name__ == "__main__":
    unittest.main()
