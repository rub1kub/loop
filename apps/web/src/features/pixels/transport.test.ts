import { afterEach, expect, it, vi } from 'vitest';
import { pixelApi } from '../../api';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
const hangingFetch = () => {
  const fetcher = vi.fn<typeof fetch>(
    (_url, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        );
      }),
  );
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
};

it('ends a stalled paint request without retrying a financial or pixel mutation', async () => {
  vi.useFakeTimers();
  const fetcher = hangingFetch();
  const request = expect(
    pixelApi.place({
      round_id: '2026-09-28',
      x: 0,
      y: 0,
      color: 1,
      operation_id: crypto.randomUUID(),
    }),
  ).rejects.toThrow('Полотно не отвечает');
  await vi.advanceTimersByTimeAsync(15000);
  await request;
  expect(fetcher).toHaveBeenCalledOnce();
});

it('aborts a hidden page poll immediately without retrying it', async () => {
  const fetcher = hangingFetch();
  const controller = new AbortController();
  const request = expect(pixelApi.state('2026-09-28', 0, controller.signal, 20)).rejects.toThrow(
    'Aborted',
  );
  controller.abort();
  await request;
  expect(fetcher).toHaveBeenCalledOnce();
});
