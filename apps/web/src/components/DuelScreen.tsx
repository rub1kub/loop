import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { api } from '../api';
import {
  haptic,
  isMockTelegram,
  readDuelSecret,
  setMainAction,
  storeDuelSecret,
  telegram,
} from '../telegram';
import {
  buildActionTransaction,
  buildOpenOfferTransaction,
  commitmentForOffer,
  formatGram,
  newOfferId,
  newSecret,
  parseGram,
} from '../ton';
import type { Duel, Invite, Offer, Profile } from '../types';
import { ProbabilityCanvas } from './ProbabilityCanvas';

type DuelStatus = 'idle' | 'preparing' | 'wallet' | 'searching' | 'matched';

export function DuelScreen({
  profile,
  offers,
  duels,
  invite,
  onRefresh,
}: {
  profile: Profile;
  offers: Offer[];
  duels: Duel[];
  invite: Invite | null;
  onRefresh: () => Promise<void>;
}) {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  const [chance, setChance] = useState(() => (invite ? 100 - invite.chance_bps / 100 : 50));
  const [pool, setPool] = useState(() =>
    invite ? String((invite.stake_nano * 10_000) / invite.chance_bps / 1_000_000_000) : '4',
  );
  const [status, setStatus] = useState<DuelStatus>('idle');
  const [message, setMessage] = useState(
    invite ? 'Вызов принят. Проверь условия и заблокируй ставку.' : 'Выбери свою долю шанса.',
  );
  const [now, setNow] = useState(0);
  useEffect(() => {
    const update = () => setNow(Date.now());
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, []);
  const activeOffer = offers.find((offer) =>
    ['pending_funding', 'open', 'matched'].includes(offer.state),
  );
  const activeDuel = activeOffer
    ? duels.find(
        (duel) => duel.offer_id === activeOffer.onchain_offer_id && duel.state === 'revealing',
      )
    : undefined;
  const duelExpired = activeDuel ? Date.parse(activeDuel.reveal_deadline) < now : false;
  const offerExpired = activeOffer ? Date.parse(activeOffer.expires_at) < now : false;
  const effectiveStatus: DuelStatus = activeOffer
    ? activeOffer.state === 'matched'
      ? 'matched'
      : 'searching'
    : status;
  const effectiveMessage = activeOffer
    ? activeOffer.state === 'matched'
      ? !activeDuel
        ? 'Матч подтверждён. Синхронизируем раунд…'
        : duelExpired
          ? 'Окно раскрытия закрыто. Заверши расчёт в контракте.'
          : activeDuel.own_revealed
            ? 'Секрет раскрыт. Ждём соперника до дедлайна.'
            : 'Соперник найден. Раскрой секрет до дедлайна.'
      : activeOffer.state === 'open'
        ? offerExpired
          ? 'Срок поиска истёк. Верни ставку из контракта.'
          : 'Ищем соперника. Можно закрыть LOOP — мы уведомим.'
        : 'Ждём подтверждения транзакции в TON.'
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

  const runActiveAction = useCallback(async () => {
    if (!activeOffer || !wallet) {
      await tonConnectUI.openModal();
      return;
    }
    try {
      setStatus('wallet');
      let intent;
      let secret: string | undefined;
      if (activeOffer.state === 'matched') {
        if (!activeDuel) throw new Error('Матч ещё синхронизируется');
        if (duelExpired) intent = await api.expireDuelIntent(activeDuel.onchain_duel_id);
        else {
          if (activeDuel.own_revealed) return;
          intent = await api.revealIntent(activeDuel.onchain_duel_id);
          secret = (await readDuelSecret(intent.offer_id)) ?? undefined;
        }
      } else if (activeOffer.state === 'open') {
        intent = offerExpired
          ? await api.expireOfferIntent(activeOffer.onchain_offer_id)
          : await api.cancelOfferIntent(activeOffer.onchain_offer_id);
      } else {
        throw new Error('Транзакция ещё не подтверждена сетью');
      }
      await tonConnectUI.sendTransaction(
        buildActionTransaction(
          intent,
          wallet.account.address,
          wallet.account.chain as '-3' | '-239',
          secret,
        ),
      );
      setMessage('Транзакция отправлена. Ждём финализации TON.');
      haptic('success');
      await onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось выполнить действие');
      haptic('error');
    }
  }, [activeDuel, activeOffer, duelExpired, offerExpired, onRefresh, tonConnectUI, wallet]);

  const activeActionLabel = activeOffer
    ? activeOffer.state === 'matched'
      ? duelExpired
        ? 'ЗАВЕРШИТЬ РАУНД'
        : activeDuel?.own_revealed
          ? null
          : 'РАСКРЫТЬ СЕКРЕТ'
      : activeOffer.state === 'open'
        ? offerExpired
          ? 'ВЕРНУТЬ СТАВКУ'
          : 'ОТМЕНИТЬ ПОИСК'
        : null
    : null;

  const inviteToDuel = useCallback(() => {
    const app = telegram();
    if (!app?.switchInlineQuery) {
      setMessage('Inline-вызов доступен внутри Telegram');
      haptic('warning');
      return;
    }
    app.switchInlineQuery(`${pool} ${chance}`, ['users', 'groups']);
    haptic('light');
  }, [chance, pool]);

  useEffect(() => {
    if (activeActionLabel) {
      return setMainAction(activeActionLabel, () => void runActiveAction());
    }
    if (!activeOffer) return setMainAction('ИСКАТЬ СОПЕРНИКА', () => void start());
    return setMainAction('', undefined, false);
  }, [activeActionLabel, activeOffer, runActiveAction, start]);

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
        <>
          <button className="primary-button duel-action" onClick={() => void start()}>
            {wallet ? 'ИСКАТЬ' : 'ПОДКЛЮЧИТЬ КОШЕЛЁК'}
          </button>
          <button className="duel-invite" onClick={inviteToDuel}>
            ПРИГЛАСИТЬ В ИГРУ
          </button>
        </>
      )}
      {activeActionLabel && (
        <button className="primary-button duel-action" onClick={() => void runActiveAction()}>
          {activeActionLabel}
        </button>
      )}
    </section>
  );
}
