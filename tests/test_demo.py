import tempfile
from pathlib import Path
import unittest

from cep.demo import bootstrap_demo, run_demo_gate
from cep.sandbox import NativeSandbox


GOOD = """import argparse,json,sys
from decimal import Decimal
from pathlib import Path
def encode(v):
 if isinstance(v,Decimal): return str(v)
 if isinstance(v,list): return '['+','.join(encode(x) for x in v)+']'
 if isinstance(v,dict): return '{'+','.join(json.dumps(k)+':'+encode(x) for k,x in v.items())+'}'
 return json.dumps(v,allow_nan=False)
def bad_constant(v): raise ValueError('invalid JSON')
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--file',required=True);a=p.parse_args()
try:
 root=Path(a.root).resolve(strict=True); rel=Path(a.file)
 if not root.is_dir() or rel.is_absolute() or '..' in rel.parts: raise ValueError('invalid path')
 file=(root/rel).resolve(strict=True)
 if not file.is_relative_to(root): raise ValueError('path escape')
 obj=json.loads(file.read_text(),parse_float=Decimal,parse_int=Decimal,parse_constant=bad_constant)
 if not isinstance(obj,dict) or not isinstance(obj.get('tasks'),list): raise ValueError('invalid inventory')
 for t in obj['tasks']:
  if not isinstance(t,dict) or not isinstance(t.get('id'),str) or not t['id'] or not isinstance(t.get('title'),str) or type(t.get('done')) is not bool: raise ValueError('invalid task')
 print(encode({'tasks':[t for t in obj['tasks'] if not t['done']]}))
except (OSError,ValueError):
 print('Invalid inventory or path',file=sys.stderr);raise SystemExit(2)
"""


class DemoTests(unittest.TestCase):
    def test_seed_fails_functional_and_security_checks(self):
        with tempfile.TemporaryDirectory() as d:
            repo = bootstrap_demo(Path(d) / "project")
            self.assertTrue(run_demo_gate(repo, "spec")["passed"])
            self.assertFalse(run_demo_gate(repo, "tests")["passed"])
            self.assertFalse(run_demo_gate(repo, "security")["passed"])

    def test_actual_black_box_requirements(self):
        with tempfile.TemporaryDirectory() as d:
            repo = bootstrap_demo(Path(d) / "project")
            (repo / "task_cli.py").write_text(GOOD)
            for kind in ("spec", "tests", "security", "quality"):
                with self.subTest(kind=kind):
                    self.assertTrue(run_demo_gate(repo, kind)["passed"])

    @unittest.skipUnless(
        __import__("sys").platform == "darwin", "macOS native qualification"
    )
    def test_native_restrictions_and_fork_denial(self):
        self.assertTrue(NativeSandbox().qualify()["passed"])


if __name__ == "__main__":
    unittest.main()
