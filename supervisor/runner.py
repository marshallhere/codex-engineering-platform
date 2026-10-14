#!/usr/bin/env python3
"""Codex-only autonomous spec/review/repair loop prototype.

NOTE: operator-owned policy and state MUST remain outside the agent-writable repo.
This is not an operating-system security boundary and is not production hardened.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
VALID_KINDS = {'spec', 'tests', 'security', 'quality', 'contracts', 'browser', 'design', 'storybook', 'accessibility', 'other'}
REQUIRED_KINDS = {'spec', 'tests', 'security', 'quality'}
TERMINAL = {'READY', 'BLOCKED'}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, encoding='utf-8', delete=False) as f:
        json.dump(obj, f, indent=2)
        f.write('\n')
        name = f.name
    os.replace(name, path)


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, timeout=15)
    if p.returncode:
        raise ValueError('Not a usable Git checkout, or Git command failed')
    return p.stdout.strip()


def is_under(candidate: Path, parent: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def load_policy(policy_path: Path, repo: Path) -> dict:
    if is_under(policy_path, repo):
        raise ValueError('Trusted policy must be OUTSIDE the agent-writable repository')
    obj = json.loads(policy_path.read_text(encoding='utf-8'))
    for key in ('max_iterations', 'max_minutes', 'max_stagnant'):
        if type(obj.get(key)) is not int or not 1 <= obj[key] <= 10000:
            raise ValueError(f'Invalid policy: {key} must be a positive integer')
    checks = obj.get('checks')
    if not isinstance(checks, list) or len(checks) < 4:
        raise ValueError('Policy must define at least four independent checks')
    kinds, ids = set(), set()
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get('id'), str) or not check['id']:
            raise ValueError('Every check requires id')
        if check['id'] in ids:
            raise ValueError(f'Duplicate check {check["id"]}')
        ids.add(check['id'])
        k = check.get('kind')
        if k not in VALID_KINDS:
            raise ValueError(f'Invalid check kind for {check["id"]}')
        kinds.add(k)
        args = check.get('argv')
        if not isinstance(args, list) or not args or any(type(x) is not str or not x for x in args):
            raise ValueError(f'Check {check["id"]} requires nonempty argv list')
        cwd = (repo / check.get('cwd', '.')).resolve()
        if not is_under(cwd, repo) or not cwd.is_dir():
            raise ValueError(f'Check {check["id"]} cwd missing or outside repository')
        t = check.get('timeout_seconds', 900)
        if type(t) is not int or t < 1 or t > 3600:
            raise ValueError(f'Invalid timeout for {check["id"]}')
    if not REQUIRED_KINDS.issubset(kinds):
        raise ValueError(f'Missing mandatory checks: {sorted(REQUIRED_KINDS - kinds)}')
    if obj.get('require_ui_gate', False) is not False:
        if obj['require_ui_gate'] is not True:
            raise ValueError('require_ui_gate must be a boolean')
        missing_ui = {'design', 'storybook', 'browser', 'accessibility'} - kinds
        if missing_ui:
            raise ValueError(f'UI policy missing required checks: {sorted(missing_ui)}')
    return obj


def check_checkout(repo: Path, state_exists: bool):
    root = Path(git(repo, 'rev-parse', '--show-toplevel')).resolve()
    if root != repo.resolve():
        raise ValueError('Repo must be a Git top-level checkout/worktree')
    branch = git(repo, 'symbolic-ref', '--short', 'HEAD')
    if branch.lower() in {'main', 'master', 'production', 'prod'}:
        raise ValueError('Refusing to modify protected branch: use a dedicated worktree/feature branch')
    if not state_exists and git(repo, 'status', '--porcelain'):
        raise ValueError('Refusing to start with uncommitted changes. Use a clean worktree.')


def fingerprint(repo: Path) -> str:
    """Best-effort progress fingerprint, not a proof that behavior improved."""
    d = hashlib.sha256()
    d.update(subprocess.run(['git','diff','HEAD','--binary'],cwd=repo,capture_output=True,timeout=20,check=True).stdout)
    files = subprocess.run(['git','ls-files','--others','--exclude-standard','-z'],cwd=repo,
                           capture_output=True,timeout=20,check=True).stdout.split(b'\0')
    for bpath in sorted(x for x in files if x):
        d.update(bpath)
        p = repo / os.fsdecode(bpath)
        if p.is_file() and not p.is_symlink():
            size = p.stat().st_size
            d.update(str(size).encode())
            if size <= 2_000_000:
                d.update(hashlib.sha256(p.read_bytes()).digest())
    return d.hexdigest()


def run_checks(repo: Path, policy: dict) -> list[dict]:
    results = []
    for entry in policy['checks']:
        cwd = (repo / entry.get('cwd', '.')).resolve()
        if not is_under(cwd, repo) or not cwd.is_dir():
            results.append({'id':entry['id'], 'kind':entry['kind'], 'status':'ERROR', 'exit_code':None, 'elapsed_seconds':0})
            continue
        start = time.monotonic()
        try:
            # Never use shell=True; capture output and discard it here to avoid storing secrets.
            p = subprocess.run(entry['argv'], cwd=cwd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=entry.get('timeout_seconds', 900),
                               env={k: v for k, v in os.environ.items()
                                    if k in ('PATH','HOME','TMPDIR','LANG','LC_ALL','JAVA_HOME','VIRTUAL_ENV','NODE_ENV')})
            code = p.returncode
            status = 'PASS' if code == 0 else 'FAIL'
        except (OSError, subprocess.TimeoutExpired):
            code, status = None, 'ERROR'
        results.append({'id':entry['id'],'kind':entry['kind'],'status':status,
                        'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,2)})
    return results


def tasks_complete(repo: Path, spec: str) -> tuple[bool, str]:
    task_file = repo / 'openspec' / 'changes' / spec / 'tasks.md'
    if not task_file.is_file():
        return False, 'Missing OpenSpec tasks.md'
    doc = task_file.read_text(encoding='utf-8')
    completed = re.findall(r'^\s*-\s*\[[xX]\]', doc, re.M)
    pending = re.findall(r'^\s*-\s*\[\s\]', doc, re.M)
    if not completed:
        return False, 'No checked completed tasks in tasks.md'
    if pending:
        return False, f'{len(pending)} incomplete OpenSpec tasks'
    return True, 'All OpenSpec tasks checked complete (self-reported; separate tests still required)'


def invoke_codex(repo: Path, state_dir: Path, phase: str, prompt: str, timeout: int) -> dict:
    schema = ROOT / 'schemas' / ('review.json' if phase == 'review' else 'work.json')
    out = state_dir / f'last_{phase}.json'
    cmd = ['codex','exec','--cd',str(repo),'--sandbox',
           'read-only' if phase == 'review' else 'workspace-write',
           '-c','approval_policy="never"','--output-schema',str(schema),
           '--output-last-message',str(out),'--json',prompt]
    try:
        # Codex transcript intentionally not saved by this prototype.
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError('Codex CLI not installed or not on PATH') from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'Codex {phase} execution timed out') from exc
    if p.returncode != 0:
        raise RuntimeError(f'Codex {phase} returned exit code {p.returncode}')
    try:
        result = json.loads(out.read_text(encoding='utf-8'))
        if not isinstance(result, dict) or result.get('phase') != phase:
            raise ValueError('Unexpected structured output phase')
        if phase == 'review':
            if result.get('verdict') not in ('PASS','FAIL'):
                raise ValueError('Missing reviewer verdict')
            if not isinstance(result.get('blocking_findings'), list):
                raise ValueError('Missing blocking findings')
            if result['verdict'] == 'PASS' and result['blocking_findings']:
                raise ValueError('Inconsistent reviewer verdict')
        return result
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f'Invalid {phase} agent result: {exc}') from exc


def phase_prompt(spec: str, phase: str, previous: dict | None, stalled: bool) -> str:
    scope = f'OpenSpec change: {spec}. Apply only to this change and its direct dependencies.'
    common = '''Follow repository AGENTS.md and verified user preferences. Operate autonomously within sandbox.
Never access production, change branch protection, delete production data, modify platform security policy,
weaken tests, bypass scans, or falsely report results. Execute focused tests locally and keep progress in
tracked change artifacts. Delegate bounded independent work to native specialist subagents when useful.
Do not edit the trusted outside-workspace policy. Report only evidence-based completion.
'''
    if phase == 'review':
        return (scope+'\nIndependent read-only review. Verify requirements, change scope, contract compatibility, '
                'security, missing test scenarios, errors, UX/accessibility where applicable, and code quality. '
                'Return PASS only if there are NO material actionable blocking defects. Include file references. '
                'Do not modify files.\n'+common)
    if phase == 'polish':
        return (scope+'\nPerform ONE focused polish pass: simplify unjustified complexity, complete docs, '
                'improve error handling, accessibility, test edges, performance only where evidenced. '
                'Do not broaden scope or churn working code. Changes will be independently re-tested and re-reviewed.\n'+common)
    details = json.dumps(previous or {}, separators=(',',':'))[:6000]
    return (scope+'\nImplement remaining OpenSpec tasks and repair all known blockers. '
            'Read relevant verified lessons and decisions first. Do not mark tasks completed prematurely. '
            'Use specialist subagents with non-overlapping file ownership.\n'+common+
            ('No material repository progress in last cycle: diagnose root cause and change strategy before editing.\n'
             if stalled else '')+'Previous evidence (metadata only): '+details)


def new_state(spec: str) -> dict:
    return {'schema_version':1, 'spec':spec, 'status':'RUNNING', 'phase':'implement',
            'started_utc':utc(), 'started_epoch':time.time(), 'attempts':0,'stagnant':0,'last_fingerprint':None,
            'polish_completed':False,'last_evidence':{},'events':[]}


def once(repo: Path, state_dir: Path, state: dict, policy: dict) -> dict:
    phase = state['phase']
    state['attempts'] += 1
    state['updated_utc'] = utc()
    event = {'attempt':state['attempts'],'phase':phase,'at':utc()}
    try:
        outcome = invoke_codex(repo, state_dir, phase,
                              phase_prompt(state['spec'], phase, state.get('last_evidence'),
                                           state['stagnant'] >= 2),
                              min(policy.get('codex_timeout_seconds', 3600), 7200))
        # Never trust an agent's own PASS without running external checks.
        fp = fingerprint(repo)
        old_fp = state['last_fingerprint']
        if phase != 'review':
            state['stagnant'] = state['stagnant']+1 if old_fp == fp else 0
        state['last_fingerprint'] = fp
        if phase == 'review':
            event['blocking_findings'] = len(outcome['blocking_findings'])
            if outcome['verdict'] != 'PASS':
                state['polish_completed'] = False
                state['phase'] = 'implement'
                state['last_evidence'] = {'review_blockers':outcome['blocking_findings'][:10]}
            elif not state['polish_completed']:
                state['phase'] = 'polish'
                state['last_evidence'] = {'review':'PASS; final polish required'}
            else:
                state['status'] = 'READY'
                state['last_evidence'] = {'review':'PASS', 'checks':'PASS'}
        else:
            checks = run_checks(repo, policy)
            event['checks'] = checks
            failed = [r['id'] for r in checks if r['status'] != 'PASS']
            complete, task_evidence = tasks_complete(repo, state['spec'])
            if not complete:
                failed.append('OpenSpec task-completion')
            state['last_evidence'] = {'failed_checks':failed, 'checks':checks, 'tasks':task_evidence}
            if failed:
                state['phase'] = 'implement'
            else:
                if phase == 'polish':
                    state['polish_completed'] = True
                state['phase'] = 'review'
    except (RuntimeError, ValueError) as exc:
        event['error'] = str(exc)
        state['status'] = 'BLOCKED'
        state['reason'] = str(exc)
    if state['status'] != 'READY' and state['stagnant'] >= policy['max_stagnant']:
        state['status'] = 'BLOCKED'
        state['reason'] = 'No observable repo progress across successive work iterations'
    state['events'].append(event)
    return state


def run_loop(repo: Path, policy_path: Path, state_dir: Path, spec: str) -> dict:
    repo, policy_path, state_dir = repo.resolve(), policy_path.resolve(), state_dir.resolve()
    if is_under(state_dir, repo):
        raise ValueError('Durable supervisor state must be outside the writable repo')
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = state_dir / 'lock'
    with lock.open('w') as h:
        fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = state_dir / 'state.json'
        check_checkout(repo, state_path.exists())
        policy = load_policy(policy_path, repo)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}', spec):
            raise ValueError('OpenSpec change identifier is not a simple slug')
        spec_path = (repo / 'openspec' / 'changes' / spec).resolve()
        if not is_under(spec_path, repo) or not spec_path.is_dir():
            raise ValueError('Requested OpenSpec change directory does not exist')
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if state['spec'] != spec:
                raise ValueError('Cannot reuse state for a different OpenSpec change')
            if state['status'] in TERMINAL:
                return state
        else:
            state = new_state(spec)
            atomic_json(state_path, state)
        if 'started_epoch' not in state:
            raise ValueError('Invalid or obsolete state: missing original start time')
        deadline = float(state['started_epoch']) + policy['max_minutes']*60
        while state['status'] == 'RUNNING':
            if time.time() >= deadline or state['attempts'] >= policy['max_iterations']:
                state['status'] = 'BLOCKED'
                state['reason'] = 'Configured execution time/iteration budget exhausted; incomplete work preserved'
                break
            state = once(repo, state_dir, state, policy)
            atomic_json(state_path, state)
        atomic_json(state_path, state)
        return state


def main() -> int:
    p = argparse.ArgumentParser(description='Prototype autonomous Codex feature loop')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--policy', type=Path, required=True)
    p.add_argument('--state-dir', type=Path, required=True)
    p.add_argument('--spec', required=True, help='OpenSpec change folder name')
    args = p.parse_args()
    try:
        result = run_loop(args.repo, args.policy, args.state_dir, args.spec)
    except (OSError, ValueError, BlockingIOError, json.JSONDecodeError) as exc:
        print('BLOCKED: '+str(exc), file=sys.stderr)
        return 2
    print(json.dumps({'status':result['status'],'attempts':result['attempts'],
                      'last_evidence':result['last_evidence'], 'reason':result.get('reason')}))
    return 0 if result['status'] == 'READY' else 2


if __name__ == '__main__':
    sys.exit(main())
