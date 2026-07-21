import { create } from 'zustand';

import { api } from './api';
import { isMockTelegram, telegram } from './telegram';
import type { Offer, Profile, Tab } from './types';

const demoProfile: Profile = {
  user: {
    id: 'demo',
    telegram_id: 777000,
    username: 'loop_demo',
    first_name: 'Дмитрий',
    onboarding_seen: false,
  },
  wallet: null,
  bank: null,
  balance_nano: 18_750_000_000,
  plush_brick_holder: true,
};

const mockParameters = new URLSearchParams(window.location.search);
const mockTab = mockParameters.get('screen');
const initialTab: Tab =
  isMockTelegram() && (mockTab === 'bank' || mockTab === 'duel' || mockTab === 'profile')
    ? mockTab
    : 'bank';

interface LoopState {
  loading: boolean;
  activeTab: Tab;
  profile: Profile | null;
  offers: Offer[];
  error: string | null;
  showOnboarding: boolean;
  bootstrap(): Promise<void>;
  refresh(): Promise<void>;
  setTab(tab: Tab): void;
  setError(error: string | null): void;
  finishOnboarding(): Promise<void>;
  replayOnboarding(): void;
  updateProfile(profile: Profile): void;
}

export const useLoopStore = create<LoopState>((set, get) => ({
  loading: true,
  activeTab: initialTab,
  profile: null,
  offers: [],
  error: null,
  showOnboarding: false,

  async bootstrap() {
    const started = performance.now();
    try {
      let profile: Profile;
      if (isMockTelegram()) profile = demoProfile;
      else {
        const initData = telegram()?.initData;
        if (!initData) throw new Error('Откройте LOOP внутри Telegram');
        profile = (await api.authenticate(initData)).profile;
      }
      const delay = Math.max(0, 1500 - (performance.now() - started));
      await new Promise((resolve) => setTimeout(resolve, delay));
      set({
        profile,
        loading: false,
        showOnboarding:
          !profile.user.onboarding_seen &&
          !(isMockTelegram() && mockParameters.get('skipOnboarding') === '1'),
        offers: isMockTelegram() ? [] : await api.offers(),
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
    const [profile, offers] = await Promise.all([api.me(), api.offers()]);
    set({ profile, offers });
  },

  setTab(activeTab) {
    set({ activeTab });
  },

  setError(error) {
    set({ error });
  },

  async finishOnboarding() {
    if (!isMockTelegram()) await api.updateOnboarding(true);
    let profile = get().profile;
    if (profile) profile = { ...profile, user: { ...profile.user, onboarding_seen: true } };
    set({ profile, showOnboarding: false });
  },

  replayOnboarding() {
    set({ showOnboarding: true });
  },

  updateProfile(profile) {
    set({ profile });
  },
}));
