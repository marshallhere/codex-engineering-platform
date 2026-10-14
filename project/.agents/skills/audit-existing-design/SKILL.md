---
name: audit-existing-design
description: Discover existing design conventions, component APIs and UI baselines before editing a mature UI.
---

# audit-existing-design

Trigger for any brownfield UI change without a current verified design inventory.

1. Inspect actual app and repo: CSS variables, Tailwind/theme config, global styles, fonts/icons, layout patterns, existing component library, Storybook, screenshots.
2. Inventory common components and their authoritative locations/imports; use Storybook MCP where present. Build or refresh `docs/design/component-catalog.json` with grounded references.
3. Capture representative baseline screens with stable fixtures and the repository's configured browser environment; record widths, browser, theme, locale and state. Do not automatically accept changed baselines.
4. Write a *descriptive* `docs/design/FOUNDATIONS.md` based on what the project actually uses, not a generic template or imagined values.
5. Identify existing inconsistencies as issues only; do not opportunistically redesign parts outside the change scope.
6. Produce a UI fingerprint with exact sources and risks, then delegate to the Next.js engineer and design guardian.
