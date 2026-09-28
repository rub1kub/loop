import { useCallback, useEffect, useRef, useState } from 'react';
import { pixelApi } from '../../api';
import { isMockTelegram } from '../../telegram';
import { demoPixelState, demoPlace } from './demo';
import { mergePixelState, type PixelPlace, type PixelState } from './protocol';

export function usePixels(userId: string, active: boolean) {
  const [state, setState] = useState<PixelState | null>(null);
  const [connected, setConnected] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = useRef<PixelState | null>(null);
  const busy = useRef(false);
  const timing = useRef({ server: 0, local: 0 });
  const pending = useRef<PixelPlace | null>(null);
  const refreshSignal = useRef<(() => void) | null>(null);
  const apply = useCallback((incoming: PixelState) => {
    const next = mergePixelState(current.current, incoming);
    if (next.server_time !== current.current?.server_time) {
      timing.current = { server: Date.parse(next.server_time), local: performance.now() };
    }
    current.current = next;
    setState(next);
    setConnected(true);
  }, []);
  const serverNow = useCallback(
    () => timing.current.server + performance.now() - timing.current.local,
    [],
  );

  useEffect(() => {
    let alive = true;
    let timer = 0;
    let controller: AbortController | null = null;
    let forceFull = true;
    let failures = 0;
    const schedule = (ms: number) => {
      window.clearTimeout(timer);
      if (alive && document.visibilityState !== 'hidden')
        timer = window.setTimeout(() => void tick(), ms);
    };
    const tick = async () => {
      if (!alive || document.visibilityState === 'hidden') return;
      controller?.abort();
      const requestController = new AbortController();
      controller = requestController;
      const previous = current.current;
      try {
        const incoming = isMockTelegram()
          ? demoPixelState()
          : await pixelApi.state(
              forceFull ? undefined : previous?.round?.id,
              forceFull ? undefined : previous?.round?.revision,
              requestController.signal,
              forceFull ? 0 : 20,
            );
        if (!alive || requestController.signal.aborted) return;
        apply(incoming);
        forceFull = false;
        failures = 0;
        schedule(incoming.enabled ? (active ? 1000 : 5000) : 60000);
      } catch {
        if (!alive || requestController.signal.aborted) return;
        forceFull = true;
        failures++;
        setConnected(false);
        schedule(Math.min(30000, 2000 * 2 ** Math.min(failures, 4)));
      }
    };
    const resume = () => {
      controller?.abort();
      window.clearTimeout(timer);
      if (document.visibilityState !== 'hidden') {
        forceFull = true;
        void tick();
      }
    };
    refreshSignal.current = resume;
    document.addEventListener('visibilitychange', resume);
    window.addEventListener('online', resume);
    void tick();
    return () => {
      alive = false;
      controller?.abort();
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', resume);
      window.removeEventListener('online', resume);
      refreshSignal.current = null;
    };
  }, [userId, active, apply]);

  const place = useCallback(
    async (x: number, y: number, color: number) => {
      const board = current.current;
      if (busy.current || !board?.round || board.round.archived) return false;
      busy.current = true;
      setPlacing(true);
      setError(null);
      const prior = pending.current;
      const body: PixelPlace =
        prior &&
        prior.round_id === board.round.id &&
        prior.x === x &&
        prior.y === y &&
        prior.color === color
          ? prior
          : { round_id: board.round.id, x, y, color, operation_id: crypto.randomUUID() };
      pending.current = body;
      try {
        const receipt = isMockTelegram() ? demoPlace(body) : await pixelApi.place(body);
        // Only a confirmed response paints the cell. Polling fills any missed revisions.
        const latest = current.current;
        if (latest?.round?.id === receipt.round_id) {
          const snapshot = {
            ...latest,
            server_time: receipt.server_time,
            ready_at: receipt.ready_at,
          };
          if (receipt.revision === latest.round.revision + 1) {
            snapshot.round = { ...latest.round, revision: receipt.revision };
            const pixels = (latest.pixels ?? '').split('');
            pixels[receipt.index] = receipt.color.toString(16);
            snapshot.pixels = pixels.join('');
          }
          apply(snapshot);
        }
        pending.current = null;
        refreshSignal.current?.();
        return true;
      } catch (cause) {
        setError(
          cause instanceof Error ? cause.message : 'Не удалось поставить пиксель. Повтори ход',
        );
        refreshSignal.current?.();
        return false;
      } finally {
        busy.current = false;
        setPlacing(false);
      }
    },
    [apply],
  );

  return {
    state,
    connected,
    placing,
    error,
    place,
    serverNow,
    clearError: () => setError(null),
    refresh: () => refreshSignal.current?.(),
  };
}
