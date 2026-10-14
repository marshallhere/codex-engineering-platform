import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

p=Path(__file__).resolve().parents[1] / 'scripts/quality_gate.py'
s=importlib.util.spec_from_file_location('quality_gate_v2', p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

class EvidenceTests(unittest.TestCase):
    def test_pass_evidence(self):
        with tempfile.TemporaryDirectory(dir=m.ROOT) as d:
            path=Path(d) / 'gates.json'
            out=Path(d) / 'out.json'
            path.write_text(json.dumps({'stages':{'pr':[{'id':'ok','argv':['python3','-c','print("ok")']}]}}))
            self.assertEqual(m.run(path,'pr',report_path=out),0)
            report=json.loads(out.read_text())
            self.assertEqual(report['status'],'PASSED')
            self.assertEqual(report['gates'][0]['status'],'PASSED')
            self.assertNotIn('argv',report['gates'][0])
    def test_dry_run_is_not_passed(self):
        with tempfile.TemporaryDirectory(dir=m.ROOT) as d:
            path=Path(d) / 'gates.json'
            out=Path(d) / 'out.json'
            path.write_text(json.dumps({'stages':{'pr':[{'id':'not-executed','argv':['missing-tool-x']}]}}))
            self.assertEqual(m.run(path,'pr',dry_run=True,report_path=out),0)
            report=json.loads(out.read_text())
            self.assertEqual(report['status'],'DRY_RUN')
            self.assertEqual(report['gates'][0]['status'],'NOT_RUN')
    def test_report_path_must_be_in_repo(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(m.run(Path('irrelevant'),'pr',report_path=Path(d)/'report.json'),2)

if __name__=='__main__': unittest.main()
