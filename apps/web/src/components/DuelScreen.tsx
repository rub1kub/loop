import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { api } from '../api';
import { haptic, isMockTelegram, setMainAction, storeDuelSecret } from '../telegram';
import {
  buildOpenOfferTransaction,
  commitmentForOffer,
  formatGram,
  newOfferId,
  newSecret,
  parseGram,
} from '../ton';
import type { Offer, Profile } from '../types';
import { ProbabilityCanvas } from './ProbabilityCanvas';

type DuelStatus = 'idle' | 'preparing' | 'wallet' | 'searching' | 'matched';

export function DuelScreen({
  profile,
  offers,
  onRefresh,
}: {
  profile: Profile;
  offers: Offer[];
  onRefresh: () => Promise<void>;
}) {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  const [chance, setChance] = useState(50);
  const [pool, setPool] = useState('4');
  const [status, setStatus] = useState<DuelStatus>('idle');
  const [message, setMessage] = useState('Выбери свою долю шанса.');
  const activeOffer = offers.find((offer) =>
    ['pending_funding', 'open', 'matched'].includes(offer.state),
  );
  const effectiveStatus: DuelStatus = activeOffer
    ? activeOffer.state === 'matched'
      ? 'matched'
      : 'searching'
    : status;
  const effectiveMessage = activeOffer
    ? activeOffer.state === 'matched'
      ? 'Соперник найден. Открой уведомление, чтобы раскрыть секрет.'
      : 'Ищем соперника. Можно закрыть LOOP — мы уведомим.'
    : message;

  const totalPoolNano = useMemo(() => {
    try {
      return parseGram(pool);
    } catch {
      return 0;
    }
  }, [pool]);
  const stakeNano = (totalPoolNano * chance) / 100;

  const start = useCallback(async () => {
    if (activeOffer) return;
    if (!wallet) {
      haptic('warning');
      await tonConnectUI.openModal();
      return;
    }
    if (!profile.wallet && !isMockTelegram()) {
      setMessage('Подтверждаем владение кошельком…');
      haptic('warning');
      return;
    }
    try {
      setStatus('preparing');
      setMessage('Собираем честную дуэль…');
      const parsedPoolNano = parseGram(pool);
      if (parsedPoolNano % 4) throw new Error('Пул должен делиться на 4 nanoGRAM');
      const offerId = newOfferId();
      const secret = newSecret();
      const commitment = commitmentForOffer(offerId, wallet.account.address, secret);
      const quote = isMockTelegram()
        ? null
        : await api.quoteOffer({
            offer_id: offerId,
            chance_bps: chance * 100,
            total_pool_nano: parsedPoolNano,
            commitment_hex: commitment,
          });
      await storeDuelSecret(offerId, secret.toString(16).padStart(64, '0'));
      if (quote) {
        setStatus('wallet');
        setMessage('Подтверди блокировку в кошельке.');
        await tonConnectUI.sendTransaction(
          buildOpenOfferTransaction(
            quote,
            wallet.account.address,
            wallet.account.chain as '-3' | '-239',
          ),
        );
        await onRefresh();
      }
      setStatus('searching');
      setMessage('Средства блокируются контрактом. Ищем соперника.');
      haptic('success');
    } catch (error) {
      setStatus('idle');
      setMessage(error instanceof Error ? error.message : 'Не удалось начать поиск');
      haptic('error');
    }
  }, [activeOffer, chance, onRefresh, pool, profile.wallet, tonConnectUI, wallet]);

  useEffect(
    () => setMainAction('ИСКАТЬ СОПЕРНИКА', () => void start(), !activeOffer),
    [activeOffer, start],
  );

  return (
    <section className="screen duel-screen" aria-labelledby="duel-title">
      <header className="screen-header duel-header">
        <p className="eyebrow">ЧЕСТНЫЙ ШАНС</p>
        <h1 id="duel-title">DUEL</h1>
      </header>

      <ProbabilityCanvas chance={chance} status={effectiveStatus} />

      <div className="chance-selector" aria-label="Шанс победы">
        {[25, 50, 75].map((value) => (
          <button
            key={value}
            className={chance === value ? 'active' : ''}
            onClick={() => {
              setChance(value);
              haptic('selection');
            }}
            disabled={Boolean(activeOffer)}
          >
            {value}%
          </button>
        ))}
      </div>

      <label className="pool-input">
        <span>ОБЩИЙ ПУЛ</span>
        <div>
          <input
            value={pool}
            onChange={(event) => setPool(event.target.value)}
            inputMode="decimal"
            disabled={Boolean(activeOffer)}
            aria-label="Общий пул в GRAM"
          />
          <b>GRAM</b>
        </div>
      </label>

      <div className="duel-math">
        <span>ТВОЯ СТАВКА</span>
        <strong>{formatGram(stakeNano)} GRAM</strong>
        <span>СОПЕРНИК</span>
        <strong>{formatGram(Math.max(0, totalPoolNano - stakeNano))} GRAM</strong>
      </div>

      <AnimatePresence mode="wait">
        <motion.p
          key={effectiveMessage}
          className="duel-message"
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
        >
          {effectiveMessage}
        </motion.p>
      </AnimatePresence>

      {!activeOffer && (
        <button className="primary-button duel-action" onClick={() => void start()}>
          {wallet ? 'ИСКАТЬ' : 'ПОДКЛЮЧИТЬ КОШЕЛЁК'}
        </button>
      )}
    </section>
  );
}
