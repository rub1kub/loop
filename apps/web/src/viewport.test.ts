import { afterEach, describe, expect, it, vi } from 'vitest';

import { installViewportBehavior } from './viewport';

const initialInnerHeight = window.innerHeight;

describe('Telegram keyboard viewport behavior', () => {
  afterEach(() => {
    vi.useRealTimers();
    document.body.replaceChildren();
    document.documentElement.classList.remove('keyboard-open');
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
    expect(document.documentElement.style.getPropertyValue('--loop-visual-bottom-inset')).toBe(
      '270px',
    );

    input.blur();
    window.dispatchEvent(new Event('resize'));
    expect(document.documentElement).toHaveClass('keyboard-open');
    expect(document.documentElement.style.getPropertyValue('--loop-stable-height')).toBe('700px');
    vi.advanceTimersByTime(360);
    expect(document.documentElement).not.toHaveClass('keyboard-open');
    expect(document.documentElement.style.getPropertyValue('--loop-stable-height')).toBe('430px');
    cleanup();
  });
});
