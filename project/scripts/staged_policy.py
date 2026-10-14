#!/usr/bin/env python3
"""Prevent common sensitive artifact paths being staged; flag policy edits for review."""
import os
from pathlib import PurePosixPath
import subprocess
import sys

SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks")
SENSITIVE_BASES = (".env", "id_rsa", "id_ed25519", "credentials.json", "service-account.json")
PROTECTED = ("AGENTS.md", ".codex/", ".github/workflows/", ".github/CODEOWNERS", ".pre-commit-config.yaml", "docs/engineering/invariants.md")


def path_sensitive(path):
    base = PurePosixPath(path).name.lower()
    if base in (".env.example", ".env.sample", ".env.template"):
        return False
    return (base in SENSITIVE_BASES or base.startswith(".env.") or base.endswith(SENSITIVE_SUFFIXES))


def scan_paths(paths):
    bad = [p for p in paths if path_sensitive(p)]
    reviewed = [p for p in paths if p == "AGENTS.md" or p.startswith(".codex/") or p.startswith(".github/workflows/") or p in {".github/CODEOWNERS", ".pre-commit-config.yaml", "docs/engineering/invariants.md"}]
    return bad, reviewed


def main():
    proc = subprocess.run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"], capture_output=True)
    if proc.returncode:
        print("BLOCKED: could not inspect Git staged files", file=sys.stderr)
        return 2
    paths = [os.fsdecode(x) for x in proc.stdout.split(b"\0") if x]
    bad, reviewed = scan_paths(paths)
    if reviewed:
        print("IMPORTANT: guardrail files changed: " + ", ".join(reviewed) + ". Require CODEOWNERS/human review.", file=sys.stderr)
    if bad:
        print("BLOCKED: sensitive file paths staged (remove from index): " + ", ".join(bad), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
