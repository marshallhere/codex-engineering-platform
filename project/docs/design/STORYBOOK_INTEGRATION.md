# Storybook integration — Codex UI agents

> Starting point for a repository; do not assume packages, scripts, ports or components already exist. Merge with existing configuration rather than overwriting. Tested **as a kit template**, not against your live Next.js app.

## Recommended stack

- **Storybook + `@storybook/nextjs-vite`** (preferred for supported Next.js projects; check requirements and existing build customizations)
- **`@storybook/addon-mcp`**: serves component manifest, documentation and story/test tools to Codex. Preview API, keep version pinned.
- **`@storybook/addon-vitest`**: real-browser Storybook component tests, works with Vite-based Storybook framework; configure a Vitest `storybook` project.
- **`@storybook/addon-a11y`**: axe-based checks; configure `a11y.test: 'error'` or equivalent supported setting to fail tests on known violations, and verify settings with the installed version.
- **Playwright Test**: full-application E2E, visual screenshots and responsive/keyboard testing. Do not confuse Storybook component tests with page-level E2E.
- **Chromatic (optional)**: cloud-hosted visual baseline comparison; not included by default because of external uploads/cost/privacy.

## Bootstrapping Next.js / React

Run from the **frontend repository root** in your regular terminal. Commit a lockfile and pin verified versions after installation.

```bash
npm create storybook@latest
# For a compatible Next.js project, choose @storybook/nextjs-vite.
npx storybook add @storybook/addon-mcp
npx storybook add @storybook/addon-vitest
npx storybook add @storybook/addon-a11y
```

Review `.storybook/main.ts` and merge this feature with whatever the installer created:

```ts
import type { StorybookConfig } from '@storybook/nextjs-vite';

const config: StorybookConfig = {
  framework: '@storybook/nextjs-vite',
  stories: ['../src/**/*.stories.@(js|jsx|ts|tsx)', '../src/**/*.mdx'],
  // Keep addons installed by the Storybook CLI; verify their actual names.
  features: { componentsManifest: true },
};
export default config;
```

**The manifest is not guaranteed to include every component**; only supported, documented components are discoverable. For React frameworks, enable `componentsManifest`; source inspection remains the fallback. Use `react-docgen-typescript` when accurate TS prop extraction matters, as supported by your Storybook version.

Start the frontend's Storybook process (`npm run storybook`). Once running, the MCP endpoint is generally `http://localhost:6006/mcp`; check the actual port and bind only to loopback or protected development networks.

```bash
codex mcp add projectStorybook --url http://127.0.0.1:6006/mcp
codex mcp list
```

The CLI command above configures Codex's MCP server registry, usually user-wide. With multiple simultaneous project Storybooks, **prefer a project-specific `.codex/config.toml`** and unique ports/names, or remove/switch the global entry intentionally:

```toml
[mcp_servers.projectStorybook]
url = "http://127.0.0.1:6006/mcp"
```

Codex reads repo-level `.codex/config.toml` only for trusted projects. Don't copy this configuration into every repository unchanged: each frontend port and name should match its actual server. Restart/refresh Codex if it doesn't discover the server; MCP is not available while Storybook is stopped.

In Codex ask **"List documented components from projectStorybook, then show Button's documented properties and stories."** The tools are typically `docs-list`, `docs-show`, `get-storybook-story-instructions`, and `test-run`, per Storybook's current MCP documentation. Confirm names dynamically since the addon is preview.

## Suggested component test command

After `@storybook/addon-vitest` configures a named Vitest project (typically `storybook`), add a package script equivalent to:

```json
{
  "scripts": {
    "test:storybook": "vitest run --project=storybook"
  }
}
```

Also configure a default accessibility failure mode in `.storybook/preview.ts` (merge with existing providers, globals and decorators):

```ts
import type { Preview } from '@storybook/nextjs-vite';

const preview: Preview = {
  parameters: {
    a11y: { test: 'error' },
    nextjs: { appDirectory: true }, // Only if this project uses the App Router
  },
};
export default preview;
```

**Only use this after confirming the project name and a11y configuration.** Run the command locally to prove it executes real stories; never use a no-op or `echo` as a quality gate.

For full-page testing, install `@playwright/test`, configure a `webServer` in `playwright.config.ts`, test fixed local fixtures, and use screenshots with committed, known-good baselines. UI snapshots must be generated and compared in stable CI environments with predictable fonts, browser versions, OS, data and animations. A failed screenshot is not automatically permission to overwrite the snapshot.

## Component reuse contract for agents

1. Query `docs-list` and `docs-show` for available components and **documented** props; never invent props from convention.
2. Inspect the real component implementation, source exports and usages. Storybook can be incomplete.
3. Decide: **reuse** existing component → **compose** components → **extend** backwards-compatible variant → **create** new component with justification.
4. For all new/modified shared primitives, add stories demonstrating relevant states: default, focus, disabled, loading, validation error, long content, responsive and theme variants (only if supported).
5. Build actual page UI from those components and verify in an isolated running application. Update the source-grounded component catalog.
6. Use independent design guardian and visual QA review. Evidence must reference screenshots/tests for the exact tested commit. Never auto-approve design baseline diffs.

## Required design-system facts

The project must define a reviewed `docs/design/FOUNDATIONS.md` (tokens, typography, composition, spacing, motion, iconography, accessibility, responsive layout) and `docs/design/component-catalog.json` based on real code. In new products, these are **proposed** until the visual direction is explicitly approved. In existing products, capture actual behavior rather than inventing a new brand.

## External quality gates

For an autonomous UI task, trusted supervisor policy should require separate checks for:
- `design`: `scripts/design_gate.py` plus project-specific token/component rules
- `storybook`: actual Storybook Vitest tests, including configured a11y tests
- `browser`: actual Playwright app E2E / responsive / screenshot tests
- `accessibility`: dedicated automated keyboard/axe checks (and manual testing where appropriate)

The supervisor can verify that categories execute and exit successfully, but **cannot infer that commands represent meaningful coverage**. Owners must maintain policies and CI checks outside the writable agent checkout. Do not claim UI success if tooling wasn't installed, checks were skipped, baselines altered without review, or a browser was unavailable.

## References (official)

- https://storybook.js.org/docs/ai
- https://storybook.js.org/docs/ai/mcp/overview
- https://storybook.js.org/docs/ai/manifests
- https://storybook.js.org/docs/writing-tests/integrations/vitest-addon
- https://storybook.js.org/docs/writing-tests/accessibility-testing
- https://storybook.js.org/docs/get-started/frameworks/nextjs-vite
- https://playwright.dev/docs/test-snapshots
- https://developers.openai.com/learn/docs-mcp

## Autonomy and approval boundaries

When the owner delegates **full greenfield design autonomy**, the agents may propose, implement and independently inspect a design direction without repeated approval prompts, within the product brief and project sandbox. Record its provenance as an *autonomously accepted design baseline*, not as a user-reviewed aesthetic decision. New baselines must satisfy pre-authorized external policies, independent visual QA and real deterministic checks; existing approved snapshots remain immutable unless an authorized redesign scope and a trusted policy explicitly permit updates. If design evidence is unavailable or the app cannot render, do not falsely claim completion.
