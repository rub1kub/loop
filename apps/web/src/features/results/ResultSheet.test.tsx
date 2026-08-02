import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ResultCard } from '../../types';
import { ResultSheet } from './ResultSheet';

const apiMocks = vi.hoisted(() => ({
  prepareResultShare: vi.fn(),
}));
const telegramMocks = vi.hoisted(() => ({
  sharePreparedResult: vi.fn(),
}));

vi.mock('../../api', () => ({ api: apiMocks }));
vi.mock('../../telegram', () => ({
  haptic: vi.fn(),
  isMockTelegram: () => false,
  openPlatformLink: vi.fn(),
  // Telegram's own Close overlaps the card's, so the sheet claims the Back
  // button while it is open and releases it on unmount.
  setBackAction: () => () => undefined,
  sharePreparedResult: telegramMocks.sharePreparedResult,
}));

const card: ResultCard = {
  id: 'result-1',
  mode: 'bank',
  payout_nano: 3_000_000_000,
  contributed_nano: 2_000_000_000,
  result_nano: 1_000_000_000,
  queue_position: null,
  proof_url: 'https://testnet.tonviewer.com/transaction/proof',
  image_url: 'https://loop.test/api/v1/results/cards/public.jpg',
  seen_at: null,
  created_at: '2026-07-26T12:00:00Z',
};

describe('ResultSheet', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.prepareResultShare.mockResolvedValue({
      prepared_message_id: 'prepared-result',
      expiration_date: '2030-01-01T00:00:00Z',
      fallback_query: 'result public',
    });
    telegramMocks.sharePreparedResult.mockResolvedValue(true);
  });

  afterEach(cleanup);

  it('shows only verified result facts and shares a prepared Telegram message', async () => {
    render(<ResultSheet card={card} onClose={vi.fn()} onError={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Цикл замкнулся.' })).toBeInTheDocument();
    expect(screen.getByText('+1 GRAM')).toBeInTheDocument();
    expect(screen.getByAltText('Карточка результата LOOP')).toHaveAttribute('src', card.image_url);

    fireEvent.click(screen.getByRole('button', { name: 'ПОДЕЛИТЬСЯ' }));
    await waitFor(() => expect(apiMocks.prepareResultShare).toHaveBeenCalledWith(card.id));
    expect(telegramMocks.sharePreparedResult).toHaveBeenCalledWith(
      'prepared-result',
      'result public',
    );
  });

  it('marks the card seen only when the user closes it', async () => {
    const close = vi.fn().mockResolvedValue(undefined);
    render(<ResultSheet card={card} onClose={close} onError={vi.fn()} />);

    expect(close).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
  });
});
