"""Deterministic control-plane tests; NO real Codex sessions are started."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('runner', Path(__file__).resolve().parents[1] / 'runner.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'; self.repo.mkdir()
        subprocess.run(['git','init','-q','-b','feature/new','--',str(self.repo)],check=True)
        subprocess.run(['git','-C',str(self.repo),'config','user.email','example@example.com'],check=True)
        subprocess.run(['git','-C',str(self.repo),'config','user.name','Test'],check=True)
        self.change = self.repo/'openspec'/'changes'/'sample'; self.change.mkdir(parents=True)
        (self.change/'tasks.md').write_text('- [x] Implement feature\n')
        subprocess.run(['git','-C',str(self.repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(self.repo),'commit','-q','-m','baseline'],check=True)
        self.policy = self.root / 'policy.json'
        self.policy.write_text(json.dumps({'max_iterations':8,'max_minutes':5,'max_stagnant':3,
                             'checks':[{'id':k, 'kind':k,'argv':['python3','-c','print(1)']}
                                       for k in ('spec','tests','security','quality')]}))
        self.state = self.root / 'state'
        self.default_checks = patch.object(runner, 'run_checks', side_effect=lambda repo, policy: [
            {'id': k, 'kind': k, 'status': 'PASS', 'exit_code': 0} for k in ('spec','tests','security','quality')])
        self.default_checks.start()
        self.addCleanup(self.default_checks.stop)

    def test_success_requires_work_and_independent_review_and_polish(self):
        stages=[]
        def agent(repo, state, phase, prompt, timeout):
            stages.append(phase)
            if phase == 'review':
                return {'phase':'review','verdict':'PASS','blocking_findings':[], 'summary':'ok'}
            return {'phase':phase,'summary':'ok','remaining_work':[]}
        with patch.object(runner,'invoke_codex',side_effect=agent):
            r=runner.run_loop(self.repo, self.policy, self.state,'sample')
        self.assertEqual(r['status'],'READY')
        self.assertEqual(stages,['implement','review','polish','review'])

    def test_repair_after_failed_test(self):
        phases=[]
        calls=[0]
        def checks(repo,policy):
            calls[0]+=1
            status='FAIL' if calls[0]==1 else 'PASS'
            return [{'id':'tests','kind':'tests','status':status,'exit_code':1 if calls[0]==1 else 0}]
        def agent(repo,state,phase,prompt,timeout):
            phases.append(phase)
            return ({'phase':'review','verdict':'PASS','summary':'ok','blocking_findings':[]}
                    if phase=='review' else {'phase':phase,'summary':'ok','remaining_work':[]})
        with patch.object(runner,'invoke_codex',side_effect=agent),patch.object(runner,'run_checks',side_effect=checks):
            r=runner.run_loop(self.repo,self.policy,self.state,'sample')
        self.assertEqual(r['status'],'READY')
        self.assertEqual(phases[:3],['implement','implement','review'])

    def test_incomplete_tasks_cannot_be_ready(self):
        (self.change/'tasks.md').write_text('- [x] Setup\n- [ ] Incomplete behavior\n')
        subprocess.run(['git','-C',str(self.repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(self.repo),'commit','-q','-m','test incomplete state'],check=True)
        with patch.object(runner,'invoke_codex',return_value={'phase':'implement','summary':'done','remaining_work':[]}):
            r=runner.run_loop(self.repo,self.policy,self.state,'sample')
        self.assertEqual(r['status'],'BLOCKED')
        self.assertIn('OpenSpec task-completion',r['last_evidence']['failed_checks'])

    def test_policy_cannot_live_in_agent_workspace(self):
        p=self.repo/'policy.json'; p.write_text(self.policy.read_text())
        with self.assertRaisesRegex(ValueError,'OUTSIDE'):
            runner.load_policy(p,self.repo)

    def test_requires_real_mandatory_gate_kinds(self):
        p=json.loads(self.policy.read_text()); p['checks']=[p['checks'][0]]
        self.policy.write_text(json.dumps(p))
        with self.assertRaises(ValueError):
            runner.load_policy(self.policy,self.repo)

    def test_protected_branch_fails_closed(self):
        subprocess.run(['git','-C',str(self.repo),'branch','-m','main'],check=True)
        with self.assertRaisesRegex(ValueError,'protected branch'):
            runner.run_loop(self.repo,self.policy,self.state,'sample')

    def test_requires_clean_worktree_for_new_run(self):
        (self.change/'tasks.md').write_text('dirty')
        with self.assertRaisesRegex(ValueError,'clean worktree'):
            runner.run_loop(self.repo,self.policy,self.state,'sample')

    def test_requires_external_state_dir(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            runner.run_loop(self.repo,self.policy,self.repo/'state','sample')

    def test_stagnation_stops_instead_of_infinite_loop(self):
        r=runner.new_state('sample')
        policy={'max_stagnant':2, 'checks':[]}
        def failing_checks(repo,policy):
            return [{'id':'tests','kind':'tests','status':'FAIL','exit_code':1}]
        with patch.object(runner,'invoke_codex',return_value={'phase':'implement','summary':'nothing changed','remaining_work':['bug']}),patch.object(runner,'run_checks',side_effect=failing_checks):
            runner.once(self.repo,self.state,r,policy)
            runner.once(self.repo,self.state,r,policy)
            runner.once(self.repo,self.state,r,policy)
        self.assertEqual(r['status'],'BLOCKED')

    def test_review_failure_does_not_complete(self):
        statuses=['FAIL','PASS','PASS']
        phases=[]
        def agent(repo,state,phase,prompt,timeout):
            phases.append(phase)
            if phase=='review':
                verdict=statuses.pop(0)
                return {'phase':'review','verdict':verdict, 'summary':'review',
                        'blocking_findings':[{'severity':'high','file':'app.py','reason':'bad auth'}] if verdict=='FAIL' else []}
            return {'phase':phase,'summary':'work','remaining_work':[]}
        with patch.object(runner,'invoke_codex',side_effect=agent):
            r=runner.run_loop(self.repo,self.policy,self.state,'sample')
        self.assertEqual(r['status'],'READY')
        self.assertEqual(phases,['implement','review','implement','review','polish','review'])

if __name__=='__main__':
    unittest.main()
