import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TelegramWebApp } from './types';

const profile = {
  user: {
    id: 'user-id',
    telegram_id: 42,
    username: null,
    first_name: 'Loop',
    photo_url: null,
    onboarding_seen: true,
    onboarding_enabled: true,
  },
  wallet: null,
  bank: { active: 0, completed: 0, total: 0 },
  duel: { active: 0, completed: 0, total: 0 },
  plush_brick: {
    verified: false,
    balance_nano: 0,
    holder: false,
    duel_fee_bps: 250,
    fee_discount_active: false,
  },
};

describe('API session recovery', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    delete window.Telegram;
  });

  it('re-authenticates once and retries a request rejected with 401', async () => {
    window.Telegram = {
      WebApp: { initData: 'signed-init-data' } as TelegramWebApp,
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'expired session' }), { status: 401 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: 'fresh-session' }), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(profile), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const { api } = await import('./api');
    await expect(api.me()).resolves.toEqual(profile);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/auth/telegram');
    const authenticationBody = fetchMock.mock.calls[1]?.[1]?.body;
    expect(typeof authenticationBody).toBe('string');
    if (typeof authenticationBody !== 'string') throw new Error('authentication body is missing');
    expect(JSON.parse(authenticationBody)).toEqual({
      init_data: 'signed-init-data',
    });
    expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get('Authorization')).toBe(
      'Bearer fresh-session',
    );
  });

  it('retries safe reads after a transient iOS WebView network failure', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('Load failed'))
      .mockResolvedValueOnce(new Response(JSON.stringify(profile), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const { api } = await import('./api');
    await expect(api.me()).resolves.toEqual(profile);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
