---
name: establish-design-language
description: Define a complete design system and first component catalog for a new UI project.
---

# establish-design-language

Trigger only for new projects or a design direction explicitly approved for redesign.

1. Extract design brief from OpenSpec: audience, tone, content hierarchy, platforms, localization, WCAG target, dark mode, existing brand assets, reference imagery and constraints.
2. Propose a distinctive but implementable direction, emphasizing meaningful visual hierarchy and legible interfaces. Record rationale in `docs/design/FOUNDATIONS.md` (create from the example template).
3. Define semantic token families before writing many CSS values. Choose fonts and icon style consistently; license/check assets.
4. Choose one accessible primitive approach (existing project library, Radix/Base, etc.) and one component ownership strategy. Avoid installing multiple overlapping UI kits.
5. Create an initial Storybook catalog: buttons, fields, alerts, dialogs, navigation, cards, skeletons, tables, etc., including states.
6. Implement a vertical slice: one representative screen, a complex form, and an error/empty state. Render at multiple viewports and test interaction.
7. Feed visual and a11y findings back into foundations; then define initial *provisional* screenshot baseline. Never call an AI-created baseline independently approved.
8. Update docs, spec traceability and scope-specific checks. Scope code and tool changes to the sandbox.
