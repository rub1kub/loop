import type { TelegramWebApp } from './types';

const mockTelegram = import.meta.env.VITE_MOCK_TELEGRAM === 'true';
const telegramSdkUrl = 'https://telegram.org/js/telegram-web-app.js?63';
const immersiveTelegramPlatforms = new Set(['android', 'android_x', 'ios']);
let telegramSdkPromise: Promise<void> | null = null;

export function telegram(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp;
}

export function telegramInitData(): string {
  const sdkInitData = telegram()?.initData?.trim();
  if (sdkInitData) return sdkInitData;

  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const search = new URLSearchParams(window.location.search);
  return hash.get('tgWebAppData')?.trim() || search.get('tgWebAppData')?.trim() || '';
}

export function telegramStartParam(): string | undefined {
  const unsafeStartParam = telegram()?.initDataUnsafe?.start_param;
  if (unsafeStartParam) return unsafeStartParam;
  const startParam = new URLSearchParams(telegramInitData()).get('start_param')?.trim();
  return startParam || undefined;
}

export function loadTelegramSdk(): Promise<void> {
  if (isMockTelegram() || telegram()) return Promise.resolve();
  if (telegramSdkPromise) return telegramSdkPromise;

  telegramSdkPromise = new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = telegramSdkUrl;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => resolve();
    document.head.append(script);
  });
  return telegramSdkPromise;
}

export function prefersTelegramFullscreen(platform: string | undefined): boolean {
  return immersiveTelegramPlatforms.has(platform?.trim().toLowerCase() ?? '');
}

export function initializeTelegram(): boolean {
  if (isMockTelegram()) return true;
  const app = telegram();
  if (!app) return false;
  app.setHeaderColor?.('#000000');
  app.setBackgroundColor?.('#000000');
  app.setBottomBarColor?.('#000000');
  app.MainButton?.hide();
  app.expand?.();
  app.disableVerticalSwipes?.();
  app.enableClosingConfirmation?.();
  app.ready?.();
  if (app.isVersionAtLeast?.('8.0')) {
    try {
      if (prefersTelegramFullscreen(app.platform)) {
        if (!app.isFullscreen) app.requestFullscreen?.();
      } else if (app.isFullscreen) {
        app.exitFullscreen?.();
      }
    } catch {
      // Older or partially implemented clients keep the regular expanded mode.
    }
  }
  // Telegram can restore its chrome theme during ready(); apply LOOP's monochrome chrome once more.
  app.setHeaderColor?.('#000000');
  app.setBackgroundColor?.('#000000');
  app.setBottomBarColor?.('#000000');
  return true;
}

export function isMockTelegram(): boolean {
  return mockTelegram;
}

export function haptic(
  type: 'selection' | 'light' | 'medium' | 'success' | 'warning' | 'error',
): void {
  if (isMockTelegram()) return;
  const feedback = telegram()?.HapticFeedback;
  if (!feedback) return;
  if (type === 'selection') feedback.selectionChanged();
  else if (type === 'light' || type === 'medium') feedback.impactOccurred(type);
  else feedback.notificationOccurred(type);
}

export function setBackAction(action?: () => void): () => void {
  if (isMockTelegram()) return () => undefined;
  const button = telegram()?.BackButton;
  if (!button) return () => undefined;
  if (!action) {
    button.hide();
    return () => undefined;
  }
  button.show();
  button.onClick(action);
  return () => {
    button.offClick(action);
    button.hide();
  };
}

export async function storeDuelSecret(offerId: number, secretHex: string): Promise<void> {
  const key = `loop-duel-${offerId}`;
  const storage = telegram()?.SecureStorage;
  if (storage) {
    await new Promise<void>((resolve, reject) => {
      storage.setItem(key, secretHex, (error) => (error ? reject(new Error(error)) : resolve()));
    });
    return;
  }
  if (isMockTelegram()) sessionStorage.setItem(key, secretHex);
  else throw new Error('Обновите Telegram: для дуэли требуется SecureStorage');
}

export async function readDuelSecret(offerId: number): Promise<string | null> {
  const key = `loop-duel-${offerId}`;
  const storage = telegram()?.SecureStorage;
  if (storage) {
    return await new Promise<string | null>((resolve, reject) => {
      storage.getItem(key, (error, value) => (error ? reject(new Error(error)) : resolve(value)));
    });
  }
  return isMockTelegram() ? sessionStorage.getItem(key) : null;
}

export async function removeDuelSecret(offerId: number): Promise<void> {
  const key = `loop-duel-${offerId}`;
  const storage = telegram()?.SecureStorage;
  if (storage) {
    await new Promise<void>((resolve, reject) => {
      storage.removeItem(key, (error) => (error ? reject(new Error(error)) : resolve()));
    });
  } else if (isMockTelegram()) {
    sessionStorage.removeItem(key);
  }
}

export function toggleFullscreen(): void {
  const app = telegram();
  if (app?.isVersionAtLeast?.('8.0')) {
    if (!prefersTelegramFullscreen(app.platform)) {
      if (app.isFullscreen) app.exitFullscreen?.();
      return;
    }
    if (app.isFullscreen) app.exitFullscreen?.();
    else app.requestFullscreen?.();
    return;
  }
  if (document.fullscreenElement) void document.exitFullscreen();
  else void document.documentElement.requestFullscreen?.();
}
