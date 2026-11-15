// Starter: adapt the route and interactions; see ../references/setup.md for prerequisites.
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const baseURL = process.env.UI_BASE_URL ?? 'http://localhost:3000';
const route = process.env.UI_ROUTE ?? '/';

for (const viewport of [
  { name: 'mobile', width: 375, height: 800 },
  { name: 'desktop', width: 1440, height: 900 },
]) {
  test(`UI quality: ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`${baseURL}${route}`);
    await expect(page.locator('body')).toBeVisible();

    // Detect horizontal overflow; wide tables may need scoped horizontal scrolling.
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
    );
    expect(overflow).toBe(false);

    await page.screenshot({
      path: `test-results/ui-${viewport.name}.png`,
      fullPage: true,
    });

    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(accessibility.violations).toEqual([]);
  });
}
