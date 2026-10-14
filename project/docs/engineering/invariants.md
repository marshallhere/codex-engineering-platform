# Engineering invariants — reviewed repository policies

Keep these *small* and make them fit your real project before use.

- No production credentials or customer data in local development or E2E tests.
- Authorization happens on the server, including ownership/object-level checks.
- API changes must consider backwards compatibility and migration plans.
- Side-effecting operations need explicit failure semantics (transactionality, retries, idempotency).
- Destructive DB migrations require a tested backup/restore and written approval.
- A passing test report must correspond to commands actually executed against this revision.
- All merges require the branch's configured CI checks and protected-branch human approval policy.
- Do not auto-approve architecture decisions, lesson promotions or changes to these invariants.
