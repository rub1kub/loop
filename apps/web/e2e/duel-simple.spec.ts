import { expect, test } from '@playwright/test';

test('DUEL keeps the main decision simple and progressively reveals the rest', async ({ page }) => {
  await page.goto('/?screen=duel-create');

  await expect(page.getByRole('heading', { name: 'DUEL' })).toBeVisible();
  await expect(page.getByLabel('Ставка в GRAM')).toBeVisible();
  await expect(page.getByText('50/50', { exact: true })).toBeVisible();
  await expect(page.getByText('РАВНЫЙ СТАРТ')).toBeVisible();
  await expect(page.getByText(/Соперник внесёт столько же/)).toBeVisible();
  await expect(page.getByText('Комиссия')).toBeHidden();
  await expect(page.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' })).toBeVisible();

  await page.getByText('ПРАВИЛА').click();
  await expect(page.getByText('Комиссия')).toBeVisible();
  await expect(page.getByText('Общий банк', { exact: true })).toBeVisible();

  await page.goto('/?screen=duel-boost');

  await expect(page.getByText('60 / 40')).toBeVisible();
  await expect(page.getByText('ДО КОНЦА СТАВОК')).toBeVisible();
  await expect(page.getByLabel('Сумма усиления в GRAM')).toHaveCount(0);
  await expect(page.getByText('ХОД ДУЭЛИ')).toBeHidden();

  await page.getByText('ПРАВИЛА').click();
  await expect(page.getByText('ХОД ДУЭЛИ')).toBeVisible();
  await expect(page.getByText(/\+0[,.]5 GRAM · 60[,.]0%/)).toBeVisible();
  await page.getByText('ПРАВИЛА').click();

  await page.getByRole('button', { name: 'УВЕЛИЧИТЬ ШАНС' }).click();
  await expect(page.getByText('ПРАВИЛА')).toHaveCount(0);
  await expect(page.getByLabel('Сумма усиления в GRAM')).toHaveValue('0.5');
  await expect(page.getByText(/Твоя доля станет/)).toContainText('66,7%');
  await expect(page.getByRole('button', { name: 'ДОБАВИТЬ GRAM' })).toBeVisible();

  const action = await page.getByRole('button', { name: 'ДОБАВИТЬ GRAM' }).boundingBox();
  const tabBar = await page.locator('.tab-bar').boundingBox();
  expect(action).not.toBeNull();
  expect(tabBar).not.toBeNull();
  expect(action!.y + action!.height).toBeLessThan(tabBar!.y);

  await page.getByRole('button', { name: 'НЕ СЕЙЧАС' }).click();
  await expect(page.getByLabel('Сумма усиления в GRAM')).toHaveCount(0);
  await expect(page.getByText('ПРАВИЛА')).toBeVisible();
});
