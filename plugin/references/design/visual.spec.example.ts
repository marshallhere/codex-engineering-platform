// TEMPLATE ONLY: adapt routes, fixtures, screen states and accepted baselines to your project.
// Install @playwright/test and configure webServer/baseURL in playwright.config.ts first.
import { test, expect } from '@playwright/test';

for (const viewport of [
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
]) {
  test(`EXAMPLE authenticated page visual at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    // Use local fixtures, a fixed seed, and a test user without real credentials.
    await page.goto('/YOUR-TEST-ROUTE');
    await expect(page.getByRole('main')).toBeVisible();
    await expect(page).toHaveScreenshot(`example-${viewport.width}.png`, {
      animations: 'disabled',
    });
  });
}
