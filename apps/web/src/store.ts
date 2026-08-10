import { create } from 'zustand';

import { api } from './api';
import {
  isMockTelegram,
  requestResultNotificationAccess,
  telegramInitData,
  telegramStartParam,
} from './telegram';
import type {
  BankPosition,
  BankQueuePulse,
  Duel,
  Invite,
  Offer,
  Prelaunch,
  Profile,
  Rating,
  ResultCard,
  Tab,
  TeamInvitePreview,
  TeamOverview,
} from './types';

const mockParameters = new URLSearchParams(window.location.search);
const mockScreen = mockParameters.get('screen');
const now = Date.now();
// Kept across reloads: closing a card is the user saying "I have seen this",
// and a request that never reached the server must not bring it back.
const DISMISSED_KEY = 'loop-dismissed-results';

function readDismissed(): Set<string> {
  try {
    const stored = window.localStorage.getItem(DISMISSED_KEY);
    return new Set<string>(stored ? (JSON.parse(stored) as string[]) : []);
  } catch {
    return new Set<string>();
  }
}

const dismissedResultIds = readDismissed();
// Several screens can request the same snapshot at once (the global poller,
// transaction confirmation and a visibility change). A slower, older response
// must never overwrite a newer chain projection and visually move a DUEL back
// to the previous phase.
let refreshRequestId = 0;

function rememberDismissed(cardId: string): void {
  dismissedResultIds.add(cardId);
  try {
    window.localStorage.setItem(DISMISSED_KEY, JSON.stringify([...dismissedResultIds].slice(-200)));
  } catch {
    // Private mode or a full quota: the in-memory set still covers this session.
  }
}

function hideDismissedResults(results: ResultCard[]): ResultCard[] {
  const dismissedAt = new Date().toISOString();
  return results.map((card) =>
    card.seen_at === null && dismissedResultIds.has(card.id)
      ? { ...card, seen_at: dismissedAt }
      : card,
  );
}

const demoProfile: Profile = {
  user: {
    id: 'demo',
    telegram_id: 777000,
    username: 'loop_demo',
    first_name: 'Дмитрий',
    photo_url: null,
    onboarding_seen: true,
    onboarding_enabled: true,
    result_notifications_enabled: true,
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
  duel_stake: { min_stake_nano: 500_000_000, max_stake_nano: 500_000_000 },
  // Only reachable with VITE_MOCK_TELEGRAM, and there so the sheet can be
  // looked at without waiting for a real announcement to be addressed to you.
  announcement: {
    text:
      'LOOP. ПЕРВАЯ НОЧЬ.\n\nМы открылись сегодня в 19:30 с потолком в 1 GRAM на позицию.\n\n' +
      'Прошло три часа.\n\nОтправлено людям — 575,78 GRAM\nBANK закрыл 161 позицию на 530,75\n' +
      'DUEL раздал победителям 45,03 за 20 боёв\n\nА теперь честно.\n\nНаступает ночь.',
    url: 'https://t.me/rubikub/5158',
  },
  app_open: true,
  launch_at: null,
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
  queue_position: 4,
  queue_progress_bps: 0,
  queue_ahead: 0,
  queue_ahead_nano: 0,
  queue_eta_seconds: null,
  current_status: 'partially_funded',
  funding_transaction: 'demo-bank-funding',
  payout_transaction: null,
  proof_url: 'https://testnet.tonviewer.com/transaction/demo-bank-funding',
  created_at: new Date(now - 2 * 86_400_000).toISOString(),
  completed_at: null,
};

const demoBankPulse: BankQueuePulse = {
  active_positions: 124,
  minimum_entry_nano: 1_000_000_000,
  minimum_entry_payouts: 2,
  next_payout_gross_nano: 288_888_889,
  updated_at: new Date(now).toISOString(),
};

const demoOffer: Offer = {
  id: 'duel-offer-demo',
  onchain_offer_id: 5107,
  chance_bps: mockScreen === 'duel-boost' ? 6000 : 5000,
  total_pool_nano: mockScreen === 'duel-boost' ? 2_500_000_000 : 2_000_000_000,
  stake_nano: mockScreen === 'duel-boost' ? 1_500_000_000 : 1_000_000_000,
  opponent_stake_nano: 1_000_000_000,
  fee_bps: 250,
  fee_exempt: false,
  payout_nano: mockScreen === 'duel-boost' ? 2_437_500_000 : 1_950_000_000,
  net_profit_nano: mockScreen === 'duel-boost' ? 937_500_000 : 950_000_000,
  mode: 'afk',
  direct_opponent_wallet: null,
  state:
    mockScreen === 'duel-result' ? 'settled' : mockScreen === 'duel-boost' ? 'matched' : 'open',
  expires_at: new Date(now + 10 * 60_000).toISOString(),
  funding_tx_hash: 'demo-duel-funding',
  funding_proof_url: 'https://testnet.tonviewer.com/transaction/demo-duel-funding',
};

const demoDuel: Duel = {
  id: 'duel-demo',
  onchain_duel_id: 5108,
  state: mockScreen === 'duel-boost' ? 'boosting' : 'settled',
  offer_id: demoOffer.onchain_offer_id,
  own_revealed: true,
  chance_bps: mockScreen === 'duel-boost' ? 6000 : 5000,
  stake_nano: mockScreen === 'duel-boost' ? 1_500_000_000 : 1_000_000_000,
  opponent_stake_nano: 1_000_000_000,
  total_pool_nano: mockScreen === 'duel-boost' ? 2_500_000_000 : 2_000_000_000,
  fee_exempt: false,
  payout_nano: mockScreen === 'duel-boost' ? 2_437_500_000 : 1_950_000_000,
  boost_deadline: mockScreen === 'duel-boost' ? new Date(now + 55_000).toISOString() : null,
  hard_deadline: mockScreen === 'duel-boost' ? new Date(now + 175_000).toISOString() : null,
  boost_revision: mockScreen === 'duel-boost' ? 1 : 0,
  reveal_deadline:
    mockScreen === 'duel-boost'
      ? new Date(now + 355_000).toISOString()
      : new Date(now - 60_000).toISOString(),
  boost_events:
    mockScreen === 'duel-boost'
      ? [
          {
            revision: 1,
            side: 'you',
            amount_nano: 500_000_000,
            chance_bps: 6000,
            tx_hash: 'demo-duel-boost',
            proof_url: 'https://testnet.tonviewer.com/transaction/demo-duel-boost',
            created_at: new Date(now - 5_000).toISOString(),
          },
        ]
      : [],
  winner_wallet: mockScreen === 'duel-boost' ? null : demoProfile.wallet!.address,
  opponent_first_name: null,
  opponent_username: null,
  opponent_has_photo: false,
  settled_tx_hash: mockScreen === 'duel-boost' ? null : 'demo-duel-settlement',
  settlement_proof_url:
    mockScreen === 'duel-boost'
      ? null
      : 'https://testnet.tonviewer.com/transaction/demo-duel-settlement',
};

const demoResult: ResultCard | null =
  mockScreen === 'result-entry'
    ? {
        id: 'result-entry-demo',
        mode: 'bank_entry',
        payout_nano: 0,
        contributed_nano: 2_000_000_000,
        result_nano: 0,
        queue_position: 47,
        proof_url: 'https://testnet.tonviewer.com/transaction/demo-entry',
        image_url: '',
        seen_at: null,
        created_at: new Date().toISOString(),
      }
    : mockScreen === 'result-bank' || mockScreen === 'result-duel'
      ? {
          id: 'result-demo',
          mode: mockScreen === 'result-duel' ? 'duel' : 'bank',
          payout_nano: mockScreen === 'result-duel' ? 1_950_000_000 : 3_000_000_000,
          contributed_nano: mockScreen === 'result-duel' ? 1_000_000_000 : 2_000_000_000,
          result_nano: mockScreen === 'result-duel' ? 950_000_000 : 1_000_000_000,
          queue_position: null,
          proof_url: 'https://testnet.tonviewer.com/transaction/demo-result',
          image_url: '',
          seen_at: null,
          created_at: new Date(now).toISOString(),
        }
      : null;

const demoInvite: Invite = {
  code: 'demo-direct-duel',
  creator_name: 'Миша',
  creator_username: 'misha',
  stake_nano: 1_000_000_000,
  total_pool_nano: 2_000_000_000,
  chance_bps: 5000,
  payout_nano: 1_950_000_000,
  net_profit_nano: 950_000_000,
  counter_offer_id: 7001,
  expires_at: new Date(now + 10 * 60_000).toISOString(),
};

const demoMe = {
  rank: 7,
  user_id: demoProfile.user.id,
  first_name: demoProfile.user.first_name,
  username: demoProfile.user.username,
  photo_url: null,
  score: 685,
  level: 'ORBIT' as const,
  bank_payouts: 3,
  duel_settlements: 5,
  timely_reveals: 4,
  missed_reveals: 1,
  qualified_referrals: 2,
  proofs: 8,
  reliability_bps: 8000,
  earned_nano: 0,
  is_me: true,
};

const demoLeaders: Rating['leaderboard'] = [
  {
    ...demoMe,
    rank: 1,
    user_id: 'leader-1',
    first_name: 'MIRA',
    username: 'miraloop',
    score: 1240,
    level: 'LOOP',
    is_me: false,
  },
  {
    ...demoMe,
    rank: 2,
    user_id: 'leader-2',
    first_name: 'Alex',
    username: 'alex_ton',
    score: 960,
    is_me: false,
  },
  {
    ...demoMe,
    rank: 3,
    user_id: 'leader-3',
    first_name: 'Nikita',
    username: null,
    score: 840,
    is_me: false,
  },
  demoMe,
];

const demoRating: Rating = {
  season_id: '2026-07',
  season_name: 'ИЮЛЬ · 2026',
  starts_at: '2026-07-01T00:00:00.000Z',
  ends_at: '2026-08-01T00:00:00.000Z',
  me: demoMe,
  leaderboard: demoLeaders,
  circle: [demoLeaders[1], demoMe],
  pulse: {
    active_participants: 38,
    active_bank: 21,
    active_duels: 17,
    proofs_24h: 46,
  },
  invite_race: [
    {
      rank: 1,
      first_name: 'Мария',
      username: 'masha_ton',
      earned_nano: 380_000_000,
      invited: 6,
      is_me: false,
    },
    {
      rank: 2,
      first_name: 'Дмитрий',
      username: null,
      earned_nano: 160_000_000,
      invited: 3,
      is_me: true,
    },
  ],
  invite_race_me: {
    rank: 2,
    first_name: 'Дмитрий',
    username: null,
    earned_nano: 160_000_000,
    invited: 3,
    is_me: true,
  },
  invite_race_ends_at: new Date(Date.now() + 3 * 86_400_000).toISOString(),
  formula: [
    { code: 'bank_payout', label: 'Подтверждённая выплата BANK', points: 100 },
    { code: 'duel_settlement', label: 'Подтверждённый результат DUEL', points: 60 },
    { code: 'timely_reveal', label: 'Результат открыт вовремя', points: 20 },
    {
      code: 'qualified_referral',
      label: 'Друг с подтверждённым действием',
      points: 25,
    },
    { code: 'missed_reveal', label: 'Результат DUEL не открыт вовремя', points: -40 },
  ],
};

const demoTeams: TeamOverview = {
  season: {
    id: 'team-season-demo',
    key: '2026-W32',
    name: '10–16 АВГУСТА',
    starts_at: new Date(now - 2 * 86_400_000).toISOString(),
    ends_at: new Date(now + 5 * 86_400_000).toISOString(),
    competition: 'bank_flow',
  },
  my_team: {
    id: 'team-void',
    slug: 'void-demo',
    name: 'VOID',
    description: 'Держим ритм. Забираем неделю.',
    tag: 'VOID',
    mark: 3,
    avatar_url: null,
    join_policy: 'open',
    member_count: 17,
    active_members: 8,
    flow_nano: 28_600_000_000,
    bank_entries: 22,
    bank_payouts: 9,
    duel_settlements: 12,
    rank: 4,
    is_mine: true,
    my_role: 'owner',
    my_join_state: 'joined',
    my_flow_nano: 4_000_000_000,
    top_members: [
      {
        user_id: 'demo',
        first_name: 'Дмитрий',
        username: 'loop_demo',
        photo_url: null,
        role: 'owner',
        joined_at: new Date(now - 5 * 86_400_000).toISOString(),
        flow_nano: 4_000_000_000,
        bank_entries: 3,
        bank_payouts: 1,
        duel_settlements: 2,
        is_me: true,
      },
      {
        user_id: 'team-user-2',
        first_name: 'Мира',
        username: 'miraloop',
        photo_url: null,
        role: 'admin',
        joined_at: new Date(now - 4 * 86_400_000).toISOString(),
        flow_nano: 6_500_000_000,
        bank_entries: 5,
        bank_payouts: 2,
        duel_settlements: 1,
        is_me: false,
      },
    ],
    recent_activity: [
      {
        id: 'team-event-demo',
        kind: 'bank_entry',
        user_id: 'team-user-2',
        first_name: 'Мира',
        username: 'miraloop',
        amount_nano: 2_000_000_000,
        tx_hash: 'demo-team-proof',
        event_at: new Date(now - 12 * 60_000).toISOString(),
      },
    ],
    pending_requests: [],
  },
  leaderboard: [
    {
      id: 'team-1',
      slug: 'north-demo',
      name: 'NORTH',
      description: '',
      tag: 'NORTH',
      mark: 0,
      avatar_url: null,
      join_policy: 'open',
      member_count: 31,
      active_members: 16,
      flow_nano: 43_200_000_000,
      bank_entries: 34,
      bank_payouts: 13,
      duel_settlements: 9,
      rank: 1,
      is_mine: false,
    },
    {
      id: 'team-2',
      slug: 'signal-demo',
      name: 'SIGNAL',
      description: '',
      tag: 'SGNL',
      mark: 1,
      avatar_url: null,
      join_policy: 'request',
      member_count: 24,
      active_members: 11,
      flow_nano: 35_700_000_000,
      bank_entries: 29,
      bank_payouts: 10,
      duel_settlements: 14,
      rank: 2,
      is_mine: false,
    },
    {
      id: 'team-3',
      slug: 'orbit-demo',
      name: 'ORBIT',
      description: '',
      tag: 'ORBIT',
      mark: 2,
      avatar_url: null,
      join_policy: 'invite',
      member_count: 19,
      active_members: 9,
      flow_nano: 31_700_000_000,
      bank_entries: 25,
      bank_payouts: 8,
      duel_settlements: 7,
      rank: 3,
      is_mine: false,
    },
  ],
};
demoTeams.leaderboard.push(demoTeams.my_team!);
const demoTeamsWithoutMembership: TeamOverview = {
  ...demoTeams,
  my_team: null,
  leaderboard: demoTeams.leaderboard.filter((team) => !team.is_mine),
};

const initialTab: Tab =
  mockScreen?.startsWith('duel') || mockScreen === 'inline'
    ? 'duel'
    : mockScreen?.startsWith('teams')
      ? 'teams'
      : mockScreen === 'rating'
        ? 'rating'
        : mockScreen === 'profile' || mockScreen === 'settings'
          ? 'profile'
          : 'bank';

interface LoopState {
  loading: boolean;
  activeTab: Tab;
  profile: Profile | null;
  prelaunch: Prelaunch | null;
  bankPosition: BankPosition | null;
  bankPulse: BankQueuePulse | null;
  bankHistory: BankPosition[];
  offers: Offer[];
  duels: Duel[];
  invite: Invite | null;
  /** The AFK challenge a shared card brought this person to answer. */
  challengeOfferId: number | null;
  rating: Rating | null;
  teams: TeamOverview | null;
  teamInvite: TeamInvitePreview | null;
  results: ResultCard[];
  error: string | null;
  showOnboarding: boolean;
  onboardingPage: number;
  bootstrap(): Promise<void>;
  refresh(): Promise<void>;
  refreshRating(): Promise<void>;
  clearTeamInvite(): void;
  setTab(tab: Tab): void;
  setError(error: string | null): void;
  declineInvite(): void;
  finishOnboarding(): Promise<void>;
  replayOnboarding(): void;
  setOnboardingEnabled(enabled: boolean): Promise<void>;
  setResultNotificationsEnabled(enabled: boolean): Promise<void>;
  markResultSeen(cardId: string): Promise<void>;
  setMockBankPosition(position: BankPosition): void;
}

export const useLoopStore = create<LoopState>((set, get) => ({
  loading: true,
  activeTab: initialTab,
  profile: null,
  prelaunch: null,
  bankPosition: null,
  bankPulse: null,
  bankHistory: [],
  offers: [],
  duels: [],
  invite: null,
  challengeOfferId: null,
  rating: null,
  teams: null,
  teamInvite: null,
  results: [],
  error: null,
  showOnboarding: false,
  onboardingPage:
    mockScreen === 'onboarding-bank'
      ? 1
      : mockScreen === 'onboarding-duel'
        ? 2
        : mockScreen === 'onboarding-plush'
          ? 3
          : 0,

  async bootstrap() {
    const started = performance.now();
    try {
      if (isMockTelegram()) {
        await new Promise((resolve) =>
          setTimeout(resolve, Math.max(0, 650 - (performance.now() - started))),
        );
        if (mockScreen === 'prelaunch') {
          set({
            profile: {
              ...demoProfile,
              app_open: false,
              launch_at: '2026-08-05T16:30:00Z',
            },
            prelaunch: {
              launch_at: '2026-08-05T16:30:00Z',
              referral_code: 'demo1234',
              referral_url: 'https://t.me/getloopbot?startapp=ref_demo1234',
              invited: 4,
              rank: 2,
              leaderboard: [
                { first_name: 'roma', username: 'akxiemy', invited: 7, is_me: false },
                { first_name: 'Дмитрий', username: 'loop_demo', invited: 4, is_me: true },
                { first_name: 'I love', username: 'iloveflopp', invited: 2, is_me: false },
              ],
              participants: 87,
            },
            loading: false,
          });
          return;
        }
        const empty = mockScreen === 'bank-empty';
        set({
          profile: mockScreen?.startsWith('teams')
            ? { ...demoProfile, announcement: null }
            : demoProfile,
          bankPosition: empty ? null : demoBank,
          bankPulse: demoBankPulse,
          bankHistory: empty ? [] : [demoBank],
          offers:
            mockScreen === 'duel-matchmaking' ||
            mockScreen === 'duel-result' ||
            mockScreen === 'duel-boost'
              ? [demoOffer]
              : [],
          duels: mockScreen === 'duel-result' || mockScreen === 'duel-boost' ? [demoDuel] : [],
          invite: mockScreen === 'duel-invite' ? demoInvite : null,
          rating: demoRating,
          teams: mockScreen === 'teams-create' ? demoTeamsWithoutMembership : demoTeams,
          results: demoResult ? [demoResult] : [],
          loading: false,
          showOnboarding:
            mockScreen === 'onboarding' ||
            mockScreen === 'onboarding-bank' ||
            mockScreen === 'onboarding-duel' ||
            mockScreen === 'onboarding-plush',
        });
        return;
      }
      const initData = telegramInitData();
      if (!initData) throw new Error('Откройте LOOP внутри Telegram');
      const profile = (await api.authenticate(initData)).profile;
      if (!profile.app_open) {
        set({ profile, prelaunch: await api.prelaunch(), loading: false });
        return;
      }
      const [bankPosition, bankPulse, bankHistory, offers, duels, rating, teams, results] =
        await Promise.all([
          api.currentBankPosition(),
          api.bankPulse(),
          api.bankPositions(),
          api.offers(),
          api.duels(),
          api.rating().catch(() => null),
          api.teamsOverview().catch(() => null),
          api.results(),
        ]);
      let invite: Invite | null = null;
      let challengeOfferId: number | null = null;
      // A shared duel now carries the sharer's referral at the end, after
      // `-ref_`, so that bringing a friend into a duel finally counts. The
      // server reads that half; everything in front of it is the intention.
      const startParam = telegramStartParam()?.split('-ref_')[0] ?? null;
      let teamInvite: TeamInvitePreview | null = null;
      if (startParam?.startsWith('duel_o')) {
        // The card said "принять вызов", so this person expects that exact
        // challenge — not a bare search screen. Carry the offer through.
        const parsed = Number(startParam.slice(6));
        if (Number.isInteger(parsed) && parsed > 0) challengeOfferId = parsed;
      } else if (startParam?.startsWith('duel_')) {
        invite = await api.invite(startParam.slice(5));
      } else if (startParam?.startsWith('team_')) {
        teamInvite = await api.teamInvite(startParam.slice(5)).catch(() => null);
      }
      const opensDuel = startParam === 'duel' || Boolean(invite) || challengeOfferId !== null;
      const opensTeam = Boolean(teamInvite);
      set({
        profile,
        challengeOfferId,
        bankPosition,
        bankPulse,
        bankHistory,
        offers,
        duels,
        invite,
        rating,
        teams,
        teamInvite,
        results: hideDismissedResults(results),
        loading: false,
        activeTab: opensDuel ? 'duel' : opensTeam ? 'teams' : 'bank',
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
    const requestId = ++refreshRequestId;
    const [profile, bankPosition, bankPulse, bankHistory, offers, duels, results] =
      await Promise.all([
        api.me(),
        api.currentBankPosition(),
        api.bankPulse(),
        api.bankPositions(),
        api.offers(),
        api.duels(),
        api.results(),
      ]);
    if (requestId !== refreshRequestId) return;
    set({
      profile,
      bankPosition,
      bankPulse,
      bankHistory,
      offers,
      duels,
      results: hideDismissedResults(results),
    });
  },

  async refreshRating() {
    if (isMockTelegram()) return;
    const [rating, teams] = await Promise.all([
      api.rating().catch(() => null),
      api.teamsOverview().catch(() => null),
    ]);
    if (!rating && !teams) {
      set({ error: 'Рейтинг временно не обновился. Основные режимы продолжают работать.' });
      return;
    }
    set({ rating: rating ?? get().rating, teams: teams ?? get().teams });
  },

  clearTeamInvite() {
    set({ teamInvite: null });
  },

  setTab(activeTab) {
    set({ activeTab });
  },

  declineInvite() {
    // Nothing to tell the server: an invitation is a link, and refusing it only
    // means this person is not taking it. The challenger's own offer stays as
    // it was, open until they cancel it or it expires.
    set({ invite: null });
  },

  setError(error) {
    set({ error });
  },

  async finishOnboarding() {
    const profile = get().profile;
    const wasSeen = profile?.user.onboarding_seen === true;
    // Closing an optional replay must never depend on the network. The first
    // completion is also optimistic: a slow settings request cannot trap the
    // user behind a button that appears broken.
    set({
      profile: profile ? { ...profile, user: { ...profile.user, onboarding_seen: true } } : profile,
      showOnboarding: false,
    });
    if (!isMockTelegram() && !wasSeen) {
      try {
        await api.updateSettings({ onboarding_seen: true });
      } catch {
        // The local session is usable; a later first-run can retry persistence.
      }
    }
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

  async setResultNotificationsEnabled(enabled) {
    if (enabled && !(await requestResultNotificationAccess())) {
      throw new Error('Разрешите сообщения от LOOP в Telegram');
    }
    if (!isMockTelegram()) await api.updateSettings({ result_notifications_enabled: enabled });
    const profile = get().profile;
    if (profile) {
      set({
        profile: {
          ...profile,
          user: { ...profile.user, result_notifications_enabled: enabled },
        },
      });
    }
  },

  async markResultSeen(cardId) {
    rememberDismissed(cardId);
    const seenAt = new Date().toISOString();
    set({
      results: get().results.map((card) =>
        card.id === cardId ? { ...card, seen_at: seenAt } : card,
      ),
    });
    if (!isMockTelegram()) await api.markResultSeen(cardId);
  },

  setMockBankPosition(position) {
    set({ bankPosition: position, bankHistory: [position, ...get().bankHistory] });
  },
}));
