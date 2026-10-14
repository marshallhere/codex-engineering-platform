#!/usr/bin/env python3
"""Read ONLY reviewed, scoped knowledge. Retrieval is contextual guidance, not policy."""
import argparse
from datetime import date
import fnmatch
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / 'docs/engineering/memory/approved.jsonl'
TOKEN = re.compile(r'[a-zA-Z0-9_]{3,}')
MAX_INPUT_BYTES = 1_000_000


def tokens(s: str) -> set[str]:
    return {x.lower() for x in TOKEN.findall(s)}


def retrieve(query: str, paths: list[str], path: Path = MEMORY, limit: int = 3) -> list[dict]:
    if limit < 1 or limit > 10:
        raise ValueError('limit must be 1..10')
    if not path.exists() or path.is_symlink():
        return []
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError('Reviewed memory file exceeds size limit')
    query_terms = tokens(query + ' ' + ' '.join(paths))
    found = []
    for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        if not isinstance(entry, dict) or entry.get('status') != 'approved':
            continue
        expiry = entry.get('expires_at')
        if expiry:
            try:
                if date.fromisoformat(expiry) < date.today():
                    continue
            except (TypeError, ValueError):
                continue
        if not all(isinstance(entry.get(key), str) and entry[key].strip() for key in ('id', 'title', 'rule', 'evidence', 'reviewed_at')):
            continue
        patterns = entry.get('paths', [])
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            continue
        # Scoped entries don't apply unless matching a path supplied for task.
        if patterns and not any(fnmatch.fnmatch(p, pattern) for p in paths for pattern in patterns):
            continue
        keywords = entry.get('keywords', [])
        if not isinstance(keywords, list) or not all(isinstance(x, str) for x in keywords):
            continue
        target = tokens(' '.join([entry['title'], entry['rule']] + keywords))
        hits = len(query_terms.intersection(target))
        scoped = bool(patterns)
        if hits < 1 and not scoped:
            continue
        rank = hits * 2 + int(scoped)
        found.append((rank, n, {
            'id': entry['id'], 'title': entry['title'],
            'rule': entry['rule'][:700], 'evidence': entry['evidence'][:200],
            'reviewed_at': entry['reviewed_at']
        }))
    found.sort(key=lambda t: (-t[0], t[1]))
    return [e for _, _, e in found[:limit]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', required=True)
    parser.add_argument('--paths', nargs='*', default=[])
    parser.add_argument('--limit', type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(retrieve(args.query, args.paths, limit=args.limit), indent=2))

if __name__ == '__main__':
    main()
