import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DuelScreen } from '../features/duel/DuelScreen';
import type { Duel, Invite, Offer, Profile } from '../types';

const tonConnect = vi.hoisted(() => ({
  openModal: vi.fn(() => new Promise<void>(() => undefined)),
  sendTransaction: vi.fn(),
}));

const walletState = vi.hoisted(() => ({
  current: null as null | {
    account: { address: string; chain: string };
  },
}));

const apiMocks = vi.hoisted(() => ({
  contractState: vi.fn(() => Promise.resolve({ paused: false })),
  discardOffer: vi.fn(() => Promise.resolve(undefined)),
  quoteOffer: vi.fn(),
}));

vi.mock('../api', () => ({ api: apiMocks }));

vi.mock('@tonconnect/ui-react', () => ({
  useTonConnectUI: () => [tonConnect],
  useTonWallet: () => walletState.current,
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
  duel_stake: { min_stake_nano: 500000000, max_stake_nano: 500000000 },
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
    walletState.current = null;
    apiMocks.contractState.mockResolvedValue({ paused: false });
    apiMocks.quoteOffer.mockClear();
    tonConnect.openModal.mockClear();
    tonConnect.sendTransaction.mockClear();
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

  it('does not prepare a DUEL for a wallet restored from another browser session', async () => {
    walletState.current = {
      account: { address: `0:${'22'.repeat(32)}`, chain: '-3' },
    };
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf(`0:${'11'.repeat(32)}`) }}
        offers={[]}
        duels={[]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' }));

    expect(
      await screen.findByText(
        'В TON Connect выбран другой кошелёк. Подключи кошелёк из профиля заново.',
      ),
    ).toBeVisible();
    expect(apiMocks.quoteOffer).not.toHaveBeenCalled();
    expect(tonConnect.sendTransaction).not.toHaveBeenCalled();
  });

  it('presents one equal 50/50 rule without probability controls', () => {
    render(
      <DuelScreen profile={profile} offers={[]} duels={[]} invite={null} onRefresh={vi.fn()} />,
    );

    // Равный старт теперь показывает сама шкала, а не подпись под ней.
    expect(screen.getByRole('img', { name: 'Твой шанс 50 процентов' })).toBeInTheDocument();
    expect(screen.queryByText('РАВНЫЙ СТАРТ')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Ставка в GRAM')).toBeInTheDocument();
    expect(screen.queryByText('ВВЕДИ СУММУ')).not.toBeInTheDocument();
    expect(screen.getByText(/Соперник внесёт столько же/)).toBeVisible();
    expect(screen.getByText('ПРАВИЛА').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('ПРАВИЛА').closest('summary')).toHaveTextContent('ОТКРЫТЬ');
    expect(screen.getByText(/^Комиссия /)).not.toBeVisible();
    expect(screen.getByText(/Открыл только один — он и выигрывает/)).not.toBeVisible();
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

    expect(screen.getByText(/ТЕБЯ ВЫЗЫВАЕТ МИША/)).toBeInTheDocument();
    // The rules card now names the stake too, so the banner is asserted on
    // directly rather than by a text that appears in both.
    expect(screen.getByText('ТВОЯ СТАВКА').previousElementSibling).toHaveTextContent('1 GRAM');
    fireEvent.click(screen.getByText('ПРАВИЛА'));
    expect(screen.getByText('1,95 GRAM')).toBeVisible();
    expect(screen.getByText(/^Комиссия /)).toBeVisible();
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

    expect(screen.getByRole('img', { name: 'Твой шанс 50 процентов' })).toBeVisible();
    expect(screen.getByText('ДО КОНЦА СТАВОК')).toBeVisible();
    expect(screen.queryByLabelText('Сумма усиления в GRAM')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'УВЕЛИЧИТЬ ШАНС' }));

    expect(screen.getByLabelText('Сумма усиления в GRAM')).toHaveValue('0.5');
    expect(screen.getByText('Станет').nextElementSibling).toHaveTextContent('60,0%');
    expect(screen.getByRole('button', { name: /^ДОБАВИТЬ / })).toBeInTheDocument();
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

    // The launch cap pins both ends together, so the refusal names the one
    // amount that works instead of only the floor.
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Сейчас ставка — ровно 0,5 GRAM');
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

    expect(screen.getByRole('img', { name: 'Поражение: банк ушёл сопернику' })).toBeVisible();
    expect(screen.getByText('ПОРАЖЕНИЕ')).toBeVisible();
    expect(screen.getByText('−1 GRAM')).toBeVisible();
    expect(screen.getByText('Ушло сопернику').nextElementSibling).toHaveTextContent('1 GRAM');
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

    expect(screen.getByRole('img', { name: 'Победа: банк твой' })).toBeVisible();
    expect(screen.getByText('ПОБЕДА')).toBeVisible();
    expect(screen.getByText('+0,95 GRAM')).toBeVisible();
    expect(screen.getByText('Пришло в кошелёк').nextElementSibling).toHaveTextContent('1,95 GRAM');
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
    fireEvent.click(screen.getByRole('button', { name: /ИГРАТЬ ЕЩЁ|ПОПРОБОВАТЬ СНОВА/ }));

    expect(screen.queryByText('ПОРАЖЕНИЕ')).not.toBeInTheDocument();
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

    const afterLoss = screen.getByRole('button', {
      name: /ИГРАТЬ ЕЩЁ|ПОПРОБОВАТЬ СНОВА/,
    }).parentElement!;
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

    const afterWin = screen.getByRole('button', {
      name: /ИГРАТЬ ЕЩЁ|ПОПРОБОВАТЬ СНОВА/,
    }).parentElement!;
    // After a win the way onward comes first; the proof stays available below it.
    expect(afterWin.firstElementChild).toHaveTextContent('ИГРАТЬ ЕЩЁ');
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

    fireEvent.click(screen.getByRole('button', { name: /ИГРАТЬ ЕЩЁ|ПОПРОБОВАТЬ СНОВА/ }));

    expect(screen.getByLabelText('Ставка в GRAM')).toHaveValue('0,5');
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

  it('calls an unsigned quote a pending signature rather than a search', () => {
    // The quote holds the wallet's slot before the wallet has answered. Calling
    // that "ИЩЕМ СОПЕРНИКА" told the player a duel existed when none did.
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[
          {
            id: 'quote',
            onchain_offer_id: 900,
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
            state: 'pending_funding',
            expires_at: new Date(Date.now() + 900_000).toISOString(),
            funding_tx_hash: null,
            funding_proof_url: null,
          },
        ]}
        duels={[]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText('ЖДЁМ ПОДПИСЬ В КОШЕЛЬКЕ')).toBeVisible();
    expect(screen.queryByText('ИЩЕМ СОПЕРНИКА')).not.toBeInTheDocument();
  });

  it('shows a closed DUEL as closed instead of taking a stake for it', async () => {
    // A paused contract rejects every deposit and bounces the stake back minus
    // gas. The screen used to accept a stake, open the wallet and let the
    // player sign a transaction that could only fail.
    apiMocks.contractState.mockResolvedValue({ paused: true });
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText(/DUEL сейчас закрыт/)).toBeVisible());
    expect(screen.queryByRole('button', { name: 'НАЙТИ СОПЕРНИКА' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Ставка в GRAM')).not.toBeInTheDocument();
  });
});
