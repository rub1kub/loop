import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TelegramWebApp } from '../../types';
import { gravityFromOrientation, startDeviceTilt } from './deviceTilt';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('BANK device tilt', () => {
  it('projects Telegram radians onto the screen with a stable dead zone', () => {
    expect(gravityFromOrientation(0, 0)).toEqual({ x: 0, y: 1 });
    expect(gravityFromOrientation(Number.NaN, 0)).toEqual({ x: 0, y: 1 });
    expect(gravityFromOrientation(0, Math.PI / 6)).toEqual({ x: 0.49999999999999994, y: 0 });

    const diagonal = gravityFromOrientation(Math.PI / 2, Math.PI / 6);
    expect(diagonal.x).toBeCloseTo(0.447, 3);
    expect(diagonal.y).toBeCloseTo(0.894, 3);
  });

  it('starts the Telegram sensor by feature detection and rearms it after activation', () => {
    const handlers = new Map<string, Set<() => void>>();
    const orientation = {
      isStarted: true,
      absolute: false,
      alpha: 0,
      beta: 0,
      gamma: 0,
      start: vi.fn(
        (
          _params: { refresh_rate?: number; need_absolute?: boolean },
          callback?: (started: boolean) => void,
        ) => callback?.(true),
      ),
      stop: vi.fn((callback?: (stopped: boolean) => void) => callback?.(true)),
    };
    const app = {
      DeviceOrientation: orientation,
      onEvent: vi.fn((event: string, callback: () => void) => {
        const bucket = handlers.get(event) ?? new Set();
        bucket.add(callback);
        handlers.set(event, bucket);
      }),
      offEvent: vi.fn((event: string, callback: () => void) =>
        handlers.get(event)?.delete(callback),
      ),
    } as unknown as TelegramWebApp;
    const gravity = vi.fn();

    const session = startDeviceTilt(app, gravity);

    expect(orientation.start).toHaveBeenCalledWith(
      { refresh_rate: 20, need_absolute: false },
      expect.any(Function),
    );
    orientation.beta = Math.PI / 2;
    orientation.gamma = 0;
    handlers.get('deviceOrientationChanged')?.forEach((callback) => callback());
    expect(gravity).toHaveBeenLastCalledWith({ x: 0, y: 1 });

    handlers.get('activated')?.forEach((callback) => callback());
    expect(orientation.start).toHaveBeenCalledTimes(2);

    session.stop();
    expect(orientation.stop).toHaveBeenCalledOnce();
  });

  it('falls back to the browser sensor in clients without the Telegram bridge', () => {
    const gravity = vi.fn();
    const session = startDeviceTilt(undefined, gravity);
    const event = new Event('deviceorientation') as DeviceOrientationEvent;
    Object.defineProperties(event, {
      beta: { value: 0 },
      gamma: { value: 30 },
    });

    window.dispatchEvent(event);
    expect(gravity).toHaveBeenLastCalledWith({ x: 0.49999999999999994, y: 0 });

    session.stop();
    gravity.mockClear();
    window.dispatchEvent(event);
    expect(gravity).not.toHaveBeenCalled();
  });

  it('requests the iOS browser permission only after an explicit BANK gesture', async () => {
    const requestPermission = vi.fn().mockResolvedValue('granted');
    vi.stubGlobal('DeviceOrientationEvent', { requestPermission });
    const session = startDeviceTilt(undefined, vi.fn());

    await session.requestPermission();
    await session.requestPermission();

    expect(requestPermission).toHaveBeenCalledOnce();
    session.stop();
  });
});
