import { expect, test } from '@playwright/test';

test('onboarding, BANK, DUEL and PROFILE remain usable on a phone viewport', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByLabel('LOOP загружается')).toBeVisible();
  await expect(page.getByRole('heading', { name: /Один цикл/ })).toBeVisible({ timeout: 5_000 });

  for (let pageIndex = 0; pageIndex < 4; pageIndex += 1) {
    await page.getByRole('button', { name: 'ДАЛЬШЕ' }).click();
  }
  await page.getByRole('button', { name: 'ВОЙТИ' }).click();

  await expect(page.getByRole('heading', { name: 'BANK' })).toBeVisible();
  await page.getByRole('button', { name: 'НАЧАТЬ' }).click();
  await page.getByLabel('Цель в GRAM').fill('40');
  await page.getByRole('button', { name: 'СОХРАНИТЬ' }).click();
  await page.screenshot({ path: '../../output/playwright/loop-bank.png', fullPage: true });

  await page.getByRole('button', { name: /DUEL/ }).click();
  await expect(page.getByRole('heading', { name: 'DUEL' })).toBeVisible();
  await page.getByRole('button', { name: '75%' }).click();
  await expect(page.getByRole('button', { name: '75%' })).toHaveClass(/active/);
  await expect(page.getByRole('button', { name: '50%' })).not.toHaveClass(/active/);
  await page.getByLabel('Общий пул в GRAM').fill('8');
  await expect(page.getByText('6 GRAM')).toBeVisible();
  const state = await page.evaluate(() => window.render_game_to_text?.());
  expect(JSON.parse(state ?? '{}')).toMatchObject({ chancePercent: 75, opponentChancePercent: 25 });
  await page.evaluate(() => window.advanceTime?.(1_000));
  await page.screenshot({ path: '../../output/playwright/loop-duel.png', fullPage: true });

  await page.getByRole('button', { name: /PROFILE/ }).click();
  await expect(page.getByRole('heading', { name: 'Дмитрий' })).toBeVisible();
  await expect(page.getByText('PLUSH BRICK')).toBeVisible();
  await page.screenshot({ path: '../../output/playwright/loop-profile.png', fullPage: true });
});
