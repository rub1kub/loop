import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DuelScreen } from '../features/duel/DuelScreen';
import { COMMITMENT_DOMAIN } from '../ton';
import type { Duel, Invite, Offer, Profile } from '../types';

type ContractStateMock = {
  paused: boolean;
  network?: number;
  address?: string;
  status?: string;
  code_hash_matches?: boolean;
};

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
  contractState: vi.fn<() => Promise<ContractStateMock>>(() => Promise.resolve({ paused: false })),
  discardOffer: vi.fn(() => Promise.resolve(undefined)),
  expireOfferIntent: vi.fn(),
  revealIntent: vi.fn(),
  expireDuelIntent: vi.fn(),
  quoteOffer: vi.fn(),
  duelChallengePreview: vi.fn(() =>
    Promise.resolve({
      creator_first_name: 'Иван',
      creator_username: 'ivan_loop',
      stake_nano: 1_000_000_000,
      receiver_chance_bps: 5000,
      open: true,
    }),
  ),
  meAvatar: vi.fn(() => Promise.resolve(null)),
  opponentAvatar: vi.fn(() => Promise.resolve(null)),
  matchOfferIntent: vi.fn<(offerId: number) => Promise<unknown>>(() =>
    Promise.reject(new Error('Соперника пока нет')),
  ),
  prepareDuelShare: vi.fn(() =>
    Promise.resolve({
      prepared_message_id: 'prepared-811',
      expiration_date: new Date(Date.now() + 86_400_000).toISOString(),
      fallback_query: 'duel 811',
    }),
  ),
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
  announcement: null,
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
  opponent_first_name: null,
  opponent_username: null,
  opponent_has_photo: false,
  settled_tx_hash: 'settled',
  settlement_proof_url: null,
  ...overrides,
});

const matchedOffer = (): Offer => ({
  id: 'matched-offer',
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
});

const liveDuel = (overrides: Partial<Duel> = {}): Duel => ({
  id: 'live-duel',
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
  opponent_first_name: null,
  opponent_username: null,
  opponent_has_photo: false,
  settled_tx_hash: null,
  settlement_proof_url: null,
  ...overrides,
});

describe('DuelScreen', () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    window.Telegram = undefined;
  });

  beforeEach(() => {
    walletState.current = null;
    apiMocks.contractState.mockResolvedValue({ paused: false });
    apiMocks.expireOfferIntent.mockReset();
    apiMocks.revealIntent.mockReset();
    apiMocks.expireDuelIntent.mockReset();
    apiMocks.quoteOffer.mockReset();
    apiMocks.opponentAvatar.mockClear();
    apiMocks.prepareDuelShare.mockClear();
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
    ).toBeInTheDocument();
    expect(apiMocks.quoteOffer).not.toHaveBeenCalled();
    expect(tonConnect.sendTransaction).not.toHaveBeenCalled();
  });

  it('polls the chain projection and unlocks invitation after funding', async () => {
    const walletAddress = `0:${'11'.repeat(32)}`;
    const contractAddress = `0:${'22'.repeat(32)}`;
    walletState.current = {
      account: { address: walletAddress, chain: '-3' },
    };
    apiMocks.contractState.mockResolvedValue({
      network: -3,
      address: contractAddress,
      status: 'active',
      code_hash_matches: true,
      paused: false,
    });

    let projectedOffer: Offer | null = null;
    let refreshCount = 0;
    apiMocks.quoteOffer.mockImplementation(
      (request: { offer_id: number; commitment_hex: string }) => {
        projectedOffer = {
          id: 'offer',
          onchain_offer_id: request.offer_id,
          chance_bps: 5_000,
          total_pool_nano: 1_000_000_000,
          stake_nano: 500_000_000,
          opponent_stake_nano: 500_000_000,
          fee_bps: 250,
          fee_exempt: false,
          payout_nano: 975_000_000,
          net_profit_nano: 475_000_000,
          mode: 'afk',
          direct_opponent_wallet: null,
          state: 'pending_funding',
          expires_at: new Date(Date.now() + 900_000).toISOString(),
          funding_tx_hash: null,
          funding_proof_url: null,
        };
        return Promise.resolve({
          offer: projectedOffer,
          transaction: {
            operation: 'open_offer',
            query_id: request.offer_id,
            offer_id: request.offer_id,
            counter_offer_id: 0,
            contract_address: contractAddress,
            amount_nano: '550000000',
            valid_until: Math.floor(Date.now() / 1000) + 300,
            network: -3,
            chance_bps: 5_000,
            stake_nano: '500000000',
            opponent_stake_nano: '500000000',
            total_pool_nano: '1000000000',
            commitment_hex: request.commitment_hex,
            expires_at: Math.floor(Date.now() / 1000) + 900,
            commitment_domain: COMMITMENT_DOMAIN,
            fee_bps: 250,
            invite_id_hex: null,
            direct_counter_offer_id: 0,
            direct_valid_until: 0,
            direct_signature_hex: null,
            holder_fee_supported: false,
            holder_valid_until: 0,
            holder_signature_hex: null,
          },
        });
      },
    );
    tonConnect.sendTransaction.mockResolvedValue({ boc: 'signed-message' });

    function ConfirmedOffer() {
      const [offers, setOffers] = useState<Offer[]>([]);
      const onRefresh = () => {
        refreshCount += 1;
        if (projectedOffer) {
          setOffers([
            {
              ...projectedOffer,
              state: refreshCount >= 2 ? 'open' : 'pending_funding',
              funding_tx_hash: refreshCount >= 2 ? 'confirmed' : null,
              funding_proof_url:
                refreshCount >= 2 ? 'https://tonviewer.com/transaction/confirmed' : null,
            },
          ]);
        }
        return Promise.resolve();
      };
      return (
        <DuelScreen
          profile={{ ...profile, wallet: walletOf(walletAddress) }}
          offers={offers}
          duels={[]}
          invite={null}
          onRefresh={onRefresh}
        />
      );
    }
    render(<ConfirmedOffer />);

    fireEvent.click(screen.getByRole('button', { name: 'НАЙТИ СОПЕРНИКА' }));

    await waitFor(() => expect(refreshCount).toBeGreaterThanOrEqual(2), { timeout: 3_500 });
    expect(screen.getByText('ИЩЕМ СОПЕРНИКА')).toBeVisible();
    expect(screen.getByRole('button', { name: /Пригласить соперника/i })).toBeEnabled();
  });

  it('shows invitation as an action card while the stake reaches the contract', () => {
    const offer: Offer = {
      id: 'pending-offer',
      onchain_offer_id: 810,
      chance_bps: 5_000,
      total_pool_nano: 1_000_000_000,
      stake_nano: 500_000_000,
      opponent_stake_nano: 500_000_000,
      fee_bps: 250,
      fee_exempt: false,
      payout_nano: 975_000_000,
      net_profit_nano: 475_000_000,
      mode: 'afk',
      direct_opponent_wallet: null,
      state: 'pending_funding',
      expires_at: new Date(Date.now() + 900_000).toISOString(),
      funding_tx_hash: null,
      funding_proof_url: null,
    };
    const { rerender } = render(
      <DuelScreen
        profile={profile}
        offers={[offer]}
        duels={[]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    const pendingInvite = screen.getByRole('button', { name: /Пригласить соперника/i });
    expect(pendingInvite).toHaveClass('profile-row', 'duel-invite-card');
    expect(pendingInvite).toHaveTextContent('Станет доступно через несколько секунд');
    expect(pendingInvite).toBeDisabled();

    rerender(
      <DuelScreen
        profile={profile}
        offers={[{ ...offer, state: 'open', funding_tx_hash: 'confirmed' }]}
        duels={[]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    const readyInvite = screen.getByRole('button', { name: /Пригласить соперника/i });
    expect(readyInvite).toHaveTextContent('Позвать друга в DUEL');
    expect(readyInvite).toBeEnabled();
  });

  it('does not ask the wallet to return the same stake twice', async () => {
    const walletAddress = `0:${'11'.repeat(32)}`;
    walletState.current = { account: { address: walletAddress, chain: '-3' } };
    const offer: Offer = {
      id: 'expired-offer',
      onchain_offer_id: 812,
      chance_bps: 5_000,
      total_pool_nano: 1_000_000_000,
      stake_nano: 500_000_000,
      opponent_stake_nano: 500_000_000,
      fee_bps: 250,
      fee_exempt: false,
      payout_nano: 975_000_000,
      net_profit_nano: 475_000_000,
      mode: 'afk',
      direct_opponent_wallet: null,
      state: 'open',
      expires_at: new Date(Date.now() - 1_000).toISOString(),
      funding_tx_hash: 'funding',
      funding_proof_url: null,
    };
    apiMocks.expireOfferIntent.mockResolvedValue({
      operation: 'expire_offer',
      query_id: 813,
      offer_id: offer.onchain_offer_id,
      duel_id: 0,
      contract_address: `0:${'22'.repeat(32)}`,
      amount_nano: '30000000',
      valid_until: Math.floor(Date.now() / 1000) + 300,
      network: -3,
    });
    tonConnect.sendTransaction.mockResolvedValue({ boc: 'return-request' });
    const onRefresh = vi.fn(() => Promise.resolve());
    const { unmount } = render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf(walletAddress) }}
        offers={[offer]}
        duels={[]}
        invite={null}
        onRefresh={onRefresh}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'ВЕРНУТЬ СТАВКУ' }));

    const pending = await screen.findByRole('button', { name: 'ВОЗВРАЩАЕМ…' });
    expect(pending).toBeDisabled();
    fireEvent.click(pending);
    expect(tonConnect.sendTransaction).toHaveBeenCalledOnce();

    unmount();
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf(walletAddress) }}
        offers={[offer]}
        duels={[]}
        invite={null}
        onRefresh={onRefresh}
      />,
    );
    expect(screen.getByRole('button', { name: 'ВОЗВРАЩАЕМ…' })).toBeDisabled();
    expect(tonConnect.sendTransaction).toHaveBeenCalledOnce();
  });

  it('sends a ready-made challenge card instead of dropping out of the app', async () => {
    // The old button either left the app with `duel 811` showing in the input
    // or sent a bare link carrying no stake, no odds and no button. Now the
    // server prepares the card and Telegram opens a picker over the app.
    const openTelegramLink = vi.fn();
    window.Telegram = { WebApp: { openTelegramLink } } as unknown as typeof window.Telegram;
    const offer: Offer = {
      id: 'open-offer',
      onchain_offer_id: 811,
      chance_bps: 5_000,
      total_pool_nano: 1_000_000_000,
      stake_nano: 500_000_000,
      opponent_stake_nano: 500_000_000,
      fee_bps: 250,
      fee_exempt: false,
      payout_nano: 975_000_000,
      net_profit_nano: 475_000_000,
      mode: 'afk',
      direct_opponent_wallet: null,
      state: 'open',
      expires_at: new Date(Date.now() + 900_000).toISOString(),
      funding_tx_hash: 'funding',
      funding_proof_url: 'https://tonviewer.com/transaction/funding',
    };
    const { rerender } = render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf(`0:${'11'.repeat(32)}`) }}
        offers={[offer]}
        duels={[]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Пригласить соперника/i }));

    await waitFor(() => expect(apiMocks.prepareDuelShare).toHaveBeenCalledWith(811));
    // Nothing is sent by hand any more, and the app is not left behind.
    expect(openTelegramLink).not.toHaveBeenCalled();

    apiMocks.prepareDuelShare.mockClear();
    rerender(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf(`0:${'11'.repeat(32)}`) }}
        offers={[{ ...offer, state: 'reserved' }]}
        duels={[]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );
    const returnedInvite = screen.getByRole('button', { name: /Пригласить соперника/i });
    expect(returnedInvite).toBeEnabled();
    fireEvent.click(returnedInvite);
    await waitFor(() => expect(apiMocks.prepareDuelShare).toHaveBeenCalledWith(811));
  });

  it('does not show the previous opponent while a new search is empty', () => {
    localStorage.setItem('loop-duel-seen', 'old-duel');
    const openOffer: Offer = {
      ...matchedOffer(),
      id: 'new-search',
      onchain_offer_id: 812,
      state: 'open',
    };

    render(
      <DuelScreen
        profile={profile}
        offers={[openOffer]}
        duels={[settledDuel({ id: 'old-duel', onchain_duel_id: 702 })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText('ИЩЕМ СОПЕРНИКА')).toBeVisible();
    expect(apiMocks.opponentAvatar).not.toHaveBeenCalled();
    expect(document.querySelectorAll('.duel-orbit-player')[1]?.querySelector('img')).toBeNull();
  });

  it('presents one equal 50/50 rule without probability controls', () => {
    render(
      <DuelScreen profile={profile} offers={[]} duels={[]} invite={null} onRefresh={vi.fn()} />,
    );

    // Равный старт теперь показывает сама шкала, а не подпись под ней.
    expect(screen.getByRole('img', { name: 'Твой шанс 50 процентов' })).toHaveClass(
      'duel-orbit',
      'is-setup',
    );
    expect(document.querySelector('.chance-bar')).not.toBeInTheDocument();
    expect(screen.queryByText('РАВНЫЙ СТАРТ')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Ставка в GRAM')).toBeInTheDocument();
    expect(screen.queryByText('ВВЕДИ СУММУ')).not.toBeInTheDocument();
    expect(screen.getByText(/Соперник внесёт столько же/)).toBeVisible();
    expect(screen.getByText('ПРАВИЛА').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('ПРАВИЛА').closest('summary')).toHaveTextContent('ОТКРЫТЬ');
    expect(screen.getByText(/^Комиссия /)).not.toBeVisible();
    expect(screen.getByText(/Открыл только один — он и выигрывает/)).not.toBeVisible();
    expect(screen.queryByText(/Можно закрыть приложение/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ПРИГЛАСИТЬ СРАЗИТЬСЯ/ })).toBeInTheDocument();
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
      opponent_first_name: null,
      opponent_username: null,
      opponent_has_photo: false,
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

    expect(screen.getByRole('img', { name: 'Твой шанс 50 процентов' })).toHaveClass(
      'duel-orbit',
      'phase-boosting',
    );
    expect(screen.getByText('У каждого есть минута, чтобы изменить шансы')).toBeVisible();
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

  it('checks final boosts before opening reveal and explains the automatic outcome timer', () => {
    const offer = matchedOffer();
    const { rerender } = render(
      <DuelScreen
        profile={profile}
        offers={[offer]}
        duels={[liveDuel({ boost_deadline: new Date(Date.now() - 1_000).toISOString() })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText('ОПРЕДЕЛЯЕМ ПОБЕДИТЕЛЯ')).toBeVisible();
    expect(screen.getByRole('img', { name: 'Твой шанс 50 процентов' })).toHaveClass(
      'phase-waiting',
    );
    expect(screen.getByText('Сверяем последние ставки')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'ОТКРЫТЬ РЕЗУЛЬТАТ' })).not.toBeInTheDocument();

    rerender(
      <DuelScreen
        profile={profile}
        offers={[offer]}
        duels={[liveDuel({ boost_deadline: new Date(Date.now() - 13_000).toISOString() })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText('ОПРЕДЕЛЯЕМ ПОБЕДИТЕЛЯ')).toBeVisible();
    expect(screen.getByText(/ДО РЕЗУЛЬТАТА/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'ОТКРЫТЬ РЕЗУЛЬТАТ' })).toBeEnabled();
  });

  it('starts the result animation and automatically opens the reveal transaction', async () => {
    const walletAddress = `0:${'11'.repeat(32)}`;
    walletState.current = { account: { address: walletAddress, chain: '-3' } };
    localStorage.setItem('loop-duel-701', '11'.repeat(32));
    apiMocks.revealIntent.mockResolvedValue({
      operation: 'reveal',
      query_id: 1,
      offer_id: 701,
      duel_id: 702,
      counter_offer_id: 0,
      contract_address: `0:${'22'.repeat(32)}`,
      amount_nano: '30000000',
      valid_until: Math.floor(Date.now() / 1000) + 300,
      network: -3,
    });
    tonConnect.sendTransaction.mockResolvedValue({ boc: 'reveal' });

    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf(walletAddress) }}
        offers={[matchedOffer()]}
        duels={[
          liveDuel({
            state: 'revealing',
            boost_deadline: new Date(Date.now() - 60_000).toISOString(),
          }),
        ]}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
      />,
    );

    expect(screen.getByRole('img', { name: 'Твой шанс 50 процентов' })).toHaveClass(
      'phase-waiting',
    );
    await waitFor(() => expect(apiMocks.revealIntent).toHaveBeenCalledWith(702), {
      timeout: 2_000,
    });
    expect(tonConnect.sendTransaction).toHaveBeenCalledOnce();
    expect(await screen.findByRole('button', { name: 'ОТКРЫВАЕМ…' })).toBeDisabled();
  });

  it('automatically finishes an expired reveal window', async () => {
    const walletAddress = `0:${'11'.repeat(32)}`;
    walletState.current = { account: { address: walletAddress, chain: '-3' } };
    apiMocks.expireDuelIntent.mockResolvedValue({
      operation: 'expire_duel',
      query_id: 2,
      offer_id: 701,
      duel_id: 702,
      counter_offer_id: 0,
      contract_address: `0:${'22'.repeat(32)}`,
      amount_nano: '30000000',
      valid_until: Math.floor(Date.now() / 1000) + 300,
      network: -3,
    });
    tonConnect.sendTransaction.mockResolvedValue({ boc: 'expire' });

    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf(walletAddress) }}
        offers={[matchedOffer()]}
        duels={[
          liveDuel({
            state: 'revealing',
            own_revealed: true,
            boost_deadline: new Date(Date.now() - 60_000).toISOString(),
            reveal_deadline: new Date(Date.now() - 1_000).toISOString(),
          }),
        ]}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
      />,
    );

    expect(screen.getByText('Время вышло. Завершаем дуэль')).toBeVisible();
    await waitFor(() => expect(apiMocks.expireDuelIntent).toHaveBeenCalledWith(702), {
      timeout: 2_000,
    });
    expect(tonConnect.sendTransaction).toHaveBeenCalledOnce();
    expect(await screen.findByRole('button', { name: 'ЗАВЕРШАЕМ…' })).toBeDisabled();
  });

  it('says what happens after this player has revealed', () => {
    render(
      <DuelScreen
        profile={profile}
        offers={[matchedOffer()]}
        duels={[
          liveDuel({
            state: 'revealing',
            own_revealed: true,
            boost_deadline: new Date(Date.now() - 60_000).toISOString(),
          }),
        ]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    // "Ход" здесь ни при чём: игрок не ходит, а открывает ставку, сделанную
    // при входе. Тестер прочитал «ждём ход противника» после отправки
    // транзакции и спросил, какой ход, если результат уже определён.
    expect(screen.getByText('ЖДЁМ ПОДТВЕРЖДЕНИЯ СОПЕРНИКА')).toBeVisible();
    expect(screen.getByText(/ДО РЕЗУЛЬТАТА/)).toBeVisible();
    expect(screen.queryByText('ЖДЁМ СОПЕРНИКА')).not.toBeInTheDocument();
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

    expect(screen.getByRole('img', { name: 'Результат дуэли: −1 GRAM' })).toBeVisible();
    expect(screen.getByText('−1 GRAM')).toBeVisible();
    expect(screen.getByText('СТАВКА УШЛА')).toBeVisible();
    expect(screen.getByText('ПОДРОБНОСТИ').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('Ушло сопернику').nextElementSibling).not.toBeVisible();
    fireEvent.click(screen.getByText('ПОДРОБНОСТИ'));
    expect(screen.getByText('Ушло сопернику').nextElementSibling).toHaveTextContent('1 GRAM');
    expect(screen.queryByText(/1,95/)).not.toBeInTheDocument();
    expect(screen.queryByText('ЗАВЕРШЕНО')).not.toBeInTheDocument();
  });

  it('states a win once as the amount that actually reached the wallet', () => {
    const { container } = render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:aaa' })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole('img', { name: 'Результат дуэли: +1,95 GRAM' })).toBeVisible();
    expect(container.querySelector('.duel-orbit-needle')).not.toBeNull();
    expect(screen.getByText('ОПРЕДЕЛЯЕМ ПОБЕДИТЕЛЯ')).toBeVisible();
    expect(screen.getByText('+1,95 GRAM')).toBeVisible();
    expect(screen.getByText('ПРИШЛО В КОШЕЛЁК')).toBeVisible();
    expect(screen.queryByText('ПОБЕДА')).not.toBeInTheDocument();
    expect(screen.queryByText('РЕЗУЛЬТАТ ПОДТВЕРЖДЁН')).not.toBeInTheDocument();
    expect(screen.getByText('ПОДРОБНОСТИ').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('Пришло в кошелёк').nextElementSibling).not.toBeVisible();
    fireEvent.click(screen.getByText('ПОДРОБНОСТИ'));
    expect(screen.getByText('Пришло в кошелёк').nextElementSibling).toHaveTextContent('1,95 GRAM');
  });

  it('lets a settled result be closed so another duel can be opened', () => {
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[matchedOffer()]}
        duels={[settledDuel({ offer_id: 701, winner_wallet: '0:bbb' })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText('Ставка в GRAM')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /ИГРАТЬ ЕЩЁ|ПОПРОБОВАТЬ СНОВА/ }));

    expect(screen.queryByText('СТАВКА УШЛА')).not.toBeInTheDocument();
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

  it('names the loss once instead of repeating who took the bank', () => {
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[settledDuel({ winner_wallet: '0:bbb', opponent_username: 'vasya' })]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText('СТАВКА УШЛА')).toBeVisible();
    expect(screen.queryByText('БАНК ЗАБРАЛ @vasya')).not.toBeInTheDocument();
  });

  it('puts the shared challenge in front of the person who tapped it', async () => {
    // The card said "принять вызов"; landing on a bare search screen breaks
    // that promise three taps deep.
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[]}
        duels={[]}
        invite={null}
        challengeOfferId={811}
        onRefresh={vi.fn()}
      />,
    );

    expect(await screen.findByText(/ТЕБЯ ВЫЗЫВАЕТ @IVAN_LOOP/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'ПРИНЯТЬ ВЫЗОВ' })).toBeEnabled();
    expect(apiMocks.duelChallengePreview).toHaveBeenCalledWith(811);
  });

  it('offers the wedding button the moment a lonely complement appears', async () => {
    // Two parallel searches used to stare past each other for fifteen minutes.
    apiMocks.matchOfferIntent.mockImplementationOnce(() =>
      Promise.resolve({
        operation: 'match_offers' as const,
        query_id: 7,
        offer_id: 811,
        duel_id: 0,
        counter_offer_id: 812,
        contract_address: '0:' + '11'.repeat(32),
        amount_nano: '50000000',
        valid_until: Math.floor(Date.now() / 1000) + 300,
        network: -3,
      }),
    );
    const offer: Offer = {
      id: 'open-offer',
      onchain_offer_id: 811,
      chance_bps: 5_000,
      total_pool_nano: 1_000_000_000,
      stake_nano: 500_000_000,
      opponent_stake_nano: 500_000_000,
      fee_bps: 250,
      fee_exempt: false,
      payout_nano: 975_000_000,
      net_profit_nano: 475_000_000,
      mode: 'afk',
      direct_opponent_wallet: null,
      state: 'open',
      expires_at: new Date(Date.now() + 900_000).toISOString(),
      funding_tx_hash: 'funding',
      funding_proof_url: 'https://tonviewer.com/transaction/funding',
    };
    render(
      <DuelScreen
        profile={{ ...profile, wallet: walletOf('0:aaa') }}
        offers={[offer]}
        duels={[]}
        invite={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(
      await screen.findByRole('button', { name: 'СОПЕРНИК НАЙДЕН — НАЧАТЬ БОЙ' }),
    ).toBeEnabled();
    expect(apiMocks.matchOfferIntent).toHaveBeenCalledWith(811);
  });
});
