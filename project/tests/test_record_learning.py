import importlib.util
from pathlib import Path
import tempfile
import unittest

P = Path(__file__).resolve().parents[1] / "scripts/record_learning.py"
spec = importlib.util.spec_from_file_location("record_learning", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class LearningTests(unittest.TestCase):
    def test_proposal_only(self):
        with tempfile.TemporaryDirectory() as d:
            original = mod.PENDING
            try:
                mod.PENDING = Path(d)
                p = mod.record('bug', 'Failed retry', 'request duplicated', 'missing idempotency', 'deduplicate by key', 'repro case XYZ', 'test retry')
                data = p.read_text()
                self.assertIn('PROPOSED', data)
                self.assertIn('Regression test', data)
                self.assertTrue(p.exists())
            finally:
                mod.PENDING = original


if __name__ == "__main__":
    unittest.main()
