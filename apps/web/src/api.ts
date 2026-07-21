import { z } from 'zod';

import { telegramInitData } from './telegram';
import type {
  ActionIntent,
  BankPosition,
  BankPreview,
  BankQuote,
  Duel,
  Invite,
  Offer,
  OfferQuote,
  Profile,
  Referral,
  Wallet,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
let accessToken: string | null = null;
let reauthentication: Promise<boolean> | null = null;

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
  }),
  wallet: z
    .object({ address: z.string(), network: z.number(), verified_at: z.string() })
    .nullable(),
  bank: modeStatsSchema,
  duel: modeStatsSchema,
  plush_brick: z.object({
    verified: z.boolean(),
    balance_nano: z.number(),
    holder: z.boolean(),
    duel_fee_bps: z.number(),
    fee_discount_active: z.boolean(),
  }),
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
  headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
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
  return (await response.json()) as T;
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

  async updateSettings(input: {
    onboarding_seen?: boolean;
    onboarding_enabled?: boolean;
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

  async revealIntent(duelId: number): Promise<ActionIntent> {
    return await request(`/duels/${duelId}/reveal-intent`, { method: 'POST', body: '{}' });
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
