import {
  ArrowRight,
  ArrowSquareOut,
  HourglassSimple,
  PaperPlaneTilt,
  ShieldCheck,
  User,
  UserPlus,
} from '@phosphor-icons/react';
import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../../api';
import { DisclosureIndicator } from '../../components/DisclosureIndicator';
import { haptic, isMockTelegram, readDuelSecret, storeDuelSecret, telegram } from '../../telegram';
import {
  buildActionTransaction,
  buildOpenOfferTransaction,
  commitmentForOffer,
  assertOpenOfferQuoteContext,
  formatGram,
  isSupportedTonNetwork,
  newOfferId,
  newSecret,
  parseGram,
} from '../../ton';
import type { Duel, Invite, Offer, Profile } from '../../types';

const DEFAULT_CHANCE_BPS = 5000;

function canonicalTerms(requestedStake: number, chanceBps: number) {
  const quarterUnits = chanceBps / 2500;
  const poolUnit = Math.floor((requestedStake + quarterUnits - 1) / quarterUnits);
  const stake = quarterUnits * poolUnit;
  const opponentStake = (4 - quarterUnits) * poolUnit;
  return { stake, opponentStake, totalPool: 4 * poolUnit };
}

function timeLeft(until: number | null, now: number): string {
  if (!until) return '—';
  const seconds = Math.max(0, Math.ceil((until - now) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
}

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
  const [stake, setStake] = useState(() => (invite ? formatGram(invite.stake_nano, 3) : '1'));
  const chance = invite?.chance_bps ?? DEFAULT_CHANCE_BPS;
  const [mode, setMode] = useState<'afk' | 'direct'>(invite ? 'direct' : 'afk');
  const [busy, setBusy] = useState(false);
  const [mockSearching, setMockSearching] = useState(false);
  const [mockExpiresAt, setMockExpiresAt] = useState<number | null>(null);
  const [message, setMessage] = useState(invite ? `${invite.creator_name} бросил тебе вызов.` : '');
  const [now, setNow] = useState(() => Date.now());
  const locked = useRef(false);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const activeOffer = offers.find((offer) =>
    ['pending_funding', 'open', 'reserved', 'matched'].includes(offer.state),
  );
  const activeDuel = activeOffer
    ? duels.find(
        (duel) => duel.offer_id === activeOffer.onchain_offer_id && duel.state === 'revealing',
      )
    : undefined;
  const latestDuel = duels[0];
  const offerExpired = activeOffer ? Date.parse(activeOffer.expires_at) <= now : false;
  const duelExpired = activeDuel ? Date.parse(activeDuel.reveal_deadline) <= now : false;

  const requestedStake = useMemo(() => {
    try {
      return parseGram(stake);
    } catch {
      return 0;
    }
  }, [stake]);
  const terms = useMemo(() => canonicalTerms(requestedStake, chance), [chance, requestedStake]);
  const feeNano = (terms.totalPool * profile.plush_brick.duel_fee_bps) / 10_000;
  const payoutNano = terms.totalPool - feeNano;
  const profitNano = payoutNano - terms.stake;

  const status =
    activeOffer?.state === 'matched'
      ? 'matched'
      : activeOffer || mockSearching
        ? 'searching'
        : latestDuel?.state === 'settled'
          ? 'result'
          : 'idle';

  const start = useCallback(
    async (selectedMode: 'afk' | 'direct') => {
      if (locked.current || activeOffer) return;
      locked.current = true;
      setBusy(true);
      setMode(selectedMode);
      try {
        if (requestedStake < 250_000_000) throw new Error('Минимальная ставка — 0,25 GRAM');
        if (isMockTelegram()) {
          setMockSearching(true);
          setMockExpiresAt(Date.now() + 15 * 60_000);
          setMessage(selectedMode === 'afk' ? '' : 'Вызов создан. Отправь его через Telegram.');
          haptic('success');
          return;
        }
        if (!wallet) {
          await tonConnectUI.openModal();
          return;
        }
        if (!isSupportedTonNetwork(wallet.account.chain)) {
          throw new Error('Этот кошелёк сейчас не поддерживается');
        }
        if (!profile.wallet) throw new Error('Ждём подтверждение владения внешним кошельком');
        let acceptedInvite = invite;
        if (invite) acceptedInvite = await api.acceptInvite(invite.code);
        const contract = await api.contractState('duel');
        if (
          contract.network !== Number(wallet.account.chain) ||
          contract.status !== 'active' ||
          !contract.code_hash_matches
        ) {
          throw new Error('DUEL временно недоступен: проверка не пройдена');
        }
        const offerId = newOfferId();
        const secret = newSecret();
        const commitment = commitmentForOffer(
          offerId,
          wallet.account.address,
          secret,
          contract.network,
          contract.address,
        );
        const quote = await api.quoteOffer({
          offer_id: offerId,
          chance_bps: chance,
          stake_nano: terms.stake,
          commitment_hex: commitment,
          mode: selectedMode,
          ...(acceptedInvite ? { challenge_code: acceptedInvite.code } : {}),
        });
        assertOpenOfferQuoteContext(quote, {
          operation: acceptedInvite
            ? 'accept_direct_offer'
            : selectedMode === 'direct'
              ? 'open_direct_offer'
              : 'open_offer',
          offerId,
          commitmentHex: commitment,
          chanceBps: chance,
          stakeNano: terms.stake,
          opponentStakeNano: terms.opponentStake,
          totalPoolNano: terms.totalPool,
          network: contract.network,
          contractAddress: contract.address,
          ...(acceptedInvite ? { counterOfferId: acceptedInvite.counter_offer_id } : {}),
        });
        await storeDuelSecret(offerId, secret.toString(16).padStart(64, '0'));
        setMessage('Подтверди ставку во внешнем кошельке.');
        await tonConnectUI.sendTransaction(
          buildOpenOfferTransaction(quote, wallet.account.address, wallet.account.chain),
        );
        setMessage('Проверяем ставку. Закрытие кошелька ещё не означает успех.');
        await onRefresh();
        haptic('success');
      } catch (error) {
        setMessage(error instanceof Error ? error.message : 'Не удалось создать DUEL');
        haptic('error');
      } finally {
        locked.current = false;
        setBusy(false);
      }
    },
    [
      activeOffer,
      chance,
      invite,
      onRefresh,
      profile.wallet,
      requestedStake,
      terms.stake,
      terms.opponentStake,
      terms.totalPool,
      tonConnectUI,
      wallet,
    ],
  );

  const runActiveAction = useCallback(async () => {
    if (locked.current || !activeOffer) return;
    if (!wallet) {
      await tonConnectUI.openModal();
      return;
    }
    locked.current = true;
    setBusy(true);
    try {
      let intent;
      let secret: string | undefined;
      if (activeOffer.state === 'matched') {
        if (!activeDuel) throw new Error('Обновляем состояние DUEL');
        if (duelExpired) intent = await api.expireDuelIntent(activeDuel.onchain_duel_id);
        else {
          if (activeDuel.own_revealed) return;
          intent = await api.revealIntent(activeDuel.onchain_duel_id);
          secret = (await readDuelSecret(intent.offer_id)) ?? undefined;
        }
      } else if (activeOffer.state === 'open' || activeOffer.state === 'reserved') {
        intent = offerExpired
          ? await api.expireOfferIntent(activeOffer.onchain_offer_id)
          : await api.cancelOfferIntent(activeOffer.onchain_offer_id);
      } else {
        throw new Error('Ждём подтверждение предыдущего действия');
      }
      await tonConnectUI.sendTransaction(
        buildActionTransaction(intent, wallet.account.address, wallet.account.chain, secret),
      );
      setMessage('Действие отправлено. Ждём окончательный результат.');
      await onRefresh();
      haptic('success');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Действие не выполнено');
      haptic('error');
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }, [activeDuel, activeOffer, duelExpired, offerExpired, onRefresh, tonConnectUI, wallet]);

  function inviteToTelegram() {
    if (!activeOffer || activeOffer.state !== 'open') {
      setMessage('Сначала дождись подтверждения вызова.');
      haptic('warning');
      return;
    }
    const app = telegram();
    if (!app?.switchInlineQuery) {
      setMessage('Приглашение в Telegram доступно только внутри приложения.');
      return;
    }
    app.switchInlineQuery(`duel ${activeOffer.onchain_offer_id}`, ['users', 'groups']);
    haptic('light');
  }

  const activeActionLabel = activeOffer
    ? activeOffer.state === 'matched'
      ? duelExpired
        ? 'ЗАВЕРШИТЬ ПО ТАЙМАУТУ'
        : activeDuel?.own_revealed
          ? null
          : 'ОТКРЫТЬ РЕЗУЛЬТАТ'
      : activeOffer.state === 'open' || activeOffer.state === 'reserved'
        ? offerExpired
          ? 'ВЕРНУТЬ СТАВКУ'
          : 'ОСТАНОВИТЬ ПОИСК'
        : null
    : mockSearching
      ? 'ОСТАНОВИТЬ ПОИСК'
      : null;
  const activeDeadline =
    status === 'matched' && activeDuel
      ? Date.parse(activeDuel.reveal_deadline)
      : activeOffer
        ? Date.parse(activeOffer.expires_at)
        : mockExpiresAt;

  return (
    <section className="screen duel-screen" aria-labelledby="duel-title">
      <header className="mode-header">
        <p className="eyebrow">ВЫЗОВ 1 НА 1</p>
        <h1 id="duel-title">DUEL</h1>
      </header>

      {status !== 'idle' && (
        <div className={`duel-stage is-${status}`}>
          <span className="player-node">
            <User aria-hidden="true" />
          </span>
          <span className="duel-link">
            <HourglassSimple aria-hidden="true" />
          </span>
          <span className="player-node opponent">
            {status === 'matched' || status === 'result' || invite ? (
              <User weight="fill" aria-hidden="true" />
            ) : (
              <UserPlus aria-hidden="true" />
            )}
          </span>
        </div>
      )}

      {status === 'idle' && (
        <div className="duel-form">
          {invite ? (
            <div className="invite-banner">
              <p className="eyebrow">
                ВЫЗОВ ОТ {invite.creator_name.toUpperCase()} · {chance / 100}/
                {(10_000 - chance) / 100}
              </p>
              <strong>Перед принятием ещё раз проверь сумму и выплату.</strong>
            </div>
          ) : (
            <>
              <label className="stake-input">
                <span className="stake-input-heading">
                  <span>СТАВКА</span>
                  <span className="stake-edit-cue">ВВЕДИ СУММУ</span>
                </span>
                <div>
                  <input
                    inputMode="decimal"
                    value={stake}
                    onChange={(event) => setStake(event.target.value)}
                    aria-label="Ставка в GRAM"
                  />
                  <b>GRAM</b>
                </div>
              </label>
              <div className="duel-equal-rule">
                <strong>50/50</strong>
                <span>РАВНЫЕ УСЛОВИЯ</span>
              </div>
            </>
          )}

          <dl className="duel-terms duel-primary-terms" aria-label="Расчёт DUEL">
            <Term
              label="Ставки"
              value={`${formatGram(terms.stake, 3)} + ${formatGram(terms.opponentStake, 3)} GRAM`}
            />
            <Term label="Победитель получит" value={`${formatGram(payoutNano, 3)} GRAM`} />
            <Term label="Комиссия" value={`${formatGram(feeNano, 4)} GRAM`} />
          </dl>
          <p className="duel-deadline-rule">
            <ShieldCheck aria-hidden="true" />
            Оба открыли числа — исход 50/50. Открыл только один за 5 минут — он победил.
          </p>
          <details className="technical-details duel-breakdown">
            <summary>
              <span>ВОЗВРАТ И ПРАВИЛА</span>
              <DisclosureIndicator />
            </summary>
            <p>
              После ставки изменить тайное число нельзя. Если не откроет никто, обе ставки вернутся.
            </p>
            <dl className="detail-list">
              <Term label="Общая сумма" value={`${formatGram(terms.totalPool, 3)} GRAM`} />
              <Term label="Чистый результат победы" value={`+${formatGram(profitNano, 3)} GRAM`} />
            </dl>
            <p>Поиск можно остановить и вернуть ставку через подтверждение в кошельке.</p>
          </details>
        </div>
      )}

      {(status === 'searching' || status === 'matched') && (
        <div className="duel-live-state">
          <p className="eyebrow">
            {status === 'matched'
              ? 'СОПЕРНИК НАЙДЕН'
              : mode === 'direct'
                ? 'ПРЯМОЙ ВЫЗОВ'
                : 'ПОИСК СОПЕРНИКА'}
          </p>
          <strong>
            {status === 'matched'
              ? 'Соперник найден. Открой результат.'
              : 'Ищем игрока с такой же ставкой. Можно закрыть приложение.'}
          </strong>
          <div className="duel-live-numbers">
            <span>
              <b>{formatGram(activeOffer?.stake_nano ?? terms.stake, 3)} GRAM</b>
              <small>ТВОЯ СТАВКА</small>
            </span>
            <span>
              <b>{timeLeft(activeDeadline, now)}</b>
              <small>{status === 'matched' ? 'НА РАСКРЫТИЕ' : 'ДО ИСТЕЧЕНИЯ'}</small>
            </span>
          </div>
          {status === 'searching' && (
            <p className="duel-live-help">
              Остановить поиск можно в любой момент. Возврат нужно подтвердить в кошельке.
            </p>
          )}
        </div>
      )}

      {status === 'result' && latestDuel && (
        <div className="duel-result">
          <p className="eyebrow">РЕЗУЛЬТАТ ПОДТВЕРЖДЁН</p>
          <h2>{latestDuel.winner_wallet === profile.wallet?.address ? 'ПОБЕДА' : 'ЗАВЕРШЕНО'}</h2>
          <strong>{formatGram(latestDuel.payout_nano, 3)} GRAM</strong>
          {latestDuel.settlement_proof_url && (
            <a href={latestDuel.settlement_proof_url} target="_blank" rel="noreferrer">
              Посмотреть подтверждение <ArrowSquareOut aria-hidden="true" />
            </a>
          )}
        </div>
      )}

      <AnimatePresence mode="wait">
        {message && (
          <motion.p
            key={message}
            className="duel-message"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <ShieldCheck aria-hidden="true" /> {message}
          </motion.p>
        )}
      </AnimatePresence>

      <div className="duel-actions">
        {status === 'idle' && (
          <>
            <button
              className="primary-button"
              disabled={busy}
              onClick={() => void start(invite ? 'direct' : 'afk')}
            >
              {busy ? 'ГОТОВИМ…' : invite ? 'ПРИНЯТЬ ВЫЗОВ' : 'НАЙТИ СОПЕРНИКА'}
            </button>
            {!invite && (
              <button
                className="duel-direct-action"
                disabled={busy}
                onClick={() => void start('direct')}
              >
                <PaperPlaneTilt aria-hidden="true" /> ВЫЗВАТЬ ДРУГА
              </button>
            )}
          </>
        )}
        {(activeOffer?.mode === 'direct' || (mockSearching && mode === 'direct')) &&
          status === 'searching' && (
            <button className="primary-button" onClick={inviteToTelegram}>
              ПРИГЛАСИТЬ В TELEGRAM <ArrowRight aria-hidden="true" />
            </button>
          )}
        {activeActionLabel && (
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => {
              if (mockSearching && !activeOffer) {
                setMockSearching(false);
                setMockExpiresAt(null);
                setMessage('Поиск остановлен. Тестовая ставка возвращена.');
                haptic('success');
                return;
              }
              void runActiveAction();
            }}
          >
            {activeActionLabel}
          </button>
        )}
      </div>
    </section>
  );
}

function Term({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
