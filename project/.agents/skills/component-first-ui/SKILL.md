---
name: component-first-ui
description: Implement UI by reusing approved components and design tokens before creating new ones.
---

# component-first-ui

Trigger for modifying React/Next.js/TypeScript UI.

1. Read affected UI acceptance criteria and referenced design spec.
2. Query the Storybook MCP component manifest (if available), then examine exact source APIs, documented stories and call sites.
3. Decide in order: reuse existing; compose existing; extend supported variant; add a new component only if no equivalent exists and the architecture justifies it.
4. Implement with semantic tokens, accessible primitives, responsive states, and localization-safe layouts. No off-brand arbitrary CSS values unless recorded as a deliberate component decision.
5. Update Storybook states, catalog entries, test cases, visual baselines proposal, and OpenSpec traceability.
6. Have an independent design guardian and visual QA agent inspect final renders. A screenshot diff is not self-approval to regenerate the baseline.
