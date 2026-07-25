import { Buffer } from 'buffer';

import controlStylesUrl from './control/control.css?url';
import landingStylesUrl from './landing/landing.css?url';
import miniAppStylesUrl from './styles.css?url';
import { resolveWebSurface } from './surface';

globalThis.Buffer = Buffer;

function loadStylesheet(href: string, surface: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.loopStylesheet = surface;
    link.addEventListener('load', () => resolve(), { once: true });
    link.addEventListener(
      'error',
      () => reject(new Error(`Failed to load ${surface} stylesheet`)),
      { once: true },
    );
    document.head.append(link);
  });
}

const surface = resolveWebSurface({
  pathname: window.location.pathname,
  search: window.location.search,
  hash: window.location.hash,
  telegramInitData: window.Telegram?.WebApp?.initData,
  mockTelegram: import.meta.env.VITE_MOCK_TELEGRAM === 'true',
});

if (surface === 'control') {
  void loadStylesheet(controlStylesUrl, surface).then(() => import('./control/bootstrap'));
} else if (surface === 'mini-app') {
  void loadStylesheet(miniAppStylesUrl, surface).then(() => import('./bootstrap'));
} else {
  void loadStylesheet(landingStylesUrl, surface).then(() => import('./landing/bootstrap'));
}
