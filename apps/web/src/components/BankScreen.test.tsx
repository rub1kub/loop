import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { BankScreen } from '../features/bank/BankScreen';
import type { BankPosition, Profile } from '../types';

vi.mock('@tonconnect/ui-react', () => ({
  useTonConnectUI: () => [{ openModal: vi.fn() }],
  useTonWallet: () => null,
}));

const profile: Profile = {
  user: {
    id: 'user-id',
    telegram_id: 42,
    username: null,
    first_name: 'Loop',
    photo_url: null,
    onboarding_seen: true,
    onboarding_enabled: true,
    result_notifications_enabled: true,
  },
  wallet: null,
  bank: { active: 1, completed: 0, total: 1 },
  duel: { active: 0, completed: 0, total: 0 },
  plush_brick: {
    verified: false,
    balance_nano: 0,
    holder: false,
    duel_fee_bps: 250,
    fee_discount_active: false,
  },
  duel_stake: { min_stake_nano: 500000000, max_stake_nano: 500000000 },
  app_open: true,
  launch_at: null,
};

const position: BankPosition = {
  id: 'bank-test',
  position_id: 100,
  owner_wallet: `0:${'42'.repeat(32)}`,
  principal_nano: 2_000_000_000,
  multiplier_bps: 15000,
  target_payout_nano: 3_000_000_000,
  funded_amount_nano: 1_110_000_000,
  remaining_amount_nano: 1_890_000_000,
  progress_bps: 3700,
  queue_index: 4,
  queue_position: 2,
  current_status: 'partially_funded',
  funding_transaction: 'test-transaction',
  payout_transaction: null,
  proof_url: null,
  created_at: '2026-07-22T00:00:00.000Z',
  completed_at: null,
};

describe('BankScreen', () => {
  afterEach(cleanup);

  it('keeps the empty state concise before the user creates a position', () => {
    render(
      <BankScreen
        profile={profile}
        position={null}
        pulse={null}
        onRefresh={vi.fn()}
        onMockCreated={vi.fn()}
      />,
    );

    const action = screen.getByRole('button', { name: 'СОЗДАТЬ ПОЗИЦИЮ' });
    expect(action).toBeVisible();
    // The empty state carries no copy of its own: the metrics and the action
    // say everything it needs to. The payout warning is not dropped, it lives
    // where the user actually commits money — see the multiplier step below.
    expect(screen.queryByRole('heading', { name: /очередь/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/не гарантирована/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('bank-sand-level')).not.toBeInTheDocument();
  });

  it('shows on-chain progress and explains the target', () => {
    render(
      <BankScreen
        profile={profile}
        position={position}
        pulse={{ active_participants: 8, active_bank: 5, active_duels: 3, proofs_24h: 4 }}
        onRefresh={vi.fn()}
        onMockCreated={vi.fn()}
      />,
    );

    // Under the jar the percent stands alone: the amounts, the status and the
    // payout promise all said what the number already says.
    expect(screen.getByText('37%')).toBeVisible();
    expect(screen.queryByText(/Собрано/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Позиция ждёт новых взносов/)).not.toBeInTheDocument();
    expect(screen.queryByText(/выплата отправится автоматически/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /собрано 37%/i }));
    expect(screen.getByText(/Первым в неё попадает остаток твоего взноса/i)).toBeInTheDocument();
    // The row names whose money it is: at the start it is the depositor's own.
    expect(screen.getByText('Собрано, включая твой взнос')).toBeInTheDocument();
    expect(screen.getByText('Осталось собрать')).toBeInTheDocument();
    expect(screen.getAllByText('#2').length).toBeGreaterThan(0);
  });
});
