import type { TelegramWebApp } from './types';

const FOCUS_SETTLE_MS = 360;
const POINTER_SETTLE_MS = 80;
const FULLSCREEN_CONTROLS_TOP_INSET_PX = 72;

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
    pageTop: Math.max(
      0,
      Math.round(viewport?.pageTop ?? 0),
      Math.round((viewport?.offsetTop ?? 0) + window.scrollY),
      Math.round(window.scrollY),
    ),
  };
}

export function installViewportBehavior(): () => void {
  const root = document.documentElement;
  let stableHeight = Math.max(window.innerHeight, currentViewport().height);
  let protectedTopInset = 0;
  let blurTimer: number | undefined;
  let viewportCorrectionTimer: number | undefined;
  let focusCorrectionTimer: number | undefined;
  let keyboardSettling = false;
  const activePointers = new Set<number>();
  const pointerReleaseTimers = new Map<number, number>();
  let subscribedTelegram: TelegramWebApp | undefined;

  const restoreFixedViewport = () => {
    root.scrollTop = 0;
    document.body.scrollTop = 0;
    const shell = document.querySelector<HTMLElement>('.app-shell');
    const stage = document.querySelector<HTMLElement>('.screen-stage');
    if (shell) {
      shell.scrollTop = 0;
      shell.scrollLeft = 0;
    }
    if (stage) {
      stage.scrollTop = 0;
      stage.scrollLeft = 0;
    }
  };

  const restoreFocusedScreen = () => {
    restoreFixedViewport();
    const active = document.activeElement;
    if (!isEditable(active)) return;
    const screen = active.closest<HTMLElement>('.screen');
    if (screen && screen.scrollTop !== 0) screen.scrollTop = 0;
  };

  const syncSafeArea = () => {
    const app = window.Telegram?.WebApp;
    const device = app?.safeAreaInset;
    const content = app?.contentSafeAreaInset;
    const inset = (side: 'top' | 'right' | 'bottom' | 'left') =>
      Math.max(
        device?.[side] ?? 0,
        content?.[side] ?? 0,
        side === 'top' && app?.isFullscreen ? FULLSCREEN_CONTROLS_TOP_INSET_PX : 0,
      );

    // Telegram can briefly report a smaller top inset while iOS opens its keyboard
    // or changes fullscreen state. A session must never move content back under the
    // native controls after a larger safe boundary has already been established.
    protectedTopInset = Math.max(protectedTopInset, inset('top'));

    root.style.setProperty('--loop-safe-area-inset-top', `${protectedTopInset}px`);
    root.style.setProperty('--loop-safe-area-inset-right', `${inset('right')}px`);
    root.style.setProperty('--loop-safe-area-inset-bottom', `${inset('bottom')}px`);
    root.style.setProperty('--loop-safe-area-inset-left', `${inset('left')}px`);
  };

  const sync = () => {
    restoreFixedViewport();
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
    root.style.setProperty('--loop-visual-page-top', `${keyboardOpen ? viewport.pageTop : 0}px`);
    root.classList.toggle('keyboard-open', keyboardOpen);
    syncSafeArea();
    if (keyboardOpen) restoreFocusedScreen();
  };

  const resyncAfterViewportSettles = () => {
    if (viewportCorrectionTimer !== undefined) window.clearTimeout(viewportCorrectionTimer);
    viewportCorrectionTimer = window.setTimeout(sync, 50);
  };

  const onViewportMutation = () => {
    sync();
    resyncAfterViewportSettles();
  };

  const onTelegramViewport = () => onViewportMutation();

  const subscribeTelegram = () => {
    const app = window.Telegram?.WebApp;
    if (!app || app === subscribedTelegram) return;
    subscribedTelegram = app;
    app.onEvent?.('viewportChanged', onTelegramViewport);
    app.onEvent?.('safeAreaChanged', onTelegramViewport);
    app.onEvent?.('contentSafeAreaChanged', onTelegramViewport);
    app.onEvent?.('fullscreenChanged', onTelegramViewport);
  };

  const onFocusIn = (event: FocusEvent) => {
    if (!isEditable(event.target instanceof Element ? event.target : null)) return;
    if (blurTimer !== undefined) window.clearTimeout(blurTimer);
    if (focusCorrectionTimer !== undefined) window.clearTimeout(focusCorrectionTimer);
    keyboardSettling = false;
    sync();
    resyncAfterViewportSettles();
    focusCorrectionTimer = window.setTimeout(sync, 320);
  };

  const finishFocusOut = () => {
    if (activePointers.size > 0) {
      blurTimer = window.setTimeout(finishFocusOut, POINTER_SETTLE_MS);
      return;
    }
    keyboardSettling = false;
    restoreFixedViewport();
    sync();
  };

  const onFocusOut = () => {
    keyboardSettling = true;
    if (focusCorrectionTimer !== undefined) window.clearTimeout(focusCorrectionTimer);
    blurTimer = window.setTimeout(finishFocusOut, FOCUS_SETTLE_MS);
  };

  const releasePointer = (pointerId: number) => {
    const timer = pointerReleaseTimers.get(pointerId);
    if (timer !== undefined) window.clearTimeout(timer);
    pointerReleaseTimers.delete(pointerId);
    activePointers.delete(pointerId);
  };
  const onPointerDown = (event: PointerEvent) => {
    releasePointer(event.pointerId);
    activePointers.add(event.pointerId);
  };
  const onPointerUp = (event: PointerEvent) => {
    // Keep the layout frozen until the synthetic click has been delivered. A due
    // keyboard timer may otherwise reveal the tab bar between pointerup and click.
    pointerReleaseTimers.set(
      event.pointerId,
      window.setTimeout(() => releasePointer(event.pointerId), POINTER_SETTLE_MS * 2),
    );
  };
  const onPointerCancel = (event: PointerEvent) => releasePointer(event.pointerId);
  const onClick = () => {
    for (const pointerId of activePointers) releasePointer(pointerId);
    restoreFixedViewport();
  };
  const onScroll = (event: Event) => {
    const target = event.target;
    if (
      target === document ||
      target === root ||
      target === document.body ||
      (target instanceof Element && target.matches('.app-shell, .screen-stage'))
    ) {
      restoreFixedViewport();
    }
  };

  subscribeTelegram();
  sync();
  window.addEventListener('resize', onViewportMutation);
  window.visualViewport?.addEventListener('resize', onViewportMutation);
  window.visualViewport?.addEventListener('scroll', onViewportMutation);
  document.addEventListener('focusin', onFocusIn);
  document.addEventListener('focusout', onFocusOut);
  document.addEventListener('pointerdown', onPointerDown);
  document.addEventListener('pointerup', onPointerUp);
  document.addEventListener('pointercancel', onPointerCancel);
  document.addEventListener('click', onClick);
  document.addEventListener('scroll', onScroll, true);

  return () => {
    if (blurTimer !== undefined) window.clearTimeout(blurTimer);
    if (viewportCorrectionTimer !== undefined) window.clearTimeout(viewportCorrectionTimer);
    if (focusCorrectionTimer !== undefined) window.clearTimeout(focusCorrectionTimer);
    window.removeEventListener('resize', onViewportMutation);
    window.visualViewport?.removeEventListener('resize', onViewportMutation);
    window.visualViewport?.removeEventListener('scroll', onViewportMutation);
    document.removeEventListener('focusin', onFocusIn);
    document.removeEventListener('focusout', onFocusOut);
    document.removeEventListener('pointerdown', onPointerDown);
    document.removeEventListener('pointerup', onPointerUp);
    document.removeEventListener('pointercancel', onPointerCancel);
    document.removeEventListener('click', onClick);
    document.removeEventListener('scroll', onScroll, true);
    for (const timer of pointerReleaseTimers.values()) window.clearTimeout(timer);
    subscribedTelegram?.offEvent?.('viewportChanged', onTelegramViewport);
    subscribedTelegram?.offEvent?.('safeAreaChanged', onTelegramViewport);
    subscribedTelegram?.offEvent?.('contentSafeAreaChanged', onTelegramViewport);
    subscribedTelegram?.offEvent?.('fullscreenChanged', onTelegramViewport);
    root.classList.remove('keyboard-open');
    root.style.removeProperty('--loop-stable-height');
    root.style.removeProperty('--loop-visual-height');
    root.style.removeProperty('--loop-visual-page-top');
    root.style.removeProperty('--loop-safe-area-inset-top');
    root.style.removeProperty('--loop-safe-area-inset-right');
    root.style.removeProperty('--loop-safe-area-inset-bottom');
    root.style.removeProperty('--loop-safe-area-inset-left');
  };
}
