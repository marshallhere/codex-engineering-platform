# Design tooling and MCP (review before enabling)

Full Storybook setup and Codex MCP commands: [`STORYBOOK_INTEGRATION.md`](STORYBOOK_INTEGRATION.md).

1. **Storybook** provides executable component documentation and states. Its current MCP addon is in preview (Storybook docs, 2026). For existing projects, inspect framework compatibility and upgrade costs first.
2. **Storybook MCP**: `npx storybook add @storybook/addon-mcp` in the UI project. Start its dev server, expose only local `http://127.0.0.1:6006/mcp` (adjust for actual port) to Codex using Codex's HTTP MCP setup. Enable `features.componentsManifest=true` if supported by the installed framework; verify manifest availability. Do not invent props; use documented manifests/stories.
3. **Playwright**: deterministic screenshot comparisons via `toHaveScreenshot()` plus mobile/desktop full-flow tests; keep snapshots on the same browser/OS/fonts and stable fixture data. Store PNG diffs and traces as evidence. Browsing through MCP is exploratory and should not replace committed tests.
4. **Storybook accessibility addon** (axe): configure tests to fail in CI; automated tests do NOT cover all accessibility issues, so inspect focus, keyboard/touch, zoom, reduced motion and screen reader interactions where relevant.
5. **Design tokens**: use the project's existing token format. For new React/Tailwind/shadcn projects, prefer semantic CSS variables; for cross-platform token exchange consider the DTCG 2025.10 format and a build pipeline. Do not rename all brownfield tokens simply to standardize conventions.
6. **Visual CI**: Playwright screenshots are local/open-source. Chromatic is an optional hosted alternative (privacy/cost review needed) with baseline workflow. Do not make cloud uploads the default without explicit decision.
7. **Figma (optional)**: connect only if project source-of-truth designs live in Figma. Figma MCP can supply real components and variables; it is not necessary for a code-first project.

References:
- https://storybook.js.org/docs/ai
- https://storybook.js.org/docs/writing-tests/accessibility-testing
- https://playwright.dev/docs/test-snapshots
- https://ui.shadcn.com/docs/theming
- https://www.designtokens.org/tr/2025.10/format/
- https://www.w3.org/WAI/WCAG22/quickref/
