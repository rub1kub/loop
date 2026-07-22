import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TelegramWebApp } from './types';
import { installViewportBehavior } from './viewport';

const initialInnerHeight = window.innerHeight;
const initialVisualViewport = Object.getOwnPropertyDescriptor(window, 'visualViewport');

describe('Telegram keyboard viewport behavior', () => {
  afterEach(() => {
    vi.useRealTimers();
    document.body.replaceChildren();
    document.documentElement.classList.remove('keyboard-open');
    delete window.Telegram;
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      value: initialInnerHeight,
    });
    if (initialVisualViewport)
      Object.defineProperty(window, 'visualViewport', initialVisualViewport);
    else Object.defineProperty(window, 'visualViewport', { configurable: true, value: undefined });
  });

  it('hides navigation and freezes the app height while an input owns the keyboard', () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 700 });
    const input = document.createElement('input');
    document.body.append(input);
    const cleanup = installViewportBehavior();

    expect(document.documentElement.style.getPropertyValue('--loop-stable-height')).toBe('700px');
    input.focus();
    expect(document.documentElement).toHaveClass('keyboard-open');

    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 430 });
    window.dispatchEvent(new Event('resize'));
    expect(document.documentElement.style.getPropertyValue('--loop-stable-height')).toBe('700px');
    expect(document.documentElement.style.getPropertyValue('--loop-visual-height')).toBe('430px');
    input.blur();
    window.dispatchEvent(new Event('resize'));
    expect(document.documentElement).toHaveClass('keyboard-open');
    expect(document.documentElement.style.getPropertyValue('--loop-stable-height')).toBe('700px');
    vi.advanceTimersByTime(360);
    expect(document.documentElement).not.toHaveClass('keyboard-open');
    expect(document.documentElement.style.getPropertyValue('--loop-stable-height')).toBe('430px');
    cleanup();
  });

  it('does not restore navigation in the middle of a tap after keyboard blur', () => {
    vi.useFakeTimers();
    const input = document.createElement('input');
    const button = document.createElement('button');
    document.body.append(input, button);
    const cleanup = installViewportBehavior();

    input.focus();
    input.blur();
    button.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 7 }));
    button.focus();
    vi.advanceTimersByTime(360);
    expect(document.documentElement).toHaveClass('keyboard-open');

    button.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 7 }));
    button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    vi.advanceTimersByTime(80);
    expect(document.documentElement).not.toHaveClass('keyboard-open');
    cleanup();
  });

  it('uses Telegram stable height and the largest native safe-area inset', () => {
    const onEvent = vi.fn();
    const offEvent = vi.fn();
    window.Telegram = {
      WebApp: {
        viewportStableHeight: 720,
        safeAreaInset: { top: 44, right: 0, bottom: 34, left: 0 },
        contentSafeAreaInset: { top: 56, right: 8, bottom: 0, left: 8 },
        onEvent,
        offEvent,
      } as unknown as TelegramWebApp,
    };

    const cleanup = installViewportBehavior();
    expect(document.documentElement.style.getPropertyValue('--loop-stable-height')).toBe('720px');
    expect(document.documentElement.style.getPropertyValue('--loop-safe-area-inset-top')).toBe(
      '56px',
    );
    expect(document.documentElement.style.getPropertyValue('--loop-safe-area-inset-bottom')).toBe(
      '34px',
    );
    expect(onEvent).toHaveBeenCalledWith('contentSafeAreaChanged', expect.any(Function));

    cleanup();
    expect(offEvent).toHaveBeenCalledWith('contentSafeAreaChanged', expect.any(Function));
  });

  it('keeps fullscreen content below Telegram overlay controls', () => {
    let onFullscreenChanged: (() => void) | undefined;
    window.Telegram = {
      WebApp: {
        isFullscreen: false,
        safeAreaInset: { top: 44, right: 0, bottom: 34, left: 0 },
        contentSafeAreaInset: { top: 56, right: 0, bottom: 0, left: 0 },
        onEvent: (event: string, callback: (payload?: { isStateStable?: boolean }) => void) => {
          if (event === 'fullscreenChanged') onFullscreenChanged = () => callback();
        },
      } as unknown as TelegramWebApp,
    };

    const cleanup = installViewportBehavior();
    expect(document.documentElement.style.getPropertyValue('--loop-safe-area-inset-top')).toBe(
      '56px',
    );
    window.Telegram.WebApp.isFullscreen = true;
    onFullscreenChanged?.();
    expect(document.documentElement.style.getPropertyValue('--loop-safe-area-inset-top')).toBe(
      '72px',
    );
    window.Telegram.WebApp.isFullscreen = false;
    window.Telegram.WebApp.safeAreaInset = { top: 44, right: 0, bottom: 34, left: 0 };
    window.Telegram.WebApp.contentSafeAreaInset = { top: 56, right: 0, bottom: 0, left: 0 };
    onFullscreenChanged?.();
    expect(document.documentElement.style.getPropertyValue('--loop-safe-area-inset-top')).toBe(
      '72px',
    );
    cleanup();
  });

  it('counters delayed iOS visual viewport panning and restores the focused screen', () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 700 });
    const viewportValues = { height: 700, offsetTop: 0, pageTop: 0 };
    const viewportTarget = new EventTarget();
    Object.defineProperties(viewportTarget, {
      height: { get: () => viewportValues.height },
      offsetTop: { get: () => viewportValues.offsetTop },
      pageTop: { get: () => viewportValues.pageTop },
    });
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: viewportTarget,
    });

    const screen = document.createElement('section');
    screen.className = 'screen';
    const input = document.createElement('input');
    screen.append(input);
    document.body.append(screen);
    const cleanup = installViewportBehavior();

    input.focus();
    screen.scrollTop = 180;
    viewportValues.height = 430;
    viewportTarget.dispatchEvent(new Event('resize'));
    expect(screen.scrollTop).toBe(0);
    expect(document.documentElement.style.getPropertyValue('--loop-visual-page-top')).toBe('0px');

    viewportValues.offsetTop = 260;
    viewportValues.pageTop = 260;
    vi.advanceTimersByTime(50);
    expect(document.documentElement.style.getPropertyValue('--loop-visual-page-top')).toBe('260px');
    cleanup();
  });
});
