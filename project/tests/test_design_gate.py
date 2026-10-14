import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'design_gate.py'
spec = importlib.util.spec_from_file_location('design_gate', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DesignGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = self.root / 'src/components/ui'
        self.base.mkdir(parents=True)
        (self.root / 'quality').mkdir()
        self.policy_data = {
            'schema_version': 1,
            'component_roots': ['src/components/ui/'],
            'ui_roots': ['src/'],
            'ignored_paths': ['src/generated/'],
            'token_files': ['src/styles/tokens.css'],
            'component_catalog': 'docs/design/component-catalog.json',
            'require_catalog_entry_for_changed_components': True,
            'require_story_for_changed_components': True,
            'reject_literal_colors_in_changed_ui': True,
            'prohibited_baseline_roots': ['tests/visual/snapshots/'],
            'baseline_authorization': 'deny_by_default',
        }
        self.write_catalog([])
        self.write_policy()

    def tearDown(self):
        self.tmp.cleanup()

    def write_policy(self):
        p = self.root / 'quality/design-policy.json'
        p.write_text(json.dumps(self.policy_data), encoding='utf-8')
        self.policy = module.load_policy(self.root, p)

    def write_catalog(self, components):
        p = self.root / 'docs/design/component-catalog.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'components': components}), encoding='utf-8')

    def component(self, body='export function Button(){return <button className="bg-primary">Go</button>}'):
        p = self.base / 'Button.tsx'
        p.write_text(body, encoding='utf-8')
        return 'src/components/ui/Button.tsx'

    def register_component(self):
        self.write_catalog([{'name': 'Button', 'path': 'src/components/ui/Button.tsx', 'story': 'src/components/ui/Button.stories.tsx'}])
        (self.base / 'Button.stories.tsx').write_text('export const Default = {};', encoding='utf-8')

    def test_reject_missing_catalog_entry(self):
        f = self.component()
        result = module.check_design(self.root, self.policy, [f])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertTrue(any('catalog entry' in x for x in result['errors']))

    def test_valid_catalog_and_story_pass(self):
        f = self.component()
        self.register_component()
        self.assertEqual(module.check_design(self.root,self.policy,[f])['status'], 'PASS')

    def test_missing_story_fails(self):
        f = self.component()
        self.register_component()
        (self.base / 'Button.stories.tsx').unlink()
        self.assertTrue(any('missing' in x for x in module.check_design(self.root,self.policy,[f])['errors']))

    def test_literal_hex_blocked(self):
        f = self.component('export const Button = () => <button style={{ color: "#ff0000" }}>Hi</button>;')
        self.register_component()
        errors=module.check_design(self.root,self.policy,[f])['errors']
        self.assertTrue(any('literal' in x for x in errors))

    def test_tailwind_direct_palette_blocked(self):
        f = self.component('export const Button = () => <button className="text-red-500">Hi</button>;')
        self.register_component()
        self.assertTrue(any('literal' in x for x in module.check_design(self.root,self.policy,[f])['errors']))

    def test_token_file_exempt(self):
        p=self.root/'src/styles/tokens.css';p.parent.mkdir(exist_ok=True)
        p.write_text(':root { --primary: #334455; }',encoding='utf-8')
        self.assertEqual(module.check_design(self.root,self.policy,['src/styles/tokens.css'])['status'],'PASS')

    def test_unapproved_baseline_blocked(self):
        result=module.check_design(self.root,self.policy,['tests/visual/snapshots/home.png'])
        self.assertEqual(result['status'],'BLOCKED')
        self.assertIn('not approved', result['errors'][0])

    def test_external_policy_allows_specifically_named_baseline(self):
        self.policy_data['approved_baseline_paths']=['tests/visual/snapshots/home.png']
        self.write_policy()
        result=module.check_design(self.root,self.policy,['tests/visual/snapshots/home.png'])
        self.assertEqual(result['status'],'PASS')

    def test_path_traversal_blocked(self):
        r=module.check_design(self.root,self.policy,['../../.ssh/id_rsa'])
        self.assertEqual(r['status'],'BLOCKED')

    def test_symlink_escape_blocked(self):
        other=Path(self.tmp.name).parent
        (self.root/'src/out').symlink_to(other, target_is_directory=True)
        r=module.check_design(self.root,self.policy,['src/out/private.tsx'])
        self.assertEqual(r['status'],'BLOCKED')

    def test_ignored_generated_ui(self):
        p=self.root/'src/generated/Button.tsx';p.parent.mkdir(exist_ok=True)
        p.write_text('const c = "#ff0000"',encoding='utf-8')
        r=module.check_design(self.root,self.policy,['src/generated/Button.tsx'])
        self.assertEqual(r['status'],'PASS')

    def test_nonui_does_not_require_catalog(self):
        r=module.check_design(self.root,self.policy,['README.md'])
        self.assertEqual(r['status'],'PASS')

    def test_reject_duplicate_catalog_entries(self):
        f=self.component()
        entry={'path':f,'story':'src/components/ui/Button.stories.tsx'}
        self.write_catalog([entry,entry])
        r=module.check_design(self.root,self.policy,[f])
        self.assertEqual(r['status'],'BLOCKED')
        self.assertIn('duplicate',r['errors'][0])

    def test_policy_reject_absolute_dirs(self):
        self.policy_data['component_roots']=['/tmp']
        with self.assertRaises(ValueError):self.write_policy()


if __name__ == '__main__': unittest.main()
