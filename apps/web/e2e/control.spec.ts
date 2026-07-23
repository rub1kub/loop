import { expect, test } from '@playwright/test';

const owner = `0:${'22'.repeat(32)}`;
const contractAddress = `0:${'11'.repeat(32)}`;

test('browser control is a desktop site independent from Telegram Mini App', async ({
  page,
}, testInfo) => {
  await page.route('**/api/v1/control/session', async (route) => {
    await route.fulfill({ json: { wallet: owner } });
  });
  await page.route('**/api/v1/control/overview', async (route) => {
    await route.fulfill({
      json: {
        wallet: owner,
        application: {
          maintenance_enabled: false,
          bank_enabled: true,
          duel_enabled: true,
          updated_at: '2026-07-23T18:00:00Z',
        },
        metrics: {
          users: 142,
          bank_positions: 38,
          active_bank_positions: 9,
          duel_offers: 71,
          active_duels: 4,
          worker_healthy: true,
        },
        contracts: [
          {
            mode: 'bank',
            address: contractAddress,
            network: -3,
            status: 'active',
            code_hash: 'AA'.repeat(32),
            code_hash_matches: true,
            balance_nano: 14_200_000_000,
            locked_nano: 8_400_000_000,
            withdrawable_nano: 5_600_000_000,
            owner,
            treasury: owner,
            fee_bps: 100,
            paused: false,
            owner_matches_session: true,
            extended_controls: true,
            last_transaction_hash: null,
            error: null,
          },
          {
            mode: 'duel',
            address: `0:${'33'.repeat(32)}`,
            network: -3,
            status: 'active',
            code_hash: 'BB'.repeat(32),
            code_hash_matches: true,
            balance_nano: 3_500_000_000,
            locked_nano: 2_000_000_000,
            withdrawable_nano: 1_300_000_000,
            owner,
            treasury: owner,
            fee_bps: 250,
            paused: true,
            owner_matches_session: true,
            extended_controls: true,
            last_transaction_hash: null,
            error: null,
          },
        ],
        audit: [
          {
            id: 'audit-1',
            action: 'duel.pause',
            target: contractAddress,
            status: 'confirmed',
            created_at: '2026-07-23T18:02:00Z',
          },
        ],
        generated_at: '2026-07-23T18:03:00Z',
      },
    });
  });
  await page.route('**/api/v1/control/application', async (route) => {
    const update = route.request().postDataJSON() as Record<string, boolean>;
    await route.fulfill({
      json: {
        maintenance_enabled: update.maintenance_enabled ?? false,
        bank_enabled: update.bank_enabled ?? true,
        duel_enabled: update.duel_enabled ?? true,
        updated_at: '2026-07-23T18:04:00Z',
      },
    });
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/control');

  await expect(page).toHaveTitle('LOOP — Панель управления');
  await expect(page.getByRole('heading', { name: 'LOOP работает частично' })).toBeVisible();
  await expect(page.getByText('142')).toBeVisible();
  await expect(page.getByRole('button', { name: /Пополнить резерв/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Вывести доступное/ })).toBeVisible();
  await expect(page.locator('.service-money').getByText('Участникам', { exact: true })).toHaveCount(
    2,
  );
  await expect(
    page.locator('.service-money').getByText('Можно вывести', { exact: true }),
  ).toHaveCount(2);
  await expect(page.locator('.tab-bar')).toHaveCount(0);
  await expect(page.locator('.app-shell')).toHaveCount(0);
  await expect(page.locator('meta[name="viewport"]')).not.toHaveAttribute(
    'content',
    /user-scalable=no/,
  );

  const shell = await page.locator('.control-shell').boundingBox();
  const header = await page.locator('.control-header').boundingBox();
  expect(shell).not.toBeNull();
  expect(header).not.toBeNull();
  expect(header!.height).toBeLessThan(90);
  expect(shell!.width).toBe(1440);

  await page.getByRole('button', { name: /Пополнить резерв/ }).click();
  await expect(page.getByRole('heading', { name: 'Пополнить резерв' })).toBeVisible();
  await expect(page.getByText('Кошелёк покажет точную сумму перед подтверждением.')).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click();

  await page.getByRole('button', { name: /Расширенное управление/ }).click();
  const bankControls = page.locator('#contract-bank');
  await expect(bankControls.getByRole('heading', { name: 'BANK' })).toBeVisible();
  await bankControls.getByText('ОПЕРАЦИИ И ПРАВИЛА').click();
  await expect(bankControls.getByText('Вывести доступное, GRAM')).toBeVisible();
  await expect(bankControls.getByText('Комиссия, %')).toBeVisible();
  await expect(bankControls.getByText(/Зарезервированные участникам средства/)).toBeVisible();
  await expect(page.getByText('базисные пункты')).toHaveCount(0);

  if (testInfo.project.name === 'desktop-chromium') {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: '../../output/playwright/control-desktop.png',
      fullPage: true,
    });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'LOOP работает частично' })).toBeVisible();
  await page.getByRole('button', { name: /Вывести доступное/ }).click();
  await expect(page.getByRole('heading', { name: 'Вывести доступное' })).toBeVisible();
  await expect(page.getByText('Сначала поставь BANK на паузу')).toBeVisible();
  const sheet = await page.locator('.quick-sheet').boundingBox();
  const viewportHeight = await page.evaluate(() => window.innerHeight);
  expect(sheet).not.toBeNull();
  expect(sheet!.width).toBe(390);
  expect(sheet!.y + sheet!.height).toBeLessThanOrEqual(viewportHeight + 1);
  if (testInfo.project.name === 'mobile-webkit') {
    await page.screenshot({
      path: '../../output/playwright/control-mobile.png',
      fullPage: false,
    });
  }
});
