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
  buildBoostTransaction,
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
  const [boostAmount, setBoostAmount] = useState('0.5');
  const chance = invite?.chance_bps ?? DEFAULT_CHANCE_BPS;
  const [mode, setMode] = useState<'afk' | 'direct'>(invite ? 'direct' : 'afk');
  const [busy, setBusy] = useState(false);
  const [mockSearching, setMockSearching] = useState(false);
  const [mockExpiresAt, setMockExpiresAt] = useState<number | null>(null);
  const [message, setMessage] = useState(invite ? `${invite.creator_name} бросил тебе вызов.` : '');
  const [now, setNow] = useState(() => Date.now());
  const locked = useRef(false);
  const lastBoostRevision = useRef<number | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const activeOffer = offers.find((offer) =>
    ['pending_funding', 'open', 'reserved', 'matched'].includes(offer.state),
  );
  const activeDuel = activeOffer
    ? duels.find(
        (duel) =>
          duel.offer_id === activeOffer.onchain_offer_id &&
          ['boosting', 'revealing'].includes(duel.state),
      )
    : undefined;
  const latestDuel = duels[0];
  const offerExpired = activeOffer ? Date.parse(activeOffer.expires_at) <= now : false;
  const duelExpired = activeDuel ? Date.parse(activeDuel.reveal_deadline) <= now : false;
  const boostDeadline = activeDuel?.boost_deadline ? Date.parse(activeDuel.boost_deadline) : null;
  const duelBoosting = Boolean(
    activeDuel && activeDuel.state === 'boosting' && boostDeadline && boostDeadline >= now,
  );

  useEffect(() => {
    if (!activeDuel) {
      lastBoostRevision.current = null;
      return;
    }
    if (lastBoostRevision.current === null) {
      lastBoostRevision.current = activeDuel.boost_revision;
      return;
    }
    if (activeDuel.boost_revision <= lastBoostRevision.current) return;
    lastBoostRevision.current = activeDuel.boost_revision;
    const latest = activeDuel.boost_events.at(-1);
    if (!latest) return;
    const notification = window.setTimeout(() => {
      setMessage(
        latest.side === 'you'
          ? `Твоё усиление подтверждено: ${(activeDuel.chance_bps / 100).toFixed(1).replace('.', ',')}%`
          : `Соперник усилился. Твой шанс: ${(activeDuel.chance_bps / 100).toFixed(1).replace('.', ',')}%`,
      );
      haptic(latest.side === 'you' ? 'success' : 'warning');
    }, 0);
    return () => window.clearTimeout(notification);
  }, [activeDuel]);

  const requestedStake = useMemo(() => {
    try {
      return parseGram(stake);
    } catch {
      return 0;
    }
  }, [stake]);
  const terms = useMemo(() => canonicalTerms(requestedStake, chance), [chance, requestedStake]);
  // A verified PLUSH BRICK holder pays no protocol fee on a won duel; the
  // exemption is proven on chain by a permit attached to the offer.
  const feeNano = profile.plush_brick.fee_discount_active
    ? 0
    : (terms.totalPool * profile.plush_brick.duel_fee_bps) / 10_000;
  const payoutNano = terms.totalPool - feeNano;
  const profitNano = payoutNano - terms.stake;
  const boostNano = useMemo(() => {
    try {
      return parseGram(boostAmount);
    } catch {
      return 0;
    }
  }, [boostAmount]);
  const boostedChanceBps = activeDuel
    ? Math.floor(
        ((activeDuel.stake_nano + boostNano) * 10_000) / (activeDuel.total_pool_nano + boostNano),
      )
    : 0;

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
        if (duelBoosting) throw new Error('Сначала дождись конца усиления');
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
  }, [
    activeDuel,
    activeOffer,
    duelBoosting,
    duelExpired,
    offerExpired,
    onRefresh,
    tonConnectUI,
    wallet,
  ]);

  const boostDuel = useCallback(async () => {
    if (locked.current || !activeDuel || !activeOffer || !duelBoosting) return;
    if (boostNano < 100_000_000) {
      setMessage('Минимальное усиление — 0,1 GRAM');
      haptic('warning');
      return;
    }
    if (boostedChanceBps > 9_000) {
      setMessage('Максимальный перевес — 90%');
      haptic('warning');
      return;
    }
    if (!wallet) {
      await tonConnectUI.openModal();
      return;
    }
    locked.current = true;
    setBusy(true);
    try {
      if (!isSupportedTonNetwork(wallet.account.chain)) {
        throw new Error('Этот кошелёк сейчас не поддерживается');
      }
      const contract = await api.contractState('duel');
      if (contract.status !== 'active' || !contract.code_hash_matches) {
        throw new Error('DUEL временно недоступен');
      }
      const intent = await api.boostDuelIntent(activeDuel.onchain_duel_id, {
        amount_nano: boostNano,
        expected_revision: activeDuel.boost_revision,
        min_chance_bps: boostedChanceBps,
      });
      await tonConnectUI.sendTransaction(
        buildBoostTransaction(intent, wallet.account.address, wallet.account.chain, {
          duelId: activeDuel.onchain_duel_id,
          offerId: activeOffer.onchain_offer_id,
          amountNano: boostNano,
          revision: activeDuel.boost_revision,
          minChanceBps: boostedChanceBps,
          contractAddress: contract.address,
        }),
      );
      setMessage('Усиление отправлено. Шанс изменится после подтверждения.');
      await onRefresh();
      haptic('success');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось усилить DUEL');
      haptic('error');
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }, [
    activeDuel,
    activeOffer,
    boostNano,
    boostedChanceBps,
    duelBoosting,
    onRefresh,
    tonConnectUI,
    wallet,
  ]);

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
        : duelBoosting || activeDuel?.own_revealed
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
      ? duelBoosting && activeDuel.boost_deadline
        ? Date.parse(activeDuel.boost_deadline)
        : Date.parse(activeDuel.reveal_deadline)
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
            Старт 50/50. После пары будет минута, чтобы усилить свою сторону.
          </p>
          <details className="technical-details duel-breakdown">
            <summary>
              <span>ВОЗВРАТ И ПРАВИЛА</span>
              <DisclosureIndicator />
            </summary>
            <p>
              После ставки своё число изменить нельзя. Результат нужно открыть самому, и на это есть
              несколько минут после конца усиления. Откроют оба — забирает победитель. Откроет
              только соперник — он забирает весь пул. Не откроет никто — обе ставки вернутся.
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
              ? duelBoosting
                ? 'Соперник найден. Теперь можно изменить перевес.'
                : 'Усиление закрыто. Открой результат.'
              : // Telling the player to close the app is only true while the
                // offer is unmatched. Once a match lands there is no push
                // notification, the secret lives on this device, and a player
                // who does not reveal in time hands the whole pool to the
                // opponent who did.
                'Ищем соперника с такой же ставкой. Ставка уже списана. Как только соперник найдётся, вернись сюда и открой результат — иначе его заберёт соперник.'}
          </strong>
          <div className="duel-live-numbers">
            <span>
              <b>
                {status === 'matched' && activeDuel
                  ? `${(activeDuel.chance_bps / 100).toFixed(1).replace('.', ',')}%`
                  : `${formatGram(activeOffer?.stake_nano ?? terms.stake, 3)} GRAM`}
              </b>
              <small>{status === 'matched' ? 'ТВОЙ ШАНС' : 'ТВОЯ СТАВКА'}</small>
            </span>
            <span>
              <b>{timeLeft(activeDeadline, now)}</b>
              <small>
                {status === 'matched'
                  ? duelBoosting
                    ? 'НА УСИЛЕНИЕ'
                    : 'НА РАСКРЫТИЕ'
                  : 'ДО ИСТЕЧЕНИЯ'}
              </small>
            </span>
          </div>
          {status === 'matched' && activeDuel && duelBoosting && (
            <div className="duel-boost-panel">
              <div className="duel-chance-labels">
                <span>ТЫ {Math.round(activeDuel.chance_bps / 100)}%</span>
                <span>СОПЕРНИК {Math.round((10_000 - activeDuel.chance_bps) / 100)}%</span>
              </div>
              <div className="duel-chance-track" aria-label="Текущие шансы">
                <span style={{ width: `${activeDuel.chance_bps / 100}%` }} />
              </div>
              <label className="boost-input">
                <span>УСИЛИТЬ НА</span>
                <div>
                  <input
                    inputMode="decimal"
                    value={boostAmount}
                    onChange={(event) => setBoostAmount(event.target.value)}
                    aria-label="Сумма усиления в GRAM"
                  />
                  <b>GRAM</b>
                </div>
              </label>
              <div className="boost-quick-values">
                {['0.1', '0.5', '1'].map((value) => (
                  <button
                    key={value}
                    className={boostAmount === value ? 'active' : ''}
                    onClick={() => setBoostAmount(value)}
                  >
                    +{value}
                  </button>
                ))}
              </div>
              <p>
                После подтверждения:{' '}
                <strong>{(boostedChanceBps / 100).toFixed(1).replace('.', ',')}%</strong>
              </p>
              <button className="primary-button" disabled={busy} onClick={() => void boostDuel()}>
                {busy ? 'ПОДТВЕРЖДАЕМ…' : 'УСИЛИТЬ'}
              </button>
              {activeDuel.boost_events.length > 0 && (
                <ol className="duel-boost-events" aria-label="Подтверждённые усиления">
                  {activeDuel.boost_events
                    .slice(-4)
                    .reverse()
                    .map((event) => (
                      <li key={event.tx_hash}>
                        <span>{event.side === 'you' ? 'Ты' : 'Соперник'}</span>
                        <strong>
                          +{formatGram(event.amount_nano, 3)} GRAM ·{' '}
                          {(event.chance_bps / 100).toFixed(1)}%
                        </strong>
                      </li>
                    ))}
                </ol>
              )}
            </div>
          )}
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
