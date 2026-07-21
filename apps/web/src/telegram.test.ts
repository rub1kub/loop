import { afterEach, describe, expect, it, vi } from 'vitest';

import { initializeTelegram, telegramInitData, telegramStartParam } from './telegram';
import type { TelegramWebApp } from './types';

describe('Telegram launch compatibility', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
    delete window.Telegram;
  });

  it('reads signed launch data from the URL when the remote SDK is unavailable', () => {
    const raw =
      'query_id=AAE-test&auth_date=1784640000&start_param=duel_INVITE42&hash=' + 'a'.repeat(64);
    window.history.replaceState(
      null,
      '',
      `/#tgWebAppData=${encodeURIComponent(raw)}&tgWebAppVersion=9.1`,
    );

    expect(telegramInitData()).toBe(raw);
    expect(telegramStartParam()).toBe('duel_INVITE42');
  });

  it('initializes partial desktop SDKs without throwing and clears the native main button', () => {
    const hide = vi.fn();
    const setHeaderColor = vi.fn();
    const setBottomBarColor = vi.fn();
    const ready = vi.fn();
    window.Telegram = {
      WebApp: {
        initData: 'sdk-init-data',
        MainButton: { hide },
        setHeaderColor,
        setBottomBarColor,
        ready,
      } as unknown as TelegramWebApp,
    };

    expect(initializeTelegram()).toBe(true);
    expect(hide).toHaveBeenCalledOnce();
    expect(ready).toHaveBeenCalledOnce();
    expect(setHeaderColor).toHaveBeenCalledWith('#000000');
    expect(setBottomBarColor).toHaveBeenCalledWith('#000000');
    expect(telegramInitData()).toBe('sdk-init-data');
  });
});
