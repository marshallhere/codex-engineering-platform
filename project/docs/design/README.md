# Design engineering — two modes

For complete Storybook installation, live MCP wiring, agent rules and component-testing gates, see [`STORYBOOK_INTEGRATION.md`](STORYBOOK_INTEGRATION.md).

This directory is for **project-specific** truth. The kit does not know your brand until it has inspected your real application or received an explicit design brief.

## Greenfield (`establish-design-language`)
- Product brief and UI acceptance scenarios live in OpenSpec. The design architect creates `FOUNDATIONS.md` (not the example's placeholder values), semantic tokens and a Storybook component catalog.
- Deliver a representative screen and component states, verify mobile/desktop interactions, then establish a baseline scoped to the approved direction.
- Record unreviewed visual artifacts as **provisional**, not as approved designs.

## Brownfield (`audit-existing-design`)
- Inventory real components, source paths, tokens, Storybook stories and actual running UI before implementing a change.
- Preserve existing typography, spacing, palette, iconography, density, interaction conventions and component APIs unless OpenSpec authorizes changing them.
- Prefer existing component → composition → variant → justified new component. Update `component-catalog.json` when introducing a component.
- Capture screenshots of existing UI as approved baselines only when there's reliable evidence they represent known-good behavior.

## Authoritative sources
1. Approved OpenSpec requirements and UI acceptance criteria (intent)
2. Actual code and Storybook component catalog (available implementation APIs)
3. Reviewed `FOUNDATIONS.md`/ADRs/tokens (design constraints)
4. Approved screenshot baselines for defined environments (expected appearance)
5. AI memories or external inspiration (non-authoritative hints)

## Required UI states
Cover default, hover/focus, disabled, loading, empty, success/error, validation and permissions-dependent states where applicable. Test RTL/long translations where supported, viewport changes, keyboard-only focus and reduced-motion preferences. Automated WCAG checks are only one part of accessibility verification.

## Quality gate
- Run `design_gate.py` for changed UI files; it enforces catalog/story discipline and literal-color restrictions according to a project policy.
- Run Storybook component tests, accessibility checks, Playwright interaction tests and visual screenshots as applicable. The deterministic gate **does not know whether a design is aesthetically excellent**; independent real-browser review is needed.
- Policy and baseline authorization must be owned by CI/external supervisor, not adjusted by the same writable agent on failure.
- A UI change without an accessible running browser or configured checks is UNVERIFIED, not READY.
