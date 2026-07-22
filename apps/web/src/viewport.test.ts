import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TelegramWebApp } from './types';
import { installViewportBehavior } from './viewport';

const initialInnerHeight = window.innerHeight;

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
});
