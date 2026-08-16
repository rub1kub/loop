import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { BankScreen } from '../features/bank/BankScreen';
import type { BankPosition, BankQueuePulse, Profile } from '../types';

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
  announcement: null,
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
  queue_progress_bps: 0,
  queue_ahead: 0,
  queue_ahead_nano: 0,
  queue_eta_seconds: null,
  current_status: 'partially_funded',
  funding_transaction: 'test-transaction',
  payout_transaction: null,
  proof_url: null,
  created_at: '2026-07-22T00:00:00.000Z',
  completed_at: null,
};

const queuePulse: BankQueuePulse = {
  active_positions: 124,
  minimum_entry_nano: 1_000_000_000,
  minimum_entry_payouts: 2,
  next_payout_gross_nano: 288_888_889,
  updated_at: '2026-08-10T12:00:00.000Z',
  wave: null,
};

describe('BankScreen', () => {
  afterEach(cleanup);

  it('keeps the empty state concise before the user creates a position', () => {
    render(
      <BankScreen
        profile={profile}
        position={null}
        queuePulse={queuePulse}
        pulse={null}
        onRefresh={vi.fn()}
        onMockCreated={vi.fn()}
      />,
    );

    const action = screen.getByRole('button', { name: 'СОЗДАТЬ ПОЗИЦИЮ' });
    expect(action).toBeVisible();
    expect(screen.getByText('Следующий вход закроет 2 позиции')).toBeVisible();
    // The payout warning is not dropped, it lives where the user actually
    // commits money — see the multiplier step below.
    expect(screen.queryByRole('heading', { name: /очередь/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/не гарантирована/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('bank-sand-level')).not.toBeInTheDocument();
  });

  it('shows on-chain progress and explains the target', () => {
    render(
      <BankScreen
        profile={profile}
        position={position}
        queuePulse={queuePulse}
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

  it('does not show the nearest-payout amount in BANK', () => {
    render(
      <BankScreen
        profile={profile}
        position={position}
        queuePulse={{
          ...queuePulse,
          minimum_entry_payouts: 0,
          next_payout_gross_nano: 4_389_000_000,
        }}
        pulse={null}
        onRefresh={vi.fn()}
        onMockCreated={vi.fn()}
      />,
    );

    expect(screen.queryByText(/до ближайшей выплаты/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/4[,.]389\s*GRAM/i)).not.toBeInTheDocument();
  });

  it('keeps Wave compact until the user opens its rules', () => {
    render(
      <BankScreen
        profile={profile}
        position={null}
        queuePulse={{
          ...queuePulse,
          wave: {
            id: '2026-08-16',
            state: 'active',
            starts_at: '2026-08-16T17:00:00Z',
            ends_at: '2026-08-16T17:30:00Z',
            participants: 6,
            goal: 8,
            boost_nano: 5_000_000_000,
            boost_confirmed: false,
            proof_url: null,
            closer_name: null,
            closer_username: null,
            is_closer: false,
          },
        }}
        pulse={null}
        onRefresh={vi.fn()}
        onMockCreated={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: /ПОСЛЕДНИЙ ХОД · ЖДЁМ ПЕРВЫЙ ВЗНОС/i }),
    ).toBeVisible();
    expect(screen.queryByText(/15 GRAM за последний ход/i)).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: /ПОСЛЕДНИЙ ХОД · ЖДЁМ ПЕРВЫЙ ВЗНОС/i }),
    );
    expect(screen.getByText(/15 GRAM за последний ход/i)).toBeInTheDocument();
    expect(screen.getByText(/Каждый новый взнос запускает 30 минут заново/i)).toBeInTheDocument();
    expect(screen.getByText(/До 20:30 должны войти 8 разных участников/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'УЧАСТВОВАТЬ' })).toBeInTheDocument();
  });

  it('does not advertise the one-off prize in later Waves', () => {
    render(
      <BankScreen
        profile={profile}
        position={null}
        queuePulse={{
          ...queuePulse,
          wave: {
            id: '2026-08-23',
            state: 'upcoming',
            starts_at: '2026-08-23T17:00:00Z',
            ends_at: '2026-08-23T17:30:00Z',
            participants: 0,
            goal: 8,
            boost_nano: 5_000_000_000,
            boost_confirmed: false,
            proof_url: null,
            closer_name: null,
            closer_username: null,
            is_closer: false,
          },
        }}
        pulse={null}
        onRefresh={vi.fn()}
        onMockCreated={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /ВОЛНА · ВС 20:00 · \+5 GRAM/i })).toBeVisible();
    expect(screen.queryByText(/15 GRAM/i)).not.toBeInTheDocument();
  });
});
