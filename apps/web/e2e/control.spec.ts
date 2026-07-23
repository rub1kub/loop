import { expect, test } from '@playwright/test';

const owner = `0:${'22'.repeat(32)}`;
const contractAddress = `0:${'11'.repeat(32)}`;

test('browser control is a desktop site independent from Telegram Mini App', async ({ page }) => {
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
  await expect(page.getByRole('heading', { name: 'Состояние LOOP' })).toBeVisible();
  await expect(page.getByText('142')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'BANK' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'DUEL' })).toBeVisible();
  await expect(page.locator('.tab-bar')).toHaveCount(0);
  await expect(page.locator('.app-shell')).toHaveCount(0);
  await expect(page.locator('meta[name="viewport"]')).not.toHaveAttribute(
    'content',
    /user-scalable=no/,
  );

  const shell = await page.locator('.control-shell').boundingBox();
  const rail = await page.locator('.control-rail').boundingBox();
  expect(shell).not.toBeNull();
  expect(rail).not.toBeNull();
  expect(rail!.width).toBeGreaterThan(200);
  expect(shell!.width).toBe(1440);

  await page.getByText('РЕЗЕРВ И НАСТРОЙКИ').first().click();
  await expect(page.getByText('Вывести свободный резерв, GRAM').first()).toBeVisible();
  await expect(page.getByText(/Средства участников недоступны/).first()).toBeVisible();

  await page.screenshot({
    path: '../../output/playwright/control-desktop.png',
    fullPage: true,
  });
});
