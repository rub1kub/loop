import type {
  ApplicationControl,
  ControlActionInput,
  ControlAnalytics,
  ControlOverview,
  ControlParticipants,
  ControlReferralPayout,
  ControlReferralPayouts,
  ControlTransaction,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export class ControlApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_BASE}/control${path}`, {
    ...init,
    credentials: 'include',
    headers,
  });
  if (!response.ok) {
    const body = (await response
      .json()
      .catch(() => ({ detail: 'Сервис временно недоступен' }))) as {
      detail?: string;
    };
    throw new ControlApiError(body.detail ?? `HTTP ${response.status}`, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const controlApi = {
  session(): Promise<{ wallet: string }> {
    return request('/session');
  },

  challenge(): Promise<{ payload: string; expires_at: string }> {
    return request('/challenge', { method: 'POST', body: '{}' });
  },

  createSession(input: {
    address: string;
    network: number;
    publicKey: string;
    proof: unknown;
  }): Promise<{ wallet: string; expires_at: string }> {
    return request('/session', { method: 'POST', body: JSON.stringify(input) });
  },

  logout(): Promise<void> {
    return request('/session', { method: 'DELETE' });
  },

  overview(): Promise<ControlOverview> {
    return request('/overview');
  },

  participants(limit = 100): Promise<ControlParticipants> {
    return request(`/participants?limit=${limit}`);
  },

  analytics(days = 30): Promise<ControlAnalytics> {
    return request(`/analytics?days=${days}`);
  },

  referralPayouts(limit = 100): Promise<ControlReferralPayouts> {
    return request(`/referral-payouts?limit=${limit}`);
  },

  prepareReferralPayout(id: string): Promise<ControlTransaction> {
    return request(`/referral-payouts/${encodeURIComponent(id)}/transaction`, {
      method: 'POST',
      body: '{}',
    });
  },

  confirmReferralPayout(id: string, signedBoc?: string): Promise<ControlReferralPayout> {
    return request(`/referral-payouts/${encodeURIComponent(id)}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ signed_boc: signedBoc ?? null }),
    });
  },

  rejectReferralPayout(id: string, reason: string): Promise<ControlReferralPayout> {
    return request(`/referral-payouts/${encodeURIComponent(id)}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  updateApplication(input: Partial<ApplicationControl>): Promise<ApplicationControl> {
    return request('/application', { method: 'PATCH', body: JSON.stringify(input) });
  },

  transaction(input: ControlActionInput): Promise<ControlTransaction> {
    return request('/transactions', { method: 'POST', body: JSON.stringify(input) });
  },

  waveTransaction(): Promise<ControlTransaction> {
    return request('/wave/transaction', { method: 'POST', body: '{}' });
  },
};
