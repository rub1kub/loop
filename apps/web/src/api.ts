import { z } from 'zod';

import { telegramInitData } from './telegram';
import type {
  ActionIntent,
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

const userSchema = z.object({
  id: z.string(),
  telegram_id: z.number(),
  username: z.string().nullable(),
  first_name: z.string(),
  photo_url: z.string().nullable(),
  onboarding_seen: z.boolean(),
});

const cycleEventSchema = z.object({
  id: z.string(),
  kind: z.string(),
  title: z.string(),
  proof_type: z.enum(['system', 'telegram', 'ton_transaction', 'ton_state']),
  proof_ref: z.string().nullable(),
  proof_url: z.string().url().nullable(),
  created_at: z.string(),
});

const bankCycleSchema = z.object({
  id: z.string(),
  sequence_number: z.number(),
  status: z.enum(['active', 'completed', 'expired']),
  goal_events: z.number(),
  event_count: z.number(),
  progress_bps: z.number(),
  started_at: z.string(),
  ends_at: z.string(),
  completed_at: z.string().nullable(),
  events: z.array(cycleEventSchema),
});

const profileSchema = z.object({
  user: userSchema,
  wallet: z
    .object({ address: z.string(), network: z.number(), verified_at: z.string() })
    .nullable(),
  bank: bankCycleSchema.nullable(),
});

async function restoreSession(): Promise<boolean> {
  const initData = telegramInitData();
  if (!initData) return false;
  if (!reauthentication) {
    reauthentication = request<{ access_token: string }>(
      '/auth/telegram',
      {
        method: 'POST',
        body: JSON.stringify({ init_data: initData }),
      },
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

  async updateOnboarding(onboardingSeen: boolean): Promise<void> {
    await request('/me/settings', {
      method: 'PATCH',
      body: JSON.stringify({ onboarding_seen: onboardingSeen }),
    });
  },

  async startCycle(goalEvents = 6): Promise<void> {
    await request('/bank/cycles', {
      method: 'POST',
      body: JSON.stringify({ goal_events: goalEvents }),
    });
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

  async quoteOffer(input: {
    offer_id: number;
    chance_bps: number;
    total_pool_nano: number;
    commitment_hex: string;
    challenge_code?: string;
  }): Promise<OfferQuote> {
    return await request('/duels/quote', { method: 'POST', body: JSON.stringify(input) });
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
};
