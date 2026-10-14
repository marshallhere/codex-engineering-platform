# Agent evaluations — placeholder tasks, NOT test results

`cases.example.jsonl` describes candidate evaluation cases and intentionally has no executable fixtures. Turn each into a throwaway repository fixture and a deterministic grader not editable by the evaluated Codex worker. Seed known bug/expectation in a separate harness. Run the baseline (without specialization), current setup, and proposed setup repeatedly under the same task/budget; grade both objective test results and false claims, security misses, cost and user interruptions.

Use `codex exec --json --output-schema schema.json -o result.json` for structured events where appropriate. Run evaluations with minimal credentials, no production access, a locked evaluation environment, and separate local working copies per run. Never add API keys to untrusted CI jobs. Retain redacted outcome summaries, not raw sensitive prompts or auth tokens.
