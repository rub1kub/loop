import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from './App';

const tonConnect = vi.hoisted(() => ({
  disconnect: vi.fn(() => Promise.resolve()),
  setConnectRequestParameters: vi.fn(),
}));

const walletState = vi.hoisted(() => ({
  current: {
    account: {
      address: `0:${'22'.repeat(32)}`,
      chain: '-239',
      publicKey: 'public-key',
    },
    connectItems: {},
  },
}));

const store = vi.hoisted(() => ({
  setError: vi.fn(),
  refresh: vi.fn(() => Promise.resolve()),
  refreshRating: vi.fn(() => Promise.resolve()),
  bootstrap: vi.fn(() => Promise.resolve()),
  state: {
    loading: false,
    profile: {
      user: {
        id: 'user-id',
        telegram_id: 1084693264,
        username: 'rub1kub',
        first_name: 'Loop',
        photo_url: null,
        onboarding_seen: true,
        onboarding_enabled: true,
        result_notifications_enabled: true,
      },
      wallet: {
        address: `0:${'11'.repeat(32)}`,
        network: -239,
        verified_at: '2026-08-02T10:26:14.000Z',
      },
      bank: { active: 0, completed: 0, total: 0 },
      duel: { active: 0, completed: 0, total: 0 },
      plush_brick: {
        verified: false,
        balance_nano: 0,
        holder: false,
        duel_fee_bps: 250,
        fee_discount_active: false,
      },
      duel_stake: { min_stake_nano: 500_000_000, max_stake_nano: 500_000_000 },
      app_open: true,
      launch_at: null,
    },
    prelaunch: null,
    error: null,
    showOnboarding: false,
    onboardingPage: 0,
    activeTab: 'bank',
    bankPosition: null,
    bankHistory: [],
    offers: [],
    duels: [],
    invite: null,
    rating: null,
    results: [],
    finishOnboarding: vi.fn(),
    setMockBankPosition: vi.fn(),
    declineInvite: vi.fn(),
    replayOnboarding: vi.fn(),
    setResultNotificationsEnabled: vi.fn(),
    setTab: vi.fn(),
    markResultSeen: vi.fn(),
  },
}));

const apiMocks = vi.hoisted(() => ({
  walletChallenge: vi.fn(() =>
    Promise.resolve({
      payload: 'challenge',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
    }),
  ),
  verifyWallet: vi.fn(),
}));

vi.mock('@tonconnect/ui-react', () => ({
  useIsConnectionRestored: () => true,
  useTonConnectUI: () => [tonConnect],
  useTonWallet: () => walletState.current,
}));

vi.mock('./api', () => ({ api: apiMocks }));
vi.mock('./store', () => ({
  useLoopStore: Object.assign(() => store.state, {
    getState: () => ({
      ...store.state,
      bootstrap: store.bootstrap,
      refresh: store.refresh,
      refreshRating: store.refreshRating,
      setError: store.setError,
    }),
  }),
}));
vi.mock('./interactionGuards', () => ({ installInteractionGuards: () => vi.fn() }));
vi.mock('./viewport', () => ({ installViewportBehavior: () => vi.fn() }));
vi.mock('./telegram', () => ({
  haptic: vi.fn(),
  initializeTelegram: () => true,
  isMockTelegram: () => false,
  loadTelegramSdk: () => Promise.resolve(),
  removeDuelSecret: () => Promise.resolve(),
  toggleFullscreen: vi.fn(),
}));

vi.mock('./components/InlineDuelPreview', () => ({ InlineDuelPreview: () => null }));
vi.mock('./components/Loader', () => ({ Loader: () => null }));
vi.mock('./components/PrelaunchScreen', () => ({ PrelaunchScreen: () => null }));
vi.mock('./components/Onboarding', () => ({ Onboarding: () => null }));
vi.mock('./components/ProfileScreen', () => ({ ProfileScreen: () => null }));
vi.mock('./components/Celebration', () => ({ Celebration: () => null }));
vi.mock('./components/TabBar', () => ({ TabBar: () => null }));
vi.mock('./features/bank/BankScreen', () => ({ BankScreen: () => <div>BANK</div> }));
vi.mock('./features/duel/DuelScreen', () => ({ DuelScreen: () => null }));
vi.mock('./features/rating/RatingScreen', () => ({ RatingScreen: () => null }));
vi.mock('./features/results/ResultSheet', () => ({ ResultSheet: () => null }));

describe('App wallet restoration', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('disconnects a stale browser wallet instead of reusing it for the profile', async () => {
    render(<App />);

    await waitFor(() => expect(tonConnect.disconnect).toHaveBeenCalledOnce());
    expect(store.setError).toHaveBeenCalledWith(
      'В TON Connect выбран другой кошелёк. Подключи кошелёк из профиля заново.',
    );
    expect(apiMocks.verifyWallet).not.toHaveBeenCalled();
  });

  it('asks for a new challenge after one is refused, instead of stranding the wallet', async () => {
    // The challenge lives five minutes. It used to be fetched once per page
    // load, so anyone who pressed connect later signed something expired — and
    // every retry repeated it, because the page never asked for another. The
    // only cure was restarting the mini app.
    walletState.current = {
      account: {
        address: '0:' + 'ab'.repeat(32),
        chain: '-239',
        publicKey: 'cd'.repeat(32),
      },
      connectItems: {
        tonProof: { proof: { timestamp: 1, domain: {}, signature: 'sig', payload: 'challenge' } },
      },
    };
    apiMocks.verifyWallet.mockRejectedValueOnce(new Error('wallet challenge is invalid or used'));

    render(<App />);

    await waitFor(() => expect(apiMocks.verifyWallet).toHaveBeenCalledOnce());
    // A second challenge is requested without the person touching anything.
    await waitFor(() => expect(apiMocks.walletChallenge.mock.calls.length).toBeGreaterThan(1));
  });
});
