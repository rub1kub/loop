import { expect, test } from '@playwright/test';

test('BANK, DUEL and PROFILE remain usable above the Telegram tab bar', async ({ page }) => {
  const emulateFullscreenControls = () =>
    page.locator('html').evaluate((root) => {
      root.style.setProperty('--tg-content-safe-area-inset-top', '72px');
    });

  await page.goto('/?screen=bank-empty');
  await emulateFullscreenControls();
  await expect(page.getByRole('heading', { name: 'BANK' })).toBeVisible();
  await expect(page.locator('.screen-stage')).toHaveCSS('transform', 'none');
  const headerBox = await page.locator('.mode-header').boundingBox();
  expect(headerBox).not.toBeNull();
  expect(headerBox!.y).toBeGreaterThanOrEqual(100);
  const shellBox = await page.locator('.app-shell').boundingBox();
  const jarBox = await page.locator('.bank-object img').boundingBox();
  expect(shellBox).not.toBeNull();
  expect(jarBox).not.toBeNull();
  expect(
    Math.abs(jarBox!.x + jarBox!.width / 2 - (shellBox!.x + shellBox!.width / 2)),
  ).toBeLessThan(1);
  await page.getByRole('button', { name: 'НАЧАТЬ' }).click();
  await expect(page.locator('.bank-flow-screen')).toHaveCSS('transform', 'none');
  await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'hidden');
  const bankAmount = page.getByLabel('Сумма в GRAM');
  const titleBeforeKeyboard = await page
    .getByRole('heading', { name: 'Новая позиция' })
    .boundingBox();
  const inputBeforeKeyboard = await bankAmount.boundingBox();
  const nextBeforeKeyboard = await page.getByRole('button', { name: /ДАЛЬШЕ/ }).boundingBox();
  await bankAmount.fill('2');
  await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'hidden');
  await page.locator('html').evaluate((root) => {
    root.style.setProperty('--loop-visual-page-top', '180px');
  });
  await expect(page.locator('.app-shell')).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 180)');
  await page.locator('html').evaluate((root) => {
    root.style.setProperty('--loop-visual-page-top', '0px');
  });
  const bankViewport = page.viewportSize()!;
  await page.setViewportSize({ width: bankViewport.width, height: 404 });
  const inputBox = await bankAmount.boundingBox();
  const nextBox = await page.getByRole('button', { name: /ДАЛЬШЕ/ }).boundingBox();
  const closeBox = await page.getByRole('button', { name: 'Закрыть' }).boundingBox();
  const titleBox = await page.getByRole('heading', { name: 'Новая позиция' }).boundingBox();
  expect(inputBox).not.toBeNull();
  expect(nextBox).not.toBeNull();
  expect(closeBox).not.toBeNull();
  expect(titleBox).not.toBeNull();
  expect(titleBeforeKeyboard).not.toBeNull();
  expect(inputBeforeKeyboard).not.toBeNull();
  expect(nextBeforeKeyboard).not.toBeNull();
  expect(closeBox!.y).toBeGreaterThanOrEqual(100);
  expect(titleBox!.y).toBeCloseTo(titleBeforeKeyboard!.y, 0);
  expect(inputBox!.y).toBeCloseTo(inputBeforeKeyboard!.y, 0);
  expect(nextBox!.y).toBeCloseTo(nextBeforeKeyboard!.y, 0);
  await page.getByRole('button', { name: /ДАЛЬШЕ/ }).scrollIntoViewIfNeeded();
  await expect(page.getByRole('button', { name: /ДАЛЬШЕ/ })).toBeVisible();
  await page.setViewportSize(bankViewport);
  await bankAmount.blur();
  await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'hidden');
  await page.getByRole('button', { name: 'Закрыть' }).click();
  await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'visible');
  await page.getByRole('button', { name: 'НАЧАТЬ' }).click();
  await page.getByRole('button', { name: /ДАЛЬШЕ/ }).click();
  await page.getByRole('button', { name: /×2/ }).click();
  await page.getByRole('button', { name: 'ПРОВЕРИТЬ' }).click();
  await expect(page.getByText('4 GRAM')).toBeVisible();
  await expect(page.getByRole('button', { name: 'ПОДТВЕРДИТЬ В TON' })).toBeVisible();

  await page.goto('/?screen=duel-create');
  await emulateFullscreenControls();
  await expect(page.getByRole('heading', { name: 'DUEL' })).toBeVisible();
  expect((await page.locator('.mode-header').boundingBox())!.y).toBeGreaterThanOrEqual(100);
  const stableShellHeight = (await page.locator('.app-shell').boundingBox())!.height;
  const stakeInput = page.locator('.stake-input input');
  await stakeInput.fill('1');
  await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'hidden');
  const initialViewport = page.viewportSize()!;
  await page.setViewportSize({ width: 390, height: 520 });
  expect((await page.locator('.app-shell').boundingBox())!.height).toBe(stableShellHeight);
  await stakeInput.blur();
  await page.setViewportSize(initialViewport);
  await page.getByRole('button', { name: /75%/ }).click();
  await expect(page.getByRole('button', { name: /75%/ })).toHaveClass(/active/);
  await expect(page.locator('.duel-terms')).toContainText(/0[,.]333 GRAM/);
  await expect(page.locator('.duel-terms')).toContainText(/1[,.]333 GRAM/);
  await page.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' }).click();
  await expect(page.getByText('AFK ПОИСК')).toBeVisible();

  await page.goto('/?screen=profile');
  await emulateFullscreenControls();
  await expect(page.getByRole('heading', { name: 'Дмитрий' })).toBeVisible();
  expect((await page.locator('.profile-identity').boundingBox())!.y).toBeGreaterThanOrEqual(104);
  await expect(page.getByText('PLUSH BRICK')).toBeVisible();
  const tabBar = page.getByRole('navigation', { name: 'Основная навигация' });
  const tabBox = await tabBar.boundingBox();
  const profileBox = await page.locator('.screen-stage').boundingBox();
  expect(tabBox).not.toBeNull();
  expect(profileBox).not.toBeNull();
  expect(profileBox!.y + profileBox!.height).toBeLessThanOrEqual(tabBox!.y + 1);
});
