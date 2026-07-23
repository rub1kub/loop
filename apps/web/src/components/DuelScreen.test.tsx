import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DuelScreen } from '../features/duel/DuelScreen';
import type { Profile } from '../types';

const tonConnect = vi.hoisted(() => ({
  openModal: vi.fn(() => new Promise<void>(() => undefined)),
}));

vi.mock('@tonconnect/ui-react', () => ({
  useTonConnectUI: () => [tonConnect],
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

describe('DuelScreen', () => {
  afterEach(cleanup);

  beforeEach(() => {
    tonConnect.openModal.mockClear();
  });

  it('locks the opponent action while the wallet flow is opening', () => {
    render(
      <DuelScreen profile={profile} offers={[]} duels={[]} invite={null} onRefresh={vi.fn()} />,
    );

    const action = screen.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' });
    fireEvent.click(action);
    fireEvent.click(action);

    expect(tonConnect.openModal).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'ГОТОВИМ…' })).toBeDisabled();
  });

  it('presents one equal 50/50 rule without probability controls', () => {
    render(
      <DuelScreen profile={profile} offers={[]} duels={[]} invite={null} onRefresh={vi.fn()} />,
    );

    expect(screen.getByText('50/50')).toBeInTheDocument();
    expect(screen.getByText('РАВНЫЕ УСЛОВИЯ')).toBeInTheDocument();
    expect(screen.getByText(/открой результат за 5 минут/i)).toBeInTheDocument();
    expect(screen.getByText('Выплата победителю')).toBeInTheDocument();
    expect(screen.getByText('РАСЧЁТ И ПРАВИЛА').closest('details')).not.toHaveAttribute('open');
    expect(screen.queryByRole('button', { name: /25%/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /75%/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/позиция BANK/i)).not.toBeInTheDocument();
  });
});
