import { afterEach, describe, expect, it } from 'vitest';

import { installInteractionGuards } from './interactionGuards';

let cleanup: (() => void) | undefined;

afterEach(() => {
  cleanup?.();
  cleanup = undefined;
  document.body.replaceChildren();
});

describe('Mini App interaction guards', () => {
  it('blocks selection everywhere, including editable amount fields', () => {
    cleanup = installInteractionGuards();
    const label = document.createElement('span');
    const input = document.createElement('input');
    document.body.append(label, input);

    expect(label.dispatchEvent(new Event('selectstart', { bubbles: true, cancelable: true }))).toBe(
      false,
    );
    expect(input.dispatchEvent(new Event('selectstart', { bubbles: true, cancelable: true }))).toBe(
      false,
    );
  });

  it('blocks context menus, dragging and browser zoom shortcuts', () => {
    cleanup = installInteractionGuards();
    const image = document.createElement('img');
    document.body.append(image);

    expect(image.dispatchEvent(new Event('contextmenu', { bubbles: true, cancelable: true }))).toBe(
      false,
    );
    expect(image.dispatchEvent(new Event('dragstart', { bubbles: true, cancelable: true }))).toBe(
      false,
    );
    expect(
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: '+', ctrlKey: true, cancelable: true }),
      ),
    ).toBe(false);
    expect(
      document.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, cancelable: true })),
    ).toBe(false);
  });
});
