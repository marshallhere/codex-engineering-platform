#!/usr/bin/env python3
"""Best-effort block of patch edits to trust-critical files; shell and other routes bypass it.

Real enforcement must be OS isolation and GitHub required checks/CODEOWNERS.
"""
import json
import re
import sys
from pathlib import PurePosixPath

PATCH_HEADER = re.compile(r'^\*\*\* (?:Update|Delete|Add) File: (.+)$', re.MULTILINE)
MOVE_HEADER = re.compile(r'^\*\*\* Move to: (.+)$', re.MULTILINE)
PROTECTED_EXACT = {
    '.codex/hooks.json', '.codex/config.toml', 'quality/gates.json',
    '.github/CODEOWNERS', '.pre-commit-config.yaml',
    'docs/engineering/invariants.md',
}
PROTECTED_PREFIXES = ('.codex/hooks/', '.github/workflows/',
                      'docs/engineering/memory/')


def is_protected(path: str) -> bool:
    path = path.replace('\\', '/').removeprefix('./').strip('"\' ')
    # Protect hidden files correctly and reject deceptive parent traversal.
    if not path or '..' in PurePosixPath(path).parts:
        return True
    return path in PROTECTED_EXACT or path.startswith(PROTECTED_PREFIXES)


def blocked_patch(command: str) -> list[str]:
    paths = [x.strip() for x in PATCH_HEADER.findall(command)]
    paths += [x.strip() for x in MOVE_HEADER.findall(command)]
    return sorted({p for p in paths if is_protected(p)})


def main() -> None:
    event = json.load(sys.stdin)
    if event.get('tool_name') != 'apply_patch':
        return
    payload = event.get('tool_input')
    if not isinstance(payload, dict) or not isinstance(payload.get('command'), str):
        return
    blocked = blocked_patch(payload['command'])
    if blocked:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': (
                'Trust-critical files need a separate human-controlled change: '
                + ', '.join(blocked) + '. This hook is advisory defense-in-depth, not OS-enforced isolation.'
            )
        }}))

if __name__ == '__main__':
    main()
