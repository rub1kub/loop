import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DuelScreen } from '../features/duel/DuelScreen';
import type { Duel, Invite, Offer, Profile } from '../types';

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
    result_notifications_enabled: true,
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
  app_open: true,
  launch_at: null,
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

const walletOf = (address: string): Profile['wallet'] => ({
  address,
  network: -3,
  verified_at: '2026-07-01T00:00:00.000Z',
});

const settledDuel = (overrides: Partial<Duel>): Duel => ({
  id: 'settled-duel',
  onchain_duel_id: 900,
  state: 'settled',
  offer_id: 901,
  own_revealed: true,
  chance_bps: 5_000,
  stake_nano: 1_000_000_000,
  opponent_stake_nano: 1_000_000_000,
  total_pool_nano: 2_000_000_000,
  fee_exempt: false,
  payout_nano: 1_950_000_000,
  boost_deadline: null,
  hard_deadline: null,
  boost_revision: 0,
  reveal_deadline: '2026-07-01T00:00:00.000Z',
  boost_events: [],
  winner_wallet: null,
  settled_tx_hash: 'settled',
  settlement_proof_url: null,
  ...overrides,
});

describe('DuelScreen', () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

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
    expect(screen.getByText('РАВНЫЙ СТАРТ')).toBeInTheDocument();
    expect(screen.getByLabelText('Ставка в GRAM')).toBeInTheDocument();
    expect(screen.getByText('ВВЕДИ СУММУ')).toBeInTheDocument();
    expect(screen.getByText(/Соперник внесёт столько же/)).toBeVisible();
    expect(screen.getByText('ПРАВИЛА').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('ПРАВИЛА').closest('summary')).toHaveTextContent('ОТКРЫТЬ');
    expect(screen.getByText('Комиссия')).not.toBeVisible();
    expect(screen.getByText(/Открыл один — он выигрывает/)).not.toBeVisible();
    expect(screen.queryByText(/Можно закрыть приложение/)).not.toBeInTheDocument();
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
    expect(screen.getByText('1 GRAM')).toBeInTheDocument();
    expect(screen.getByText('ТВОЯ СТАВКА')).toBeInTheDocument();
    fireEvent.click(screen.getByText('ПРАВИЛА'));
    expect(screen.getByText('1,95 GRAM')).toBeVisible();
    expect(screen.getByText('Комиссия')).toBeVisible();
    expect(screen.queryByLabelText('Ставка в GRAM')).not.toBeInTheDocument();
  });

  it('shows only confirmed live chance and a clear boost input during the boost window', () => {
    const offer: Offer = {
      id: 'offer',
      onchain_offer_id: 701,
      chance_bps: 5_000,
      total_pool_nano: 2_000_000_000,
      stake_nano: 1_000_000_000,
      opponent_stake_nano: 1_000_000_000,
      fee_bps: 250,
      fee_exempt: false,
      payout_nano: 1_950_000_000,
      net_profit_nano: 950_000_000,
      mode: 'afk',
      direct_opponent_wallet: null,
      state: 'matched',
      expires_at: new Date(Date.now() + 600_000).toISOString(),
      funding_tx_hash: 'funding',
      funding_proof_url: null,
    };
    const duel: Duel = {
      id: 'duel',
      onchain_duel_id: 702,
      state: 'boosting',
      offer_id: 701,
      own_revealed: false,
      chance_bps: 5_000,
      stake_nano: 1_000_000_000,
      opponent_stake_nano: 1_000_000_000,
      total_pool_nano: 2_000_000_000,
      fee_exempt: false,
      payout_nano: 1_950_000_000,
      boost_deadline: new Date(Date.now() + 60_000).toISOString(),
      hard_deadline: new Date(Date.now() + 180_000).toISOString(),
      boost_revision: 0,
      reveal_deadline: new Date(Date.now() + 360_000).toISOString(),
      boost_events: [],
      winner_wallet: null,
      settled_tx_hash: null,
      settlement_proof_url: null,
    };
    const { rerender } = render(
      <DuelScreen
        profile={profile}
        offers={[offer]}
        duels={[duel]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText('50 / 50')).toBeVisible();
    expect(screen.getByText('ДО КОНЦА СТАВОК')).toBeVisible();
    expect(screen.queryByLabelText('Сумма усиления в GRAM')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'УВЕЛИЧИТЬ ШАНС' }));

    expect(screen.getByLabelText('Сумма усиления в GRAM')).toHaveValue('0.5');
    expect(screen.getByText('Твоя доля станет')).toHaveTextContent('60,0%');
    expect(screen.getByRole('button', { name: 'ДОБАВИТЬ GRAM' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'НЕ СЕЙЧАС' }));
    expect(screen.queryByLabelText('Сумма усиления в GRAM')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'ОТКРЫТЬ РЕЗУЛЬТАТ' })).not.toBeInTheDocument();

    rerender(
      <DuelScreen
        profile={profile}
        offers={[offer]}
        duels={[
          {
            ...duel,
            state: 'revealing',
            boost_deadline: new Date(Date.now() - 1_000).toISOString(),
          },
        ]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'УВЕЛИЧИТЬ ШАНС' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'ОТКРЫТЬ РЕЗУЛЬТАТ' })).toHaveClass('primary-button');
  });

  it('marks a failure as a failure instead of stamping it with a verified shield', () => {
    render(
      <DuelScreen profile={profile} offers={[]} duels={[]} invite={null} onRefresh={vi.fn()} />,
    );

    fireEvent.change(screen.getByLabelText('Ставка в GRAM'), { target: { value: '0.1' } });
    fireEvent.click(screen.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' }));

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Минимальная ставка — 0,5 GRAM');
    expect(alert).toHaveClass('is-error');
  });

  it('names a loss and never shows the winner-if-won payout as the outcome', () => {
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:bbb' })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'ПОРАЖЕНИЕ' })).toBeVisible();
    expect(screen.getByText('−1 GRAM')).toBeVisible();
    expect(screen.getByText(/Ставка 1 GRAM ушла сопернику/)).toBeVisible();
    expect(screen.queryByText(/1,95/)).not.toBeInTheDocument();
    expect(screen.queryByText('ЗАВЕРШЕНО')).not.toBeInTheDocument();
  });

  it('states the win as net gain and what actually reached the wallet', () => {
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:aaa' })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'ПОБЕДА' })).toBeVisible();
    expect(screen.getByText('+0,95 GRAM')).toBeVisible();
    expect(screen.getByText(/В кошелёк пришло 1,95 GRAM/)).toBeVisible();
  });

  it('lets a settled result be closed so another duel can be opened', () => {
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:bbb' })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText('Ставка в GRAM')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'ЗАКРЫТЬ' }));

    expect(screen.queryByRole('heading', { name: 'ПОРАЖЕНИЕ' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Ставка в GRAM')).toBeVisible();
    expect(screen.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' })).toBeVisible();
  });

  it('puts the proof first after a loss and the exit first after a win', () => {
    const proof = { settlement_proof_url: 'https://tonviewer.example/tx' };
    const { unmount } = render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:bbb', ...proof })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    const afterLoss = screen.getByRole('button', { name: 'ЗАКРЫТЬ' }).parentElement!;
    expect(afterLoss.firstElementChild).toHaveTextContent('ПОСМОТРЕТЬ ОПЕРАЦИЮ');
    unmount();

    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:aaa', ...proof })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    const afterWin = screen.getByRole('button', { name: 'ЗАКРЫТЬ' }).parentElement!;
    expect(afterWin.firstElementChild).toHaveTextContent('ЗАКРЫТЬ');
  });

  it('resets the stake to the minimum after a loss instead of reloading it', () => {
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:bbb', stake_nano: 5_000_000_000 })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'ЗАКРЫТЬ' }));

    expect(screen.getByLabelText('Ставка в GRAM')).toHaveValue('0.5');
  });

  it('drops the waiting metaphor once the duel is settled', () => {
    const { container } = render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:aaa' })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(container.querySelector('.duel-stage')).toBeNull();
  });

  it('offers no rematch wording that pushes a losing player straight back in', () => {
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:bbb' })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.queryByText(/ЕЩЁ РАЗ|ОТЫГРАТЬСЯ|РЕВАНШ|СЫГРАТЬ СНОВА/i)).not.toBeInTheDocument();
  });
});
