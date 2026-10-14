---
name: evolve-design-system
description: Safely change established component APIs or tokens, with migration and regression coverage.
---

# evolve-design-system

Trigger when a task changes shared tokens, global CSS variables, shared components or design foundations.

1. Collect impacted imports/stories/pages and approved OpenSpec rationale.
2. Prefer compatible additions; flag breaking changes and plan migrations.
3. Have component_librarian update API examples and design_system_maintainer evolve foundations.
4. Verify all affected stories/themes/states, browser screenshots and accessibility.
5. Include a migration note, reviewed visual baseline proposal and deprecation strategy.
6. Update component catalog and approved decisions. Do not rewrite all pages for stylistic taste.
