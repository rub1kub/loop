import { describe, expect, it } from 'vitest';
import { mergePixelState, pixelStateSchema, type PixelState } from './protocol';
import { pixelAt } from './geometry';

const snapshot = (revision = 0): PixelState => ({
  enabled: true,
  round: {
    id: '2026-09-28',
    starts_at: '2026-09-27T21:00:00Z',
    ends_at: '2026-10-04T21:00:00Z',
    revision,
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

describe('Pixel synchronization', () => {
  it('applies ordered changes and tolerates overlapping delivery', () => {
    const initial = snapshot();
    const delta = {
      ...snapshot(2),
      pixels: null,
      changes: [
        { revision: 1, index: 50, color: 4 },
        { revision: 2, index: 50, color: 6 },
      ],
    };
    const next = mergePixelState(initial, delta);
    expect(next.pixels?.[50]).toBe('6');
    expect(mergePixelState(next, delta).round?.revision).toBe(2);
  });
  it('keeps newer paint when an earlier snapshot arrives late', () => {
    const current = { ...snapshot(4), pixels: '4' + '0'.repeat(16383) };
    expect(mergePixelState(current, snapshot(2)).pixels?.[0]).toBe('4');
  });
  it('does not lose an acknowledged cooldown to an old poll', () => {
    const current = {
      ...snapshot(1),
      server_time: '2026-09-28T12:00:05Z',
      ready_at: '2026-09-28T12:00:35Z',
    };
    expect(mergePixelState(current, snapshot()).ready_at).toBe(current.ready_at);
  });
  it('requests a fresh snapshot on missing revisions', () => {
    expect(() =>
      mergePixelState(snapshot(), {
        ...snapshot(2),
        pixels: null,
        changes: [{ revision: 2, index: 0, color: 5 }],
      }),
    ).toThrow();
    expect(() => mergePixelState(null, { ...snapshot(), pixels: null })).toThrow();
  });
  it('cannot bring the previous week back after rollover', () => {
    const current = { ...snapshot(), round: { ...snapshot().round!, id: '2026-10-05' } };
    expect(mergePixelState(current, snapshot(5)).round?.id).toBe('2026-10-05');
  });
  it('validates bounds and snapshot size', () => {
    expect(pixelStateSchema.safeParse({ ...snapshot(), pixels: '0' }).success).toBe(false);
    expect(
      pixelStateSchema.safeParse({
        ...snapshot(),
        changes: [{ revision: 1, index: 16384, color: 1 }],
      }).success,
    ).toBe(false);
  });
});

describe('Canvas hit testing', () => {
  it('maps the center consistently on phone and folded viewports', () => {
    for (const [width, height] of [
      [320, 500],
      [390, 520],
      [768, 350],
    ]) {
      expect(
        pixelAt({ x: width / 2, y: height / 2 }, width, height, { zoom: 1, x: 0, y: 0 }),
      ).toEqual({ x: 64, y: 64 });
    }
  });
  it('ignores letterbox space and accounts for pan and zoom', () => {
    expect(pixelAt({ x: 0, y: 0 }, 390, 600, { zoom: 1, x: 0, y: 0 })).toBeNull();
    expect(pixelAt({ x: 245, y: 320 }, 390, 600, { zoom: 4, x: 50, y: 20 })).toEqual({
      x: 64,
      y: 64,
    });
  });
});
