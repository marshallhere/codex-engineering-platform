#!/usr/bin/env python3
"""Best-effort local shell hook. Do not treat string matching as a security boundary."""
import json
import re
import sys

# Restrict obviously destructive actions, including common prefixes. This is not exhaustive:
# indirection, shell aliases, Python, other tools, and hosted tools can evade regex matching.
BLOCK = [
    (r"\bgit\s+(?:-\S+\s+)*reset\s+--hard\b", "Potentially destructive Git reset"),
    (r"\bgit\s+(?:-\S+\s+)*clean\s+-[a-zA-Z]*f[a-zA-Z]*d", "Potentially destructive Git clean"),
    (r"\bgit\s+push\b[^\n]*\s--force(?:-with-lease)?\b", "Force push requires manual review"),
    (r"\bterraform\s+destroy\b", "Infrastructure destruction is not agent-delegated"),
    (r"\b(?:kubectl|helm)\s+delete\b", "Cluster deletion requires manual review"),
    (r"\b(?:rm|sudo\s+rm)\s+-[a-zA-Z]*r[a-zA-Z]*f\s+(?:/|\.|\*|~)(?:\s|$)", "Potential recursive removal of broad path"),
    (r"\bdocker\s+(?:system|volume)\s+prune\b", "Docker-wide cleanup requires manual review"),
    (r"\b(?:DROP\s+DATABASE|TRUNCATE\s+TABLE)\b", "Destructive SQL operation requires manual review"),
    (r"\bcurl\b[^\n|]{0,250}\|\s*(?:bash|sh)\b", "Piping downloaded scripts directly to a shell is prohibited"),
]


def deny_reason(command: str) -> str | None:
    for regex, reason in BLOCK:
        if re.search(regex, command, re.I):
            return reason
    return None


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if event.get("tool_name") != "Bash":
            return
        command = event.get("tool_input", {}).get("command")
        if not isinstance(command, str):
            return
        reason = deny_reason(command)
        if reason:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": f"{reason}; use an independently approved human workflow."
            }}))
    except Exception as exc:
        print(f"pre_tool_use failed: {exc}", file=sys.stderr)
        # Fail closed for a malformed tool event.
        raise SystemExit(2)


if __name__ == "__main__":
    main()
