import { expect, test } from '@playwright/test';

test('DUEL keeps the main decision simple and progressively reveals the rest', async ({ page }) => {
  await page.goto('/?screen=duel-create');

  const announcement = page.getByRole('dialog', { name: 'Сообщение из канала' });
  await expect(announcement).toBeVisible();
  await announcement.getByRole('button', { name: 'Закрыть' }).click();

  await expect(page.getByRole('heading', { name: 'DUEL' })).toBeVisible();
  await expect(page.getByLabel('Ставка в GRAM')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Твой шанс 50 процентов' })).toBeVisible();
  await expect(page.getByText(/Соперник внесёт столько же/)).toBeVisible();
  await expect(page.getByText('Комиссия')).toBeHidden();
  await expect(page.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' })).toBeVisible();

  await page.getByText('ПРАВИЛА').click();
  await expect(page.getByText('Комиссия')).toBeVisible();
  await expect(page.getByText('Общий банк', { exact: true })).toBeVisible();

  await page.goto('/?screen=duel-boost');

  await expect(page.locator('.duel-orbit')).toHaveAttribute('aria-label', 'Твой шанс 60 процентов');
  await expect(page.getByText('ТЫ').locator('..').getByText('60%')).toBeVisible();
  await expect(page.getByText('СОПЕРНИК').locator('..').getByText('40%')).toBeVisible();
  await expect(page.locator('.duel-orbit-centre')).toContainText('2,5');
  await expect(page.getByText('ДО КОНЦА СТАВОК')).toBeVisible();
  await expect(page.getByLabel('Сумма усиления в GRAM')).toHaveCount(0);
  await expect(page.getByText(/Ты усилился: \+0[,.]5 GRAM/)).toBeVisible();

  await page.getByRole('button', { name: 'УВЕЛИЧИТЬ ШАНС' }).click();
  await expect(page.getByLabel('Сумма усиления в GRAM')).toHaveValue('0.5');
  await expect(page.getByText('Станет', { exact: true }).locator('..')).toContainText('66,7%');
  const addGram = page.getByRole('button', { name: /^ДОБАВИТЬ .* GRAM$/ });
  await expect(addGram).toBeVisible();

  const action = await addGram.boundingBox();
  const tabBar = await page.locator('.tab-bar').boundingBox();
  expect(action).not.toBeNull();
  expect(tabBar).not.toBeNull();
  expect(action!.y + action!.height).toBeLessThan(tabBar!.y);

  await page.getByRole('button', { name: 'НЕ СЕЙЧАС' }).click();
  await expect(page.getByLabel('Сумма усиления в GRAM')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'УВЕЛИЧИТЬ ШАНС' })).toBeVisible();

  await page.goto('/?screen=duel-result');
  const resolvedOrbit = page.locator('.duel-orbit.phase-won');
  await expect(resolvedOrbit).toHaveAttribute('aria-label', 'Победа: банк твой');
  await expect(resolvedOrbit.locator('.duel-orbit-needle')).toHaveCount(1);
  await expect(resolvedOrbit.getByText('ОПРЕДЕЛЯЕМ ПОБЕДИТЕЛЯ')).toBeVisible();
  await expect(resolvedOrbit.getByText('ПОБЕДА')).toBeVisible();
  await expect(resolvedOrbit.getByText('+0,95 GRAM')).toBeVisible();
  await expect(resolvedOrbit.getByText('РЕЗУЛЬТАТ ПОДТВЕРЖДЁН')).toBeVisible();
});
