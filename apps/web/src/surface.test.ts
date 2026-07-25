import { describe, expect, it } from 'vitest';

import { resolveWebSurface } from './surface';

const browserContext = {
  pathname: '/',
  search: '',
  hash: '',
};

describe('web surface routing', () => {
  it('shows the public landing to a regular browser', () => {
    expect(resolveWebSurface(browserContext)).toBe('landing');
  });

  it('keeps the owner control route independent from Telegram', () => {
    expect(
      resolveWebSurface({
        ...browserContext,
        pathname: '/control/contracts',
        hash: '#tgWebAppPlatform=ios',
      }),
    ).toBe('control');
  });

  it.each([
    { hash: '#tgWebAppData=signed&tgWebAppPlatform=ios' },
    { search: '?tgWebAppVersion=9.0&tgWebAppPlatform=tdesktop' },
    { telegramInitData: 'signed-init-data' },
    { mockTelegram: true },
  ])('opens the Mini App for Telegram context %#', (context) => {
    expect(resolveWebSurface({ ...browserContext, ...context })).toBe('mini-app');
  });
});
