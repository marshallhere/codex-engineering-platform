---
name: visual-quality-loop
description: Iterate on real browser screenshots, visual diffs and accessibility evidence until UI acceptance gates pass.
---

# visual-quality-loop

Trigger for any meaningful visual change after implementation.

1. Start a sandboxed application and/or Storybook with non-production fixtures. Capture a stable browser environment and record commit/viewport/locale/theme/fixtures.
2. Run Storybook interaction/a11y tests, Playwright behavior and screenshots, and applicable deterministic design guard.
3. Inspect actual screenshots (not just image filenames) with visual_qa_reviewer. Verify mobile/tablet/desktop, keyboard focus, errors, loading, long translations and dark/light when applicable.
4. Contrast with approved baselines and design intent. Unexpected diffs are defects; intentional diffs need spec-linked authorization. Do not overwrite approved screenshots by merely running `--update-snapshots`.
5. Dispatch actionable problems to implementation agent; rerun the specific checks and whole required visual gate after fixes.
6. Stop READY only when required checks pass and no unresolved blocking design issues remain. If evidence or browser access unavailable, report BLOCKED/UNVERIFIED rather than fabricated confidence.
