#!/usr/bin/env python3
"""Create pending lesson proposals. Does not modify reviewed lessons or preferences."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / ".codex" / "learning" / "pending"


def record(kind: str, title: str, symptom: str, cause: str, prevention: str, evidence: str, regression: str) -> Path:
    fields = (title, symptom, cause, prevention, evidence, regression)
    if any(not x.strip() for x in fields):
        raise ValueError("All lesson fields require meaningful content")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:65]
    if not slug:
        raise ValueError("title must contain letters or numbers")
    PENDING.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = PENDING / f"{date}-{slug}.md"
    if path.exists():
        raise FileExistsError(f"proposal already exists: {path}")
    body = f"""# {title}\n\nStatus: PROPOSED — requires user review (not binding).\nType: {kind}\nCreated (UTC): {date}\n\n## Symptom / correction\n{symptom}\n\n## Root cause\n{cause}\n\n## Prevention rule / changed preference\n{prevention}\n\n## Evidence\n{evidence}\n\n## Regression test to add or update\n{regression}\n\n## Review and promotion\n- [ ] User confirms no secret/PII\n- [ ] User approves preference, ADR, or lesson scope\n- [ ] Add regression test or explain why inapplicable\n- [ ] Commit reviewed lesson/ADR/preference in appropriate location\n- [ ] Update the relevant index or checklist\n"""
    path.write_text(body, encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="Record a pending learning proposal")
    parser.add_argument("--type", required=True, choices=["bug", "preference", "architecture", "security", "testing"])
    for flag in ("title", "symptom", "cause", "prevention", "evidence", "regression"):
        parser.add_argument("--"+flag, required=True)
    args = parser.parse_args()
    path = record(args.type, args.title, args.symptom, args.cause, args.prevention, args.evidence, args.regression)
    print(f"PROPOSED (not approved): {path}")


if __name__ == "__main__":
    main()
