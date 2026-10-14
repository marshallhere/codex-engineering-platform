---
name: design
description: Route an approved UI change through design discovery, component reuse, rendered review and accessibility evidence.
---

Classify the change from actual project state. For an existing UI, use
`audit-existing-design` and `component-first-ui`. For a new UI or an explicitly
requested redesign, use `establish-design-language`, render a representative
screen, and obtain approval of that initial direction before extending it.

Storybook and source are the component inventory. Read
[Storybook integration](../../references/design/STORYBOOK_INTEGRATION.md) when
configuring it, verify the installed versions and live tools, and use
`storybook-component-workflow` when available. Reuse components and semantic
tokens before proposing new primitives. Missing Storybook never justifies
inventing available components.

Use `visual-quality-loop` for real screenshots, browser interaction, responsive
behavior, keyboard/focus inspection and automated accessibility checks. Protect
approved screenshot baselines. Separate pre-existing design debt from defects
introduced by this change. UI completion needs all project-required visual,
Storybook, accessibility and product acceptance evidence on the final candidate.

The Python/Go functional demonstration does not qualify these UI capabilities.
Report unavailable UI integrations as unverified and retain the required gates.
