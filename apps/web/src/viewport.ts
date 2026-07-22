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
    offsetTop: Math.round(viewport?.offsetTop ?? 0),
  };
}

export function installViewportBehavior(): () => void {
  const root = document.documentElement;
  let stableHeight = Math.max(window.innerHeight, currentViewport().height);
  let blurTimer: number | undefined;
  let keyboardSettling = false;

  const sync = () => {
    const viewport = currentViewport();
    const keyboardOpen = isEditable(document.activeElement) || keyboardSettling;
    const bottomInset = Math.max(0, stableHeight - viewport.height - viewport.offsetTop);

    if (!keyboardOpen) stableHeight = viewport.height;
    root.style.setProperty('--loop-stable-height', `${stableHeight}px`);
    root.style.setProperty('--loop-visual-height', `${viewport.height}px`);
    root.style.setProperty('--loop-visual-offset-top', `${viewport.offsetTop}px`);
    root.style.setProperty('--loop-visual-bottom-inset', `${bottomInset}px`);
    root.classList.toggle('keyboard-open', keyboardOpen);
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
    root.classList.remove('keyboard-open');
    root.style.removeProperty('--loop-stable-height');
    root.style.removeProperty('--loop-visual-height');
    root.style.removeProperty('--loop-visual-offset-top');
    root.style.removeProperty('--loop-visual-bottom-inset');
  };
}
