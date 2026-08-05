import { describe, expect, it } from 'vitest';

import { queueNote, spokenWait } from './queueNote';
import type { BankPosition } from '../../types';

const position = (overrides: Partial<BankPosition> = {}): BankPosition => ({
  id: 'p1',
  position_id: 1,
  owner_wallet: '0:' + 'ab'.repeat(32),
  principal_nano: 1_000_000_000,
  multiplier_bps: 20000,
  target_payout_nano: 2_000_000_000,
  funded_amount_nano: 0,
  remaining_amount_nano: 2_000_000_000,
  progress_bps: 0,
  queue_index: 40,
  queue_position: 7,
  queue_progress_bps: 4029,
  queue_ahead: 6,
  queue_ahead_nano: 8_000_000_000,
  queue_eta_seconds: 1200,
  current_status: 'queued',
  funding_transaction: null,
  payout_transaction: null,
  proof_url: null,
  created_at: '2026-08-05T19:40:00Z',
  completed_at: null,
  ...overrides,
});

describe('what the jar says while you wait', () => {
  it('names the half of the wait you are in, and who moves it', () => {
    // Six positions in front is not a failure of yours to fix — it is other
    // people's deposits that move it, and the number has to say so plainly.
    expect(queueNote(6, 8_000_000_000, 1200, position())).toBe(
      'Впереди 6 позиций — им нужно 8 GRAM · около 20 мин',
    );
  });

  it('drops the estimate rather than inventing one when nothing is arriving', () => {
    expect(queueNote(1, 500_000_000, null, position())).toBe(
      'Впереди 1 позиция — им нужно 0,5 GRAM',
    );
  });

  it('switches to your own filling once the queue reaches you', () => {
    expect(
      queueNote(0, 0, null, position({ funded_amount_nano: 750_000_000, queue_ahead: 0 })),
    ).toBe('Твоя очередь: собрано 0,75 из 2 GRAM');
  });

  it('says the money is gone once it has been sent', () => {
    expect(
      queueNote(0, 0, null, position({ current_status: 'payout_sent', remaining_amount_nano: 0 })),
    ).toBe('Выплата отправлена');
  });
});

describe('spokenWait', () => {
  it('never promises precision it does not have', () => {
    expect(spokenWait(45)).toBe('меньше минуты');
    expect(spokenWait(600)).toBe('около 10 мин');
    expect(spokenWait(7200)).toBe('около 2 ч');
    expect(spokenWait(180_000)).toBe('около 2 дн');
  });
});
