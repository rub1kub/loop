import { TonConnectUIProvider } from '@tonconnect/ui-react';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import ControlApp from './ControlApp';
import './control.css';

const manifestUrl =
  import.meta.env.VITE_TONCONNECT_MANIFEST_URL ??
  `${window.location.origin}/tonconnect-manifest.json`;

document.title = 'LOOP — Панель управления';
document.documentElement.dataset.surface = 'control';
document
  .querySelector('meta[name="viewport"]')
  ?.setAttribute('content', 'width=device-width, initial-scale=1, viewport-fit=cover');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TonConnectUIProvider manifestUrl={manifestUrl}>
      <ControlApp />
    </TonConnectUIProvider>
  </StrictMode>,
);
