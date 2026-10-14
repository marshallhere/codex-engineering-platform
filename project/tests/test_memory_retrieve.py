import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

p=Path(__file__).resolve().parents[1] / 'scripts/memory_retrieve.py'
s=importlib.util.spec_from_file_location('memory_retrieve', p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

class MemoryTests(unittest.TestCase):
    def put(self, records):
        tmp=tempfile.TemporaryDirectory()
        path=Path(tmp.name) / 'approved.jsonl'
        path.write_text('\n'.join(json.dumps(x) for x in records))
        self.addCleanup(tmp.cleanup)
        return path
    def sample(self, **kwargs):
        result=dict(id='L1',title='AsyncSession ownership',rule='Avoid sharing AsyncSession between tasks',evidence='regression:test_1',reviewed_at='2026-10-14',status='approved',keywords=['sqlalchemy'],paths=[])
        result.update(kwargs)
        return result
    def test_only_approved_lessons(self):
        path=self.put([self.sample(status='proposed'), self.sample(id='L2')])
        self.assertEqual([x['id'] for x in m.retrieve('sqlalchemy',[],path)], ['L2'])
    def test_scoped_lesson_requires_path(self):
        path=self.put([self.sample(paths=['backend/**/*.py'])])
        self.assertEqual(m.retrieve('AsyncSession',[],path), [])
        self.assertEqual(m.retrieve('AsyncSession',['backend/src/foo.py'],path)[0]['id'],'L1')
    def test_lexical_relevance(self):
        path=self.put([self.sample()])
        self.assertEqual(m.retrieve('unrelated documentation',[],path), [])
    def test_no_expired_lessons(self):
        path=self.put([self.sample(expires_at='2001-01-01')])
        self.assertEqual(m.retrieve('AsyncSession',[],path), [])
    def test_limit(self):
        path=self.put([self.sample(id=str(i)) for i in range(10)])
        self.assertEqual(len(m.retrieve('AsyncSession', [], path, limit=3)),3)

if __name__=='__main__': unittest.main()
