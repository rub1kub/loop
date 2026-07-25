import { Buffer } from 'buffer';

import { resolveWebSurface } from './surface';

globalThis.Buffer = Buffer;

const surface = resolveWebSurface({
  pathname: window.location.pathname,
  search: window.location.search,
  hash: window.location.hash,
  telegramInitData: window.Telegram?.WebApp?.initData,
  mockTelegram: import.meta.env.VITE_MOCK_TELEGRAM === 'true',
});

if (surface === 'control') {
  void import('./control/bootstrap');
} else if (surface === 'mini-app') {
  void import('./styles.css').then(() => import('./bootstrap'));
} else {
  void import('./landing/bootstrap');
}
