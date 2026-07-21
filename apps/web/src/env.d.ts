/// <reference types="vite/client" />

import type { TelegramWebApp } from './types';

declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
    readonly VITE_TONCONNECT_MANIFEST_URL?: string;
    readonly VITE_MOCK_TELEGRAM?: string;
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }

  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
    render_game_to_text?: () => string;
    advanceTime?: (milliseconds: number) => void;
  }
}

export {};
