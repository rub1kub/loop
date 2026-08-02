import { useEffect, useRef, useState } from 'react';

/**
 * Counts from the previous value to the next one instead of jumping. A figure
 * that slides reads as the thing itself changing; a figure that snaps reads as
 * the page having been redrawn. Honours reduced motion by snapping.
 */
export function useCountUp(value: number, duration = 600): number {
  const [shown, setShown] = useState(value);
  const fromRef = useRef(value);
  const rafRef = useRef(0);

  useEffect(() => {
    const from = fromRef.current;
    if (from === value) return;
    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || duration <= 0) {
      // Snap on the next frame rather than synchronously: a setState in the
      // effect body would run before paint and defeats the point anyway.
      rafRef.current = window.requestAnimationFrame(() => {
        fromRef.current = value;
        setShown(value);
      });
      return () => window.cancelAnimationFrame(rafRef.current);
    }
    const started = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / duration);
      // Ease out: fast at first, settling at the end.
      const eased = 1 - (1 - progress) ** 3;
      const current = from + (value - from) * eased;
      setShown(current);
      if (progress < 1) rafRef.current = window.requestAnimationFrame(tick);
      else fromRef.current = value;
    };
    rafRef.current = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(rafRef.current);
  }, [duration, value]);

  return shown;
}
