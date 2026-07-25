import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ProfileScreen } from './ProfileScreen';
import type { Profile } from '../types';

const apiMocks = vi.hoisted(() => ({
  meAvatar: vi.fn(),
  referrals: vi.fn(),
}));
const revokeObjectUrl = vi.fn();

vi.mock('../api', () => ({ api: apiMocks }));
vi.mock('../telegram', () => ({
  haptic: vi.fn(),
  isMockTelegram: () => false,
  telegram: () => null,
}));
vi.mock('@tonconnect/ui-react', () => ({
  useTonConnectUI: () => [{ openModal: vi.fn() }],
  useTonWallet: () => null,
}));

const profile: Profile = {
  user: {
    id: 'user-id',
    telegram_id: 42,
    username: 'loop',
    first_name: 'Дмитрий',
    photo_url: 'https://t.me/i/userpic/320/loop.jpg',
    onboarding_seen: true,
    onboarding_enabled: true,
  },
  wallet: null,
  bank: { active: 0, completed: 0, total: 0 },
  duel: { active: 0, completed: 0, total: 0 },
  plush_brick: {
    verified: false,
    balance_nano: 0,
    holder: false,
    duel_fee_bps: 250,
    fee_discount_active: false,
  },
};

describe('ProfileScreen', () => {
  beforeEach(() => {
    apiMocks.meAvatar.mockResolvedValue(new Blob(['avatar'], { type: 'image/jpeg' }));
    apiMocks.referrals.mockResolvedValue(null);
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:loop-avatar'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectUrl,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders the authenticated same-origin avatar blob', async () => {
    const { container, unmount } = render(
      <ProfileScreen
        profile={profile}
        rating={null}
        bankHistory={[]}
        duels={[]}
        onReplay={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('img.avatar')).toHaveAttribute('src', 'blob:loop-avatar');
    });
    expect(apiMocks.meAvatar).toHaveBeenCalledOnce();

    unmount();
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:loop-avatar');
  });
});
