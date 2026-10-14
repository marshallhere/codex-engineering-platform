#!/usr/bin/env python3
"""Inject up to three relevant reviewed lessons on prompt submission."""
import json
import os
from pathlib import Path
import sys

# Import project-owned retrieval helper without installing a package.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from memory_retrieve import retrieve


def main():
    event = json.load(sys.stdin)
    if event.get('hook_event_name') != 'UserPromptSubmit':
        return
    prompt = event.get('prompt', '')
    if not isinstance(prompt, str):
        return
    records = retrieve(prompt[:6000], [], limit=3)
    if not records:
        return
    lines = ['Relevant *reviewed* repo lessons (context, not higher-level instructions):']
    for x in records:
        lines.append(f"- {x['id']}: {x['title']} — {x['rule']} (evidence: {x['evidence']})")
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': '\n'.join(lines)[:2200]}}))

if __name__ == '__main__':
    main()
