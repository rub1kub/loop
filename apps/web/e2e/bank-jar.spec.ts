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

test('BANK stays centred on a Fold cover screen with an asymmetric safe area', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto('/?screen=bank-active');
  await expect(page.locator('.bank-object')).toBeVisible();
  await page.locator('.announcement-close').click();
  await page.locator('html').evaluate((root) => {
    root.style.setProperty('--tg-content-safe-area-inset-left', '24px');
    root.style.setProperty('--tg-content-safe-area-inset-right', '0px');
  });
  await page.waitForTimeout(1_200);

  const layout = await page.evaluate(() => {
    const centre = (selector: string) => {
      const bounds = document.querySelector<HTMLElement>(selector)!.getBoundingClientRect();
      return bounds.left + bounds.width / 2;
    };
    return {
      viewport: window.innerWidth / 2,
      shell: centre('.app-shell'),
      header: centre('.bank-screen .mode-header'),
      object: centre('.bank-object'),
      vessel: centre('.bank-vessel'),
      state: centre('.bank-state'),
      paddingLeft: Number.parseFloat(
        getComputedStyle(document.querySelector('.bank-screen')!).paddingLeft,
      ),
      paddingRight: Number.parseFloat(
        getComputedStyle(document.querySelector('.bank-screen')!).paddingRight,
      ),
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    };
  });

  expect(layout.overflow).toBeLessThanOrEqual(0);
  expect(layout.paddingLeft).toBe(layout.paddingRight);
  expect(layout.paddingLeft).toBeGreaterThanOrEqual(40);
  for (const key of ['shell', 'header', 'object', 'vessel', 'state'] as const) {
    expect(layout[key], `${key} must stay on the physical viewport centre`).toBeCloseTo(
      layout.viewport,
      0,
    );
  }
  await page.screenshot({ path: testInfo.outputPath('fold-cover-bank.png') });
});
