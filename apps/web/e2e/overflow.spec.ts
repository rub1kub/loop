import { expect, test } from '@playwright/test';

const screens = [
  'bank-empty',
  'bank-active',
  'bank-create-position',
  'duel-create',
  'duel-boost',
  'duel-result',
  'duel-invite',
  'rating',
  'profile',
  'settings',
  'onboarding',
];

type Overflow = { selector: string; scroll: number; client: number };

test.describe('narrow phone', () => {
  test.use({ viewport: { width: 320, height: 640 } });

  for (const screen of screens) {
    test(`${screen} fits a 320px column without horizontal overflow`, async ({ page }) => {
      await page.goto(`/?screen=${screen}`);
      await page.waitForSelector('.app-shell, .onboarding, .inline-preview');
      await page.waitForTimeout(400);

      const bodyOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(bodyOverflow, 'the page itself must never scroll sideways').toBeLessThanOrEqual(0);

      const clipped: Overflow[] = await page.evaluate(() => {
        const found: Overflow[] = [];
        for (const node of document.querySelectorAll<HTMLElement>('.app-shell *')) {
          const style = getComputedStyle(node);
          if (style.overflowX !== 'visible' || style.position === 'fixed') continue;
          if (node.scrollWidth - node.clientWidth <= 1) continue;
          const name =
            node.tagName.toLowerCase() +
            (node.className && typeof node.className === 'string'
              ? `.${node.className.trim().split(/\s+/).join('.')}`
              : '');
          found.push({ selector: name, scroll: node.scrollWidth, client: node.clientWidth });
        }
        return found;
      });

      expect(clipped, JSON.stringify(clipped, null, 2)).toEqual([]);
    });
  }
});
