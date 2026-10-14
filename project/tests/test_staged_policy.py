import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / "scripts/staged_policy.py"
spec = importlib.util.spec_from_file_location("staged_policy", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class StagedPolicyTests(unittest.TestCase):
    def test_sensitive_paths(self):
        for path in (".env", ".env.local", "config/prod.pem", "infra/service-account.json", "id_ed25519"):
            with self.subTest(path=path):
                self.assertTrue(mod.path_sensitive(path))

    def test_examples_allowed(self):
        for path in (".env.example", "README.md", "src/main.py", "demo.env.template"):
            with self.subTest(path=path):
                self.assertFalse(mod.path_sensitive(path))


if __name__ == "__main__":
    unittest.main()
