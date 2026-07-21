import { TonConnectUIProvider } from '@tonconnect/ui-react';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';

const manifestUrl =
  import.meta.env.VITE_TONCONNECT_MANIFEST_URL ??
  `${window.location.origin}/tonconnect-manifest.json`;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TonConnectUIProvider
      manifestUrl={manifestUrl}
      actionsConfiguration={{ twaReturnUrl: window.location.href as `${string}://${string}` }}
    >
      <App />
    </TonConnectUIProvider>
  </StrictMode>,
);
