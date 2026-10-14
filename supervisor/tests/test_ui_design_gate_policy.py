import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'runner.py'
spec=importlib.util.spec_from_file_location('design_ui_runner',SCRIPT)
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class UIRunnerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'repo'
        self.root.mkdir()
        self.policy_path=Path(self.tmp.name)/'owner-policy.json'
        self.obj={'max_iterations':2,'max_minutes':4,'max_stagnant':2,
                  'require_ui_gate':True,
                  'checks':[{'id':k,'kind':k,'argv':['true']} for k in ('spec','tests','security','quality')]}

    def tearDown(self):self.tmp.cleanup()

    def save(self):self.policy_path.write_text(json.dumps(self.obj))

    def test_reject_missing_ui_gate(self):
        self.save()
        with self.assertRaisesRegex(ValueError,'UI policy missing required checks'):
            runner.load_policy(self.policy_path,self.root)

    def test_accept_trusted_ui_gate(self):
        self.obj['checks'].extend([{'id':k+'-check','kind':k,'argv':['true']} for k in ('design','storybook','browser','accessibility')])
        self.save()
        self.assertTrue(runner.load_policy(self.policy_path,self.root)['require_ui_gate'])

    def test_static_design_check_alone_is_insufficient(self):
        self.obj['checks'].append({'id':'design','kind':'design','argv':['true']})
        self.save()
        with self.assertRaisesRegex(ValueError,'accessibility'):
            runner.load_policy(self.policy_path,self.root)

    def test_reject_invalid_ui_flag(self):
        self.obj['require_ui_gate']='yes'
        self.save()
        with self.assertRaisesRegex(ValueError,'boolean'):
            runner.load_policy(self.policy_path,self.root)

if __name__=='__main__':unittest.main()
