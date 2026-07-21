import { create } from 'zustand';

import { api } from './api';
import { isMockTelegram, telegram } from './telegram';
import type { Duel, Invite, Offer, Profile, Tab } from './types';

const mockParameters = new URLSearchParams(window.location.search);
const mockState = mockParameters.get('state');
const mockNow = Date.now();

const demoProfile: Profile = {
  user: {
    id: 'demo',
    telegram_id: 777000,
    username: 'loop_demo',
    first_name: 'Дмитрий',
    photo_url: null,
    onboarding_seen: false,
  },
  wallet: null,
  bank:
    mockState === 'empty'
      ? null
      : {
          id: 'cycle-demo-04',
          sequence_number: 4,
          status: mockState === 'completed' ? 'completed' : 'active',
          goal_events: 8,
          event_count: mockState === 'completed' ? 8 : 5,
          progress_bps: mockState === 'completed' ? 10_000 : 6_200,
          started_at: new Date(mockNow - 2 * 86_400_000).toISOString(),
          ends_at: new Date(mockNow + 5 * 86_400_000).toISOString(),
          completed_at: mockState === 'completed' ? new Date(mockNow).toISOString() : null,
          events: [
            {
              id: 'event-1',
              kind: 'invite_accepted',
              title: 'Миша принял вызов',
              proof_type: 'telegram',
              proof_ref: 'demo-invite',
              proof_url: null,
              created_at: new Date(mockNow - 2 * 60_000).toISOString(),
            },
            {
              id: 'event-2',
              kind: 'duel_matched',
              title: 'Соперник найден',
              proof_type: 'ton_transaction',
              proof_ref: 'demo-chain-proof',
              proof_url: 'https://testnet.tonviewer.com/transaction/demo-chain-proof',
              created_at: new Date(mockNow - 42 * 60_000).toISOString(),
            },
            {
              id: 'event-3',
              kind: 'cycle_started',
              title: 'Цикл начат',
              proof_type: 'system',
              proof_ref: 'cycle-demo-04',
              proof_url: null,
              created_at: new Date(mockNow - 2 * 86_400_000).toISOString(),
            },
          ],
        },
};

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
  duels: Duel[];
  invite: Invite | null;
  error: string | null;
  showOnboarding: boolean;
  bootstrap(): Promise<void>;
  refresh(): Promise<void>;
  setTab(tab: Tab): void;
  setError(error: string | null): void;
  finishOnboarding(): Promise<void>;
  replayOnboarding(): void;
  startCycle(): Promise<void>;
  updateProfile(profile: Profile): void;
}

export const useLoopStore = create<LoopState>((set, get) => ({
  loading: true,
  activeTab: initialTab,
  profile: null,
  offers: [],
  duels: [],
  invite: null,
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
      let invite: Invite | null = null;
      const startParam = telegram()?.initDataUnsafe?.start_param;
      if (!isMockTelegram() && startParam?.startsWith('duel_')) {
        try {
          invite = await api.invite(startParam.slice(5));
        } catch {
          invite = null;
        }
      }
      const [offers, duels] = isMockTelegram()
        ? [[], []]
        : await Promise.all([api.offers(), api.duels()]);
      set({
        profile,
        loading: false,
        showOnboarding:
          !profile.user.onboarding_seen &&
          !(isMockTelegram() && mockParameters.get('skipOnboarding') === '1'),
        offers,
        duels,
        invite,
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
    const [profile, offers, duels] = await Promise.all([api.me(), api.offers(), api.duels()]);
    set({ profile, offers, duels });
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

  async startCycle() {
    if (!isMockTelegram()) {
      await api.startCycle();
      await get().refresh();
      return;
    }
    const profile = get().profile;
    if (!profile) return;
    const now = Date.now();
    set({
      profile: {
        ...profile,
        bank: {
          id: `cycle-demo-${now}`,
          sequence_number: (profile.bank?.sequence_number ?? 0) + 1,
          status: 'active',
          goal_events: 6,
          event_count: 1,
          progress_bps: 1_666,
          started_at: new Date(now).toISOString(),
          ends_at: new Date(now + 7 * 86_400_000).toISOString(),
          completed_at: null,
          events: [
            {
              id: `event-${now}`,
              kind: 'cycle_started',
              title: 'Цикл начат',
              proof_type: 'system',
              proof_ref: `cycle-demo-${now}`,
              proof_url: null,
              created_at: new Date(now).toISOString(),
            },
          ],
        },
      },
    });
  },

  updateProfile(profile) {
    set({ profile });
  },
}));
