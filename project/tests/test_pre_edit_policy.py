import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/'.codex/hooks/pre_edit_policy.py'
s=importlib.util.spec_from_file_location('policy_edit',p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

class GuardPatchTests(unittest.TestCase):
    def test_patch_policy_denied(self):
        patch='*** Begin Patch\n*** Update File: .codex/hooks.json\n@@\n*** End Patch'
        self.assertEqual(m.blocked_patch(patch),['.codex/hooks.json'])
    def test_patch_regular_allowed(self):
        patch='*** Begin Patch\n*** Update File: backend/main.py\n@@\n*** End Patch'
        self.assertEqual(m.blocked_patch(patch),[])
    def test_move_into_policy_path(self):
        patch='*** Begin Patch\n*** Update File: notes/normal.md\n*** Move to: .github/CODEOWNERS\n*** End Patch'
        self.assertEqual(m.blocked_patch(patch),['.github/CODEOWNERS'])
    def test_hidden_policy_path(self):
        self.assertTrue(m.is_protected('./.github/workflows/quality.yml'))
    def test_readme_not_blocked(self):
        self.assertFalse(m.is_protected('docs/readme.md'))
    def test_traversal(self):
        self.assertTrue(m.is_protected('../evil'))

if __name__=='__main__': unittest.main()
