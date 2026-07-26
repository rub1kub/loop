import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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
});
