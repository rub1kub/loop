import { expect, test } from '@playwright/test';

test('a failed pixel stylesheet cannot prevent the main app from opening', async ({ page }) => {
  await page.route('**/src/features/pixels/pixels.css*', (route) =>
    route.request().resourceType() === 'stylesheet' ? route.abort() : route.continue(),
  );
  await page.goto('/?screen=bank-closed');
  await expect(page.getByRole('button', { name: 'BANK', exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-loop-pixel-styles', 'unavailable');
  await expect(page.getByRole('button', { name: 'ПОЛОТНО', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'ПРОФИЛЬ', exact: true }).click();
  await expect(page.getByRole('button', { name: 'ПРОФИЛЬ', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
});

test('draw, cooldown, pan, share and return to the existing screen', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/?screen=pixels');
  await expect(page.getByRole('heading', { name: 'ПОЛОТНО', exact: true })).toBeVisible();
  const game = () =>
    page.evaluate(
      () =>
        JSON.parse(window.render_game_to_text!()) as {
          revision: number;
          selected: { x: number; y: number };
          ready_in_seconds: number;
        },
    );
  const before = await game();
  await page.getByRole('button', { name: 'Выбрать цвет', exact: true }).click();
  await page.getByRole('button', { name: 'Красный', exact: true }).click();
  const canvas = page.getByTestId('pixel-canvas');
  const bounds = (await canvas.boundingBox())!;
  await canvas.click({ position: { x: bounds.width * 0.35, y: bounds.height * 0.55 } });
  await page.getByRole('button', { name: 'ПОСТАВИТЬ ПИКСЕЛЬ', exact: true }).click();
  await expect.poll(async () => (await game()).revision).toBe(before.revision + 1);
  await expect(page.getByRole('button', { name: /СЛЕДУЮЩИЙ ЧЕРЕЗ/ })).toBeDisabled();
  const selected = (await game()).selected;
  const panBefore = await canvas.getAttribute('data-pan-x');
  await page.mouse.move(bounds.x + bounds.width * 0.6, bounds.y + bounds.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * 0.8, bounds.y + bounds.height * 0.7, {
    steps: 8,
  });
  await page.mouse.up();
  expect((await game()).selected).toEqual(selected);
  expect(await canvas.getAttribute('data-pan-x')).not.toBe(panBefore);
  await page.evaluate(async () => {
    await window.advanceTime?.(2000);
  });
  await expect.poll(async () => (await game()).ready_in_seconds).toBe(0);
  await page.getByRole('button', { name: 'Выбрать цвет', exact: true }).click();
  await page.getByRole('button', { name: 'Синий', exact: true }).click();
  await page.getByRole('button', { name: 'ПОСТАВИТЬ ПИКСЕЛЬ', exact: true }).click();
  await expect.poll(async () => (await game()).revision).toBe(before.revision + 2);
  expect((await game()).ready_in_seconds).toBeLessThanOrEqual(2);
  await page.getByRole('button', { name: 'Поделиться полотном' }).click();
  await expect(page.getByText('Карточка фрагмента готова')).toBeVisible();
  await page.getByRole('button', { name: 'О полотне', exact: true }).click();
  await expect(page.getByText('COMICS CREW', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть подробности' }).click();
  await page.getByRole('button', { name: 'В центр полотна' }).click();
  await page.screenshot({ path: `../../output/pixels/${testInfo.project.name}-drawing.png` });
  await page.getByRole('button', { name: 'Закрыть полотно', exact: true }).click();
  const announcement = page.getByRole('dialog', { name: 'Сообщение из канала' });
  if (await announcement.isVisible())
    await announcement.getByRole('button', { name: 'Закрыть', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
  await expect(page.getByTestId('pixel-background')).toBeVisible();
  await page.getByRole('button', { name: 'КОМАНДЫ', exact: true }).click();
  await page.getByRole('button', { name: 'ПОЛОТНО', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'ПОЛОТНО', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть полотно', exact: true }).click();
  await expect(page.getByRole('button', { name: 'КОМАНДЫ', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  expect(errors).toEqual([]);
});

test('two-finger zoom changes the canvas without painting or zooming the page', async ({
  page,
  browserName,
}) => {
  test.skip(
    browserName !== 'chromium',
    'Native two-touch injection is available through Chromium CDP',
  );
  await page.goto('/?screen=pixels');
  const canvas = page.getByTestId('pixel-canvas');
  await expect(canvas).toHaveAttribute('data-zoom', '1.000');
  const bounds = (await canvas.boundingBox())!;
  const center = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
  const session = await page.context().newCDPSession(page);
  const touches = (gap: number) => [
    { id: 0, x: center.x - gap, y: center.y, radiusX: 5, radiusY: 5, force: 1 },
    { id: 1, x: center.x + gap, y: center.y, radiusX: 5, radiusY: 5, force: 1 },
  ];
  await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: touches(25) });
  for (const gap of [40, 60, 90])
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: touches(gap),
    });
  await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  expect(Number(await canvas.getAttribute('data-zoom'))).toBeGreaterThan(2);
  expect(await page.evaluate(() => window.visualViewport?.scale)).toBe(1);
  expect(await page.evaluate(() => JSON.parse(window.render_game_to_text!()).revision)).toBe(64);
  await session.detach();
});

test('background and drawing controls stay inside narrow and tablet viewports', async ({
  page,
}, testInfo) => {
  test.setTimeout(60_000); // Five viewport sizes, each with all five tab transitions.
  for (const width of [320, 390, 430, 768, 1280]) {
    await page.setViewportSize({ width, height: width === 320 ? 640 : 844 });
    await page.goto('/?screen=bank-closed');
    await page.evaluate(() => {
      document.documentElement.style.setProperty('--safe-top', '115px');
      document.documentElement.style.setProperty('--safe-bottom', '34px');
    });
    await expect(page.getByRole('button', { name: 'ПОЛОТНО', exact: true })).toBeVisible();
    await expect(page.locator('.bank-season-closed-copy')).toHaveCSS('opacity', '1');
    const position = (await page
      .getByRole('button', { name: 'МОЯ ПОЗИЦИЯ', exact: true })
      .boundingBox())!;
    const navigation = (await page.getByRole('navigation').boundingBox())!;
    expect(position.y + position.height).toBeLessThanOrEqual(navigation.y);
    expect(await page.locator('.bank-screen').evaluate((screen) => screen.scrollTop)).toBe(0);
    await expect(page.locator('.pixel-background')).toHaveCSS('opacity', '0.32');
    await expect(page.locator('.bank-jar-shell')).toHaveCSS('mask-mode', 'luminance');
    for (const tab of ['BANK', 'DUEL', 'РЕЙТИНГ', 'КОМАНДЫ', 'ПРОФИЛЬ']) {
      await page.getByRole('button', { name: tab, exact: true }).click();
      await expect(page.getByRole('button', { name: tab, exact: true })).toHaveAttribute(
        'aria-current',
        'page',
      );
      await expect(page.locator('.screen-stage')).toHaveCSS('opacity', '1');
      await expect(page.getByTestId('pixel-background')).toBeVisible();
      const background = (await page.getByTestId('pixel-background').boundingBox())!;
      expect(background.x).toBe(0);
      expect(background.y).toBe(0);
      expect(background.width).toBe(width);
      expect(background.height).toBe(width === 320 ? 640 : 844);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
    }
    await page.getByRole('button', { name: 'BANK', exact: true }).click();
    await expect(page.getByRole('button', { name: 'BANK', exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(page.locator('.screen-stage')).toHaveCSS('opacity', '1');
    if (width === 390)
      await page.screenshot({
        path: `../../output/pixels/${testInfo.project.name}-background.png`,
      });
    await page.getByRole('button', { name: 'ПОЛОТНО', exact: true }).click();
    const fullCanvas = (await page.getByTestId('pixel-canvas').boundingBox())!;
    expect(fullCanvas).toEqual({ x: 0, y: 0, width, height: width === 320 ? 640 : 844 });
    await expect(page.locator('.pixel-viewport')).toHaveCSS('border-radius', '0px');
    await expect(page.getByText(/Приближай|выбирай · рисуй|ОБЩИЙ ФОН LOOP/)).toHaveCount(0);
    await page.getByRole('button', { name: 'Выбрать цвет', exact: true }).click();
    const swatches = page
      .getByRole('group', { name: 'Палитра' })
      .locator('button[aria-pressed="false"]');
    expect(await swatches.count()).toBe(15);
    const red = (await page.getByRole('button', { name: 'Красный', exact: true }).boundingBox())!;
    expect(red.x).toBeGreaterThanOrEqual(0);
    expect(red.x + red.width).toBeLessThanOrEqual(width);
    expect(red.height).toBeGreaterThanOrEqual(44);
    expect(red.y + red.height).toBeLessThanOrEqual(844);
    if (width === 320)
      await page.screenshot({
        path: `../../output/pixels/${testInfo.project.name}-palette-320.png`,
      });
    await page.getByRole('button', { name: 'Красный', exact: true }).click();
    const paint = (await page
      .getByRole('button', { name: 'ПОСТАВИТЬ ПИКСЕЛЬ', exact: true })
      .boundingBox())!;
    expect(paint.x + paint.width).toBeLessThanOrEqual(width);
    expect(paint.y + paint.height).toBeLessThanOrEqual(width === 320 ? 640 : 844);
  }
});
