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
        if (wallet.account.chain !== '-3') throw new Error('LOOP работает только в TON testnet');
        if (!profile.wallet) throw new Error('Ждём подтверждение владения внешним кошельком');
        let acceptedInvite = invite;
        if (invite) acceptedInvite = await api.acceptInvite(invite.code);
        const contract = await api.contractState('duel');
        if (
          contract.network !== -3 ||
          contract.status !== 'active' ||
          !contract.code_hash_matches
        ) {
          throw new Error('DUEL contract не прошёл on-chain проверку');
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
        setMessage('Подтверди блокировку тестовых GRAM во внешнем кошельке.');
        await tonConnectUI.sendTransaction(
          buildOpenOfferTransaction(quote, wallet.account.address, wallet.account.chain),
        );
        setMessage('Ждём on-chain подтверждение. Callback кошелька ещё не результат.');
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
        if (!activeDuel) throw new Error('Синхронизируем DUEL с сетью');
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
        throw new Error('Ждём подтверждение TON');
      }
      await tonConnectUI.sendTransaction(
        buildActionTransaction(intent, wallet.account.address, wallet.account.chain, secret),
      );
      setMessage('Транзакция отправлена. Ждём финализацию TON.');
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
      setMessage('Сначала дождись on-chain подтверждения вызова.');
      haptic('warning');
      return;
    }
    const app = telegram();
    if (!app?.switchInlineQuery) {
      setMessage('Telegram inline доступен внутри Mini App.');
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
        <p className="eyebrow">TESTNET · ВЫЗОВ 1 НА 1</p>
        <h1 id="duel-title">DUEL</h1>
      </header>

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

      {status === 'idle' && (
        <div className="duel-form">
          {invite ? (
            <div className="invite-banner">
              <p className="eyebrow">
                ВЫЗОВ ОТ {invite.creator_name.toUpperCase()} · {chance / 100}/
                {(10_000 - chance) / 100}
              </p>
              <strong>Условия проверяются заново перед принятием.</strong>
            </div>
          ) : (
            <>
              <label className="stake-input">
                <span className="stake-input-heading">
                  <span>ТВОЯ СТАВКА</span>
                  <span className="stake-edit-cue">ИЗМЕНИТЬ</span>
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

          <dl className="duel-terms duel-primary-terms">
            <Term label="Твоя ставка" value={`${formatGram(terms.stake, 3)} GRAM`} />
            <Term
              label={invite ? 'Ставка создателя' : 'Соперник должен внести'}
              value={`${formatGram(terms.opponentStake, 3)} GRAM`}
            />
            <Term label="Выплата победителю" value={`${formatGram(payoutNano, 3)} GRAM`} />
          </dl>
          <p className="duel-deadline-rule">
            <ShieldCheck aria-hidden="true" />
            После матча открой результат за 5 минут. Если соперник откроет, а ты нет — он получит
            выплату.
          </p>
          <details className="technical-details duel-breakdown">
            <summary>
              <span>РАСЧЁТ И ПРАВИЛА</span>
              <DisclosureIndicator />
            </summary>
            <dl className="detail-list">
              <Term label="Общий пул" value={`${formatGram(terms.totalPool, 3)} GRAM`} />
              <Term
                label={`Комиссия DUEL · ${profile.plush_brick.duel_fee_bps / 100}%`}
                value={`${formatGram(feeNano, 4)} GRAM`}
              />
              <Term label="Чистый результат победы" value={`+${formatGram(profitNano, 3)} GRAM`} />
            </dl>
            <p>
              Если никто не откроет результат, контракт вернёт обе ставки. Открытый поиск можно
              остановить и вернуть свою ставку on-chain.
            </p>
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
                : 'AFK ПОИСК'}
          </p>
          <strong>
            {status === 'matched'
              ? 'Соперник найден. Открой результат.'
              : 'Ищем равную ставку. Можно закрыть Mini App.'}
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
              Поиск можно остановить в любой момент: контракт вернёт ставку после отдельного
              подтверждения в TON.
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
              Проверить settlement <ArrowSquareOut aria-hidden="true" />
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
                className="secondary-button"
                disabled={busy}
                onClick={() => void start('direct')}
              >
                <PaperPlaneTilt aria-hidden="true" /> СОЗДАТЬ ПРЯМОЙ ВЫЗОВ
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
