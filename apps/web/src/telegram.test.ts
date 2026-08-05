import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  haptic,
  initializeTelegram,
  isHapticsEnabled,
  openPlatformLink,
  requestResultNotificationAccess,
  setHapticsEnabled,
  sharePreparedResult,
  telegramInitData,
  telegramStartParam,
} from './telegram';
import type { TelegramWebApp } from './types';

describe('Telegram launch compatibility', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
    localStorage.removeItem('loop-haptics-enabled');
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

  it('persists the vibration preference and suppresses haptics when disabled', () => {
    const notificationOccurred = vi.fn();
    window.Telegram = {
      WebApp: {
        HapticFeedback: {
          impactOccurred: vi.fn(),
          notificationOccurred,
          selectionChanged: vi.fn(),
        },
      } as unknown as TelegramWebApp,
    };

    expect(isHapticsEnabled()).toBe(true);
    setHapticsEnabled(false);
    expect(isHapticsEnabled()).toBe(false);
    haptic('success');
    expect(notificationOccurred).not.toHaveBeenCalled();

    setHapticsEnabled(true);
    haptic('success');
    expect(notificationOccurred).toHaveBeenCalledWith('success');
  });

  it('opens Telegram and web market links through the matching native bridge', () => {
    const openTelegramLink = vi.fn();
    const openLink = vi.fn();
    window.Telegram = {
      WebApp: {
        openTelegramLink,
        openLink,
      } as unknown as TelegramWebApp,
    };

    openPlatformLink('https://t.me/dtrade', true);
    openPlatformLink('https://app.ston.fi/swap');

    expect(openTelegramLink).toHaveBeenCalledWith('https://t.me/dtrade');
    expect(openLink).toHaveBeenCalledWith('https://app.ston.fi/swap');
  });

  it('requests private-message access only when Telegram has not granted it', async () => {
    const requestWriteAccess = vi.fn((callback: (allowed: boolean) => void) => callback(true));
    window.Telegram = {
      WebApp: {
        initDataUnsafe: { user: { id: 42, first_name: 'Loop' } },
        requestWriteAccess,
      } as unknown as TelegramWebApp,
    };

    await expect(requestResultNotificationAccess()).resolves.toBe(true);
    expect(requestWriteAccess).toHaveBeenCalledOnce();

    window.Telegram.WebApp.initDataUnsafe!.user!.allows_write_to_pm = true;
    await expect(requestResultNotificationAccess()).resolves.toBe(true);
    expect(requestWriteAccess).toHaveBeenCalledOnce();
  });

  it('uses Telegram prepared messages for native result sharing', async () => {
    const shareMessage = vi.fn((_messageId: string, callback: (shared: boolean) => void) =>
      callback(true),
    );
    const switchInlineQuery = vi.fn();
    window.Telegram = {
      WebApp: {
        shareMessage,
        switchInlineQuery,
      } as unknown as TelegramWebApp,
    };

    await expect(sharePreparedResult('prepared-1', 'result public-id')).resolves.toBe(true);
    expect(shareMessage).toHaveBeenCalledWith('prepared-1', expect.any(Function));
    expect(switchInlineQuery).not.toHaveBeenCalled();
  });
});

describe('Telegram SDK loading never blocks the app', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.resetModules();
    delete window.Telegram;
    document.querySelectorAll('script[src*="telegram-web-app"]').forEach((n) => n.remove());
  });

  it('resolves on a timeout when no script ever fires load or error', async () => {
    vi.resetModules();
    const { loadTelegramSdk: load } = await import('./telegram');
    vi.useFakeTimers();
    let settled = false;
    const loading = load().then(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(1000);
    expect(settled, 'must not resolve before the timeout').toBe(false);

    await vi.advanceTimersByTimeAsync(6000);
    await loading;
    expect(settled).toBe(true);
  });

  it('asks its own origin first so a blocked telegram.org cannot stall the launch', async () => {
    vi.resetModules();
    const { loadTelegramSdk: load } = await import('./telegram');
    void load();
    const script = document.querySelector<HTMLScriptElement>('script[src*="telegram-web-app"]');
    expect(script).not.toBeNull();
    expect(script!.src).toContain('/telegram-web-app.js');
    expect(script!.src).not.toContain('telegram.org');
  });
});

describe('duel secret storage', () => {
  const key = 'loop-duel-777';

  beforeEach(() => {
    window.localStorage.clear();
    delete (window as { Telegram?: unknown }).Telegram;
  });

  it('keeps the duel playable when SecureStorage answers UNSUPPORTED', async () => {
    // SecureStorage landed in Bot API 9.0; most clients reject its calls with a
    // bare "UNSUPPORTED", which used to reach the player as their whole
    // explanation and made DUEL unplayable for them.
    const cloud = new Map<string, string>();
    (window as unknown as { Telegram: unknown }).Telegram = {
      WebApp: {
        SecureStorage: {
          setItem: (_k: string, _v: string, cb: (e: string | null) => void) => cb('UNSUPPORTED'),
          getItem: (_k: string, cb: (e: string | null, v: string | null) => void) =>
            cb('UNSUPPORTED', null),
          removeItem: (_k: string, cb?: (e: string | null) => void) => cb?.('UNSUPPORTED'),
        },
        CloudStorage: {
          setItem: (k: string, v: string, cb?: (e: string | null) => void) => {
            cloud.set(k, v);
            cb?.(null);
          },
          getItem: (k: string, cb: (e: string | null, v: string | null) => void) =>
            cb(null, cloud.get(k) ?? null),
          removeItem: (k: string, cb?: (e: string | null) => void) => {
            cloud.delete(k);
            cb?.(null);
          },
        },
      },
    };

    const { storeDuelSecret, readDuelSecret, removeDuelSecret } = await import('./telegram');
    await expect(storeDuelSecret(777, 'beef')).resolves.toBeUndefined();
    expect(cloud.get(key)).toBe('beef');
    await expect(readDuelSecret(777)).resolves.toBe('beef');
    await removeDuelSecret(777);
    await expect(readDuelSecret(777)).resolves.toBeNull();
  });

  it('still keeps the secret when the client offers no storage at all', async () => {
    (window as unknown as { Telegram: unknown }).Telegram = { WebApp: {} };
    const { storeDuelSecret, readDuelSecret } = await import('./telegram');

    await expect(storeDuelSecret(777, 'cafe')).resolves.toBeUndefined();
    await expect(readDuelSecret(777)).resolves.toBe('cafe');
  });
});
