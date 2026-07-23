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

  it('keeps the empty BANK focused after the one-time onboarding', () => {
    render(
      <BankScreen
        profile={profile}
        position={null}
        pulse={null}
        onRefresh={vi.fn()}
        onMockCreated={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Твоя очередь начинается здесь.' })).toBeVisible();
    expect(screen.queryByText(/Следующие вклады сначала наполняют ранние банки/)).toBeNull();
    expect(screen.queryByText(/Досрочной отмены и возврата нет/)).toBeNull();
    expect(screen.getByRole('button', { name: 'НАЧАТЬ ЦИКЛ' })).toBeVisible();
    expect(screen.queryByTestId('bank-sand-level')).not.toBeInTheDocument();
  });

  it('maps on-chain progress to the live sand level and explains the target', () => {
    render(
      <BankScreen
        profile={profile}
        position={position}
        pulse={{ active_participants: 8, active_bank: 5, active_duels: 3, proofs_24h: 4 }}
        onRefresh={vi.fn()}
        onMockCreated={vi.fn()}
      />,
    );

    expect(screen.getByText('37%')).toBeVisible();
    expect(screen.getByText(/Собрано 1[,.]11 из 3 GRAM/)).toBeVisible();
    expect(screen.getByTestId('bank-sand-level').style.getPropertyValue('--bank-fill')).toBe('37%');

    fireEvent.click(screen.getByRole('button', { name: /собрано 37 процентов/i }));
    expect(
      screen.getByText(/сколько следующие вклады уже собрали до твоей целевой выплаты/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Уже собрано')).toBeInTheDocument();
    expect(screen.getByText('Осталось собрать')).toBeInTheDocument();
    expect(screen.getAllByText('#2').length).toBeGreaterThan(0);
  });
});
