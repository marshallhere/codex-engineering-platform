# Approved decisions — 2026-10-14

The handoff remains the architectural intent; the following user decisions refine it.

- Standalone public repository on marshallhere, MIT license, macOS first.
- Codex plugin plus a small deterministic local runtime; no second AI assistant.
- Install once and enable per project. Eventu retains eventu-tooling ownership.
- Native fail-closed isolation; no automatic container fallback.
- Technology packs extend the core without scheduler changes. Unknown stacks produce
  a proposed tested pack that the user activates before unattended use.
- Submit-and-steer jobs continue after the chat closes. Sleep pauses active time;
  reboot requires explicit resume and requalification.
- Multiple jobs per project, separate worktrees/resources, serialized integration.
- Every job requires an active-time budget; optional tokens only when enforceable.
- Routine implementation choices are autonomous; consequential choices need input.
- Add necessary compatible dependencies; ask before major upgrades/replacements.
- Standing named development-resource access is configured per project.
- Auto-merge categories are project-configured; disabled before configuration.
  Deployment is a separate authorization. Existing project restrictions still apply.
- Approve initial design/redesign once using rendered output. Preserve existing
  language, reuse components, and retain Storybook/visual/a11y evidence.
- Propose lessons automatically; authoritative promotion requires human batch review.
- First functional proof is a Python CLI. Prove extension via a minimal Go pack.

The original handoff proposed dedicated users/VMs/containers. The later explicit
native-only decision supersedes that implementation preference, not the isolation
requirement. Native qualification must establish the promised boundary or block work.
