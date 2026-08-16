import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Profile } from './types';

const apiMocks = vi.hoisted(() => ({
  authenticate: vi.fn(),
  me: vi.fn(),
  prelaunch: vi.fn(),
  currentBankPosition: vi.fn(() => Promise.resolve(null)),
  bankPulse: vi.fn(() =>
    Promise.resolve({
      bank_enabled: true,
      active_positions: 0,
      minimum_entry_nano: 1_000_000_000,
      minimum_entry_payouts: 0,
      next_payout_gross_nano: 0,
      updated_at: '2026-08-10T12:00:00.000Z',
    }),
  ),
  bankPositions: vi.fn(() => Promise.resolve([])),
  offers: vi.fn(() => Promise.resolve([])),
  duels: vi.fn(() => Promise.resolve([])),
  rating: vi.fn(() => Promise.resolve(null)),
  teamsOverview: vi.fn(() => Promise.resolve(null)),
  teamInvite: vi.fn(() => Promise.resolve(null)),
  results: vi.fn(() => Promise.resolve([])),
  invite: vi.fn(),
  updateSettings: vi.fn(),
}));

const telegramState = vi.hoisted(() => ({ startParam: null as string | null }));

vi.mock('./api', () => ({ api: apiMocks, ApiError: class extends Error {} }));
vi.mock('./telegram', () => ({
  telegramInitData: () => 'init-data',
  telegramStartParam: () => telegramState.startParam,
  isMockTelegram: () => false,
  haptic: vi.fn(),
  markDuelSeen: vi.fn(),
  readSeenDuelId: () => null,
}));

const baseProfile: Profile = {
  user: {
    id: 'u1',
    telegram_id: 1,
    username: null,
    first_name: 'Гость',
    photo_url: null,
    onboarding_seen: false,
    onboarding_enabled: true,
    result_notifications_enabled: true,
  },
  wallet: null,
  bank: { active: 0, completed: 0, total: 0 },
  duel: { active: 0, completed: 0, total: 0 },
  plush_brick: {
    verified: false,
    balance_nano: 0,
    holder: false,
    duel_fee_bps: 1000,
    fee_discount_active: false,
  },
  duel_stake: { min_stake_nano: 500_000_000, max_stake_nano: 500_000_000 },
  announcement: null,
  app_open: false,
  launch_at: '2026-08-05T16:30:00Z',
};

const prelaunch = {
  launch_at: '2026-08-05T16:30:00Z',
  referral_code: 'abc',
  referral_url: 'https://t.me/getloopbot?startapp=ref_abc',
  invited: 0,
  rank: null,
  leaderboard: [],
  participants: 1,
};

async function freshStore() {
  vi.resetModules();
  const { useLoopStore } = await import('./store');
  return useLoopStore;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('bootstrap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    telegramState.startParam = null;
    apiMocks.prelaunch.mockResolvedValue(prelaunch);
  });

  it('keeps the onboarding owed to someone who only ever saw the countdown', async () => {
    // Waiting out the launch week must not spend the introduction: the
    // prelaunch screen replaces the whole app, so nobody who sat behind it has
    // been shown what BANK is or that a position cannot be cancelled.
    apiMocks.authenticate.mockResolvedValue({ profile: baseProfile, token: 't' });
    const waiting = await freshStore();
    await waiting.getState().bootstrap();

    expect(waiting.getState().prelaunch).not.toBeNull();
    expect(waiting.getState().showOnboarding).toBe(false);
    // Nothing marked the introduction as delivered.
    expect(waiting.getState().profile?.user.onboarding_seen).toBe(false);

    // The door opens, the page reloads, and the same person is introduced.
    apiMocks.authenticate.mockResolvedValue({
      profile: { ...baseProfile, app_open: true },
      token: 't',
    });
    const opened = await freshStore();
    await opened.getState().bootstrap();

    expect(opened.getState().showOnboarding).toBe(true);
  });

  it('does not introduce someone who has already been introduced', async () => {
    apiMocks.authenticate.mockResolvedValue({
      profile: {
        ...baseProfile,
        app_open: true,
        user: { ...baseProfile.user, onboarding_seen: true },
      },
      token: 't',
    });
    const store = await freshStore();
    await store.getState().bootstrap();

    expect(store.getState().showOnboarding).toBe(false);
  });

  it('opens DUEL directly from a shared search invitation', async () => {
    telegramState.startParam = 'duel';
    apiMocks.authenticate.mockResolvedValue({
      profile: {
        ...baseProfile,
        app_open: true,
        user: { ...baseProfile.user, onboarding_seen: true },
      },
      token: 't',
    });
    const store = await freshStore();
    await store.getState().bootstrap();

    expect(store.getState().activeTab).toBe('duel');
    expect(apiMocks.invite).not.toHaveBeenCalled();
  });
});

describe('refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.currentBankPosition.mockResolvedValue(null);
    apiMocks.bankPositions.mockResolvedValue([]);
    apiMocks.offers.mockResolvedValue([]);
    apiMocks.duels.mockResolvedValue([]);
    apiMocks.results.mockResolvedValue([]);
  });

  it('does not let an older response move the interface back in time', async () => {
    const older = deferred<Profile>();
    const newer = deferred<Profile>();
    apiMocks.me
      .mockImplementationOnce(() => older.promise)
      .mockImplementationOnce(() => newer.promise);
    const store = await freshStore();

    const first = store.getState().refresh();
    const second = store.getState().refresh();
    newer.resolve({ ...baseProfile, user: { ...baseProfile.user, first_name: 'Новое состояние' } });
    await second;
    older.resolve({
      ...baseProfile,
      user: { ...baseProfile.user, first_name: 'Старое состояние' },
    });
    await first;

    expect(store.getState().profile?.user.first_name).toBe('Новое состояние');
  });
});

describe('onboarding completion', () => {
  beforeEach(() => vi.clearAllMocks());

  it('closes a settings replay without another network request', async () => {
    const store = await freshStore();
    store.setState({
      profile: {
        ...baseProfile,
        user: { ...baseProfile.user, onboarding_seen: true },
      },
      showOnboarding: true,
    });

    await store.getState().finishOnboarding();

    expect(store.getState().showOnboarding).toBe(false);
    expect(apiMocks.updateSettings).not.toHaveBeenCalled();
  });

  it('does not trap a first-time user when saving the setting fails', async () => {
    apiMocks.updateSettings.mockRejectedValueOnce(new Error('offline'));
    const store = await freshStore();
    store.setState({ profile: baseProfile, showOnboarding: true });

    await store.getState().finishOnboarding();

    expect(store.getState().showOnboarding).toBe(false);
    expect(store.getState().profile?.user.onboarding_seen).toBe(true);
  });
});
