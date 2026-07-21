import type { TelegramWebApp } from './types';

const mockTelegram = import.meta.env.VITE_MOCK_TELEGRAM === 'true';

export function telegram(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp;
}

export function initializeTelegram(): void {
  if (isMockTelegram()) return;
  const app = telegram();
  if (!app) return;
  app.setHeaderColor('#000000');
  app.setBackgroundColor('#000000');
  app.setBottomBarColor?.('#000000');
  app.expand();
  app.disableVerticalSwipes?.();
  app.enableClosingConfirmation?.();
  if (app.isVersionAtLeast('8.0') && !app.isFullscreen) {
    try {
      app.requestFullscreen?.();
    } catch {
      // Older clients may report a version before exposing fullscreen in this launch mode.
    }
  }
  app.ready();
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

export function setMainAction(label: string, action?: () => void, enabled = true): () => void {
  if (isMockTelegram()) return () => undefined;
  const button = telegram()?.MainButton;
  if (!button) return () => undefined;
  if (!action) {
    button.hide();
    return () => undefined;
  }
  button.setText(label);
  if (enabled) button.enable();
  else button.disable();
  button.onClick(action);
  button.show();
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
  if (app?.isVersionAtLeast('8.0')) {
    if (app.isFullscreen) app.exitFullscreen?.();
    else app.requestFullscreen?.();
    return;
  }
  if (document.fullscreenElement) void document.exitFullscreen();
  else void document.documentElement.requestFullscreen?.();
}
