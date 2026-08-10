import { expect, test } from '@playwright/test';

test('team creation waits for the first tap and keeps its layout fixed with the keyboard', async ({
  page,
}, testInfo) => {
  await page.goto('/?screen=teams-create');
  await page.getByRole('button', { name: 'СОЗДАТЬ СВОЮ' }).click();

  const name = page.getByRole('textbox', { name: 'НАЗВАНИЕ' });
  await expect(name).toBeVisible();
  await expect(name).not.toBeFocused();

  const headerBefore = await page.locator('.team-subpage-header').boundingBox();
  const nameBefore = await name.boundingBox();
  const shellHeight = (await page.locator('.app-shell').boundingBox())!.height;
  expect(headerBefore).not.toBeNull();
  expect(nameBefore).not.toBeNull();

  await name.click();
  await expect(name).toBeFocused();
  await expect(page.locator('html')).toHaveClass(/keyboard-open/);

  const viewport = page.viewportSize()!;
  await page.setViewportSize({ width: viewport.width, height: 520 });
  await expect
    .poll(async () => (await page.locator('.app-shell').boundingBox())!.height)
    .toBe(shellHeight);

  const headerAfter = await page.locator('.team-subpage-header').boundingBox();
  const nameAfter = await name.boundingBox();
  expect(headerAfter).not.toBeNull();
  expect(nameAfter).not.toBeNull();
  expect(headerAfter!.y).toBeCloseTo(headerBefore!.y, 0);
  expect(nameAfter!.y).toBeCloseTo(nameBefore!.y, 0);
  await expect.poll(() => page.locator('.screen').evaluate((screen) => screen.scrollTop)).toBe(0);

  await page.setViewportSize(viewport);
  await name.blur();
  await expect(page.locator('html')).not.toHaveClass(/keyboard-open/);
  await name.click();
  await page.setViewportSize({ width: viewport.width, height: 520 });
  expect((await page.locator('.team-subpage-header').boundingBox())!.y).toBeCloseTo(
    headerBefore!.y,
    0,
  );
  expect((await name.boundingBox())!.y).toBeCloseTo(nameBefore!.y, 0);

  await page.waitForTimeout(120);
  await page.screenshot({ path: testInfo.outputPath('teams-create-first-focus.png') });
});
