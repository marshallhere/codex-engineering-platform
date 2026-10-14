#!/usr/bin/env python3
"""Conservative, scope-limited *static* design checks for changed UI files.

This is NOT proof of visual quality, component reuse, accessibility or runtime safety.
For enforceability run this from CI/external supervisor using an owner-controlled policy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
UI_EXTENSIONS = {'.css', '.scss', '.tsx', '.jsx'}
COMPONENT_EXTENSIONS = {'.tsx', '.jsx'}
HEX = re.compile(r'(?<![A-Za-z0-9#])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])')
COLOR_FUNCTIONS = re.compile(r'(?<![\w-])(?:rgba?|hsla?)\s*\(', re.I)
TAILWIND_PALETTES = re.compile(
    r'(?<![\w-])(?:bg|text|border|ring|from|via|to|fill|stroke)-'
    r'(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b'
)


def normalize_relative(value: str) -> str:
    if not isinstance(value, str) or not value or '\x00' in value or '\\' in value:
        raise ValueError('paths must be nonempty POSIX relative strings')
    p = Path(value)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError(f'path must be relative without parent traversal: {value!r}')
    return p.as_posix().lstrip('./')


def in_roots(path: str, roots: list[str]) -> bool:
    return any(path == r.rstrip('/') or path.startswith(r.rstrip('/') + '/') for r in roots)


def inside(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f'path leaves repo (possibly via symlink): {rel}') from exc
    return p


def load_policy(root: Path, path: Path) -> dict:
    # This validator verifies shape; the caller is responsible for trusting its source.
    obj = json.loads(path.read_text(encoding='utf-8'))
    if obj.get('schema_version') != 1:
        raise ValueError('design-policy requires schema_version=1')
    list_fields = (
        'component_roots', 'ui_roots', 'ignored_paths', 'token_files',
        'prohibited_baseline_roots', 'approved_baseline_paths'
    )
    for key in list_fields:
        values = obj.get(key, [])
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            raise ValueError(f'{key} must be a list of paths')
        obj[key] = [normalize_relative(x) for x in values]
    for key in (
        'require_catalog_entry_for_changed_components',
        'require_story_for_changed_components',
        'reject_literal_colors_in_changed_ui'
    ):
        if type(obj.get(key)) is not bool:
            raise ValueError(f'{key} must be boolean')
    if obj.get('baseline_authorization') != 'deny_by_default':
        raise ValueError('Only baseline_authorization=deny_by_default is supported')
    obj['component_catalog'] = normalize_relative(obj.get('component_catalog', 'docs/design/component-catalog.json'))
    inside(root, obj['component_catalog'])
    return obj


def git_changes(root: Path, base: str) -> list[str]:
    if not base or base.startswith('-'):
        raise ValueError('base must be a Git revision, not a flag')
    # diff base to worktree includes tracked uncommitted changes plus committed changes.
    commands = [['git','diff','--name-only','--diff-filter=ACMRD','-z',base,'--'],
                ['git','ls-files','--others','--exclude-standard','-z']]
    names: set[str] = set()
    for cmd in commands:
        p = subprocess.run(cmd, cwd=root, capture_output=True, check=False, timeout=15)
        if p.returncode:
            raise ValueError(f'git discovery failed: {cmd[1]} (check branch base and repository)')
        names.update(normalize_relative(part.decode('utf-8')) for part in p.stdout.split(b'\x00') if part)
    return sorted(names)


def check_design(root: Path, policy: dict, changes: list[str]) -> dict:
    errors: list[str] = []
    analyzed: list[str] = []
    try:
        paths = sorted(set(normalize_relative(p) for p in changes))
    except ValueError as exc:
        return {'status':'BLOCKED','changed_files': [], 'ui_analyzed': [], 'errors':[str(exc)]}
    try:
        catalog_path = inside(root, policy['component_catalog'])
        if catalog_path.is_file():
            catalog_data = json.loads(catalog_path.read_text(encoding='utf-8'))
            entries = catalog_data.get('components')
            if not isinstance(entries, list):
                raise ValueError('component catalog must contain components[]')
            catalog: dict[str, dict] = {}
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
                    raise ValueError('each catalog entry requires path')
                key = normalize_relative(entry['path'])
                if key in catalog:
                    raise ValueError(f'duplicate component catalog entry: {key}')
                catalog[key] = entry
        else:
            catalog = {}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return {'status':'BLOCKED','changed_files': paths, 'ui_analyzed': [], 'errors':[f'Invalid component catalog: {exc}']}

    for rel in paths:
        try:
            path = inside(root, rel)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        if in_roots(rel, policy['prohibited_baseline_roots']) and rel not in policy['approved_baseline_paths']:
            errors.append(f'{rel}: visual baseline modification not approved by external design policy')
        if in_roots(rel, policy['ignored_paths']):
            continue
        if not in_roots(rel, policy['ui_roots']):
            continue
        if path.suffix.lower() not in UI_EXTENSIONS or not path.is_file():
            continue
        analyzed.append(rel)
        try:
            content = path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            errors.append(f'{rel}: failed to read UI file')
            continue
        if (policy['reject_literal_colors_in_changed_ui'] and rel not in policy['token_files']):
            if HEX.search(content) or COLOR_FUNCTIONS.search(content) or TAILWIND_PALETTES.search(content):
                errors.append(f'{rel}: literal or palette colors found; use semantic design tokens or a reviewed exception')

        is_shared_component = (
            path.suffix.lower() in COMPONENT_EXTENSIONS
            and in_roots(rel, policy['component_roots'])
            and not any(x in path.name for x in ('.stories.', '.test.', '.spec.'))
            and path.stem not in ('index', 'types')
        )
        if is_shared_component:
            if rel not in catalog:
                if policy['require_catalog_entry_for_changed_components']:
                    errors.append(f'{rel}: missing component catalog entry')
                if policy['require_story_for_changed_components']:
                    errors.append(f'{rel}: cannot verify story without catalog entry')
            elif policy['require_story_for_changed_components']:
                story = catalog[rel].get('story')
                if not isinstance(story, str) or not story:
                    errors.append(f'{rel}: component catalog lacks story path')
                else:
                    try:
                        story_path = inside(root, normalize_relative(story))
                        if not story_path.is_file() or '.stories.' not in story_path.name:
                            errors.append(f'{rel}: referenced Storybook story is missing or not a *.stories.* file')
                    except ValueError as exc:
                        errors.append(str(exc))
    return {
        'status':'PASS' if not errors else 'BLOCKED',
        'changed_files':paths,
        'ui_analyzed':analyzed,
        'errors':errors,
        'note':'Static conventions only; requires independent actual browser, visual, accessibility and UX verification.'
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default=str(ROOT), help='Project root, defaults to directory above scripts/')
    ap.add_argument('--config', default='quality/design-policy.json')
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--files', nargs='+', help='Explicit changed files, paths relative to root')
    group.add_argument('--changed-from', help='Git revision to compare to working tree, includes untracked files')
    ap.add_argument('--report', help='JSON report path; must be inside repository')
    a = ap.parse_args()
    root = Path(a.root).resolve()
    try:
        config = Path(a.config)
        if not config.is_absolute(): config = root / config
        # for security, CI must supply this config from a trusted source; this CLI cannot verify policy origin.
        policy = load_policy(root, config)
        changes = a.files if a.files is not None else git_changes(root, a.changed_from)
        report = check_design(root, policy, changes)
        if a.report:
            path = inside(root, normalize_relative(a.report))
            if path.suffix != '.json': raise ValueError('report must end with .json')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
        return 0 if report['status'] == 'PASS' else 1
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print('BLOCKED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
