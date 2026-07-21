import {
  ArrowRight,
  HourglassSimple,
  Infinity as InfinityIcon,
  PaperPlaneTilt,
  ShieldCheck,
  User,
  UserPlus,
} from '@phosphor-icons/react';
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

type DuelStatus = 'idle' | 'preparing' | 'wallet' | 'searching' | 'matched';

const CONTRIBUTIONS = ['1', '2', '5'];

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
  const [contribution, setContribution] = useState(() =>
    invite ? formatGram(invite.stake_nano) : '2',
  );
  const [status, setStatus] = useState<DuelStatus>('idle');
  const [message, setMessage] = useState(
    invite
      ? `${invite.creator_name} бросил тебе вызов. Условия уже закреплены.`
      : 'Равные условия. Вклад блокируется только смарт-контрактом.',
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
        ? 'Вызов принят on-chain. Синхронизируем дуэль…'
        : duelExpired
          ? 'Окно подтверждения закрыто. Заверши дуэль в контракте.'
          : activeDuel.own_revealed
            ? 'Твой результат подтверждён. Ждём второго игрока.'
            : 'Соперник найден. Подтверди результат до дедлайна.'
      : activeOffer.state === 'open'
        ? offerExpired
          ? 'Поиск завершён. Верни вклад из контракта.'
          : 'Ищем человека. LOOP можно закрыть — цикл продолжится.'
        : 'TON подтверждает участие.'
    : message;

  const contributionNano = useMemo(() => {
    try {
      return parseGram(contribution);
    } catch {
      return 0;
    }
  }, [contribution]);
  const totalPoolNano = contributionNano * 2;

  const start = useCallback(async () => {
    if (activeOffer) return;
    if (isMockTelegram()) {
      setStatus('searching');
      setMessage('Ищем человека. LOOP можно закрыть — цикл продолжится.');
      haptic('success');
      return;
    }
    if (!wallet) {
      haptic('warning');
      await tonConnectUI.openModal();
      return;
    }
    if (!profile.wallet) {
      setMessage('Подтверждаем владение внешним кошельком…');
      haptic('warning');
      return;
    }
    try {
      setStatus('preparing');
      setMessage('Готовим on-chain вызов…');
      if (contributionNano <= 0) throw new Error('Выбери вклад для участия');
      if (totalPoolNano % 4) throw new Error('Выбери сумму с точностью до nanoGRAM');
      const offerId = newOfferId();
      const secret = newSecret();
      const commitment = commitmentForOffer(offerId, wallet.account.address, secret);
      const quote = await api.quoteOffer({
        offer_id: offerId,
        chance_bps: 5000,
        total_pool_nano: totalPoolNano,
        commitment_hex: commitment,
        ...(invite ? { challenge_code: invite.code } : {}),
      });
      await storeDuelSecret(offerId, secret.toString(16).padStart(64, '0'));
      setStatus('wallet');
      setMessage('Подтверди участие во внешнем кошельке.');
      await tonConnectUI.sendTransaction(
        buildOpenOfferTransaction(
          quote,
          wallet.account.address,
          wallet.account.chain as '-3' | '-239',
        ),
      );
      await onRefresh();
      setStatus('searching');
      setMessage('Ищем человека. LOOP можно закрыть — цикл продолжится.');
      haptic('success');
    } catch (error) {
      setStatus('idle');
      setMessage(error instanceof Error ? error.message : 'Не удалось создать вызов');
      haptic('error');
    }
  }, [
    activeOffer,
    contributionNano,
    invite,
    onRefresh,
    profile.wallet,
    tonConnectUI,
    totalPoolNano,
    wallet,
  ]);

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
        if (!activeDuel) throw new Error('Дуэль ещё синхронизируется');
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
        ? 'ЗАВЕРШИТЬ ДУЭЛЬ'
        : activeDuel?.own_revealed
          ? null
          : 'ПОДТВЕРДИТЬ РЕЗУЛЬТАТ'
      : activeOffer.state === 'open'
        ? offerExpired
          ? 'ВЕРНУТЬ ВКЛАД'
          : 'ОСТАНОВИТЬ ПОИСК'
        : null
    : null;

  const inviteToDuel = useCallback(() => {
    if (!activeOffer || activeOffer.state !== 'open') {
      setMessage('Сначала дождись on-chain подтверждения вызова.');
      haptic('warning');
      return;
    }
    const app = telegram();
    if (!app?.switchInlineQuery) {
      setMessage('Telegram inline доступен внутри Mini App.');
      haptic('warning');
      return;
    }
    app.switchInlineQuery(`duel ${activeOffer.onchain_offer_id}`, ['users', 'groups']);
    haptic('light');
  }, [activeOffer]);

  useEffect(() => {
    if (activeActionLabel) {
      return setMainAction(activeActionLabel, () => void runActiveAction());
    }
    if (!activeOffer) {
      return setMainAction(invite ? 'ПРИНЯТЬ ВЫЗОВ' : 'НАЙТИ СОПЕРНИКА', () => void start());
    }
    return setMainAction('', undefined, false);
  }, [activeActionLabel, activeOffer, invite, runActiveAction, start]);

  const statusLabel =
    effectiveStatus === 'matched'
      ? 'СОПЕРНИК НАЙДЕН'
      : effectiveStatus === 'searching'
        ? 'ПОИСК ИДЁТ'
        : invite
          ? `ВЫЗОВ ОТ ${invite.creator_name.toUpperCase()}`
          : 'ГОТОВ К ВЫЗОВУ';

  return (
    <section className="screen duel-screen" aria-labelledby="duel-title">
      <header className="duel-heading">
        <p className="eyebrow">СОЦИАЛЬНЫЙ ВЫЗОВ</p>
        <h1 id="duel-title">DUEL</h1>
      </header>

      <div className={`duel-players is-${effectiveStatus}`} aria-label={statusLabel}>
        <span className="player-node">
          <User aria-hidden="true" />
        </span>
        <span className="duel-link">
          {effectiveStatus === 'searching' ? (
            <HourglassSimple aria-hidden="true" />
          ) : (
            <InfinityIcon aria-hidden="true" />
          )}
        </span>
        <span className="player-node opponent">
          {effectiveStatus === 'matched' || invite ? (
            <User weight="fill" aria-hidden="true" />
          ) : (
            <UserPlus aria-hidden="true" />
          )}
        </span>
      </div>
      <strong className="duel-status">{statusLabel}</strong>

      {!activeOffer && effectiveStatus !== 'searching' && (
        <div className="duel-setup">
          <div className="duel-rule">
            <span>УСЛОВИЯ</span>
            <strong>РАВНЫЙ ВКЛАД · 50 / 50</strong>
          </div>
          <div className="contribution-picker" aria-label="Вклад в GRAM">
            {CONTRIBUTIONS.map((value) => (
              <button
                key={value}
                className={contribution === value ? 'active' : ''}
                onClick={() => {
                  setContribution(value);
                  haptic('selection');
                }}
                disabled={Boolean(invite)}
              >
                <strong>{value}</strong>
                <span>GRAM</span>
              </button>
            ))}
          </div>
          <div className="duel-proof-line">
            <ShieldCheck aria-hidden="true" />
            <span>Commit–reveal и результат подтверждаются в TON</span>
          </div>
        </div>
      )}

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

      <div className="duel-actions">
        {!activeOffer && effectiveStatus !== 'searching' && (
          <>
            <button className="primary-button" onClick={() => void start()}>
              {invite ? 'ПРИНЯТЬ ВЫЗОВ' : wallet || isMockTelegram() ? 'НАЙТИ СОПЕРНИКА' : 'ПРОДОЛЖИТЬ'}
            </button>
            {!invite && (
              <button
                className="secondary-button"
                onClick={() => {
                  setMessage('Создай on-chain вызов — после подтверждения отправим его в Telegram.');
                  void start();
                }}
              >
                <PaperPlaneTilt aria-hidden="true" />
                СОЗДАТЬ ПРЯМОЙ ВЫЗОВ
              </button>
            )}
          </>
        )}
        {activeOffer?.state === 'open' && !offerExpired && (
          <button className="primary-button" onClick={inviteToDuel}>
            ПРИГЛАСИТЬ В TELEGRAM
            <ArrowRight aria-hidden="true" />
          </button>
        )}
        {activeActionLabel && (
          <button className="secondary-button" onClick={() => void runActiveAction()}>
            {activeActionLabel}
          </button>
        )}
      </div>
    </section>
  );
}
