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
  'prelaunch',
];

type Overflow = { selector: string; scroll: number; client: number };

test.describe('narrow phone', () => {
  test.use({ viewport: { width: 320, height: 640 } });

  for (const screen of screens) {
    test(`${screen} fits a 320px column without horizontal overflow`, async ({ page }) => {
      await page.goto(`/?screen=${screen}`);
      await page.waitForSelector('.app-shell, .onboarding, .prelaunch, .inline-preview');
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

test.describe('tablet', () => {
  for (const viewport of [
    { name: 'portrait', width: 800, height: 1280 },
    { name: 'landscape', width: 1024, height: 768 },
  ]) {
    test(`prelaunch is centred in ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto('/?screen=prelaunch');
      await page.waitForSelector('.prelaunch');

      const layout = await page.locator('.prelaunch').evaluate((screen) => {
        const bounds = screen.getBoundingClientRect();
        return {
          centre: bounds.left + bounds.width / 2,
          viewportCentre: window.innerWidth / 2,
          pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        };
      });

      expect(Math.abs(layout.centre - layout.viewportCentre)).toBeLessThanOrEqual(1);
      expect(layout.pageOverflow).toBeLessThanOrEqual(0);
    });
  }
});
