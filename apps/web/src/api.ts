import { z } from 'zod';

import { telegramInitData } from './telegram';
import type {
  ActionIntent,
  ChallengePreview,
  BankPosition,
  BankQueuePulse,
  BankPreview,
  BankQuote,
  BankLimit,
  ContractState,
  Duel,
  DuelBoostIntent,
  Invite,
  Offer,
  OfferQuote,
  Prelaunch,
  Profile,
  PreparedResultShare,
  Rating,
  Referral,
  ReferralPayout,
  ResultCard,
  TeamDetail,
  TeamInvitePreview,
  TeamJoinResult,
  TeamMembersPage,
  TeamOverview,
  Wallet,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
let accessToken: string | null = null;
let reauthentication: Promise<boolean> | null = null;
const RETRYABLE_STATUSES = new Set([408, 425, 429, 502, 503, 504]);
const RETRY_DELAYS_MS = [250, 750];

const modeStatsSchema = z.object({ active: z.number(), completed: z.number(), total: z.number() });
const profileSchema = z.object({
  user: z.object({
    id: z.string(),
    telegram_id: z.number(),
    username: z.string().nullable(),
    first_name: z.string(),
    photo_url: z.string().nullable(),
    onboarding_seen: z.boolean(),
    onboarding_enabled: z.boolean(),
    result_notifications_enabled: z.boolean(),
  }),
  wallet: z
    .object({ address: z.string(), network: z.number(), verified_at: z.string() })
    .nullable(),
  bank: modeStatsSchema,
  duel: modeStatsSchema,
  // Absent on an older server, and a missing note is simply no note.
  announcement: z
    .object({ text: z.string(), url: z.string().nullable().default(null) })
    .nullable()
    .default(null),
  plush_brick: z.object({
    verified: z.boolean(),
    balance_nano: z.number(),
    holder: z.boolean(),
    duel_fee_bps: z.number(),
    fee_discount_active: z.boolean(),
  }),
  duel_stake: z.object({ min_stake_nano: z.number(), max_stake_nano: z.number() }),
  app_open: z.boolean(),
  launch_at: z.string().nullable(),
});

const prelaunchSchema = z.object({
  launch_at: z.string().nullable(),
  referral_code: z.string(),
  referral_url: z.string(),
  invited: z.number(),
  rank: z.number().nullable(),
  leaderboard: z.array(
    z.object({
      first_name: z.string(),
      username: z.string().nullable(),
      invited: z.number(),
      is_me: z.boolean(),
    }),
  ),
  participants: z.number(),
});

const bankPositionSchema = z.object({
  id: z.string(),
  position_id: z.number(),
  owner_wallet: z.string(),
  principal_nano: z.number(),
  multiplier_bps: z.union([z.literal(12500), z.literal(15000), z.literal(20000)]),
  target_payout_nano: z.number(),
  funded_amount_nano: z.number(),
  remaining_amount_nano: z.number(),
  progress_bps: z.number(),
  queue_index: z.number().nullable(),
  queue_position: z.number().nullable(),
  // Defaulted rather than required: a screen already open when this shipped
  // keeps polling with the older shape, and a jar is not worth an exception.
  queue_progress_bps: z.number().default(0),
  queue_ahead: z.number().default(0),
  queue_ahead_nano: z.number().default(0),
  queue_eta_seconds: z.number().nullable().default(null),
  current_status: z.enum([
    'pending_confirmation',
    'queued',
    'partially_funded',
    'completed',
    'payout_sent',
    'failed',
  ]),
  funding_transaction: z.string().nullable(),
  payout_transaction: z.string().nullable(),
  proof_url: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});

const bankWaveSchema = z.object({
  id: z.string(),
  state: z.enum(['upcoming', 'active', 'goal_reached', 'missed', 'awaiting_boost', 'completed']),
  starts_at: z.string(),
  ends_at: z.string(),
  participants: z.number(),
  goal: z.number(),
  boost_nano: z.number(),
  boost_confirmed: z.boolean(),
  proof_url: z.string().nullable(),
  closer_name: z.string().nullable(),
  closer_username: z.string().nullable(),
  is_closer: z.boolean(),
});

const bankQueuePulseSchema = z.object({
  active_positions: z.number(),
  minimum_entry_nano: z.number(),
  minimum_entry_payouts: z.number(),
  next_payout_gross_nano: z.number(),
  updated_at: z.string(),
  wave: bankWaveSchema.nullable().default(null),
});

const resultCardSchema = z.object({
  id: z.string(),
  mode: z.enum(['bank', 'duel', 'bank_entry']),
  payout_nano: z.number(),
  contributed_nano: z.number(),
  result_nano: z.number(),
  queue_position: z.number().nullable(),
  proof_url: z.string(),
  image_url: z.string(),
  seen_at: z.string().nullable(),
  created_at: z.string(),
});

const ratingEntrySchema = z.object({
  rank: z.number(),
  user_id: z.string(),
  first_name: z.string(),
  username: z.string().nullable(),
  photo_url: z.string().nullable(),
  score: z.number(),
  level: z.enum(['SIGNAL', 'PULSE', 'ORBIT', 'LOOP']),
  bank_payouts: z.number(),
  duel_settlements: z.number(),
  timely_reveals: z.number(),
  missed_reveals: z.number(),
  qualified_referrals: z.number(),
  proofs: z.number(),
  reliability_bps: z.number(),
  earned_nano: z.number().default(0),
  is_me: z.boolean(),
});

const inviteRaceEntrySchema = z.object({
  rank: z.number(),
  first_name: z.string(),
  username: z.string().nullable(),
  earned_nano: z.number(),
  invited: z.number(),
  is_me: z.boolean(),
});

const ratingSchema = z.object({
  season_id: z.string(),
  season_name: z.string(),
  starts_at: z.string(),
  ends_at: z.string(),
  me: ratingEntrySchema,
  leaderboard: z.array(ratingEntrySchema),
  circle: z.array(ratingEntrySchema),
  pulse: z.object({
    active_participants: z.number(),
    active_bank: z.number(),
    active_duels: z.number(),
    proofs_24h: z.number(),
  }),
  formula: z.array(
    z.object({
      code: z.string(),
      label: z.string(),
      points: z.number(),
    }),
  ),
  // Absent on an older server; an empty race is simply not shown.
  invite_race: z.array(inviteRaceEntrySchema).default([]),
  invite_race_me: inviteRaceEntrySchema.nullable().default(null),
  invite_race_ends_at: z.string().nullable().default(null),
});

const teamEntrySchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  description: z.string(),
  tag: z.string(),
  mark: z.number(),
  avatar_url: z.string().nullable(),
  join_policy: z.enum(['open', 'request', 'invite']),
  member_count: z.number(),
  active_members: z.number(),
  flow_nano: z.number(),
  bank_entries: z.number(),
  bank_payouts: z.number(),
  duel_settlements: z.number(),
  rank: z.number(),
  is_mine: z.boolean(),
});

const teamMemberSchema = z.object({
  user_id: z.string(),
  first_name: z.string(),
  username: z.string().nullable(),
  photo_url: z.string().nullable(),
  role: z.enum(['owner', 'admin', 'member']),
  joined_at: z.string(),
  flow_nano: z.number(),
  bank_entries: z.number(),
  bank_payouts: z.number(),
  duel_settlements: z.number(),
  is_me: z.boolean(),
});

const teamDetailSchema = teamEntrySchema.extend({
  my_role: z.enum(['owner', 'admin', 'member']).nullable(),
  my_join_state: z.enum(['none', 'pending', 'joined']),
  my_flow_nano: z.number(),
  top_members: z.array(teamMemberSchema),
  recent_activity: z.array(
    z.object({
      id: z.string(),
      kind: z.enum(['bank_entry', 'bank_payout', 'duel_settlement']),
      user_id: z.string(),
      first_name: z.string(),
      username: z.string().nullable(),
      amount_nano: z.number(),
      tx_hash: z.string(),
      event_at: z.string(),
    }),
  ),
  pending_requests: z.array(
    z.object({
      id: z.string(),
      user_id: z.string(),
      first_name: z.string(),
      username: z.string().nullable(),
      photo_url: z.string().nullable(),
      created_at: z.string(),
    }),
  ),
});

const teamOverviewSchema = z.object({
  season: z.object({
    id: z.string(),
    key: z.string(),
    name: z.string(),
    starts_at: z.string(),
    ends_at: z.string(),
    competition: z.literal('bank_flow'),
  }),
  my_team: teamDetailSchema.nullable(),
  leaderboard: z.array(teamEntrySchema),
});

const teamInvitePreviewSchema = z.object({
  token: z.string(),
  expires_at: z.string(),
  team: teamEntrySchema,
  inviter_name: z.string(),
});

const teamMembersPageSchema = z.object({
  items: z.array(teamMemberSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
});

const teamJoinResultSchema = z.object({
  state: z.enum(['joined', 'requested']),
  team: teamDetailSchema,
});

const IDEMPOTENT_POSTS = /^\/(results\/[^/]+\/seen|bank\/positions\/\d+\/discard)$/;

async function restoreSession(): Promise<boolean> {
  const initData = telegramInitData();
  if (!initData) return false;
  if (!reauthentication) {
    reauthentication = request<{ access_token: string }>(
      '/auth/telegram',
      { method: 'POST', body: JSON.stringify({ init_data: initData }) },
      false,
    )
      .then((auth) => {
        accessToken = auth.access_token;
        return true;
      })
      .finally(() => {
        reauthentication = null;
      });
  }
  return reauthentication;
}

async function request<T>(path: string, init?: RequestInit, retryUnauthorized = true): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const method = (init?.method ?? 'GET').toUpperCase();
  // Marking a card seen sets one timestamp once, so repeating it is harmless
  // and a dropped request must not cost the user a dismissal.
  const canRetry = method === 'GET' || path === '/auth/telegram' || IDEMPOTENT_POSTS.test(path);
  let response: Response | undefined;
  let networkError: unknown;
  const attempts = canRetry ? RETRY_DELAYS_MS.length + 1 : 1;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      response = await fetch(`${API_BASE}${path}`, { ...init, headers });
      networkError = undefined;
      if (!RETRYABLE_STATUSES.has(response.status) || attempt === attempts - 1) break;
    } catch (error) {
      response = undefined;
      networkError = error;
      if (attempt === attempts - 1) break;
    }
    await new Promise((resolve) => window.setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
  }
  if (!response) {
    throw new Error('Не удалось загрузить данные. Проверьте соединение и повторите.', {
      cause: networkError,
    });
  }
  if (response.status === 401 && retryUnauthorized && path !== '/auth/telegram') {
    accessToken = null;
    if (await restoreSession()) return request<T>(path, init, false);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({ detail: 'Ошибка соединения' }))) as {
      detail?: string;
    };
    throw new Error(body.detail ?? `HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function requestAvatar(path = '/me/avatar', retryUnauthorized = true): Promise<Blob | null> {
  const headers = new Headers({ Accept: 'image/*' });
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { headers });
  } catch (error) {
    throw new Error('Не удалось загрузить аватар.', { cause: error });
  }
  if (response.status === 401 && retryUnauthorized) {
    accessToken = null;
    if (await restoreSession()) return requestAvatar(path, false);
  }
  if (response.status === 404) return null;
  if (!response.ok || !response.headers.get('Content-Type')?.startsWith('image/')) {
    throw new Error('Не удалось загрузить аватар.');
  }
  return await response.blob();
}

export const api = {
  async authenticate(initData: string): Promise<{ profile: Profile; token: string }> {
    const auth = await request<{ access_token: string }>('/auth/telegram', {
      method: 'POST',
      body: JSON.stringify({ init_data: initData }),
    });
    accessToken = auth.access_token;
    return {
      profile: profileSchema.parse(await request<unknown>('/me')),
      token: auth.access_token,
    };
  },

  setToken(token: string): void {
    accessToken = token;
  },

  async me(): Promise<Profile> {
    return profileSchema.parse(await request<unknown>('/me'));
  },

  async meAvatar(): Promise<Blob | null> {
    return await requestAvatar();
  },

  async opponentAvatar(duelId: number): Promise<Blob | null> {
    try {
      return await requestAvatar(`/duels/${duelId}/opponent-avatar`);
    } catch {
      // A face is a nicety: a proxy hiccup must not mark the whole duel failed.
      return null;
    }
  },

  async updateSettings(input: {
    onboarding_seen?: boolean;
    onboarding_enabled?: boolean;
    result_notifications_enabled?: boolean;
  }): Promise<void> {
    await request('/me/settings', { method: 'PATCH', body: JSON.stringify(input) });
  },

  async walletChallenge(): Promise<{ payload: string; expires_at: string }> {
    return await request('/wallet/challenge', { method: 'POST', body: '{}' });
  },

  async verifyWallet(input: {
    address: string;
    network: number;
    publicKey: string;
    proof: unknown;
  }): Promise<Wallet> {
    return await request('/wallet/verify', { method: 'POST', body: JSON.stringify(input) });
  },

  async currentBankPosition(): Promise<BankPosition | null> {
    const result = await request<unknown>('/bank/positions/current');
    return result === null ? null : bankPositionSchema.parse(result);
  },

  async bankPositions(): Promise<BankPosition[]> {
    return z.array(bankPositionSchema).parse(await request<unknown>('/bank/positions'));
  },

  async quoteBankPosition(input: {
    position_id: number;
    principal_nano: number;
    multiplier_bps: number;
  }): Promise<BankQuote> {
    return await request('/bank/positions/quote', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async previewBankPosition(input: {
    principal_nano: number;
    multiplier_bps: number;
  }): Promise<BankPreview> {
    return await request('/bank/positions/preview', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async bankLimits(): Promise<BankLimit> {
    return await request('/bank/limits');
  },

  async bankPulse(): Promise<BankQueuePulse> {
    return bankQueuePulseSchema.parse(await request<unknown>('/bank/pulse'));
  },

  async results(): Promise<ResultCard[]> {
    return z.array(resultCardSchema).parse(await request<unknown>('/results'));
  },

  async markResultSeen(cardId: string): Promise<ResultCard> {
    return resultCardSchema.parse(
      await request<unknown>(`/results/${encodeURIComponent(cardId)}/seen`, {
        method: 'POST',
        body: '{}',
      }),
    );
  },

  async prepareDuelShare(offerId: number): Promise<PreparedResultShare> {
    return await request(`/duels/offers/${offerId}/share`, { method: 'POST', body: '{}' });
  },

  async prepareResultShare(cardId: string): Promise<PreparedResultShare> {
    return await request(`/results/${encodeURIComponent(cardId)}/prepare`, {
      method: 'POST',
      body: '{}',
    });
  },

  async contractState(mode: 'bank' | 'duel'): Promise<ContractState> {
    return await request(`/onchain/contracts/${mode}`);
  },

  async quoteOffer(input: {
    offer_id: number;
    chance_bps: number;
    stake_nano: number;
    commitment_hex: string;
    mode: 'afk' | 'direct';
    challenge_code?: string;
  }): Promise<OfferQuote> {
    return await request('/duels/offers/quote', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async offers(): Promise<Offer[]> {
    return await request('/duels/offers');
  },

  async duels(): Promise<Duel[]> {
    return await request('/duels');
  },

  async duelChallengePreview(offerId: number): Promise<ChallengePreview> {
    return await request(`/duels/offers/${offerId}/preview`);
  },

  async matchOfferIntent(offerId: number): Promise<ActionIntent> {
    return await request(`/duels/offers/${offerId}/match-intent`, { method: 'POST', body: '{}' });
  },

  async revealIntent(duelId: number): Promise<ActionIntent> {
    return await request(`/duels/${duelId}/reveal-intent`, { method: 'POST', body: '{}' });
  },

  async boostDuelIntent(
    duelId: number,
    input: {
      amount_nano: number;
      expected_revision: number;
      min_chance_bps: number;
    },
  ): Promise<DuelBoostIntent> {
    return await request(`/duels/${duelId}/boost-intent`, {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async discardOffer(offerId: number): Promise<void> {
    await request(`/duels/offers/${offerId}/discard`, { method: 'POST', body: '{}' });
  },

  async cancelOfferIntent(offerId: number): Promise<ActionIntent> {
    return await request(`/duels/offers/${offerId}/cancel-intent`, {
      method: 'POST',
      body: '{}',
    });
  },

  async expireOfferIntent(offerId: number): Promise<ActionIntent> {
    return await request(`/duels/offers/${offerId}/expire-intent`, {
      method: 'POST',
      body: '{}',
    });
  },

  async expireDuelIntent(duelId: number): Promise<ActionIntent> {
    return await request(`/duels/${duelId}/expire-intent`, { method: 'POST', body: '{}' });
  },

  async referrals(): Promise<Referral> {
    return await request('/referrals');
  },

  async requestReferralPayout(address: string): Promise<ReferralPayout> {
    return await request('/referrals/payout', {
      method: 'POST',
      body: JSON.stringify({ address }),
    });
  },

  async discardBankPosition(positionId: number): Promise<void> {
    await request(`/bank/positions/${positionId}/discard`, { method: 'POST', body: '{}' });
  },

  async prelaunch(): Promise<Prelaunch> {
    return prelaunchSchema.parse(await request<unknown>('/prelaunch'));
  },

  async prepareInviteShare(): Promise<PreparedResultShare> {
    return await request('/prelaunch/share', { method: 'POST', body: '{}' });
  },

  async rating(): Promise<Rating> {
    return ratingSchema.parse(await request<unknown>('/rating'));
  },

  async teamsOverview(): Promise<TeamOverview> {
    return teamOverviewSchema.parse(await request<unknown>('/teams/overview'));
  },

  async team(slug: string): Promise<TeamDetail> {
    return teamDetailSchema.parse(await request<unknown>(`/teams/${encodeURIComponent(slug)}`));
  },

  async searchTeams(
    q = '',
    offset = 0,
  ): Promise<{ items: TeamOverview['leaderboard']; total: number }> {
    const result = z
      .object({
        items: z.array(teamEntrySchema),
        total: z.number(),
        offset: z.number(),
        limit: z.number(),
      })
      .parse(
        await request<unknown>(
          `/teams/search?q=${encodeURIComponent(q)}&offset=${offset}&limit=20`,
        ),
      );
    return { items: result.items, total: result.total };
  },

  async teamMembers(slug: string, offset = 0): Promise<TeamMembersPage> {
    return teamMembersPageSchema.parse(
      await request<unknown>(
        `/teams/${encodeURIComponent(slug)}/members?offset=${offset}&limit=50`,
      ),
    );
  },

  async teamInvite(token: string): Promise<TeamInvitePreview> {
    return teamInvitePreviewSchema.parse(
      await request<unknown>(`/teams/invites/${encodeURIComponent(token)}`),
    );
  },

  async createTeam(input: {
    name: string;
    join_policy: 'open' | 'request' | 'invite';
  }): Promise<TeamDetail> {
    return teamDetailSchema.parse(
      await request<unknown>('/teams', { method: 'POST', body: JSON.stringify(input) }),
    );
  },

  async updateTeam(
    slug: string,
    input: {
      name?: string;
      description?: string;
      mark?: number;
      join_policy?: 'open' | 'request' | 'invite';
    },
  ): Promise<TeamDetail> {
    return teamDetailSchema.parse(
      await request<unknown>(`/teams/${encodeURIComponent(slug)}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    );
  },

  async updateTeamAvatar(slug: string, file: File): Promise<TeamDetail> {
    return teamDetailSchema.parse(
      await request<unknown>(`/teams/${encodeURIComponent(slug)}/avatar`, {
        method: 'PUT',
        headers: { 'Content-Type': file.type },
        body: file,
      }),
    );
  },

  async deleteTeamAvatar(slug: string): Promise<TeamDetail> {
    return teamDetailSchema.parse(
      await request<unknown>(`/teams/${encodeURIComponent(slug)}/avatar`, {
        method: 'DELETE',
      }),
    );
  },

  async joinTeam(slug: string): Promise<TeamJoinResult> {
    return teamJoinResultSchema.parse(
      await request(`/teams/${encodeURIComponent(slug)}/join`, {
        method: 'POST',
        body: '{}',
      }),
    );
  },

  async joinTeamInvite(token: string): Promise<TeamJoinResult> {
    return teamJoinResultSchema.parse(
      await request(`/teams/invites/${encodeURIComponent(token)}/join`, {
        method: 'POST',
        body: '{}',
      }),
    );
  },

  async leaveTeam(slug: string): Promise<void> {
    await request(`/teams/${encodeURIComponent(slug)}/leave`, { method: 'POST', body: '{}' });
  },

  async prepareTeamShare(slug: string): Promise<PreparedResultShare> {
    return await request(`/teams/${encodeURIComponent(slug)}/share`, {
      method: 'POST',
      body: '{}',
    });
  },

  async decideTeamRequest(slug: string, requestId: string, approve: boolean): Promise<void> {
    await request(`/teams/${encodeURIComponent(slug)}/requests/${encodeURIComponent(requestId)}`, {
      method: 'POST',
      body: JSON.stringify({ approve }),
    });
  },

  async updateTeamMember(slug: string, userId: string, role: 'admin' | 'member'): Promise<void> {
    await request(`/teams/${encodeURIComponent(slug)}/members/${encodeURIComponent(userId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    });
  },

  async removeTeamMember(slug: string, userId: string): Promise<void> {
    await request(`/teams/${encodeURIComponent(slug)}/members/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
    });
  },

  async transferTeam(slug: string, userId: string): Promise<void> {
    await request(`/teams/${encodeURIComponent(slug)}/transfer`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId }),
    });
  },

  async invite(code: string): Promise<Invite> {
    return await request(`/invites/${encodeURIComponent(code)}`);
  },

  async acceptInvite(code: string): Promise<Invite> {
    return await request(`/invites/${encodeURIComponent(code)}/accept`, {
      method: 'POST',
      body: '{}',
    });
  },
};
