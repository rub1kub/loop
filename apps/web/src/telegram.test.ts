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
    const setBackgroundColor = vi.fn();
    const setBottomBarColor = vi.fn();
    const ready = vi.fn();
    window.Telegram = {
      WebApp: {
        initData: 'sdk-init-data',
        MainButton: { hide },
        setHeaderColor,
        setBackgroundColor,
        setBottomBarColor,
        ready,
      } as unknown as TelegramWebApp,
    };

    expect(initializeTelegram()).toBe(true);
    expect(hide).toHaveBeenCalledOnce();
    expect(ready).toHaveBeenCalledOnce();
    expect(setHeaderColor).toHaveBeenCalledWith('#000000');
    expect(setBackgroundColor).toHaveBeenCalledWith('#000000');
    expect(setBottomBarColor).toHaveBeenCalledWith('#000000');
    expect(telegramInitData()).toBe('sdk-init-data');
  });

  it('preserves fullscreen when a mobile client already launched in that mode', () => {
    const exitFullscreen = vi.fn();
    const requestFullscreen = vi.fn();
    window.Telegram = {
      WebApp: {
        initData: 'sdk-init-data',
        platform: 'ios',
        isFullscreen: true,
        isVersionAtLeast: () => true,
        exitFullscreen,
        requestFullscreen,
        MainButton: { hide: vi.fn() },
      } as unknown as TelegramWebApp,
    };

    expect(initializeTelegram()).toBe(true);
    expect(exitFullscreen).not.toHaveBeenCalled();
    expect(requestFullscreen).not.toHaveBeenCalled();
  });

  it('requests fullscreen for entry points that ignore the BotFather launch mode', () => {
    const expand = vi.fn();
    const exitFullscreen = vi.fn();
    const requestFullscreen = vi.fn();
    window.Telegram = {
      WebApp: {
        initData: 'sdk-init-data',
        platform: 'android',
        isFullscreen: false,
        isVersionAtLeast: () => true,
        expand,
        exitFullscreen,
        requestFullscreen,
        MainButton: { hide: vi.fn() },
      } as unknown as TelegramWebApp,
    };

    expect(initializeTelegram()).toBe(true);
    expect(expand).toHaveBeenCalledOnce();
    expect(requestFullscreen).toHaveBeenCalledOnce();
    expect(exitFullscreen).not.toHaveBeenCalled();
    expect(expand.mock.invocationCallOrder[0]).toBeLessThan(
      requestFullscreen.mock.invocationCallOrder[0],
    );
  });

  it.each(['tdesktop', 'macos', 'web', 'weba', 'webk', 'unknown'])(
    'exits fullscreen on non-mobile Telegram platform %s',
    (platform) => {
      const expand = vi.fn();
      const exitFullscreen = vi.fn();
      const requestFullscreen = vi.fn();
      window.Telegram = {
        WebApp: {
          initData: 'sdk-init-data',
          platform,
          isFullscreen: true,
          isVersionAtLeast: () => true,
          expand,
          exitFullscreen,
          requestFullscreen,
          MainButton: { hide: vi.fn() },
        } as unknown as TelegramWebApp,
      };

      expect(initializeTelegram()).toBe(true);
      expect(exitFullscreen).toHaveBeenCalledOnce();
      expect(expand).toHaveBeenCalledOnce();
      expect(requestFullscreen).not.toHaveBeenCalled();
      expect(exitFullscreen.mock.invocationCallOrder[0]).toBeLessThan(
        expand.mock.invocationCallOrder[0],
      );
    },
  );

  it('does not request fullscreen for a regular desktop launch', () => {
    const expand = vi.fn();
    const exitFullscreen = vi.fn();
    const requestFullscreen = vi.fn();
    window.Telegram = {
      WebApp: {
        initData: 'sdk-init-data',
        platform: 'tdesktop',
        isFullscreen: false,
        isVersionAtLeast: () => true,
        expand,
        exitFullscreen,
        requestFullscreen,
        MainButton: { hide: vi.fn() },
      } as unknown as TelegramWebApp,
    };

    expect(initializeTelegram()).toBe(true);
    expect(expand).toHaveBeenCalledOnce();
    expect(exitFullscreen).not.toHaveBeenCalled();
    expect(requestFullscreen).not.toHaveBeenCalled();
  });

  it('re-expands desktop after Telegram confirms fullscreen exit', () => {
    const handlers = new Map<string, () => void>();
    const expand = vi.fn();
    const app = {
      initData: 'sdk-init-data',
      platform: 'tdesktop',
      isFullscreen: true,
      isVersionAtLeast: () => true,
      expand,
      exitFullscreen: vi.fn(),
      onEvent: (event: string, callback: () => void) => handlers.set(event, callback),
      MainButton: { hide: vi.fn() },
    } as unknown as TelegramWebApp;
    window.Telegram = { WebApp: app };

    expect(initializeTelegram()).toBe(true);
    app.isFullscreen = false;
    handlers.get('fullscreenChanged')?.();

    expect(expand).toHaveBeenCalledTimes(2);
  });

  it('restores black Telegram chrome after theme, activation and fullscreen events', () => {
    const handlers = new Map<string, () => void>();
    const setHeaderColor = vi.fn();
    const setBackgroundColor = vi.fn();
    const setBottomBarColor = vi.fn();
    const app = {
      initData: 'sdk-init-data',
      platform: 'ios',
      isFullscreen: true,
      isVersionAtLeast: () => true,
      setHeaderColor,
      setBackgroundColor,
      setBottomBarColor,
      onEvent: (event: string, callback: () => void) => handlers.set(event, callback),
      MainButton: { hide: vi.fn() },
    } as unknown as TelegramWebApp;
    window.Telegram = { WebApp: app };

    expect(initializeTelegram()).toBe(true);
    setHeaderColor.mockClear();
    setBackgroundColor.mockClear();
    setBottomBarColor.mockClear();

    handlers.get('themeChanged')?.();
    handlers.get('activated')?.();
    handlers.get('fullscreenChanged')?.();

    expect(setHeaderColor).toHaveBeenCalledTimes(3);
    expect(setBackgroundColor).toHaveBeenCalledTimes(3);
    expect(setBottomBarColor).toHaveBeenCalledTimes(3);
    expect(setHeaderColor).toHaveBeenLastCalledWith('#000000');
    expect(setBackgroundColor).toHaveBeenLastCalledWith('#000000');
    expect(setBottomBarColor).toHaveBeenLastCalledWith('#000000');
  });
});
