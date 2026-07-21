import { z } from 'zod';

import type { Offer, OfferQuote, Profile, Referral, Wallet } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
let accessToken: string | null = null;

const userSchema = z.object({
  id: z.string(),
  telegram_id: z.number(),
  username: z.string().nullable(),
  first_name: z.string(),
  onboarding_seen: z.boolean(),
});

const profileSchema = z.object({
  user: userSchema,
  wallet: z
    .object({ address: z.string(), network: z.number(), verified_at: z.string() })
    .nullable(),
  bank: z.object({ target_nano: z.number(), updated_at: z.string() }).nullable(),
  balance_nano: z.number().nullable(),
  plush_brick_holder: z.boolean(),
});

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
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

  async setBankTarget(targetNano: number): Promise<void> {
    await request('/bank', {
      method: 'PUT',
      body: JSON.stringify({ target_nano: targetNano }),
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
  }): Promise<OfferQuote> {
    return await request('/duels/quote', { method: 'POST', body: JSON.stringify(input) });
  },

  async offers(): Promise<Offer[]> {
    return await request('/duels/offers');
  },

  async referrals(): Promise<Referral> {
    return await request('/referrals');
  },
};
