#!/usr/bin/env python3
"""Inject short human-reviewed notes into session/subagent context. Never read transcripts."""
import json
import os
from pathlib import Path
import subprocess
import sys

MAX_FILE = 1250
MAX_ALL = 2600


def git_root(cwd: str) -> Path:
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, check=False)
    return Path(proc.stdout.strip() if proc.returncode == 0 else cwd).resolve()


def context(cwd: str) -> str:
    repo = git_root(cwd)
    files = [
        ("Personal preferences (human-curated)", Path.home() / ".codex" / "PREFERENCES.md"),
        ("Project invariants", repo / "docs/engineering/invariants.md"),
    ]
    output = ["Engineering context: reviewed notes, not a security boundary. Read ADRs and scoped lessons only when relevant; run memory_retrieve.py with affected paths for targeted recall."]
    for name, path in files:
        if not path.is_file() or path.is_symlink():
            continue
        try:
            body = path.read_text(encoding="utf-8")[:MAX_FILE]
        except (OSError, UnicodeError):
            continue
        if body.strip():
            output.append(f"### {name}\n{body}")
    return "\n\n".join(output)[:MAX_ALL]


def main():
    try:
        event = json.load(sys.stdin)
        event_name = event.get("hook_event_name")
        if event_name not in {"SessionStart", "SubagentStart"}:
            return
        cwd = event.get("cwd") or os.getcwd()
        payload = {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": context(cwd)}}
        print(json.dumps(payload))
    except Exception as exc:
        print(f"session_context hook failed: {exc}", file=sys.stderr)
        # Context is a convenience, not a security enforcement point. Fail visibly, not silently.
        raise SystemExit(1)


if __name__ == "__main__":
    main()
