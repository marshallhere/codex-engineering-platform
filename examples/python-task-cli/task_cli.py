"""Intentionally defective seed for the protected repair demonstration."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--file", required=True)
args = parser.parse_args()
# DEMO-LIST and DEMO-BOUNDARY deliberately fail until a Codex worker repairs them.
print(json.dumps(json.loads((Path(args.root) / args.file).read_text())))
