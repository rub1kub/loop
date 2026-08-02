import { expect, test } from '@playwright/test';

test('BANK keeps its verified fill and physical token layer usable on mobile', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => consoleErrors.push(String(error)));

  await page.goto('/?screen=bank-active');
  const jar = page.locator('.bank-ball-canvas');
  await expect(jar).toBeVisible();
  await expect(page.getByText('62%', { exact: true })).toBeVisible();
  await expect
    .poll(async () => {
      return jar.evaluate(
        (canvas) => Number(canvas.dataset.ballCount) - Number(canvas.dataset.targetCount),
      );
    })
    .toBe(0);
  expect(await jar.evaluate((canvas) => Number(canvas.dataset.ballCount))).toBeGreaterThan(100);

  const viewport = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    height: document.documentElement.clientHeight,
    scrollHeight: document.documentElement.scrollHeight,
  }));
  expect(viewport.scrollWidth).toBe(viewport.width);
  expect(viewport.scrollHeight).toBe(viewport.height);
  expect(consoleErrors).toEqual([]);
});
