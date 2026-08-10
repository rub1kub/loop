import type { TelegramWebApp } from '../../types';

const TELEGRAM_REFRESH_MS = 20;
const TELEGRAM_EVENT_FRESH_MS = 750;
const TILT_DEAD_ZONE = 0.12;

export interface TiltGravity {
  x: number;
  y: number;
}

type PermissionedDeviceOrientationEvent = typeof DeviceOrientationEvent & {
  requestPermission?: () => Promise<'granted' | 'denied'>;
};

/** Converts the device's attitude into gravity projected onto the screen. */
export function gravityFromOrientation(beta: number, gamma: number): TiltGravity {
  if (!Number.isFinite(beta) || !Number.isFinite(gamma)) return { x: 0, y: 1 };
  const x = Math.sin(gamma);
  const y = Math.sin(beta);
  const magnitude = Math.hypot(x, y);
  if (magnitude < TILT_DEAD_ZONE) return { x: 0, y: 1 };
  const scale = Math.max(magnitude, 1);
  return { x: x / scale, y: y / scale };
}

export interface DeviceTiltSession {
  /** iOS only allows the browser sensor prompt from a direct user gesture. */
  requestPermission(): Promise<void>;
  stop(): void;
}

/**
 * Feeds BANK from the Telegram 8.0 orientation bridge and keeps a standards-
 * based fallback alive for third-party Telegram clients that expose the Mini
 * App API but answer its sensor request with UNSUPPORTED.
 */
export function startDeviceTilt(
  app: TelegramWebApp | undefined,
  onGravity: (gravity: TiltGravity) => void,
  host: Window = window,
): DeviceTiltSession {
  const orientation = app?.DeviceOrientation;
  let disposed = false;
  let startPending = false;
  let telegramOwned = false;
  let lastTelegramEvent = Number.NEGATIVE_INFINITY;
  let permissionRequested = false;

  const applyTelegramOrientation = () => {
    if (!orientation || !Number.isFinite(orientation.beta) || !Number.isFinite(orientation.gamma)) {
      return;
    }
    lastTelegramEvent = host.performance.now();
    onGravity(gravityFromOrientation(orientation.beta, orientation.gamma));
  };

  const startTelegram = () => {
    if (!orientation || disposed || startPending) return;
    startPending = true;
    orientation.start({ refresh_rate: TELEGRAM_REFRESH_MS, need_absolute: false }, (started) => {
      startPending = false;
      if (disposed) {
        if (started) orientation.stop();
        return;
      }
      telegramOwned ||= started;
      if (started) applyTelegramOrientation();
    });
  };

  const onTelegramStarted = () => {
    startPending = false;
    telegramOwned = true;
    applyTelegramOrientation();
  };
  const onTelegramStopped = () => {
    startPending = false;
  };
  const onTelegramFailed = () => {
    // The W3C listener below remains active and takes over automatically.
    startPending = false;
  };
  const restartTelegram = () => startTelegram();

  app?.onEvent?.('deviceOrientationChanged', applyTelegramOrientation);
  app?.onEvent?.('deviceOrientationStarted', onTelegramStarted);
  app?.onEvent?.('deviceOrientationStopped', onTelegramStopped);
  app?.onEvent?.('deviceOrientationFailed', onTelegramFailed);
  app?.onEvent?.('activated', restartTelegram);
  app?.onEvent?.('fullscreenChanged', restartTelegram);
  startTelegram();

  const onBrowserOrientation = (event: DeviceOrientationEvent) => {
    // Never let a lower-rate browser event fight a working Telegram stream.
    if (host.performance.now() - lastTelegramEvent < TELEGRAM_EVENT_FRESH_MS) return;
    if (!Number.isFinite(event.beta) || !Number.isFinite(event.gamma)) return;
    const toRadians = Math.PI / 180;
    onGravity(gravityFromOrientation(event.beta! * toRadians, event.gamma! * toRadians));
  };
  host.addEventListener('deviceorientation', onBrowserOrientation, { passive: true });

  const requestPermission = async () => {
    if (permissionRequested || disposed) return;
    const constructor = (
      host as unknown as {
        DeviceOrientationEvent?: PermissionedDeviceOrientationEvent;
      }
    ).DeviceOrientationEvent;
    if (!constructor?.requestPermission) return;
    permissionRequested = true;
    try {
      await constructor.requestPermission();
    } catch {
      // A denied browser fallback does not affect Telegram's native bridge.
    }
  };

  return {
    requestPermission,
    stop() {
      if (disposed) return;
      disposed = true;
      host.removeEventListener('deviceorientation', onBrowserOrientation);
      app?.offEvent?.('deviceOrientationChanged', applyTelegramOrientation);
      app?.offEvent?.('deviceOrientationStarted', onTelegramStarted);
      app?.offEvent?.('deviceOrientationStopped', onTelegramStopped);
      app?.offEvent?.('deviceOrientationFailed', onTelegramFailed);
      app?.offEvent?.('activated', restartTelegram);
      app?.offEvent?.('fullscreenChanged', restartTelegram);
      if (telegramOwned || orientation?.isStarted) orientation?.stop();
    },
  };
}
