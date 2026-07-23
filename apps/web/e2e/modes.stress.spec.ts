import { expect, test } from '@playwright/test';

const modes = [
  { name: 'compact phone', width: 320, height: 568, safeTop: 56 },
  { name: 'regular phone', width: 390, height: 844, safeTop: 56 },
  { name: 'fullscreen phone', width: 390, height: 844, safeTop: 72 },
  { name: 'desktop mini app', width: 430, height: 800, safeTop: 24 },
];

for (const mode of modes) {
  test(`${mode.name} survives repeated keyboard and DUEL state transitions`, async ({ page }) => {
    await page.setViewportSize({ width: mode.width, height: mode.height });
    await page.goto('/?screen=duel-create');
    await page.locator('html').evaluate((root, safeTop) => {
      root.style.setProperty('--tg-content-safe-area-inset-top', `${safeTop}px`);
    }, mode.safeTop);

    const viewport = await page.locator('meta[name="viewport"]').getAttribute('content');
    expect(viewport).toContain('maximum-scale=1');
    expect(viewport).toContain('user-scalable=no');
    await expect(page.locator('body')).toHaveCSS('user-select', 'none');
    await expect(page.locator('body')).toHaveCSS('touch-action', 'pan-y');

    const noHorizontalOverflow = await page
      .locator('html')
      .evaluate((root) => root.scrollWidth <= root.clientWidth);
    expect(noHorizontalOverflow).toBe(true);
    const screenPaddingTop = await page
      .locator('.duel-screen')
      .evaluate((screen) => Number.parseFloat(getComputedStyle(screen).paddingTop));
    expect(screenPaddingTop).toBeGreaterThanOrEqual(mode.safeTop + 29);

    const input = page.locator('.stake-input input');
    await expect(input).toHaveCSS('user-select', 'none');
    await input.fill('2');
    const stableHeight = (await page.locator('.app-shell').boundingBox())!.height;
    const keyboardHeight = Math.max(360, mode.height - 220);
    for (let iteration = 0; iteration < 20; iteration += 1) {
      await page.setViewportSize({ width: mode.width, height: keyboardHeight });
      expect((await page.locator('.app-shell').boundingBox())!.height).toBeCloseTo(stableHeight, 0);
      await page.setViewportSize({ width: mode.width, height: mode.height });
      expect((await page.locator('.app-shell').boundingBox())!.height).toBeCloseTo(stableHeight, 0);
    }
    await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'hidden');
    await input.blur();

    for (let transition = 0; transition < 20; transition += 1) {
      const tab = transition % 2 === 0 ? 'BANK' : 'DUEL';
      await page.getByRole('button', { name: tab, exact: true }).click();
      await expect
        .poll(() => page.locator('.app-shell').evaluate((shell) => shell.scrollTop))
        .toBe(0);
    }

    const interactionsBlocked = await page.locator('body').evaluate((body) => {
      const select = new Event('selectstart', { bubbles: true, cancelable: true });
      const context = new Event('contextmenu', { bubbles: true, cancelable: true });
      body.dispatchEvent(select);
      body.dispatchEvent(context);
      return { selection: select.defaultPrevented, context: context.defaultPrevented };
    });
    expect(interactionsBlocked).toEqual({ selection: true, context: true });

    const findOpponent = page.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА', exact: true });
    await expect(findOpponent).toBeVisible();
    await findOpponent.click();
    await expect(page.getByText('AFK ПОИСК')).toBeVisible();
    await expect(page.getByText('Ищем равную ставку. Можно закрыть Mini App.')).toBeVisible();
    await expect(page.getByText('ДО ИСТЕЧЕНИЯ')).toBeVisible();
    await expect(page.getByRole('button', { name: 'ОСТАНОВИТЬ ПОИСК' })).toBeVisible();
  });
}
