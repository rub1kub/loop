export type Tab = 'bank' | 'duel' | 'profile';

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe?: {
    start_param?: string;
    user?: { id: number; first_name: string; username?: string };
  };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  isFullscreen?: boolean;
  safeAreaInset?: { top: number; bottom: number; left: number; right: number };
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number };
  ready(): void;
  expand(): void;
  isVersionAtLeast(version: string): boolean;
  requestFullscreen?(): void;
  exitFullscreen?(): void;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  setBottomBarColor?(color: string): void;
  disableVerticalSwipes?(): void;
  enableClosingConfirmation?(): void;
  openTelegramLink(url: string): void;
  switchInlineQuery?(query: string, chooseChatTypes?: string[]): void;
  BackButton: {
    show(): void;
    hide(): void;
    onClick(callback: () => void): void;
    offClick(callback: () => void): void;
  };
  MainButton: {
    show(): void;
    hide(): void;
    enable(): void;
    disable(): void;
    setText(text: string): void;
    onClick(callback: () => void): void;
    offClick(callback: () => void): void;
  };
  HapticFeedback: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(type: 'error' | 'success' | 'warning'): void;
    selectionChanged(): void;
  };
  SecureStorage?: {
    setItem(key: string, value: string, callback?: (error: string | null) => void): void;
    getItem(key: string, callback: (error: string | null, value: string | null) => void): void;
    removeItem(key: string, callback?: (error: string | null) => void): void;
  };
}

export interface User {
  id: string;
  telegram_id: number;
  username: string | null;
  first_name: string;
  onboarding_seen: boolean;
}

export interface Wallet {
  address: string;
  network: number;
  verified_at: string;
}

export interface BankPosition {
  target_nano: number;
  updated_at: string;
}

export interface Profile {
  user: User;
  wallet: Wallet | null;
  bank: BankPosition | null;
  balance_nano: number | null;
  plush_brick_holder: boolean;
}

export interface Offer {
  id: string;
  onchain_offer_id: number;
  chance_bps: number;
  total_pool_nano: number;
  stake_nano: number;
  state: string;
  expires_at: string;
}

export interface OfferQuote {
  offer: Offer;
  transaction: {
    operation: 'open_offer';
    query_id: number;
    offer_id: number;
    counter_offer_id: number;
    contract_address: string;
    amount_nano: string;
    valid_until: number;
    chance_bps: number;
    total_pool_nano: string;
    commitment_hex: string;
    expires_at: number;
    commitment_domain: number;
  };
}

export interface Duel {
  id: string;
  onchain_duel_id: number;
  state: string;
  offer_id: number;
  own_revealed: boolean;
  chance_bps: number;
  total_pool_nano: number;
  reveal_deadline: string;
  winner_wallet: string | null;
}

export interface ActionIntent {
  operation: 'reveal' | 'cancel_offer' | 'expire_offer' | 'expire_duel';
  query_id: number;
  offer_id: number;
  duel_id: number;
  contract_address: string;
  amount_nano: string;
  valid_until: number;
}

export interface Referral {
  code: string;
  url: string;
  invited: number;
  qualified: number;
  reward_points: number;
}

export interface Invite {
  code: string;
  creator_telegram_id: number;
  stake_nano: number;
  chance_bps: number;
  expires_at: string;
}
