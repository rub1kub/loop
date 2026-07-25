import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DuelScreen } from '../features/duel/DuelScreen';
import type { Invite, Profile } from '../types';

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

const invite: Invite = {
  code: 'direct-duel',
  creator_name: 'Миша',
  creator_username: 'misha',
  stake_nano: 1_000_000_000,
  total_pool_nano: 2_000_000_000,
  chance_bps: 5000,
  payout_nano: 1_950_000_000,
  net_profit_nano: 950_000_000,
  counter_offer_id: 7001,
  expires_at: '2026-07-23T21:00:00.000Z',
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
    expect(screen.getByLabelText('Ставка в GRAM')).toBeInTheDocument();
    expect(screen.getByText('ВВЕДИ СУММУ')).toBeInTheDocument();
    expect(screen.getByText('Ставки')).toBeInTheDocument();
    expect(screen.getByText('1 + 1 GRAM')).toBeInTheDocument();
    expect(screen.getByText('Победитель получит')).toBeInTheDocument();
    expect(screen.getByText('0,05 GRAM')).toBeInTheDocument();
    expect(screen.getByText(/Оба открыли числа — исход 50\/50/)).toBeVisible();
    expect(screen.getByText(/Открыл только один за 5 минут — он победил/)).toBeVisible();
    expect(screen.getByText('ВОЗВРАТ И ПРАВИЛА').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('ВОЗВРАТ И ПРАВИЛА').closest('summary')).toHaveTextContent('ОТКРЫТЬ');
    expect(screen.queryByText('Твоя ставка')).not.toBeInTheDocument();
    expect(screen.queryByText(/После ставки изменить тайное число нельзя/)).not.toBeVisible();
    expect(screen.getByRole('button', { name: /ВЫЗВАТЬ ДРУГА/ })).toBeInTheDocument();
    expect(screen.queryByText(/Одинаковая ставка/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /25%/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /75%/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/позиция BANK/i)).not.toBeInTheDocument();
  });

  it('shows the complete cost before an incoming invite is accepted', () => {
    render(
      <DuelScreen profile={profile} offers={[]} duels={[]} invite={invite} onRefresh={vi.fn()} />,
    );

    expect(screen.getByText(/ВЫЗОВ ОТ МИША/)).toBeInTheDocument();
    expect(screen.getByText('1 + 1 GRAM')).toBeInTheDocument();
    expect(screen.getByText('0,05 GRAM')).toBeInTheDocument();
    expect(screen.queryByLabelText('Ставка в GRAM')).not.toBeInTheDocument();
  });
});
