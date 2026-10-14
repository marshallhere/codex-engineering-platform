import tempfile
from pathlib import Path
import unittest
import sys
import subprocess

from cep.demo import bootstrap_demo, run_demo_gate
from cep.sandbox import NativeSandbox


GOOD = """import argparse,json,sys
from decimal import Decimal
from pathlib import Path
def encode(value):
 stack=[('value',value)];output=[]
 while stack:
  kind,v=stack.pop()
  if kind=='text': output.append(v)
  elif isinstance(v,Decimal): output.append(str(v))
  elif isinstance(v,(list,dict)):
   tokens=[('text','[' if isinstance(v,list) else '{')]
   pairs=list(enumerate(v)) if isinstance(v,list) else list(v.items())
   for i,(k,item) in enumerate(pairs):
    if i: tokens.append(('text',','))
    if isinstance(v,dict): tokens.append(('text',json.dumps(k)+':'))
    tokens.append(('value',item))
   tokens.append(('text',']' if isinstance(v,list) else '}'));stack.extend(reversed(tokens))
  else: output.append(json.dumps(v,allow_nan=False))
 return ''.join(output)
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

    @unittest.skipUnless(sys.platform == "darwin", "macOS native fixture isolation")
    def test_grader_inputs_are_readable_but_not_writable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            repo = bootstrap_demo(root / "project")
            fixtures, scratch = root / "fixtures", root / "worker"
            fixtures.mkdir()
            scratch.mkdir()
            original = fixtures / "input.json"
            original.write_text("unchanged")
            code = f"from pathlib import Path; p=Path({str(original)!r}); print(p.read_text()); p.write_text('changed')"
            result = NativeSandbox().run(
                [sys.executable, "-I", "-c", code],
                repo,
                scratch,
                5,
                readable=(fixtures,),
            )
            self.assertEqual(result["stdout"].strip(), "unchanged")
            self.assertIn("PermissionError", result["stderr"])
            self.assertEqual(original.read_text(), "unchanged")

    @unittest.skipUnless(sys.platform == "darwin", "macOS native process isolation")
    def test_worker_cannot_signal_an_external_process(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            repo, scratch = root / "repo", root / "scratch"
            repo.mkdir()
            scratch.mkdir()
            target = subprocess.Popen(
                [sys.executable, "-I", "-c", "import time; time.sleep(20)"]
            )
            try:
                result = NativeSandbox().run(
                    [
                        sys.executable,
                        "-I",
                        "-c",
                        f"import os,signal; os.kill({target.pid},signal.SIGTERM)",
                    ],
                    repo,
                    scratch,
                    5,
                )
                self.assertIn("PermissionError", result["stderr"])
                self.assertIsNone(target.poll())
            finally:
                if target.poll() is None:
                    target.terminate()
                target.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
