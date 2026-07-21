import { expect, test } from '@playwright/test';

test('BANK, DUEL and PROFILE remain usable above the Telegram tab bar', async ({ page }) => {
  await page.goto('/?screen=bank-empty');
  await expect(page.getByRole('heading', { name: 'BANK' })).toBeVisible();
  await page.getByRole('button', { name: 'НАЧАТЬ' }).click();
  await page.getByLabel('Сумма в GRAM').fill('2');
  await page.getByRole('button', { name: /ДАЛЬШЕ/ }).click();
  await page.getByRole('button', { name: /×2/ }).click();
  await page.getByRole('button', { name: 'ПРОВЕРИТЬ' }).click();
  await expect(page.getByText('4 GRAM')).toBeVisible();
  await expect(page.getByRole('button', { name: 'ПОДТВЕРДИТЬ В TON' })).toBeVisible();

  await page.goto('/?screen=duel-create');
  await expect(page.getByRole('heading', { name: 'DUEL' })).toBeVisible();
  await page.locator('.stake-input input').fill('1');
  await page.getByRole('button', { name: /75%/ }).click();
  await expect(page.getByRole('button', { name: /75%/ })).toHaveClass(/active/);
  await expect(page.locator('.duel-terms')).toContainText(/0[,.]333 GRAM/);
  await expect(page.locator('.duel-terms')).toContainText(/1[,.]333 GRAM/);
  await page.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' }).click();
  await expect(page.getByText('AFK ПОИСК')).toBeVisible();

  await page.goto('/?screen=profile');
  await expect(page.getByRole('heading', { name: 'Дмитрий' })).toBeVisible();
  await expect(page.getByText('PLUSH BRICK')).toBeVisible();
  const tabBar = page.getByRole('navigation', { name: 'Основная навигация' });
  const tabBox = await tabBar.boundingBox();
  const profileBox = await page.locator('.screen-stage').boundingBox();
  expect(tabBox).not.toBeNull();
  expect(profileBox).not.toBeNull();
  expect(profileBox!.y + profileBox!.height).toBeLessThanOrEqual(tabBox!.y + 1);
});
