import { create } from 'zustand';

import { api } from './api';
import { isMockTelegram, telegramInitData, telegramStartParam } from './telegram';
import type { BankPosition, Duel, Invite, Offer, Profile, Tab } from './types';

const mockParameters = new URLSearchParams(window.location.search);
const mockScreen = mockParameters.get('screen');
const now = Date.now();

const demoProfile: Profile = {
  user: {
    id: 'demo',
    telegram_id: 777000,
    username: 'loop_demo',
    first_name: 'Дмитрий',
    photo_url: null,
    onboarding_seen: true,
    onboarding_enabled: true,
  },
  wallet: {
    address: `0:${'42'.repeat(32)}`,
    network: -3,
    verified_at: new Date(now - 86_400_000).toISOString(),
  },
  bank: { active: 1, completed: 3, total: 4 },
  duel: { active: 0, completed: 8, total: 9 },
  plush_brick: {
    verified: true,
    balance_nano: 1,
    holder: true,
    duel_fee_bps: 250,
    fee_discount_active: false,
  },
};

const demoBank: BankPosition = {
  id: 'bank-demo',
  position_id: 4107,
  owner_wallet: demoProfile.wallet!.address,
  principal_nano: 2_000_000_000,
  multiplier_bps: 15000,
  target_payout_nano: 3_000_000_000,
  funded_amount_nano: 1_860_000_000,
  remaining_amount_nano: 1_140_000_000,
  progress_bps: 6200,
  queue_index: 14,
  current_status: 'partially_funded',
  funding_transaction: 'demo-bank-funding',
  payout_transaction: null,
  proof_url: 'https://testnet.tonviewer.com/transaction/demo-bank-funding',
  created_at: new Date(now - 2 * 86_400_000).toISOString(),
  completed_at: null,
};

const demoOffer: Offer = {
  id: 'duel-offer-demo',
  onchain_offer_id: 5107,
  chance_bps: 2500,
  total_pool_nano: 4_000_000_000,
  stake_nano: 1_000_000_000,
  opponent_stake_nano: 3_000_000_000,
  fee_bps: 250,
  payout_nano: 3_900_000_000,
  net_profit_nano: 2_900_000_000,
  mode: 'afk',
  state: mockScreen === 'duel-result' ? 'settled' : 'open',
  expires_at: new Date(now + 10 * 60_000).toISOString(),
  funding_tx_hash: 'demo-duel-funding',
  funding_proof_url: 'https://testnet.tonviewer.com/transaction/demo-duel-funding',
};

const demoDuel: Duel = {
  id: 'duel-demo',
  onchain_duel_id: 5108,
  state: 'settled',
  offer_id: demoOffer.onchain_offer_id,
  own_revealed: true,
  chance_bps: 2500,
  stake_nano: 1_000_000_000,
  opponent_stake_nano: 3_000_000_000,
  total_pool_nano: 4_000_000_000,
  payout_nano: 3_900_000_000,
  reveal_deadline: new Date(now - 60_000).toISOString(),
  winner_wallet: demoProfile.wallet!.address,
  settled_tx_hash: 'demo-duel-settlement',
  settlement_proof_url: 'https://testnet.tonviewer.com/transaction/demo-duel-settlement',
};

const demoInvite: Invite = {
  code: 'demo-direct-duel',
  creator_name: 'Миша',
  creator_username: 'misha',
  stake_nano: 1_000_000_000,
  total_pool_nano: 4_000_000_000,
  chance_bps: 2500,
  payout_nano: 3_900_000_000,
  net_profit_nano: 2_900_000_000,
  counter_offer_id: 7001,
  expires_at: new Date(now + 10 * 60_000).toISOString(),
};

const initialTab: Tab =
  mockScreen?.startsWith('duel') || mockScreen === 'inline'
    ? 'duel'
    : mockScreen === 'profile' || mockScreen === 'settings'
      ? 'profile'
      : 'bank';

interface LoopState {
  loading: boolean;
  activeTab: Tab;
  profile: Profile | null;
  bankPosition: BankPosition | null;
  bankHistory: BankPosition[];
  offers: Offer[];
  duels: Duel[];
  invite: Invite | null;
  error: string | null;
  showOnboarding: boolean;
  onboardingPage: number;
  bootstrap(): Promise<void>;
  refresh(): Promise<void>;
  setTab(tab: Tab): void;
  setError(error: string | null): void;
  finishOnboarding(): Promise<void>;
  replayOnboarding(): void;
  setOnboardingEnabled(enabled: boolean): Promise<void>;
  setMockBankPosition(position: BankPosition): void;
}

export const useLoopStore = create<LoopState>((set, get) => ({
  loading: true,
  activeTab: initialTab,
  profile: null,
  bankPosition: null,
  bankHistory: [],
  offers: [],
  duels: [],
  invite: null,
  error: null,
  showOnboarding: false,
  onboardingPage: mockScreen === 'onboarding-duel' ? 2 : 1,

  async bootstrap() {
    const started = performance.now();
    try {
      if (isMockTelegram()) {
        await new Promise((resolve) =>
          setTimeout(resolve, Math.max(0, 650 - (performance.now() - started))),
        );
        const empty = mockScreen === 'bank-empty';
        set({
          profile: demoProfile,
          bankPosition: empty ? null : demoBank,
          bankHistory: empty ? [] : [demoBank],
          offers:
            mockScreen === 'duel-matchmaking' || mockScreen === 'duel-result' ? [demoOffer] : [],
          duels: mockScreen === 'duel-result' ? [demoDuel] : [],
          invite: mockScreen === 'duel-invite' ? demoInvite : null,
          loading: false,
          showOnboarding: mockScreen === 'onboarding-bank' || mockScreen === 'onboarding-duel',
        });
        return;
      }
      const initData = telegramInitData();
      if (!initData) throw new Error('Откройте LOOP внутри Telegram');
      const profile = (await api.authenticate(initData)).profile;
      const [bankPosition, bankHistory, offers, duels] = await Promise.all([
        api.currentBankPosition(),
        api.bankPositions(),
        api.offers(),
        api.duels(),
      ]);
      let invite: Invite | null = null;
      const startParam = telegramStartParam();
      if (startParam?.startsWith('duel_')) invite = await api.invite(startParam.slice(5));
      set({
        profile,
        bankPosition,
        bankHistory,
        offers,
        duels,
        invite,
        loading: false,
        activeTab: invite ? 'duel' : 'bank',
        showOnboarding: profile.user.onboarding_enabled && !profile.user.onboarding_seen,
      });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : 'Не удалось запустить LOOP',
      });
    }
  },

  async refresh() {
    if (isMockTelegram()) return;
    const [profile, bankPosition, bankHistory, offers, duels] = await Promise.all([
      api.me(),
      api.currentBankPosition(),
      api.bankPositions(),
      api.offers(),
      api.duels(),
    ]);
    set({ profile, bankPosition, bankHistory, offers, duels });
  },

  setTab(activeTab) {
    set({ activeTab });
  },

  setError(error) {
    set({ error });
  },

  async finishOnboarding() {
    if (!isMockTelegram()) await api.updateSettings({ onboarding_seen: true });
    const profile = get().profile;
    set({
      profile: profile ? { ...profile, user: { ...profile.user, onboarding_seen: true } } : profile,
      showOnboarding: false,
    });
  },

  replayOnboarding() {
    set({ showOnboarding: true, onboardingPage: 0 });
  },

  async setOnboardingEnabled(enabled) {
    if (!isMockTelegram()) await api.updateSettings({ onboarding_enabled: enabled });
    const profile = get().profile;
    if (profile) {
      set({ profile: { ...profile, user: { ...profile.user, onboarding_enabled: enabled } } });
    }
  },

  setMockBankPosition(position) {
    set({ bankPosition: position, bankHistory: [position, ...get().bankHistory] });
  },
}));
