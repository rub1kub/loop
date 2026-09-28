import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { PixelPlace, PixelReceipt, PixelState } from './protocol';
import { usePixels } from './usePixels';

const api = vi.hoisted(() => ({
  state:
    vi.fn<
      (round?: string, after?: number, signal?: AbortSignal, wait?: number) => Promise<PixelState>
    >(),
  place: vi.fn<(body: PixelPlace) => Promise<PixelReceipt>>(),
}));
vi.mock('../../api', () => ({ pixelApi: api }));
vi.mock('../../telegram', () => ({ isMockTelegram: () => false }));
const board = (): PixelState => ({
  enabled: true,
  round: {
    id: '2026-09-28',
    starts_at: '2026-09-27T21:00:00Z',
    ends_at: '2026-10-04T21:00:00Z',
    revision: 0,
    archived: false,
  },
  server_time: '2026-09-28T12:00:00Z',
  ready_at: null,
  size: 128,
  cooldown_seconds: 30,
  palette: Array<string>(16).fill('#000000'),
  pixels: '0'.repeat(16384),
  changes: [],
});
const receipt: PixelReceipt = {
  round_id: '2026-09-28',
  revision: 1,
  index: 1300,
  color: 4,
  server_time: '2026-09-28T12:00:01Z',
  ready_at: '2026-09-28T12:00:31Z',
  replayed: false,
};
beforeEach(() => {
  api.state.mockReset().mockResolvedValue(board());
  api.place.mockReset();
});
afterEach(cleanup);

it('keeps an unconfirmed cell unchanged and reuses the move ID after a network error', async () => {
  api.place.mockRejectedValueOnce(new Error('Связь потеряна')).mockResolvedValueOnce(receipt);
  const { result } = renderHook(() => usePixels('player', true));
  await waitFor(() => expect(result.current.connected).toBe(true));
  await act(async () => {
    expect(await result.current.place(20, 10, 4)).toBe(false);
  });
  expect(result.current.state?.pixels?.[1300]).toBe('0');
  expect(result.current.placing).toBe(false);
  await act(async () => {
    expect(await result.current.place(20, 10, 4)).toBe(true);
  });
  const [first, second] = api.place.mock.calls.map((call) => call[0]);
  expect(first.operation_id).toBe(second.operation_id);
  expect(result.current.state?.pixels?.[1300]).toBe('4');
  expect(result.current.state?.ready_at).toBe(receipt.ready_at);
});

it('blocks a double tap while confirmation is pending', async () => {
  let confirm!: (value: PixelReceipt) => void;
  api.place.mockImplementation(
    () =>
      new Promise<PixelReceipt>((resolve) => {
        confirm = resolve;
      }),
  );
  const { result } = renderHook(() => usePixels('player', true));
  await waitFor(() => expect(result.current.connected).toBe(true));
  await act(async () => {
    const first = result.current.place(20, 10, 4);
    expect(await result.current.place(21, 10, 4)).toBe(false);
    confirm(receipt);
    await first;
  });
  expect(api.place).toHaveBeenCalledOnce();
});

it('ignores a response from an aborted poll after the mode changes', async () => {
  let finish!: (value: PixelState) => void;
  api.state.mockImplementationOnce(
    () =>
      new Promise<PixelState>((resolve) => {
        finish = resolve;
      }),
  );
  const { result, rerender } = renderHook(({ active }) => usePixels('player', active), {
    initialProps: { active: false },
  });
  rerender({ active: true });
  await waitFor(() => expect(result.current.connected).toBe(true));
  await act(async () => {
    finish({ ...board(), enabled: false });
    await Promise.resolve();
  });
  expect(result.current.state?.enabled).toBe(true);
  expect(api.state.mock.calls[0][2]?.aborted).toBe(true);
});
