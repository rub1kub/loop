import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Prelaunch, Profile } from '../types';
import { PrelaunchScreen } from './PrelaunchScreen';

vi.mock('../telegram', () => ({
  haptic: vi.fn(),
  openPlatformLink: vi.fn(),
  telegram: () => undefined,
}));

const profile: Profile = {
  user: {
    id: 'u1',
    telegram_id: 1,
    username: 'guest',
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
  app_open: false,
  launch_at: '2026-08-08T16:00:00Z',
};

const prelaunch: Prelaunch = {
  launch_at: '2026-08-08T16:00:00Z',
  referral_code: 'abc123',
  referral_url: 'https://t.me/getloopbot?startapp=ref_abc123',
  invited: 2,
  rank: 3,
  leaderboard: [
    { first_name: 'roma', username: 'akxiemy', invited: 7, is_me: false },
    { first_name: 'Гость', username: 'guest', invited: 2, is_me: true },
  ],
  participants: 41,
};

describe('PrelaunchScreen', () => {
  beforeEach(() => {
    // Two days, three hours, four minutes and five seconds before the door
    // opens — every unit of the countdown is distinct and non-zero.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-06T12:55:55Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it('counts down to the launch moment and shows the race', () => {
    render(<PrelaunchScreen profile={profile} prelaunch={prelaunch} />);

    expect(screen.getByText('ОТКРЫТИЕ · 8 АВГУСТА · 19:00 МСК')).toBeInTheDocument();
    const clock = screen.getByRole('timer');
    expect(clock.textContent).toContain('02');
    expect(clock.textContent).toContain('03');
    expect(clock.textContent).toContain('04');
    expect(clock.textContent).toContain('05');

    expect(screen.getByTestId('referral-url').textContent).toContain(
      't.me/getloopbot?startapp=ref_abc123',
    );
    expect(screen.getByText('2% с каждого взноса приглашённых. Навсегда.')).toBeInTheDocument();
    expect(screen.getByText('@akxiemy')).toBeInTheDocument();
    expect(screen.getByText('41')).toBeInTheDocument();
    // Ranked second in the list even though rank says third overall.
    expect(screen.getByText(/место №3/)).toBeInTheDocument();
  });

  it('ticks live and never reloads before the moment', () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    render(<PrelaunchScreen profile={profile} prelaunch={prelaunch} />);

    const seconds = () => screen.getByRole('timer').textContent ?? '';
    expect(seconds()).toContain('05');
    vi.advanceTimersByTime(1000);
    expect(seconds()).toContain('04');
    expect(reload).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
