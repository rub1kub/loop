export type CelebrationKind = 'burst' | 'spark';

const EVENT = 'loop-celebrate';

/**
 * Fires the app-wide celebration canvas from anywhere. A window event rather
 * than a store: nothing needs to know whether anyone is listening, and a
 * celebration that arrives while the canvas is unmounted is simply lost, which
 * is the right outcome for decoration.
 *
 * `burst` is the full confetti; `spark` is a smaller one for moments that are
 * good but not the point of the app.
 */
export function celebrate(kind: CelebrationKind = 'burst'): void {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: kind }));
}

export function onCelebrate(handler: (kind: CelebrationKind) => void): () => void {
  const listener = (event: Event) => {
    handler(((event as CustomEvent).detail as CelebrationKind) ?? 'burst');
  };
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
