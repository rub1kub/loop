import { expect, test } from '@playwright/test';

test('BANK, DUEL, РЕЙТИНГ and ПРОФИЛЬ remain usable above the Telegram tab bar', async ({
  page,
}) => {
  test.slow();

  const emulateFullscreenControls = () =>
    page.locator('html').evaluate((root) => {
      root.style.setProperty('--tg-content-safe-area-inset-top', '72px');
    });

  await page.goto('/?screen=bank-empty');
  await emulateFullscreenControls();
  await expect(page.getByRole('heading', { name: 'BANK' })).toBeVisible();
  await expect(page.getByText(/Вносишь GRAM и выбираешь цель/)).toHaveCount(0);
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
  await expect(page.getByRole('heading', { name: 'Войди в очередь.' })).toBeVisible();
  await expect(
    page.getByText('Выплата зависит от новых взносов и не гарантирована.'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'СОЗДАТЬ ПОЗИЦИЮ', exact: true }).click();
  await expect(page.locator('.bank-flow-screen')).toHaveCSS('transform', 'none');
  await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'hidden');
  await expect.poll(() => page.locator('.app-shell').evaluate((shell) => shell.scrollTop)).toBe(0);
  const bankAmount = page.getByLabel('Сумма в GRAM');
  const titleBeforeKeyboard = await page
    .getByRole('heading', { name: 'Новая позиция' })
    .boundingBox();
  const inputBeforeKeyboard = await bankAmount.boundingBox();
  const nextBeforeKeyboard = await page.getByRole('button', { name: /ДАЛЬШЕ/ }).boundingBox();
  await bankAmount.fill('2');
  await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'hidden');
  const compensatedTransform = await page.locator('.app-shell').evaluate((shell) => {
    document.documentElement.classList.add('keyboard-open');
    document.documentElement.style.setProperty('--loop-visual-page-top', '180px');
    return getComputedStyle(shell).transform;
  });
  expect(compensatedTransform).toBe('matrix(1, 0, 0, 1, 0, 180)');
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
  await page.getByRole('button', { name: 'СОЗДАТЬ ПОЗИЦИЮ', exact: true }).click();
  await page.getByRole('button', { name: /ДАЛЬШЕ/ }).click();
  await expect.poll(() => page.locator('.app-shell').evaluate((shell) => shell.scrollTop)).toBe(0);
  await page.getByRole('button', { name: /×2/ }).click();
  await page.getByRole('button', { name: 'ПРОВЕРИТЬ' }).click();
  await expect.poll(() => page.locator('.app-shell').evaluate((shell) => shell.scrollTop)).toBe(0);
  expect(
    (await page.getByRole('heading', { name: 'Новая позиция' }).boundingBox())!.y,
  ).toBeGreaterThanOrEqual(100);
  await expect(page.getByText('4 GRAM')).toBeVisible();
  await expect(
    page.getByText(/Выплата зависит от будущих взносов и может не наступить/i),
  ).toBeVisible();
  await expect(page.locator('.technical-details .disclosure-open-label')).toBeVisible();
  await expect(page.getByRole('button', { name: 'ПОДПИСАТЬ В КОШЕЛЬКЕ' })).toBeVisible();

  await page.goto('/?screen=bank-active');
  await emulateFullscreenControls();
  await expect(
    page.getByRole('button', {
      name: 'Открыть позицию BANK, собрано 62%',
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText(/Собрано 1[,.]86 из 3 GRAM/)).toBeVisible();
  expect(
    await page
      .getByTestId('bank-sand-level')
      .evaluate((element) => element.style.getPropertyValue('--bank-fill')),
  ).toBe('62%');

  await page.goto('/?screen=duel-create');
  await emulateFullscreenControls();
  await expect(page.getByRole('heading', { name: 'DUEL' })).toBeVisible();
  expect((await page.locator('.mode-header').boundingBox())!.y).toBeGreaterThanOrEqual(100);
  const stableShellHeight = (await page.locator('.app-shell').boundingBox())!.height;
  const stakeInput = page.getByLabel('Ставка в GRAM');
  await expect(page.locator('.duel-stage')).toHaveCount(0);
  await expect(page.getByText('ВВЕДИ СУММУ')).toBeVisible();
  await expect(page.getByText('Ставки', { exact: true })).toBeVisible();
  await expect(page.locator('.stake-input > div')).toHaveCSS('border-top-width', '1px');
  await expect(page.locator('.stake-input > div')).toHaveCSS('border-radius', '16px');
  await stakeInput.fill('1');
  await expect(page.locator('.stake-input > div')).toHaveCSS(
    'border-top-color',
    'rgb(245, 245, 247)',
  );
  await expect(page.locator('.tab-bar')).toHaveCSS('visibility', 'hidden');
  const initialViewport = page.viewportSize()!;
  await page.setViewportSize({ width: 390, height: 520 });
  expect((await page.locator('.app-shell').boundingBox())!.height).toBe(stableShellHeight);
  await stakeInput.blur();
  await page.setViewportSize(initialViewport);
  await expect(page.getByText('50/50', { exact: true })).toBeVisible();
  await expect(page.getByText('РАВНЫЙ СТАРТ')).toBeVisible();
  await expect(page.getByText('Комиссия')).toBeHidden();
  await expect(page.getByText(/Соперник внесёт столько же/i)).toBeVisible();
  expect(
    await page
      .locator('.duel-simple-rule')
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
  ).toBeGreaterThanOrEqual(12);
  await expect(page.locator('.duel-rules .disclosure-open-label')).toBeVisible();
  await expect(page.getByRole('button', { name: /ПРИГЛАСИТЬ СРАЗИТЬСЯ/ })).toBeVisible();
  const duelDisclosure = page.locator('.duel-rules summary');
  await duelDisclosure.focus();
  await expect(duelDisclosure).toHaveCSS('outline-color', 'rgb(245, 245, 247)');
  await page.getByText('ПРАВИЛА').click();
  await expect(page.locator('.duel-rules .disclosure-close-label')).toBeVisible();
  await expect(page.getByText('Общий банк')).toBeVisible();
  await expect(page.getByText('2 GRAM')).toBeVisible();
  await page.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' }).click();
  await expect(page.getByText('ИЩЕМ СОПЕРНИКА')).toBeVisible();
  await expect(page.getByRole('button', { name: 'ПРИГЛАСИТЬ' })).toBeVisible();
  await expect(page.getByText('ПОИСК ИДЁТ')).toBeVisible();
  await expect(page.getByRole('button', { name: 'ОСТАНОВИТЬ ПОИСК' })).toBeVisible();

  await page.goto('/?screen=duel-boost');
  await emulateFullscreenControls();
  await expect(page.getByText('60 / 40')).toBeVisible();
  await expect(page.getByText('ДО КОНЦА СТАВОК')).toBeVisible();
  await expect(page.getByLabel('Сумма усиления в GRAM')).toHaveCount(0);
  await page.getByRole('button', { name: 'УВЕЛИЧИТЬ ШАНС' }).click();
  await expect(page.getByLabel('Сумма усиления в GRAM')).toBeVisible();
  await expect(page.getByText(/Твоя доля станет/)).toContainText('66,7%');
  await expect(page.getByRole('button', { name: 'ДОБАВИТЬ GRAM' })).toBeVisible();
  await page.getByRole('button', { name: 'НЕ СЕЙЧАС' }).click();
  await page.getByText('ПРАВИЛА').click();
  await expect(page.getByText('ХОД ДУЭЛИ')).toBeVisible();
  await expect(page.getByText(/\+0[,.]5 GRAM · 60[,.]0%/)).toBeVisible();

  await page.goto('/?screen=rating');
  await emulateFullscreenControls();
  await expect(page.getByRole('heading', { name: 'РЕЙТИНГ' })).toBeVisible();
  await expect(page.getByText('ТВОЙ СЧЁТ LOOP')).toBeVisible();
  await expect(page.getByText('685').first()).toBeVisible();
  await expect(page.getByText('315 ДО УРОВНЯ LOOP')).toBeVisible();
  await expect(page.locator('.rating-progress')).toBeVisible();
  await expect(page.getByText(/Главный фактор:/)).toBeHidden();
  await expect(page.locator('.rating-details .disclosure-open-label')).toHaveCount(1);
  await page.getByText('МОЯ СТАТИСТИКА').click();
  await expect(page.getByText(/Главный фактор:/)).toBeVisible();
  await expect(
    page.getByText('Счёт отражает участие и надёжность.', { exact: false }),
  ).toBeVisible();
  expect(
    await page
      .locator('.rating-explainer')
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
  ).toBeGreaterThanOrEqual(11);
  await page.getByRole('button', { name: /ДРУЗЬЯ/ }).click();
  await expect(page.locator('.rating-list')).toContainText('Alex');

  await page.goto('/?screen=profile');
  await emulateFullscreenControls();
  await expect(page.getByRole('heading', { name: 'Дмитрий' })).toBeVisible();
  expect((await page.locator('.profile-identity').boundingBox())!.y).toBeGreaterThanOrEqual(104);
  await expect(page.getByText('СЧЁТ LOOP')).toBeVisible();
  await expect(page.getByText('ПОДКЛЮЧЕНИЕ И ИСТОРИЯ')).toBeVisible();
  await expect(page.locator('.profile-proof-details .disclosure-open-label')).toBeVisible();
  expect(
    await page
      .locator('.profile-row small')
      .first()
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
  ).toBeGreaterThanOrEqual(11);
  await expect(page.getByText('PLUSH BRICK')).not.toBeVisible();
  await page.getByText('ПОДКЛЮЧЕНИЕ И ИСТОРИЯ').click();
  await expect(page.locator('.profile-proof-details .disclosure-close-label')).toBeVisible();
  await expect(page.getByText('PLUSH BRICK')).toBeVisible();
  const tabBar = page.getByRole('navigation', { name: 'Основная навигация' });
  const tabBox = await tabBar.boundingBox();
  const profileBox = await page.locator('.screen-stage').boundingBox();
  expect(tabBox).not.toBeNull();
  expect(profileBox).not.toBeNull();
  expect(profileBox!.y + profileBox!.height).toBeLessThanOrEqual(tabBox!.y + 1);
  await expect(page.locator('body')).not.toContainText(
    /ON-CHAIN|PROOFS?|TESTNET|AFK|MINI APP|SETTLEMENT|HOLDER|JETTON|POINTS|LOOP SCORE|RATING|PROFILE|SEASON/i,
  );

  await page.goto('/?screen=settings');
  const vibration = page.getByRole('switch', { name: 'Вибрация' });
  await expect(vibration).toBeChecked();
  await vibration.click();
  await expect(vibration).not.toBeChecked();
  await page.reload();
  await expect(page.getByRole('switch', { name: 'Вибрация' })).not.toBeChecked();
});
