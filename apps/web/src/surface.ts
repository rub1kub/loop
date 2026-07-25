export type WebSurface = 'control' | 'landing' | 'mini-app';

interface SurfaceContext {
  pathname: string;
  search: string;
  hash: string;
  telegramInitData?: string;
  mockTelegram?: boolean;
}

function hasTelegramParameter(value: string): boolean {
  const parameters = new URLSearchParams(value.replace(/^[?#]/, ''));
  return (
    parameters.has('tgWebAppData') ||
    parameters.has('tgWebAppVersion') ||
    parameters.has('tgWebAppPlatform')
  );
}

export function resolveWebSurface({
  pathname,
  search,
  hash,
  telegramInitData,
  mockTelegram = false,
}: SurfaceContext): WebSurface {
  if (pathname === '/control' || pathname.startsWith('/control/')) return 'control';
  if (
    mockTelegram ||
    Boolean(telegramInitData?.trim()) ||
    hasTelegramParameter(search) ||
    hasTelegramParameter(hash)
  ) {
    return 'mini-app';
  }
  return 'landing';
}
