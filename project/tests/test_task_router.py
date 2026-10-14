import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1] / 'scripts/task_router.py'
s=importlib.util.spec_from_file_location('task_router', p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

class RouterTests(unittest.TestCase):
    def test_unknown_scope_is_not_low_risk(self):
        self.assertEqual(m.route([], [])['risk'], 'moderate')
    def test_docs_low_risk(self):
        self.assertEqual(m.route(['docs/user-guide.md'], [])['risk'], 'low')
    def test_auth_is_high(self):
        res=m.route(['backend/src/auth/login.py'], [])
        self.assertEqual(res['risk'], 'high')
        self.assertTrue(res['requires_human_review'])
        self.assertIn('security_reviewer', res['roles_to_consider'])
    def test_policy_change_critical(self):
        self.assertEqual(m.route(['.codex/hooks.json'], [])['risk'], 'critical')
    def test_explicit_flag_overrides_path(self):
        self.assertEqual(m.route(['docs/readme.md'], ['destructive-migration'])['risk'], 'critical')

if __name__ == '__main__': unittest.main()
