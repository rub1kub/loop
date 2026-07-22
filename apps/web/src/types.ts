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
  viewportHeight?: number;
  viewportStableHeight?: number;
  safeAreaInset?: { top: number; bottom: number; left: number; right: number };
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number };
  ready?(): void;
  expand?(): void;
  isVersionAtLeast?(version: string): boolean;
  requestFullscreen?(): void;
  exitFullscreen?(): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  setBottomBarColor?(color: string): void;
  disableVerticalSwipes?(): void;
  enableClosingConfirmation?(): void;
  onEvent?(event: string, callback: (payload?: { isStateStable?: boolean }) => void): void;
  offEvent?(event: string, callback: (payload?: { isStateStable?: boolean }) => void): void;
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
  photo_url: string | null;
  onboarding_seen: boolean;
  onboarding_enabled: boolean;
}

export interface Wallet {
  address: string;
  network: number;
  verified_at: string;
}

export interface ModeStats {
  active: number;
  completed: number;
  total: number;
}

export interface PlushBrick {
  verified: boolean;
  balance_nano: number;
  holder: boolean;
  duel_fee_bps: number;
  fee_discount_active: boolean;
}

export interface Profile {
  user: User;
  wallet: Wallet | null;
  bank: ModeStats;
  duel: ModeStats;
  plush_brick: PlushBrick;
}

export type BankStatus =
  'pending_confirmation' | 'queued' | 'partially_funded' | 'completed' | 'payout_sent' | 'failed';

export interface BankPosition {
  id: string;
  position_id: number;
  owner_wallet: string;
  principal_nano: number;
  multiplier_bps: 12500 | 15000 | 20000;
  target_payout_nano: number;
  funded_amount_nano: number;
  remaining_amount_nano: number;
  progress_bps: number;
  queue_index: number | null;
  current_status: BankStatus;
  funding_transaction: string | null;
  payout_transaction: string | null;
  proof_url: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface BankQuote {
  position: BankPosition;
  transaction: {
    operation: 'create_bank_position';
    query_id: number;
    position_id: number;
    contract_address: string;
    amount_nano: string;
    principal_nano: string;
    multiplier_bps: number;
    valid_until: number;
    network: number;
    fee_nano: string;
  };
}

export interface BankPreview {
  principal_nano: number;
  multiplier_bps: number;
  target_payout_nano: number;
  fee_nano: number;
  gas_nano: number;
  transaction_amount_nano: number;
  contract_address: string;
  network: number;
}

export interface Offer {
  id: string;
  onchain_offer_id: number;
  chance_bps: 2500 | 5000 | 7500;
  total_pool_nano: number;
  stake_nano: number;
  opponent_stake_nano: number;
  fee_bps: number;
  payout_nano: number;
  net_profit_nano: number;
  mode: 'afk' | 'direct';
  state: string;
  expires_at: string;
  funding_tx_hash: string | null;
  funding_proof_url: string | null;
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
    network: number;
    chance_bps: number;
    stake_nano: string;
    opponent_stake_nano: string;
    total_pool_nano: string;
    commitment_hex: string;
    expires_at: number;
    commitment_domain: number;
    fee_bps: number;
  };
}

export interface Duel {
  id: string;
  onchain_duel_id: number;
  state: string;
  offer_id: number;
  own_revealed: boolean;
  chance_bps: number;
  stake_nano: number;
  opponent_stake_nano: number;
  total_pool_nano: number;
  payout_nano: number;
  reveal_deadline: string;
  winner_wallet: string | null;
  settled_tx_hash: string | null;
  settlement_proof_url: string | null;
}

export interface ActionIntent {
  operation: 'reveal' | 'cancel_offer' | 'expire_offer' | 'expire_duel';
  query_id: number;
  offer_id: number;
  duel_id: number;
  contract_address: string;
  amount_nano: string;
  valid_until: number;
  network: number;
}

export interface Referral {
  code: string;
  url: string;
  invited: number;
  qualified: number;
  reward_points: number;
  history: {
    cause: string;
    reward_points: number;
    payout_tx_hash: string | null;
    created_at: string;
  }[];
}

export interface Invite {
  code: string;
  creator_name: string;
  creator_username: string | null;
  stake_nano: number;
  total_pool_nano: number;
  chance_bps: 2500 | 5000 | 7500;
  payout_nano: number;
  net_profit_nano: number;
  counter_offer_id: number;
  expires_at: string;
}
