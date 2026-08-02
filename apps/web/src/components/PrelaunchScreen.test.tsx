import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Prelaunch } from '../types';
import { PrelaunchScreen } from './PrelaunchScreen';

vi.mock('../telegram', () => ({
  haptic: vi.fn(),
  openPlatformLink: vi.fn(),
  telegram: () => undefined,
}));

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
    render(<PrelaunchScreen prelaunch={prelaunch} />);

    expect(screen.getByText('8 АВГУСТА · 19:00 МСК')).toBeInTheDocument();
    const clock = screen.getByRole('timer');
    expect(clock.textContent).toContain('02');
    expect(clock.textContent).toContain('03');
    expect(clock.textContent).toContain('04');
    expect(clock.textContent).toContain('05');

    expect(screen.getByText('2% с каждого взноса приглашённых. Навсегда.')).toBeInTheDocument();
    expect(screen.getByText('@akxiemy')).toBeInTheDocument();
    expect(screen.getByText('Уже внутри: 41')).toBeInTheDocument();
    // Покупка кирпича ведёт на маркеты, а не на сайт.
    expect(screen.getByRole('button', { name: 'dTrade' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'RedoTrade' })).toBeInTheDocument();
    expect(screen.getByText(/выкупается с рынка/)).toBeInTheDocument();
    // Ranked second in the list even though rank says third overall.
    expect(screen.getByText(/место №3/)).toBeInTheDocument();
  });

  it('ticks live and never reloads before the moment', () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    render(<PrelaunchScreen prelaunch={prelaunch} />);

    const seconds = () => screen.getByRole('timer').textContent ?? '';
    expect(seconds()).toContain('05');
    vi.advanceTimersByTime(1000);
    expect(seconds()).toContain('04');
    expect(reload).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
