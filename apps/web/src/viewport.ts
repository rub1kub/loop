import type { TelegramWebApp } from './types';

const FOCUS_SETTLE_MS = 360;

function isEditable(element: Element | null): element is HTMLElement {
  return (
    element instanceof HTMLElement &&
    (element.matches('input, textarea, select') || element.isContentEditable)
  );
}

function currentViewport() {
  const viewport = window.visualViewport;
  return {
    height: Math.round(viewport?.height ?? window.innerHeight),
  };
}

export function installViewportBehavior(): () => void {
  const root = document.documentElement;
  let stableHeight = Math.max(window.innerHeight, currentViewport().height);
  let blurTimer: number | undefined;
  let keyboardSettling = false;
  let subscribedTelegram: TelegramWebApp | undefined;

  const syncSafeArea = () => {
    const app = window.Telegram?.WebApp;
    const device = app?.safeAreaInset;
    const content = app?.contentSafeAreaInset;
    const inset = (side: 'top' | 'right' | 'bottom' | 'left') =>
      Math.max(device?.[side] ?? 0, content?.[side] ?? 0);

    root.style.setProperty('--loop-safe-area-inset-top', `${inset('top')}px`);
    root.style.setProperty('--loop-safe-area-inset-right', `${inset('right')}px`);
    root.style.setProperty('--loop-safe-area-inset-bottom', `${inset('bottom')}px`);
    root.style.setProperty('--loop-safe-area-inset-left', `${inset('left')}px`);
  };

  const sync = () => {
    subscribeTelegram();
    const viewport = currentViewport();
    const keyboardOpen = isEditable(document.activeElement) || keyboardSettling;
    const telegramStableHeight = window.Telegram?.WebApp.viewportStableHeight;

    if (!keyboardOpen) {
      stableHeight =
        typeof telegramStableHeight === 'number' && telegramStableHeight > 0
          ? Math.round(telegramStableHeight)
          : viewport.height;
    }
    root.style.setProperty('--loop-stable-height', `${stableHeight}px`);
    root.style.setProperty('--loop-visual-height', `${viewport.height}px`);
    root.classList.toggle('keyboard-open', keyboardOpen);
    syncSafeArea();
  };

  const onTelegramViewport = () => sync();

  const subscribeTelegram = () => {
    const app = window.Telegram?.WebApp;
    if (!app || app === subscribedTelegram) return;
    subscribedTelegram = app;
    app.onEvent?.('viewportChanged', onTelegramViewport);
    app.onEvent?.('safeAreaChanged', onTelegramViewport);
    app.onEvent?.('contentSafeAreaChanged', onTelegramViewport);
    app.onEvent?.('fullscreenChanged', onTelegramViewport);
  };

  const onFocusIn = () => {
    if (blurTimer !== undefined) window.clearTimeout(blurTimer);
    keyboardSettling = false;
    sync();
  };
  const onFocusOut = () => {
    keyboardSettling = true;
    blurTimer = window.setTimeout(() => {
      keyboardSettling = false;
      sync();
    }, FOCUS_SETTLE_MS);
  };

  subscribeTelegram();
  sync();
  window.addEventListener('resize', sync);
  window.visualViewport?.addEventListener('resize', sync);
  window.visualViewport?.addEventListener('scroll', sync);
  document.addEventListener('focusin', onFocusIn);
  document.addEventListener('focusout', onFocusOut);

  return () => {
    if (blurTimer !== undefined) window.clearTimeout(blurTimer);
    window.removeEventListener('resize', sync);
    window.visualViewport?.removeEventListener('resize', sync);
    window.visualViewport?.removeEventListener('scroll', sync);
    document.removeEventListener('focusin', onFocusIn);
    document.removeEventListener('focusout', onFocusOut);
    subscribedTelegram?.offEvent?.('viewportChanged', onTelegramViewport);
    subscribedTelegram?.offEvent?.('safeAreaChanged', onTelegramViewport);
    subscribedTelegram?.offEvent?.('contentSafeAreaChanged', onTelegramViewport);
    subscribedTelegram?.offEvent?.('fullscreenChanged', onTelegramViewport);
    root.classList.remove('keyboard-open');
    root.style.removeProperty('--loop-stable-height');
    root.style.removeProperty('--loop-visual-height');
    root.style.removeProperty('--loop-safe-area-inset-top');
    root.style.removeProperty('--loop-safe-area-inset-right');
    root.style.removeProperty('--loop-safe-area-inset-bottom');
    root.style.removeProperty('--loop-safe-area-inset-left');
  };
}
