# OpenSpec UI acceptance extension (template)

Attach this to the feature's OpenSpec change; do not treat this template as an approved screen specification.

## Product intent
- Target persona and primary job:
- User journey and information hierarchy:
- Existing route(s) or new route(s):
- New vs established visual direction:

## Design constraints
- Reference `docs/design/FOUNDATIONS.md` and component catalog:
- Allowed changes to tokens/shared components:
- Required components and variants:
- Prohibited new dependencies or UI patterns:

## Required screen states
| Screen | Route/story | Viewport(s) | State | Acceptance criteria | Evidence |
|---|---|---|---|---|---|
| Example | /example | 390, 768, 1440 | default/error/loading | No clipping; correct hierarchy; focus visible | pending |

## Behavior
- Keyboard/touch semantics:
- Validation and error recovery:
- Accessibility target, color contrast and reduced motion:
- Responsive navigation/layout and long-content behavior:
- Localization, RTL, content truncation policy:

## Visual baselines
- Approved baselines and their provenance:
- New screenshots allowed by this specific change:
- Testing environment and fixtures:
- Explicit deviations from existing design language:

## Completion
- Stories/tests map to acceptance IDs.
- Independent visual QA observes the rendered app, not just code.
- Screenshots compared to baseline; baseline updates are explicitly authorized, not auto-accepted.
- Final browser, accessibility, design guard and functional tests pass after last edit.
