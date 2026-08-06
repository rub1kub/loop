import { TonConnectUIProvider } from '@tonconnect/ui-react';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import ControlApp from './ControlApp';

const manifestUrl =
  import.meta.env.VITE_TONCONNECT_MANIFEST_URL ??
  `${window.location.origin}/tonconnect-manifest.json`;

// Заголовок вкладки виден и в истории браузера, и в превью ссылки.
document.title = 'LOOP';
document.documentElement.dataset.surface = 'control';
// Дверь не должна попадать в поисковую выдачу: страница ничего не отдаёт без
// подписи владельца, но и находиться по запросу «панель управления» ей незачем.
const robots = document.createElement('meta');
robots.name = 'robots';
robots.content = 'noindex, nofollow';
document.head.appendChild(robots);
document
  .querySelector('meta[name="viewport"]')
  ?.setAttribute('content', 'width=device-width, initial-scale=1, viewport-fit=cover');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TonConnectUIProvider manifestUrl={manifestUrl} analytics={{ mode: 'off' }}>
      <ControlApp />
    </TonConnectUIProvider>
  </StrictMode>,
);
