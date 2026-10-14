# Spec-driven autonomy contract

- **OpenSpec** is authoritative for intended observable behavior and acceptance criteria.
- **Architecture decisions** belong in reviewed ADRs; explicit personal preferences live separately.
- **Beads** may track dependency and execution state; it does not replace OpenSpec or tested evidence.
- **Implementers** may propose a needed spec correction but must not redefine the requirements merely to make tests pass.
- **Tests** are derived from acceptance criteria, include negative/failure behavior, and execute in isolated resources.
- **Completion** requires spec structure validation, no incomplete checked tasks, independent review, external deterministic gates, and final regression after polish.
- **Continuous autonomy** means no routine approval prompts for permitted local actions; it does not grant production credentials or write access outside the feature worktree.
- **Long-running mode**: native Codex `/goal` works for a single durable interactive objective. A separately hosted supervisor is needed for restartable queue execution and machine-enforced gates across Codex invocations.
