#!/usr/bin/env python3
"""Run explicit repository gates, fail closed, optionally export redacted machine-readable evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def check_within_repo(path: str, must_exist: bool = True) -> Path:
    folder = (ROOT / path).resolve()
    try:
        folder.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f'cwd escapes repo: {path}') from exc
    if must_exist and not folder.is_dir():
        raise ValueError(f'cwd does not exist: {path}')
    return folder


def validate_command(entry, dry_run: bool = False):
    if not isinstance(entry, dict):
        raise ValueError('gate entries must be objects')
    argv = entry.get('argv')
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        raise ValueError(f'gate {entry.get("id", "<unnamed>")} needs non-empty string argv[]')
    if not isinstance(entry.get('id'), str) or not entry['id']:
        raise ValueError('gate needs a non-empty id')
    cwd = check_within_repo(entry.get('cwd', '.'), must_exist=not dry_run)
    timeout = entry.get('timeout_seconds', 900)
    if not isinstance(timeout, int) or not 1 <= timeout <= 7200:
        raise ValueError(f'invalid timeout for {entry["id"]}')
    return argv, cwd, timeout


def git_sha() -> str | None:
    try:
        cmd = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=3)
        return cmd.stdout.strip() if cmd.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def safe_report_path(path: Path) -> Path:
    dest = path.resolve()
    # Reports must live inside the repository; avoid accidentally overwriting arbitrary external files.
    try:
        dest.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError('report path must be inside project repository') from exc
    if dest.suffix != '.json':
        raise ValueError('report path must end in .json')
    return dest


def run(config: Path, stage: str, dry_run: bool = False, report_path: Path | None = None) -> int:
    if report_path is not None:
        try:
            report_path = safe_report_path(report_path)
        except ValueError as exc:
            print(f'BLOCKED: {exc}', file=sys.stderr)
            return 2
    started = datetime.now(timezone.utc).isoformat()
    report = {'schema_version': 1, 'stage': stage, 'git_sha': git_sha(),
              'started_utc': started, 'dry_run': dry_run, 'status': 'BLOCKED',
              'gates': [], 'problems': [], 'notes': 'Evidence records outcomes, not stdout, secrets, approval or proof of reproducibility.'}
    errors = []
    validated = []
    if not config.is_file():
        errors.append(f'missing {config}; configure quality/gates.json')
    else:
        try:
            doc = json.loads(config.read_text(encoding='utf-8'))
            steps = doc.get('stages', {}).get(stage)
            if not isinstance(steps, list) or not steps:
                raise ValueError(f"stage '{stage}' has no configured gates")
            ids = set()
            for entry in steps:
                argv, cwd, timeout = validate_command(entry, dry_run)
                if entry['id'] in ids:
                    raise ValueError(f"duplicate gate id: {entry['id']}")
                ids.add(entry['id'])
                validated.append((argv, cwd, timeout, entry['id']))
        except (json.JSONDecodeError, OSError, ValueError, AttributeError, KeyError, TypeError) as exc:
            errors.append(f'invalid quality gate config: {exc}')

    if not errors:
        for argv, cwd, timeout, name in validated:
            # Never write arguments or child process output to machine-readable report.
            print(f'[{name}] cwd={cwd.relative_to(ROOT)} executable={argv[0]}', flush=True)
            result_entry = {'id': name, 'status': 'NOT_RUN' if dry_run else 'FAILED',
                            'exit_code': None, 'elapsed_seconds': None}
            if not dry_run:
                begin = time.monotonic()
                try:
                    proc = subprocess.run(argv, cwd=cwd, timeout=timeout, check=False)
                    result_entry['exit_code'] = proc.returncode
                    result_entry['status'] = 'PASSED' if proc.returncode == 0 else 'FAILED'
                    if proc.returncode != 0:
                        errors.append(f'{name}: exit {proc.returncode}')
                except (OSError, subprocess.TimeoutExpired) as exc:
                    result_entry['status'] = 'ERROR'
                    errors.append(f'{name}: {type(exc).__name__}')
                result_entry['elapsed_seconds'] = round(time.monotonic() - begin, 3)
            report['gates'].append(result_entry)
    report['problems'] = errors
    report['status'] = 'DRY_RUN' if dry_run and not errors else ('BLOCKED' if errors else 'PASSED')
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    if report_path:
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        except OSError as exc:
            print(f'BLOCKED: could not write evidence report: {exc}', file=sys.stderr)
            return 2
    if errors:
        print('BLOCKED: quality gate: ' + '; '.join(errors), file=sys.stderr)
        return 2 if not validated else 1
    if dry_run:
        print('DRY RUN ONLY — checks not executed; no proof of test coverage or tool availability')
    else:
        print(f'PASS: {stage} gates executed and returned success')
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='quality/gates.json')
    parser.add_argument('--stage', choices=['precommit','pr','release'], default='pr')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--report', help='relative or absolute .json file inside project repository')
    args = parser.parse_args()
    return run((ROOT / args.config).resolve(), args.stage, args.dry_run, Path(args.report) if args.report else None)

if __name__ == '__main__':
    sys.exit(main())
