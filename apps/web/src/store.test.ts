import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Profile } from './types';

const apiMocks = vi.hoisted(() => ({
  authenticate: vi.fn(),
  prelaunch: vi.fn(),
  currentBankPosition: vi.fn(() => Promise.resolve(null)),
  bankPositions: vi.fn(() => Promise.resolve([])),
  offers: vi.fn(() => Promise.resolve([])),
  duels: vi.fn(() => Promise.resolve([])),
  rating: vi.fn(() => Promise.resolve(null)),
  results: vi.fn(() => Promise.resolve([])),
  invite: vi.fn(),
}));

vi.mock('./api', () => ({ api: apiMocks, ApiError: class extends Error {} }));
vi.mock('./telegram', () => ({
  telegramInitData: () => 'init-data',
  telegramStartParam: () => null,
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

describe('bootstrap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});
