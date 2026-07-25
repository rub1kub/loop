import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { LandingPage } from './LandingPage';

document.title = 'LOOP — социальная игра в Telegram';
document.documentElement.dataset.surface = 'landing';
document.documentElement.lang = 'ru';
document
  .querySelector('meta[name="viewport"]')
  ?.setAttribute('content', 'width=device-width, initial-scale=1, viewport-fit=cover');
document
  .querySelector('meta[name="description"]')
  ?.setAttribute(
    'content',
    'LOOP — очередь BANK и дуэли 50/50 внутри Telegram. Открытый код и операции в TON.',
  );

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LandingPage />
  </StrictMode>,
);
