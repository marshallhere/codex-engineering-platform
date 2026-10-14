#!/usr/bin/env python3
"""Conservative *advisory* task risk and specialist suggestion; NOT a security gate."""
import argparse
import json

RISK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
FLAG_RISKS = {
    "auth": "high", "payment": "high", "pii": "high", "security": "high",
    "public-contract": "high", "infra": "high", "secrets": "critical",
    "prod-deploy": "critical", "destructive-migration": "critical",
}


def route(paths: list[str], flags: list[str]) -> dict:
    # Paths supplied by an LLM are potentially incomplete or misleading.
    paths = [p.replace('\\', '/').removeprefix('./') for p in paths if p.strip()]
    score = 0
    roles = set()
    reasons = []
    if not paths and not flags:
        score = RISK['moderate']
        reasons.append('No scope supplied; do not classify unknown work as low-risk')
    doc_only = bool(paths)
    for raw in paths:
        p = raw.lower()
        is_doc = p.endswith(('.md', '.mdx', '.txt', '.rst')) or p.startswith('docs/')
        doc_only &= is_doc
        if p.endswith(('.java', '.kt')) or '/src/main/java/' in p or 'pom.xml' in p or 'build.gradle' in p:
            roles.add('spring_engineer')
        if p.endswith(('.py', '.pyi')) or 'pyproject.toml' in p or 'alembic/' in p:
            roles.add('fastapi_engineer')
        if p.endswith(('.tsx', '.jsx', '.ts', '.js')) or p.startswith(('frontend/', 'web/')) or 'next.config.' in p:
            roles.add('nextjs_engineer')
        if p.endswith('.sql') or 'migrations/' in p or 'alembic/versions/' in p:
            roles.add('database_engineer')
            score = max(score, RISK['high'])
            reasons.append('Migration/SQL path requires DB and compatibility review')
        if p.startswith(('.github/', 'infra/', 'terraform/', 'deploy/')) or p.endswith(('.tf', '.tfvars')) or 'dockerfile' in p or 'compose.' in p:
            roles.add('devops_engineer')
            score = max(score, RISK['high'])
            reasons.append('Infrastructure/CI change requires elevated review')
        if any(x in p for x in ('auth', 'billing', 'payment', 'permission', 'access-control', 'secret')):
            score = max(score, RISK['high'])
            roles.add('security_reviewer')
            reasons.append('High-risk path keyword; verify real semantics')
        if p.startswith(('.codex/', 'quality/', 'scripts/quality_gate', 'scripts/staged_policy', 'docs/engineering/invariants.md', 'docs/engineering/memory/')):
            score = max(score, RISK['critical'])
            reasons.append('Agent/policy/gate files affect trust or verification')
    if not doc_only:
        score = max(score, RISK['moderate'])
    for flag in flags:
        tier = FLAG_RISKS[flag]
        score = max(score, RISK[tier])
        reasons.append(f'Explicit risk flag: {flag}')
        if tier in ('high','critical'):
            roles.add('security_reviewer')
    tier = next(k for k, v in RISK.items() if v == score)
    if doc_only:
        roles.add('documentation_engineer')
    if score >= RISK['moderate']:
        roles.update(('test_runner', 'code_reviewer'))
    if score >= RISK['high']:
        roles.update(('test_designer', 'architecture_reviewer', 'security_reviewer'))
    return {
        'risk': tier, 'advisory_only': True,
        'roles_to_consider': sorted(roles),
        'required_stages_to_configure': ['pr','release'] if tier in ('high','critical') else ['pr'],
        'requires_human_review': score >= RISK['high'],
        'rationale': list(dict.fromkeys(reasons)),
        'warning': 'Filenames and declared flags never replace semantic risk review, independent CI or mandatory permissions.'
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--paths', nargs='*', default=[])
    parser.add_argument('--flag', choices=sorted(FLAG_RISKS), action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(route(args.paths, args.flag), indent=2))

if __name__ == '__main__':
    main()
