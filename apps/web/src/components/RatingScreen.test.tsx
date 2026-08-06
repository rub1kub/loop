import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { RatingScreen } from '../features/rating/RatingScreen';
import type { Rating } from '../types';

const me = {
  rank: 7,
  user_id: 'me',
  first_name: 'Дмитрий',
  username: 'loop',
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
  is_me: true,
};

const rating: Rating = {
  season_id: '2026-07',
  season_name: 'ИЮЛЬ · 2026',
  starts_at: '2026-07-01T00:00:00Z',
  ends_at: '2026-08-01T00:00:00Z',
  me,
  leaderboard: [me],
  circle: [me],
  pulse: {
    active_participants: 38,
    active_bank: 21,
    active_duels: 17,
    proofs_24h: 46,
  },
  invite_race: [],
  invite_race_me: null,
  invite_race_ends_at: null,
  formula: [
    { code: 'bank_payout', label: 'Выплата BANK', points: 100 },
    { code: 'duel_settlement', label: 'Завершённый DUEL', points: 60 },
  ],
};

describe('RatingScreen', () => {
  afterEach(cleanup);

  it('keeps the score and next level visible while hiding explanations', () => {
    render(<RatingScreen rating={rating} />);

    expect(screen.getAllByText('685')[0]).toBeVisible();
    expect(screen.getByText('#7 В СЕЗОНЕ')).toBeVisible();
    expect(screen.getByText('315 ДО УРОВНЯ LOOP')).toBeVisible();
    expect(screen.getByText('УРОВЕНЬ · ОРБИТА')).toBeVisible();
    expect(screen.getByText('МОЯ СТАТИСТИКА').closest('details')).not.toHaveAttribute('open');
    expect(screen.queryByText(/Главный фактор:/)).not.toBeVisible();
    expect(screen.queryByText('СИСТЕМА СЕЙЧАС')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('МОЯ СТАТИСТИКА'));

    expect(screen.getByText(/Главный фактор:/)).toBeVisible();
    expect(screen.getByText(/Счёт отражает участие и надёжность/)).toBeVisible();
    expect(screen.getByText('СЕЙЧАС В LOOP')).toBeVisible();
  });

  it('runs the weekly race on money, with my row pinned even from outside the top', () => {
    render(
      <RatingScreen
        rating={{
          ...rating,
          invite_race: [
            {
              rank: 1,
              first_name: 'Мария',
              username: 'masha_ton',
              earned_nano: 380_000_000,
              invited: 6,
              is_me: false,
            },
          ],
          invite_race_me: {
            rank: 14,
            first_name: 'Я',
            username: null,
            earned_nano: 20_000_000,
            invited: 1,
            is_me: true,
          },
          invite_race_ends_at: new Date(Date.now() + 86_400_000).toISOString(),
        }}
      />,
    );

    expect(screen.getByText('ГОНКА НЕДЕЛИ')).toBeVisible();
    expect(screen.getByText('@masha_ton')).toBeVisible();
    expect(screen.getByText('0,38 GRAM')).toBeVisible();
    // My row appears pinned below the top even when I am fourteenth.
    const race = screen.getByLabelText('Гонка приглашающих за неделю');
    expect(within(race).getByText('#14')).toBeVisible();
    expect(within(race).getByText('ТЫ')).toBeVisible();
  });

  it('shows no race section while nobody has raced', () => {
    render(<RatingScreen rating={rating} />);
    expect(screen.queryByText('ГОНКА НЕДЕЛИ')).toBeNull();
  });
});
