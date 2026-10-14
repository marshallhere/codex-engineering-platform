"""Reject scanner failures, material findings and unreviewed low findings."""

import argparse
from collections import Counter
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--baseline", type=Path, default=Path("config/security-baseline.json")
    )
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    baseline = json.loads(args.baseline.read_text())
    if report.get("errors") or baseline.get("schema_version") != 1:
        raise ValueError("Scanner errors or unsupported reviewed baseline")
    reviewed = Counter(
        {
            (r["file"], r["test_id"], r["severity"]): r["count"]
            for r in baseline["findings"]
        }
    )
    found = Counter(
        (Path(r["filename"]).name, r["test_id"], r["issue_severity"])
        for r in report["results"]
    )
    if any(severity != "LOW" for _, _, severity in found) or found - reviewed:
        raise ValueError("Material or unreviewed security findings")
    print(f"Security gate passed; {sum(found.values())} reviewed LOW findings retained")


if __name__ == "__main__":
    main()
