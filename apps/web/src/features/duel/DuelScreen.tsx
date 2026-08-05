import {
  ArrowSquareOut,
  PaperPlaneTilt,
  ShieldCheck,
  UsersThree,
  WarningCircle,
} from '@phosphor-icons/react';
import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../../api';
import { DisclosureIndicator } from '../../components/DisclosureIndicator';
import {
  haptic,
  isMockTelegram,
  markDuelSeen,
  readDuelSecret,
  readSeenDuelId,
  storeDuelSecret,
  telegram,
} from '../../telegram';
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

import { requireLinkedWallet, sameAddress } from '../../address';

import { celebrate } from '../../celebrate';
import { humanError } from '../../errors';
import { ChanceBar, type ChancePhase } from './ChanceBar';

const DEFAULT_CHANCE_BPS = 5000;
const FUNDING_BROADCAST_NOTICE =
  'Ставка отправлена. Обычно она появляется в DUEL за несколько секунд.';
const FUNDING_CONFIRMED_NOTICE = 'Ставка в игре. Можно пригласить соперника.';
const DIRECT_FUNDING_CONFIRMED_NOTICE = 'Ставка в игре. Отправь вызов другу.';
const REVEAL_BROADCAST_NOTICE = 'Кошелёк отправил ход. Ждём подтверждение в сети.';
const PENDING_ACTION_STORAGE_KEY = 'loop.duel.pending-action.v1';
// A wallet message is valid for five minutes. Keep the action locked for the
// same window so a delayed wallet broadcast cannot be signed twice.
const PENDING_ACTION_TTL_MS = 330_000;
const PROJECTION_POLL_MS = 2_000;
// A boost sent in the final second can reach the indexer a few seconds after
// the visible clock reaches zero. During this short reconciliation window the
// contract may legally extend the response time, so do not claim reveal has
// started yet.
const BOOST_PROJECTION_GRACE_MS = 12_000;

type PendingActionKind = 'reveal' | 'cancel_offer' | 'expire_offer' | 'expire_duel';

type PendingAction = {
  offerId: number;
  kind: PendingActionKind;
  startedAt: number;
};

function readPendingAction(): PendingAction | null {
  try {
    const raw = window.localStorage.getItem(PENDING_ACTION_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<PendingAction>;
    if (
      typeof value.offerId !== 'number' ||
      typeof value.startedAt !== 'number' ||
      !['reveal', 'cancel_offer', 'expire_offer', 'expire_duel'].includes(value.kind ?? '') ||
      Date.now() - value.startedAt >= PENDING_ACTION_TTL_MS
    ) {
      window.localStorage.removeItem(PENDING_ACTION_STORAGE_KEY);
      return null;
    }
    return value as PendingAction;
  } catch {
    return null;
  }
}

function storePendingAction(value: PendingAction | null): void {
  try {
    if (value) window.localStorage.setItem(PENDING_ACTION_STORAGE_KEY, JSON.stringify(value));
    else window.localStorage.removeItem(PENDING_ACTION_STORAGE_KEY);
  } catch {
    // A private WebView may disable storage. The in-memory lock still works.
  }
}
// Four digits everywhere on the money card: at three, a 0,01 stake rounded the
// payout up to the whole bank and the card claimed the fee was both taken and
// not taken at the same time.
const MONEY_DIGITS = 4;
// The contract refuses to push either side past ninety percent.
const MAX_CHANCE_BPS = 9000;

/** A fee stated as a rate, not just as an unexplained subtraction. */
function feePercentOf(feeNano: number, poolNano: number): string {
  if (poolNano <= 0) return '';
  return `${((feeNano * 100) / poolNano).toFixed(1).replace('.', ',').replace(',0', '')}%`;
}

function canonicalTerms(requestedStake: number, chanceBps: number) {
  const quarterUnits = chanceBps / 2500;
  const poolUnit = Math.floor((requestedStake + quarterUnits - 1) / quarterUnits);
  const stake = quarterUnits * poolUnit;
  const opponentStake = (4 - quarterUnits) * poolUnit;
  return { stake, opponentStake, totalPool: 4 * poolUnit };
}

/** Keeps a money field to digits and a single separator, as it is typed. */
function sanitizeAmount(value: string): string {
  const cleaned = value.replace(/[^\d.,]/g, '').replace(/[.,]/g, ',');
  const [whole, ...rest] = cleaned.split(',');
  const fraction = rest.join('').slice(0, 9);
  return rest.length ? `${whole.slice(0, 12)},${fraction}` : whole.slice(0, 12);
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
  onDeclineInvite,
  onRefresh,
}: {
  profile: Profile;
  offers: Offer[];
  duels: Duel[];
  invite: Invite | null;
  onDeclineInvite?: () => void;
  onRefresh: () => Promise<void>;
}) {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  // The launch cap can make the pool bounds meet, and then exactly one stake is
  // possible. Offering anything else guarantees a rejected quote, so the field
  // starts at the smallest allowed amount rather than at a round number.
  const minStake = profile.duel_stake.min_stake_nano;
  const maxStake = profile.duel_stake.max_stake_nano;
  const stakeFixed = minStake === maxStake;
  const [stake, setStake] = useState(() => formatGram(invite ? invite.stake_nano : minStake, 3));
  const [boostAmount, setBoostAmount] = useState('0.5');
  const chance = invite?.chance_bps ?? DEFAULT_CHANCE_BPS;
  const [mode, setMode] = useState<'afk' | 'direct'>(invite ? 'direct' : 'afk');
  const [busy, setBusy] = useState(false);
  const [boostPanelDuelId, setBoostPanelDuelId] = useState<string | null>(null);
  const [mockSearching, setMockSearching] = useState(false);
  const [mockExpiresAt, setMockExpiresAt] = useState<number | null>(null);
  const [notice, setNotice] = useState<{ text: string; tone: 'info' | 'error' }>(() => ({
    text: invite ? `${invite.creator_name} бросил тебе вызов.` : '',
    tone: 'info',
  }));
  const setMessage = useCallback((text: string) => setNotice({ text, tone: 'info' }), []);
  const failed = useCallback((text: string) => setNotice({ text, tone: 'error' }), []);
  const [now, setNow] = useState(() => Date.now());
  const [seenDuelId, setSeenDuelId] = useState(() => readSeenDuelId());
  const locked = useRef(false);
  const lastBoostRevision = useRef<number | null>(null);
  /** The quote holding this wallet's offer slot until the wallet answers. */
  const quotedOffer = useRef<number | null>(null);
  /** Null until the contract has been asked; then whether it accepts deposits. */
  const [duelClosed, setDuelClosed] = useState<boolean | null>(null);
  /** Set the moment the wallet accepts, so the screen stops asking for a signature. */
  const [signedOffer, setSignedOffer] = useState<number | null>(null);
  /** A broadcast action stays locked until the chain projection changes. */
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(readPendingAction);
  const onRefreshRef = useRef(onRefresh);

  useEffect(() => {
    onRefreshRef.current = onRefresh;
  }, [onRefresh]);

  useEffect(() => {
    if (isMockTelegram()) return;
    // Asked once on arrival so a closed DUEL is a closed screen, not a form
    // that takes a stake and then refuses it.
    void api
      .contractState('duel')
      .then((contract) => setDuelClosed(contract.paused !== false))
      .catch(() => setDuelClosed(null));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const activeOffer = offers.find((offer) =>
    ['pending_funding', 'open', 'reserved', 'matched'].includes(offer.state),
  );

  useEffect(() => {
    if (
      signedOffer === null ||
      activeOffer?.onchain_offer_id !== signedOffer ||
      !['open', 'reserved', 'matched'].includes(activeOffer.state)
    ) {
      return;
    }
    const confirmation = window.setTimeout(() => {
      setSignedOffer(null);
      haptic('success');
    }, 0);
    return () => window.clearTimeout(confirmation);
  }, [activeOffer, signedOffer]);

  const activeDuel = activeOffer
    ? duels.find(
        (duel) =>
          duel.offer_id === activeOffer.onchain_offer_id &&
          ['boosting', 'revealing'].includes(duel.state),
      )
    : undefined;

  const clearPendingAction = useCallback(() => {
    setPendingAction(null);
    storePendingAction(null);
  }, []);

  useEffect(() => {
    if (!pendingAction) return;
    const sameOffer = activeOffer?.onchain_offer_id === pendingAction.offerId;
    const completed =
      !sameOffer ||
      (pendingAction.kind === 'reveal' && activeDuel?.own_revealed === true) ||
      (pendingAction.kind === 'expire_duel' && activeDuel === undefined);
    if (!completed) return;
    const timeout = window.setTimeout(clearPendingAction, 0);
    return () => window.clearTimeout(timeout);
  }, [activeDuel, activeOffer, clearPendingAction, pendingAction]);

  useEffect(() => {
    if (!pendingAction) return;
    const remaining = PENDING_ACTION_TTL_MS - (Date.now() - pendingAction.startedAt);
    const timeout = window.setTimeout(clearPendingAction, Math.max(0, remaining));
    return () => window.clearTimeout(timeout);
  }, [clearPendingAction, pendingAction]);

  // TON Connect only tells us that the wallet broadcast a message. Poll the
  // server projection until the contract transaction becomes visible instead
  // of leaving the player on a stale intermediate screen for an arbitrary
  // global refresh interval.
  const projectionWatchKey =
    signedOffer !== null
      ? `funding:${signedOffer}`
      : pendingAction
        ? `action:${pendingAction.offerId}:${pendingAction.kind}`
        : null;
  useEffect(() => {
    if (!projectionWatchKey || isMockTelegram()) return;
    let stopped = false;
    let timeout: number | undefined;
    const startedAt = Date.now();
    const poll = async () => {
      if (stopped) return;
      await onRefreshRef.current().catch(() => undefined);
      if (!stopped && Date.now() - startedAt < PENDING_ACTION_TTL_MS) {
        timeout = window.setTimeout(() => void poll(), PROJECTION_POLL_MS);
      }
    };
    void poll();
    return () => {
      stopped = true;
      if (timeout !== undefined) window.clearTimeout(timeout);
    };
  }, [projectionWatchKey]);
  const latestDuel = duels[0];
  const offerExpired = activeOffer ? Date.parse(activeOffer.expires_at) <= now : false;
  const duelExpired = activeDuel ? Date.parse(activeDuel.reveal_deadline) <= now : false;
  const boostDeadline = activeDuel?.boost_deadline ? Date.parse(activeDuel.boost_deadline) : null;
  const duelBoosting = Boolean(
    activeDuel && activeDuel.state === 'boosting' && boostDeadline && boostDeadline >= now,
  );
  const boostClosing = Boolean(
    activeDuel &&
    activeDuel.state === 'boosting' &&
    boostDeadline &&
    boostDeadline < now &&
    now - boostDeadline < BOOST_PROJECTION_GRACE_MS,
  );
  const boostPanelOpen = Boolean(activeDuel && duelBoosting && boostPanelDuelId === activeDuel.id);

  // TON Connect resolves when the wallet broadcasts the external message,
  // not when the DUEL contract has processed the internal one. Derive the
  // visible copy from the chain projection so a broadcast notice cannot stay
  // behind after confirmation.
  const message =
    notice.text === FUNDING_BROADCAST_NOTICE
      ? activeOffer?.state === 'open' || activeOffer?.state === 'reserved'
        ? activeOffer.mode === 'direct'
          ? DIRECT_FUNDING_CONFIRMED_NOTICE
          : FUNDING_CONFIRMED_NOTICE
        : activeOffer?.state === 'matched' || (!activeOffer && signedOffer === null)
          ? ''
          : notice.text
      : notice.text === REVEAL_BROADCAST_NOTICE
        ? activeDuel?.own_revealed
          ? 'Твой ход подтверждён. Теперь очередь соперника.'
          : activeDuel || activeOffer
            ? notice.text
            : ''
        : notice.text;

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
          ? `Твоё усиление подтверждено. Шанс ${(activeDuel.chance_bps / 100)
              .toFixed(1)
              .replace('.', ',')}%. Время на ответ обновлено.`
          : `Ставка соперника подтверждена. Твой шанс ${(activeDuel.chance_bps / 100)
              .toFixed(1)
              .replace('.', ',')}%. Время на ответ обновлено.`,
      );
      haptic(latest.side === 'you' ? 'success' : 'warning');
    }, 0);
    return () => window.clearTimeout(notification);
  }, [activeDuel, setMessage]);

  const requestedStake = useMemo(() => {
    try {
      return parseGram(stake);
    } catch {
      return 0;
    }
  }, [stake]);
  const terms = useMemo(() => canonicalTerms(requestedStake, chance), [chance, requestedStake]);
  const feeNano = profile.plush_brick.fee_discount_active
    ? 0
    : (terms.totalPool * profile.plush_brick.duel_fee_bps) / 10_000;
  const payoutNano = terms.totalPool - feeNano;
  const boostNano = useMemo(() => {
    try {
      return parseGram(boostAmount);
    } catch {
      return 0;
    }
  }, [boostAmount]);
  const boostedChanceBps = activeDuel
    ? Math.min(
        MAX_CHANCE_BPS,
        Math.floor(
          ((activeDuel.stake_nano + boostNano) * 10_000) / (activeDuel.total_pool_nano + boostNano),
        ),
      )
    : 0;
  const boostHitsCeiling = activeDuel !== undefined && boostedChanceBps >= MAX_CHANCE_BPS;

  const status =
    latestDuel?.state === 'settled' && latestDuel.id !== seenDuelId
      ? 'result'
      : activeOffer?.state === 'matched'
        ? 'matched'
        : activeOffer || mockSearching
          ? 'searching'
          : 'idle';
  const resultWon = Boolean(
    latestDuel?.winner_wallet && sameAddress(latestDuel.winner_wallet, profile.wallet?.address),
  );
  // A duel resolves in an instant and the screen simply swaps to the result.
  // The win gets a burst; the loss gets nothing — celebrating someone's money
  // leaving is mockery, not humour.
  const celebratedDuel = useRef<string | null>(null);
  useEffect(() => {
    if (status !== 'result' || !latestDuel || celebratedDuel.current === latestDuel.id) return;
    celebratedDuel.current = latestDuel.id;
    if (!resultWon) return;
    // The bar takes half a second to claim the whole pool. Fire on its landing,
    // not on its start — otherwise the burst celebrates something still moving.
    const burst = window.setTimeout(() => celebrate(), 460);
    return () => window.clearTimeout(burst);
  }, [latestDuel, resultWon, status]);

  const resultDeltaNano = latestDuel
    ? resultWon
      ? latestDuel.payout_nano - latestDuel.stake_nano
      : latestDuel.stake_nano
    : 0;

  const start = useCallback(
    async (selectedMode: 'afk' | 'direct') => {
      if (locked.current || activeOffer) return;
      locked.current = true;
      setBusy(true);
      setMode(selectedMode);
      try {
        if (!invite && (requestedStake < minStake || requestedStake > maxStake)) {
          throw new Error(
            stakeFixed
              ? `Сейчас ставка — ровно ${formatGram(minStake, 3)} GRAM`
              : `Ставка должна быть от ${formatGram(minStake, 3)} до ${formatGram(maxStake, 3)} GRAM`,
          );
        }
        if (isMockTelegram()) {
          setMockSearching(true);
          setMockExpiresAt(Date.now() + 15 * 60_000);
          setMessage(selectedMode === 'afk' ? '' : 'Вызов создан. Отправь его другу.');
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
        const from = requireLinkedWallet(profile.wallet, wallet.account);
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
        // A paused contract rejects every deposit and bounces the stake back
        // minus gas. Never ask for a signature over one.
        setDuelClosed(contract.paused !== false);
        if (contract.paused !== false) throw new Error('DUEL сейчас закрыт');
        const offerId = newOfferId();
        const secret = newSecret();
        const commitment = commitmentForOffer(
          offerId,
          from,
          secret,
          contract.network,
          contract.address,
        );
        quotedOffer.current = offerId;
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
        setMessage('Подтверди ставку в кошельке.');
        await tonConnectUI.sendTransaction(
          buildOpenOfferTransaction(quote, from, wallet.account.chain),
        );
        quotedOffer.current = null;
        setSignedOffer(offerId);
        setMessage(FUNDING_BROADCAST_NOTICE);
        haptic('success');
      } catch (error) {
        // A refused signature must leave the screen exactly as it was. The
        // quote already holds this wallet's only offer slot, so it has to go
        // before anything else — otherwise the player watches a search for a
        // duel that does not exist and cannot start another for fifteen minutes.
        const abandoned = quotedOffer.current;
        quotedOffer.current = null;
        if (abandoned !== null) {
          await api.discardOffer(abandoned).catch(() => undefined);
          await onRefresh().catch(() => undefined);
        }
        const notice = humanError(error, 'Не удалось создать DUEL');
        if (notice) failed(notice);
        else setMessage('');
        haptic(notice ? 'error' : 'selection');
      } finally {
        locked.current = false;
        setBusy(false);
      }
    },
    [
      activeOffer,
      chance,
      failed,
      invite,
      maxStake,
      minStake,
      onRefresh,
      profile.wallet,
      requestedStake,
      setMessage,
      stakeFixed,
      terms.stake,
      terms.opponentStake,
      terms.totalPool,
      tonConnectUI,
      wallet,
    ],
  );

  const abandonQuote = useCallback(
    async (offerId: number) => {
      setBusy(true);
      try {
        await api.discardOffer(offerId);
        setSignedOffer(null);
        setMessage('');
        await onRefresh();
        haptic('success');
      } catch {
        // Funded offers belong to the chain; the wallet has to cancel those.
        failed('Ставка уже ушла в сеть — дождись подтверждения');
        haptic('error');
      } finally {
        setBusy(false);
      }
    },
    [failed, onRefresh, setMessage],
  );

  const runActiveAction = useCallback(async () => {
    if (locked.current || pendingAction || !activeOffer) return;
    if (!wallet) {
      await tonConnectUI.openModal();
      return;
    }
    locked.current = true;
    setBusy(true);
    try {
      const from = requireLinkedWallet(profile.wallet, wallet.account);
      let intent;
      let secret: string | undefined;
      if (activeOffer.state === 'matched') {
        if (!activeDuel) throw new Error('Обновляем состояние DUEL');
        if (duelBoosting) throw new Error('Сначала дождись конца усиления');
        if (boostClosing) throw new Error('Проверяем последние ставки');
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
        throw new Error('Ждём, пока сеть подтвердит предыдущее действие');
      }
      await tonConnectUI.sendTransaction(
        buildActionTransaction(intent, from, wallet.account.chain, secret),
      );
      const action = {
        offerId: activeOffer.onchain_offer_id,
        kind: intent.operation,
        startedAt: Date.now(),
      } satisfies PendingAction;
      setPendingAction(action);
      storePendingAction(action);
      setMessage(
        intent.operation === 'cancel_offer' || intent.operation === 'expire_offer'
          ? 'LOOP возвращает ставку. Это обычно занимает несколько секунд.'
          : intent.operation === 'reveal'
            ? REVEAL_BROADCAST_NOTICE
            : 'Запрос отправлен. LOOP проверяет результат.',
      );
      haptic('success');
    } catch (error) {
      const notice = humanError(error, 'Действие не выполнено');
      if (notice) failed(notice);
      else setMessage('');
      haptic(notice ? 'error' : 'selection');
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }, [
    activeDuel,
    activeOffer,
    boostClosing,
    duelBoosting,
    duelExpired,
    failed,
    offerExpired,
    pendingAction,
    profile.wallet,
    setMessage,
    tonConnectUI,
    wallet,
  ]);

  const boostDuel = useCallback(async () => {
    if (locked.current || !activeDuel || !activeOffer || !duelBoosting) return;
    if (boostNano < 100_000_000) {
      failed('Минимальное усиление — 0,1 GRAM');
      haptic('warning');
      return;
    }
    if (boostedChanceBps > 9_000) {
      failed('Максимальный перевес — 90%');
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
      const from = requireLinkedWallet(profile.wallet, wallet.account);
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
        buildBoostTransaction(intent, from, wallet.account.chain, {
          duelId: activeDuel.onchain_duel_id,
          offerId: activeOffer.onchain_offer_id,
          amountNano: boostNano,
          revision: activeDuel.boost_revision,
          minChanceBps: boostedChanceBps,
          contractAddress: contract.address,
        }),
      );
      setMessage('Ждём подтверждение. После него шанс изменится.');
      setBoostPanelDuelId(null);
      await onRefresh();
      haptic('success');
    } catch (error) {
      const notice = humanError(error, 'Не удалось усилить DUEL');
      if (notice) failed(notice);
      else setMessage('');
      haptic(notice ? 'error' : 'selection');
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
    failed,
    onRefresh,
    profile.wallet,
    setMessage,
    tonConnectUI,
    wallet,
  ]);

  function inviteToTelegram() {
    if (mockSearching && !activeOffer) {
      haptic('selection');
      return;
    }
    if (!activeOffer || activeOffer.state !== 'open' || offerExpired) {
      failed('Сначала дождись, пока вызов появится в сети.');
      haptic('warning');
      return;
    }
    const app = telegram();
    if (activeOffer.mode === 'direct') {
      if (!app?.switchInlineQuery) {
        failed('Приглашение в Telegram доступно только внутри приложения.');
        return;
      }
      app.switchInlineQuery(`duel ${activeOffer.onchain_offer_id}`, ['users', 'groups']);
      haptic('light');
      return;
    }
    if (!app?.openTelegramLink) {
      failed('Приглашение в Telegram доступно только внутри приложения.');
      return;
    }
    const duelUrl = 'https://t.me/getloopbot?startapp=duel';
    const text = `Я ищу соперника в LOOP DUEL. Ставка ${formatGram(activeOffer.stake_nano, 3)} GRAM. Сразимся?`;
    app.openTelegramLink(
      `https://t.me/share/url?url=${encodeURIComponent(duelUrl)}&text=${encodeURIComponent(text)}`,
    );
    haptic('light');
  }

  const pendingActionLabel = pendingAction
    ? pendingAction.kind === 'cancel_offer' || pendingAction.kind === 'expire_offer'
      ? 'ВОЗВРАЩАЕМ…'
      : pendingAction.kind === 'reveal'
        ? 'ОТКРЫВАЕМ…'
        : 'ЗАВЕРШАЕМ…'
    : null;
  const activeActionLabel =
    pendingActionLabel ??
    (activeOffer
      ? activeOffer.state === 'matched'
        ? duelExpired
          ? 'ЗАВЕРШИТЬ ДУЭЛЬ'
          : duelBoosting || boostClosing || activeDuel?.own_revealed
            ? null
            : 'ОТКРЫТЬ РЕЗУЛЬТАТ'
        : activeOffer.state === 'open' || activeOffer.state === 'reserved'
          ? offerExpired
            ? 'ВЕРНУТЬ СТАВКУ'
            : 'ОСТАНОВИТЬ ПОИСК'
          : null
      : mockSearching
        ? 'ОСТАНОВИТЬ ПОИСК'
        : null);
  const activeDeadline =
    status === 'matched' && activeDuel
      ? boostClosing || (pendingAction?.kind === 'reveal' && !activeDuel.own_revealed)
        ? null
        : duelBoosting && activeDuel.boost_deadline
          ? Date.parse(activeDuel.boost_deadline)
          : Date.parse(activeDuel.reveal_deadline)
      : activeOffer
        ? Date.parse(activeOffer.expires_at)
        : mockExpiresAt;
  const liveMode = activeOffer?.mode ?? mode;

  // Everything the bar shows, derived once. `live` covers both the boost window
  // and the reveal window: in both the odds are settled facts and the clock is
  // the thing under pressure.
  // A quote holds the wallet's offer slot before the wallet has answered,
  // and that is not a search: nothing is on chain to find an opponent for.
  const awaitingSignature = activeOffer?.state === 'pending_funding';
  const chancePhase: ChancePhase =
    status === 'result'
      ? resultWon
        ? 'won'
        : 'lost'
      : status === 'matched'
        ? 'live'
        : awaitingSignature
          ? 'idle'
          : status;
  const chanceShare =
    status === 'matched' && activeDuel ? activeDuel.chance_bps / 10_000 : chance / 10_000;
  const chanceWindowMs =
    status === 'matched' && activeDeadline ? Math.max(0, activeDeadline - now) : null;
  // Only the boost phase has a second, absolute end to drain against: the hard
  // cap the contract will not extend past however many boosts arrive.
  // Four digits everywhere: at three a 0,01 stake rounded the payout up to the
  // bank and the card claimed the fee was both taken and not taken.
  const shownPool = activeDuel?.total_pool_nano ?? activeOffer?.total_pool_nano ?? terms.totalPool;
  const shownPayout = activeDuel?.payout_nano ?? activeOffer?.payout_nano ?? payoutNano;
  const shownFee = Math.max(0, shownPool - shownPayout);
  const shownStake = activeDuel?.stake_nano ?? activeOffer?.stake_nano ?? terms.stake;
  const feePercentText = `${((shownFee * 100) / Math.max(1, shownPool)).toFixed(1).replace('.', ',').replace(',0', '')}%`;
  const liveEyebrow = awaitingSignature
    ? signedOffer === activeOffer?.onchain_offer_id
      ? 'ПРОВЕРЯЕМ СТАВКУ В СЕТИ'
      : 'ЖДЁМ ПОДПИСЬ В КОШЕЛЬКЕ'
    : status === 'matched'
      ? pendingAction?.kind === 'reveal' && !activeDuel?.own_revealed
        ? 'ПОДТВЕРЖДАЕМ ТВОЙ ХОД'
        : duelBoosting
          ? 'УСИЛЕНИЕ ОТКРЫТО'
          : boostClosing
            ? 'ПРОВЕРЯЕМ ПОСЛЕДНИЕ СТАВКИ'
            : activeDuel?.own_revealed
              ? 'ЖДЁМ ХОД СОПЕРНИКА'
              : 'ОТКРОЙ РЕЗУЛЬТАТ'
      : status === 'searching'
        ? offerExpired
          ? 'СРОК ВЫЗОВА ИСТЁК'
          : liveMode === 'direct'
            ? 'ПРЯМОЙ ВЫЗОВ'
            : 'ИЩЕМ СОПЕРНИКА'
        : null;
  const chanceDrain =
    duelBoosting && activeDuel?.boost_deadline && activeDuel.hard_deadline
      ? (Date.parse(activeDuel.boost_deadline) - now) /
        Math.max(1000, Date.parse(activeDuel.hard_deadline) - now)
      : null;

  return (
    <section className="screen duel-screen" aria-labelledby="duel-title">
      <header className={`mode-header${status === 'idle' ? '' : ' is-compact'}`}>
        {status === 'idle' && <p className="eyebrow">ИГРА 1 НА 1</p>}
        <h1 id="duel-title">DUEL</h1>
      </header>

      {liveEyebrow && <p className="duel-live-eyebrow">{liveEyebrow}</p>}

      <ChanceBar
        mine={chanceShare}
        phase={chancePhase}
        remainingMs={chanceWindowMs}
        drain={chanceDrain}
        caption={
          status === 'matched'
            ? boostClosing || (pendingAction?.kind === 'reveal' && !activeDuel?.own_revealed)
              ? undefined
              : duelBoosting
                ? 'ДО КОНЦА СТАВОК'
                : 'ДО АВТОМАТИЧЕСКОГО ИСХОДА'
            : undefined
        }
      />

      {status === 'idle' && duelClosed && (
        <div className="duel-form duel-closed">
          <p>
            DUEL сейчас закрыт: контракт не принимает ставки. Здесь ничего не потеряешь — просто
            заходи позже.
          </p>
        </div>
      )}

      {status === 'idle' && !duelClosed && (
        <div className="duel-form">
          {invite ? (
            <div className="invite-banner">
              <p className="eyebrow">
                ТЕБЯ ВЫЗЫВАЕТ {invite.creator_name.toUpperCase()} · {chance / 100}/
                {(10_000 - chance) / 100}
              </p>
              <strong>{formatGram(terms.stake, 3)} GRAM</strong>
              <span>ТВОЯ СТАВКА</span>
            </div>
          ) : (
            <>
              <label className="stake-input">
                <span className="stake-input-heading">
                  <span>СТАВКА</span>
                  <span className="stake-edit-cue">
                    {stakeFixed
                      ? `РОВНО ${formatGram(minStake, 3)}`
                      : `${formatGram(minStake, 3)}–${formatGram(maxStake, 3)}`}
                  </span>
                </span>
                <div>
                  <input
                    inputMode="decimal"
                    value={stake}
                    onChange={(event) => setStake(sanitizeAmount(event.target.value))}
                    aria-label="Ставка в GRAM"
                  />
                  <b>GRAM</b>
                </div>
              </label>
            </>
          )}

          <p className="duel-simple-rule">
            Соперник внесёт столько же. Победитель забирает банк за вычетом комиссии{' '}
            {feePercentText}.
          </p>
        </div>
      )}

      {(status === 'searching' || status === 'matched') && (
        <div className="duel-live-state">
          {status === 'searching' && (
            <div className="duel-live-focus">
              <strong>{`${formatGram(activeOffer?.stake_nano ?? terms.stake, 3)} GRAM`}</strong>
              <span>{timeLeft(activeDeadline, now)}</span>
            </div>
          )}

          {status === 'matched' && activeDuel && duelBoosting && (
            <>
              {!boostPanelOpen && (
                <button
                  className="secondary-button duel-boost-toggle"
                  onClick={() => {
                    setBoostPanelDuelId(activeDuel.id);
                    haptic('selection');
                  }}
                >
                  УВЕЛИЧИТЬ ШАНС
                </button>
              )}
              {boostPanelOpen && (
                <motion.div
                  className="duel-boost-panel"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <label className="boost-input">
                    <span>СКОЛЬКО ДОБАВИТЬ</span>
                    <div>
                      <input
                        inputMode="decimal"
                        value={boostAmount}
                        onChange={(event) => setBoostAmount(sanitizeAmount(event.target.value))}
                        aria-label="Сумма усиления в GRAM"
                      />
                      <b>GRAM</b>
                    </div>
                  </label>
                  <div className="boost-quick-values">
                    {[100_000_000, 500_000_000, 1_000_000_000].map((step) => (
                      <button
                        key={step}
                        onClick={() => setBoostAmount(formatGram(boostNano + step, MONEY_DIGITS))}
                      >
                        +{formatGram(step, MONEY_DIGITS)}
                      </button>
                    ))}
                  </div>
                  <dl className="detail-list boost-terms">
                    <Term
                      label="Сейчас твой шанс"
                      value={`${(activeDuel.chance_bps / 100).toFixed(1).replace('.', ',')}%`}
                    />
                    <Term
                      label="Станет"
                      value={`${(boostedChanceBps / 100).toFixed(1).replace('.', ',')}%${
                        boostHitsCeiling ? ' (потолок)' : ''
                      }`}
                    />
                    <Term
                      label="Банк станет"
                      value={`${formatGram(activeDuel.total_pool_nano + boostNano, MONEY_DIGITS)} GRAM`}
                    />
                  </dl>
                  <button
                    className="primary-button"
                    disabled={busy}
                    onClick={() => void boostDuel()}
                  >
                    {busy ? 'ОТПРАВЛЯЕМ…' : `ДОБАВИТЬ ${formatGram(boostNano, MONEY_DIGITS)} GRAM`}
                  </button>
                  <button className="duel-boost-dismiss" onClick={() => setBoostPanelDuelId(null)}>
                    НЕ СЕЙЧАС
                  </button>
                </motion.div>
              )}
            </>
          )}
        </div>
      )}

      {status === 'idle' && !boostPanelOpen && (
        <details className="technical-details duel-rules">
          <summary>
            <span>ПРАВИЛА</span>
            <DisclosureIndicator />
          </summary>
          <div className="duel-rules-body">
            <p>
              Соперник вносит столько же. После встречи у обоих есть минута, чтобы увеличить свой
              шанс.
            </p>
            <dl className="detail-list">
              <Term label="Твоя ставка" value={`${formatGram(shownStake, MONEY_DIGITS)} GRAM`} />
              <Term label="Общий банк" value={`${formatGram(shownPool, MONEY_DIGITS)} GRAM`} />
              <Term
                label={`Комиссия ${feePercentText}`}
                value={`−${formatGram(shownFee, MONEY_DIGITS)} GRAM`}
              />
              <Term
                label="Победитель получит"
                value={`${formatGram(shownPayout, MONEY_DIGITS)} GRAM`}
              />
              <Term
                label="При победе"
                value={`+${formatGram(shownPayout - shownStake, MONEY_DIGITS)} GRAM`}
              />
              <Term label="При проигрыше" value={`−${formatGram(shownStake, MONEY_DIGITS)} GRAM`} />
            </dl>
            <p>
              Затем каждый открывает результат. Открыли оба — выигрывает тот, кому выпал его шанс.
              Открыл только один — он и выигрывает. Не открыл никто — ставки возвращаются целиком,
              без комиссии.
            </p>
            {activeDuel && activeDuel.boost_events.length > 0 && (
              <>
                <p className="duel-rules-caption">ХОД ДУЭЛИ</p>
                <ol className="duel-boost-events" aria-label="Подтверждённые усиления">
                  {activeDuel.boost_events
                    .slice()
                    .reverse()
                    .map((event) => (
                      <li key={event.tx_hash}>
                        <span>{event.side === 'you' ? 'Ты' : 'Соперник'}</span>
                        <strong>
                          +{formatGram(event.amount_nano, 3)} GRAM ·{' '}
                          {(event.chance_bps / 100).toFixed(1).replace('.', ',')}%
                        </strong>
                      </li>
                    ))}
                </ol>
              </>
            )}
          </div>
        </details>
      )}

      {status === 'result' && latestDuel && (
        <div className="duel-result">
          <p className="eyebrow">{resultWon ? 'ПОБЕДА' : 'ПОРАЖЕНИЕ'}</p>
          <strong>{`${resultWon ? '+' : '−'}${formatGram(resultDeltaNano, 3)} GRAM`}</strong>
          <dl className="detail-list duel-result-breakdown">
            <Term
              label="Твоя ставка"
              value={`${formatGram(latestDuel.stake_nano, MONEY_DIGITS)} GRAM`}
            />
            <Term
              label="Общий банк"
              value={`${formatGram(latestDuel.total_pool_nano, MONEY_DIGITS)} GRAM`}
            />
            <Term
              label={`Комиссия ${feePercentOf(
                latestDuel.total_pool_nano - latestDuel.payout_nano,
                latestDuel.total_pool_nano,
              )}`}
              value={`−${formatGram(
                Math.max(0, latestDuel.total_pool_nano - latestDuel.payout_nano),
                MONEY_DIGITS,
              )} GRAM`}
            />
            <Term
              label={resultWon ? 'Пришло в кошелёк' : 'Ушло сопернику'}
              value={`${formatGram(
                resultWon ? latestDuel.payout_nano : latestDuel.stake_nano,
                MONEY_DIGITS,
              )} GRAM`}
            />
          </dl>
        </div>
      )}

      <AnimatePresence mode="wait">
        {message && (
          <motion.p
            key={message}
            className={`duel-message${notice.tone === 'error' ? ' is-error' : ''}`}
            role={notice.tone === 'error' ? 'alert' : undefined}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            {notice.tone === 'error' ? (
              <WarningCircle aria-hidden="true" />
            ) : (
              <ShieldCheck aria-hidden="true" />
            )}{' '}
            {message}
          </motion.p>
        )}
      </AnimatePresence>

      <div className="duel-actions">
        {status === 'result' && latestDuel && (
          <>
            {!resultWon && latestDuel.settlement_proof_url && (
              <a
                className="duel-direct-action"
                href={latestDuel.settlement_proof_url}
                target="_blank"
                rel="noreferrer"
              >
                <ArrowSquareOut aria-hidden="true" /> ПОСМОТРЕТЬ ОПЕРАЦИЮ
              </a>
            )}
            <button
              className="secondary-button"
              onClick={() => {
                markDuelSeen(latestDuel.id);
                setSeenDuelId(latestDuel.id);
                setMessage('');
                if (!resultWon) setStake(formatGram(minStake, 3));
                haptic('selection');
              }}
            >
              {resultWon ? 'ИГРАТЬ ЕЩЁ' : 'ПОПРОБОВАТЬ СНОВА'}
            </button>
            {resultWon && latestDuel.settlement_proof_url && (
              <a
                className="duel-direct-action"
                href={latestDuel.settlement_proof_url}
                target="_blank"
                rel="noreferrer"
              >
                <ArrowSquareOut aria-hidden="true" /> ПОСМОТРЕТЬ ОПЕРАЦИЮ
              </a>
            )}
          </>
        )}
        {status === 'idle' && !duelClosed && (
          <>
            <button
              className="primary-button"
              disabled={busy}
              onClick={() => void start(invite ? 'direct' : 'afk')}
            >
              {busy ? 'ГОТОВИМ…' : invite ? 'ПРИНЯТЬ ВЫЗОВ' : 'НАЙТИ СОПЕРНИКА'}
            </button>
            {invite && (
              <button
                className="duel-direct-action"
                disabled={busy}
                onClick={() => {
                  haptic('selection');
                  onDeclineInvite?.();
                }}
              >
                НЕ СЕЙЧАС
              </button>
            )}
            {!invite && (
              <button
                className="duel-direct-action"
                disabled={busy}
                onClick={() => void start('direct')}
              >
                <PaperPlaneTilt aria-hidden="true" /> ПРИГЛАСИТЬ СРАЗИТЬСЯ
              </button>
            )}
          </>
        )}
        {status === 'searching' && !offerExpired && (activeOffer || mockSearching) && (
          <button
            className="profile-row duel-invite-card"
            disabled={!mockSearching && activeOffer?.state !== 'open'}
            onClick={inviteToTelegram}
          >
            <span className="row-icon">
              <UsersThree aria-hidden="true" />
            </span>
            <div>
              <b>Пригласить соперника</b>
              <small>
                {!mockSearching && activeOffer?.state !== 'open'
                  ? 'Станет доступно через несколько секунд'
                  : activeOffer?.mode === 'direct'
                    ? 'Отправить прямой вызов'
                    : 'Позвать друга в DUEL'}
              </small>
            </div>
            <PaperPlaneTilt aria-hidden="true" />
          </button>
        )}
        {awaitingSignature && activeOffer && (
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void abandonQuote(activeOffer.onchain_offer_id)}
          >
            ОТМЕНИТЬ
          </button>
        )}
        {activeActionLabel && (
          <button
            className={status === 'matched' ? 'primary-button' : 'secondary-button'}
            disabled={busy || Boolean(pendingAction)}
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
