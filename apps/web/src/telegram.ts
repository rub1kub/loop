import type { TelegramWebApp } from './types';

const mockTelegram = import.meta.env.VITE_MOCK_TELEGRAM === 'true';
const telegramSdkUrl = '/telegram-web-app.js';
const telegramSdkFallbackUrl = 'https://telegram.org/js/telegram-web-app.js?63';
const telegramSdkTimeoutMs = 6000;
const immersiveTelegramPlatforms = new Set(['android', 'android_x', 'ios']);
const telegramChromeColor = '#000000';
const hapticsStorageKey = 'loop-haptics-enabled';
const seenDuelStorageKey = 'loop-duel-seen';
const presentationGuardsInstalled = new WeakSet<TelegramWebApp>();
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
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      resolve();
    };
    const load = (src: string, onFail: () => void) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.onload = finish;
      script.onerror = onFail;
      document.head.append(script);
    };
    const timer = window.setTimeout(finish, telegramSdkTimeoutMs);
    load(telegramSdkUrl, () => load(telegramSdkFallbackUrl, finish));
  });
  return telegramSdkPromise;
}

export function prefersTelegramFullscreen(platform: string | undefined): boolean {
  return immersiveTelegramPlatforms.has(platform?.trim().toLowerCase() ?? '');
}

function applyTelegramChrome(app: TelegramWebApp): void {
  app.setHeaderColor?.(telegramChromeColor);
  app.setBackgroundColor?.(telegramChromeColor);
  app.setBottomBarColor?.(telegramChromeColor);
}

function applyTelegramLaunchMode(app: TelegramWebApp): void {
  const mobile = prefersTelegramFullscreen(app.platform);
  try {
    if (app.isVersionAtLeast?.('8.0') && !mobile && app.isFullscreen) {
      app.exitFullscreen?.();
    }
    app.expand?.();
    if (app.isVersionAtLeast?.('8.0') && mobile && !app.isFullscreen) {
      app.requestFullscreen?.();
    }
  } catch {
    // Partial desktop bridges must still retain Telegram's regular expanded mode.
    app.expand?.();
  }
}

function installTelegramPresentationGuards(app: TelegramWebApp): void {
  if (presentationGuardsInstalled.has(app)) return;
  presentationGuardsInstalled.add(app);

  const keepChromeBlack = () => applyTelegramChrome(app);
  const keepDesktopFullsize = () => {
    applyTelegramChrome(app);
    if (!prefersTelegramFullscreen(app.platform) && !app.isFullscreen) app.expand?.();
  };

  app.onEvent?.('themeChanged', keepChromeBlack);
  app.onEvent?.('activated', keepChromeBlack);
  app.onEvent?.('fullscreenChanged', keepDesktopFullsize);
}

export function initializeTelegram(): boolean {
  if (isMockTelegram()) return true;
  const app = telegram();
  if (!app) return false;
  applyTelegramChrome(app);
  app.MainButton?.hide();
  app.disableVerticalSwipes?.();
  app.enableClosingConfirmation?.();
  app.ready?.();
  installTelegramPresentationGuards(app);
  applyTelegramLaunchMode(app);
  // Telegram can restore its chrome theme during ready(); apply LOOP's monochrome chrome once more.
  applyTelegramChrome(app);
  return true;
}

export function isMockTelegram(): boolean {
  return mockTelegram;
}

export function isHapticsEnabled(): boolean {
  try {
    return localStorage.getItem(hapticsStorageKey) !== 'false';
  } catch {
    return true;
  }
}

export function setHapticsEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(hapticsStorageKey, String(enabled));
  } catch {
    // Some embedded browsers can deny storage; keep the session usable.
  }
}

export function readSeenDuelId(): string | null {
  try {
    return localStorage.getItem(seenDuelStorageKey);
  } catch {
    return null;
  }
}

export function markDuelSeen(duelId: string): void {
  try {
    localStorage.setItem(seenDuelStorageKey, duelId);
  } catch {
    return;
  }
}

export function haptic(
  type: 'selection' | 'light' | 'medium' | 'success' | 'warning' | 'error',
): void {
  if (isMockTelegram() || !isHapticsEnabled()) return;
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

export function openPlatformLink(url: string, telegramNative = false): void {
  const app = telegram();
  if (telegramNative && app?.openTelegramLink) {
    app.openTelegramLink(url);
    return;
  }
  if (app?.openLink) {
    app.openLink(url);
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

export async function requestResultNotificationAccess(): Promise<boolean> {
  if (isMockTelegram()) return true;
  const app = telegram();
  if (app?.initDataUnsafe?.user?.allows_write_to_pm) return true;
  if (!app?.requestWriteAccess) return false;
  return await new Promise<boolean>((resolve) => {
    app.requestWriteAccess?.((allowed) => resolve(allowed));
  });
}

export async function sharePreparedResult(
  preparedMessageId: string,
  fallbackQuery: string,
): Promise<boolean> {
  const app = telegram();
  if (isMockTelegram()) return true;
  if (app?.shareMessage) {
    const shared = await new Promise<boolean>((resolve) => {
      app.shareMessage?.(preparedMessageId, (success) => resolve(success));
    });
    if (shared) return true;
  }
  if (app?.switchInlineQuery) {
    app.switchInlineQuery(fallbackQuery, ['users', 'groups', 'channels']);
    return true;
  }
  return false;
}

/**
 * Where a duel's secret lives until it is revealed.
 *
 * SecureStorage is the right home — encrypted, on the device — but it landed in
 * Bot API 9.0 and most clients answer its calls with "UNSUPPORTED". That raw
 * word used to reach the player as their entire explanation, and DUEL was
 * simply unplayable for them. So the secret falls back to CloudStorage (6.9,
 * present almost everywhere and carried between devices) and finally to the
 * webview's own storage. None of these tiers hands the secret to LOOP's server
 * or to the opponent, which is the only property the commit-reveal needs.
 */
const secretKey = (offerId: number) => `loop-duel-${offerId}`;

type KeyValueStore = NonNullable<TelegramWebApp['SecureStorage']>;

function telegramStores(): KeyValueStore[] {
  const app = telegram();
  return [app?.SecureStorage, app?.CloudStorage].filter(Boolean) as KeyValueStore[];
}

function setIn(store: KeyValueStore, key: string, value: string): Promise<void> {
  return new Promise((resolve, reject) => {
    store.setItem(key, value, (error) => (error ? reject(new Error(error)) : resolve()));
  });
}

function getFrom(store: KeyValueStore, key: string): Promise<string | null> {
  return new Promise((resolve, reject) => {
    store.getItem(key, (error, value) => (error ? reject(new Error(error)) : resolve(value)));
  });
}

export async function storeDuelSecret(offerId: number, secretHex: string): Promise<void> {
  const key = secretKey(offerId);
  for (const store of telegramStores()) {
    try {
      await setIn(store, key, secretHex);
      return;
    } catch {
      // This client does not support that tier; try the next one.
    }
  }
  try {
    window.localStorage.setItem(key, secretHex);
  } catch {
    throw new Error('Не удалось сохранить ключ дуэли. Разреши сайту хранить данные и повтори.');
  }
}

export async function readDuelSecret(offerId: number): Promise<string | null> {
  const key = secretKey(offerId);
  for (const store of telegramStores()) {
    try {
      const value = await getFrom(store, key);
      if (value) return value;
    } catch {
      // Fall through to the next tier rather than losing a revealable duel.
    }
  }
  try {
    return (
      window.localStorage.getItem(key) ?? (isMockTelegram() ? sessionStorage.getItem(key) : null)
    );
  } catch {
    return null;
  }
}

export async function removeDuelSecret(offerId: number): Promise<void> {
  const key = secretKey(offerId);
  for (const store of telegramStores()) {
    await new Promise<void>((resolve) => {
      store.removeItem(key, () => resolve());
    });
  }
  try {
    window.localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  } catch {
    // Nothing to clean up.
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
