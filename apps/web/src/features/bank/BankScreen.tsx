import { ArrowRight, ArrowSquareOut, Check, ShareNetwork, X } from '@phosphor-icons/react';
import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../../api';
import { requireLinkedWallet, sameWalletConnection } from '../../address';
import { humanError } from '../../errors';
import { haptic, isMockTelegram, setBackAction } from '../../telegram';
import {
  buildBankPositionTransaction,
  formatGram,
  isSupportedTonNetwork,
  newOfferId,
  parseGram,
} from '../../ton';
import type {
  BankLimit,
  BankPosition,
  BankPreview,
  BankQueuePulse,
  BankWave,
  Profile,
  RatingPulse,
} from '../../types';

import { JarBalls } from './JarBalls';
import { queueNote } from './queueNote';

import { useCountUp } from '../../useCountUp';

import { celebrate } from '../../celebrate';

type WizardStep = 'amount' | 'multiplier' | 'waiting';
const multipliers = [12500, 15000, 20000] as const;
const LAST_MOVE_EVENT_ID = '2026-08-16';
const LAST_MOVE_PRIZE_NANO = 15_000_000_000;

/** The fee as a percentage, so it is a rate and not just an unexplained subtraction. */
function feePercentOf(feeNano: number, principalNano: number): string {
  if (principalNano <= 0) return '';
  return `${((feeNano * 100) / principalNano).toFixed(1).replace('.', ',').replace(',0', '')}%`;
}

const statusCopy: Record<BankPosition['current_status'], string> = {
  pending_confirmation: 'Проверяем взнос в сети',
  queued: 'Позиция ждёт новых взносов',
  partially_funded: 'Позиция наполнена частично',
  completed: 'Цель собрана',
  payout_sent: 'Выплата отправлена',
  failed: 'Взнос не подтверждён',
};

export function BankScreen({
  profile,
  position,
  queuePulse,
  pulse,
  onRefresh,
  onMockCreated,
}: {
  profile: Profile;
  position: BankPosition | null;
  queuePulse: BankQueuePulse | null;
  pulse: RatingPulse | null;
  onRefresh: () => Promise<void>;
  onMockCreated: (position: BankPosition) => void;
}) {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  const [wizard, setWizard] = useState<WizardStep | null>(null);
  const [details, setDetails] = useState(false);
  const [waveOpen, setWaveOpen] = useState(false);
  const [amount, setAmount] = useState('1');
  const [multiplier, setMultiplier] = useState<(typeof multipliers)[number]>(12500);
  const [fetchedPreview, setFetchedPreview] = useState<BankPreview | null>(null);
  const [limit, setLimit] = useState<BankLimit | null>(
    isMockTelegram()
      ? {
          completed_positions: 0,
          principal_limit_nano: 10_000_000_000,
          next_limit_nano: 15_000_000_000,
          completions_until_next: 25,
          double_limit_nano: 5_000_000_000,
        }
      : null,
  );
  const [message, setMessage] = useState('');
  const [clock, setClock] = useState(() => Date.now());
  const locked = useRef(false);
  /** The quote holding this wallet's position slot until the wallet answers. */
  const quoted = useRef<number | null>(null);

  const doubleLimitNano = limit?.double_limit_nano ?? 0;
  const principalNano = useMemo(() => {
    try {
      return parseGram(amount);
    } catch {
      return 0;
    }
  }, [amount]);

  const doubleBlocked = doubleLimitNano > 0 && principalNano > doubleLimitNano;
  // Выбранная цель выводится, а не хранится: сумма поднялась выше порога —
  // ×2 сама опускается до ×1,5, и шаг подтверждения не отказывает уже после
  // того, как человек всё выбрал.
  const effectiveMultiplier = doubleBlocked && multiplier === 20000 ? 15000 : multiplier;

  useEffect(() => {
    if (waveOpen) return setBackAction(() => setWaveOpen(false));
    if (details) return setBackAction(() => setDetails(false));
    if (!wizard) return setBackAction();
    return setBackAction(() => {
      if (wizard === 'amount') setWizard(null);
      else if (wizard === 'multiplier') setWizard('amount');
    });
  }, [details, waveOpen, wizard]);

  useEffect(() => {
    if (isMockTelegram()) return;
    void api
      .bankLimits()
      .then(setLimit)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (queuePulse?.wave?.id !== LAST_MOVE_EVENT_ID) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [queuePulse?.wave?.id]);

  function continueFromAmount() {
    if (!/^\d+([.,]\d+)?$/.test(amount.trim())) {
      setMessage('Введи сумму цифрами, например 1');
      haptic('warning');
      return;
    }
    if (principalNano < 1_000_000_000) {
      setMessage('Минимальная сумма — 1 GRAM');
      haptic('warning');
      return;
    }
    if (limit && principalNano > limit.principal_limit_nano) {
      setMessage(`Сейчас максимум — ${formatGram(limit.principal_limit_nano, 0)} GRAM`);
      haptic('warning');
      return;
    }
    setMessage('');
    setWizard('multiplier');
  }

  // The summary used to be a third screen. It is the same numbers either way,
  // so they are computed as soon as the target is on screen and shown beneath
  // it — one screen fewer, nothing hidden before signing.
  const canPreview =
    !isMockTelegram() &&
    Boolean(wallet) &&
    isSupportedTonNetwork(wallet?.account.chain ?? '') &&
    sameWalletConnection(profile.wallet, wallet?.account);

  const mockPreview = useMemo<BankPreview | null>(
    () =>
      isMockTelegram()
        ? {
            principal_nano: principalNano,
            multiplier_bps: effectiveMultiplier,
            target_payout_nano: (principalNano * effectiveMultiplier) / 10_000,
            fee_nano: principalNano / 10,
            gas_nano: 80_000_000,
            transaction_amount_nano: principalNano + 80_000_000,
            contract_address: `0:${'12'.repeat(32)}`,
            network: -3,
          }
        : null,
    [effectiveMultiplier, principalNano],
  );

  useEffect(() => {
    if (wizard !== 'multiplier' || !canPreview) return;
    let active = true;
    void api
      .previewBankPosition({ principal_nano: principalNano, multiplier_bps: effectiveMultiplier })
      .then((result) => {
        if (active) setFetchedPreview(result);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setMessage(humanError(error, 'Не удалось рассчитать позицию') ?? '');
      });
    return () => {
      active = false;
    };
  }, [canPreview, effectiveMultiplier, principalNano, wizard]);

  const preview = mockPreview ?? (canPreview ? fetchedPreview : null);

  async function confirmPosition() {
    if (locked.current || !preview) return;
    locked.current = true;
    try {
      if (isMockTelegram()) {
        const initialFunding = preview.principal_nano - preview.fee_nano;
        const created: BankPosition = {
          id: `bank-${Date.now()}`,
          position_id: newOfferId(),
          owner_wallet: profile.wallet?.address ?? `0:${'42'.repeat(32)}`,
          principal_nano: preview.principal_nano,
          multiplier_bps: effectiveMultiplier,
          target_payout_nano: preview.target_payout_nano,
          funded_amount_nano: initialFunding,
          remaining_amount_nano: preview.target_payout_nano - initialFunding,
          progress_bps: Math.floor((initialFunding * 10_000) / preview.target_payout_nano),
          queue_index: 18,
          queue_position: 19,
          queue_progress_bps: 0,
          queue_ahead: 0,
          queue_ahead_nano: 0,
          queue_eta_seconds: null,
          current_status: 'partially_funded',
          funding_transaction: 'demo-bank-transaction',
          payout_transaction: null,
          proof_url: null,
          created_at: new Date().toISOString(),
          completed_at: null,
        };
        onMockCreated(created);
        setWizard(null);
        haptic('success');
        return;
      }
      if (!wallet || !isSupportedTonNetwork(wallet.account.chain)) {
        throw new Error('Подключите поддерживаемый внешний кошелёк');
      }
      const from = requireLinkedWallet(profile.wallet, wallet.account);
      const positionId = newOfferId();
      const quote = await api.quoteBankPosition({
        position_id: positionId,
        principal_nano: preview.principal_nano,
        multiplier_bps: preview.multiplier_bps,
      });
      quoted.current = positionId;
      setWizard('waiting');
      await tonConnectUI.sendTransaction(
        buildBankPositionTransaction(quote, from, wallet.account.chain),
      );
      quoted.current = null;
      await onRefresh();
      haptic('success');
    } catch (error) {
      // The quote already holds this wallet's only position slot, so a refused
      // signature has to give it back — otherwise the next six minutes answer
      // "у тебя уже есть открытая позиция" to someone who signed nothing.
      const abandoned = quoted.current;
      quoted.current = null;
      if (abandoned !== null) {
        await api.discardBankPosition(abandoned).catch(() => undefined);
        await onRefresh().catch(() => undefined);
      }
      setMessage(humanError(error, 'Не удалось создать позицию') ?? '');
      setWizard('multiplier');
      haptic('error');
    } finally {
      locked.current = false;
    }
  }

  // The deposit is confirmed the moment the position stops being a pending
  // intent. Leaving the waiting screen up past that point showed "ждём
  // подтверждение сети" over a confirmation that had already arrived. A
  // render-phase reset, since this is state derived from the position prop.
  if (wizard === 'waiting' && position && position.current_status !== 'pending_confirmation') {
    setWizard(null);
  }

  // Two moments worth marking, and they are different: the network accepting
  // the deposit, and the jar filling. The first is watched by status rather
  // than by the waiting screen, so it lands even if the screen was closed.
  const previousStatus = useRef(position?.current_status);
  useEffect(() => {
    const was = previousStatus.current;
    const now = position?.current_status;
    previousStatus.current = now;
    if (!now || was === now) return;
    if (was === 'pending_confirmation' && now !== 'failed') {
      celebrate();
      haptic('success');
    }
  }, [position?.current_status]);

  const wasFull = useRef((position?.progress_bps ?? 0) >= 10_000);
  useEffect(() => {
    const full = (position?.progress_bps ?? 0) >= 10_000;
    if (full && !wasFull.current) {
      celebrate();
      haptic('success');
    }
    wasFull.current = full;
  }, [position?.progress_bps]);

  // The jar measures the whole wait, not the last stretch of it. A deposit
  // fills the head of the queue to the brim before a nanogram reaches anyone
  // behind, so one's own funding sits at zero until one's turn — a jar that
  // never moved for almost everybody. The queue figure counts the same journey
  // in money: of everything that must arrive before this payout, how much has.
  const progress = Math.max(position?.queue_progress_bps ?? 0, position?.progress_bps ?? 0);
  const progressPercent = Math.min(100, Math.max(0, progress / 100));
  const ahead = position?.queue_ahead ?? 0;
  const aheadNano = position?.queue_ahead_nano ?? 0;
  const etaSeconds = position?.queue_eta_seconds ?? null;
  // Other people's deposits move this while the screen is open, so it counts
  // across rather than snapping to the new figure.
  const shownPercent = useCountUp(progressPercent);
  const pulseCopy = queuePulseCopy(queuePulse);

  if (wizard) {
    return (
      <motion.section
        className={`screen bank-flow-screen bank-flow-${wizard}`}
        aria-labelledby="bank-flow-title"
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
      >
        <SheetTitle
          title="Новая позиция"
          titleId="bank-flow-title"
          onClose={() => setWizard(null)}
        />
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={wizard}
            className="wizard-step bank-flow-step"
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.16, ease: [0.2, 0.8, 0.2, 1] }}
          >
            {wizard === 'amount' && (
              <>
                <p className="eyebrow">ШАГ 1 ИЗ 2 · СУММА</p>
                <label className="amount-input">
                  <input
                    inputMode="decimal"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                    aria-label="Сумма в GRAM"
                  />
                  <span>GRAM</span>
                </label>
                <p className="form-note">
                  {/* At launch the ladder's first rung makes the floor and the
                      ceiling meet, and "От 1 до 1 GRAM" reads as a mistake. */}
                  {(limit?.principal_limit_nano ?? 5_000_000_000) <= 1_000_000_000
                    ? 'Сейчас можно внести ровно 1 GRAM.'
                    : `От 1 до ${formatGram(limit?.principal_limit_nano ?? 5_000_000_000, 0)} GRAM.`}
                  {limit?.next_limit_nano ? ' Лимит растёт вместе с завершёнными позициями.' : ''}
                </p>
                {message && (
                  <p className="form-note is-error" role="alert">
                    {message}
                  </p>
                )}
                <button className="primary-button" onClick={continueFromAmount}>
                  ДАЛЬШЕ
                  <ArrowRight aria-hidden="true" />
                </button>
              </>
            )}
            {wizard === 'multiplier' && (
              <>
                <p className="eyebrow">ШАГ 2 ИЗ 2 · ЦЕЛЬ</p>
                <h3>Выбери целевую выплату.</h3>
                <div className="choice-list">
                  {multipliers.map((value) => {
                    const blocked = value === 20000 && doubleBlocked;
                    return (
                      <button
                        key={value}
                        className={effectiveMultiplier === value ? 'active' : ''}
                        disabled={blocked}
                        onClick={() => {
                          setMultiplier(value);
                          haptic('selection');
                        }}
                      >
                        <span>×{String(value / 10_000).replace('.', ',')}</span>
                        <strong>{formatGram((principalNano * value) / 10_000, 3)} GRAM</strong>
                        {effectiveMultiplier === value && !blocked && <Check aria-hidden="true" />}
                      </button>
                    );
                  })}
                </div>
                {doubleBlocked && (
                  // Отказ после выбора читался бы как поломка. Цель гаснет
                  // сразу и объясняет причину: крупная позиция с двойной целью
                  // требует вдвое больше будущих взносов, чтобы закрыться.
                  <p className="bank-flow-note">
                    Цель ×2 доступна до {formatGram(doubleLimitNano, 0)} GRAM. Чем больше цель, тем
                    дольше очередь её закрывает.
                  </p>
                )}
                <dl className="detail-list bank-flow-summary">
                  <Detail label="Ты платишь" value={`${formatGram(principalNano, 3)} GRAM`} />
                  {preview && (
                    <Detail
                      label={`Комиссия ${feePercentOf(preview.fee_nano, preview.principal_nano)}`}
                      value={`−${formatGram(preview.fee_nano, 3)} GRAM`}
                    />
                  )}
                  <Detail
                    label="Цель"
                    value={`${formatGram((principalNano * multiplier) / 10_000, 3)} GRAM`}
                  />
                </dl>
                <p className="form-note">
                  Взнос вернуть нельзя: досрочной отмены нет. Позицию наполняют новые участники —
                  если они не придут, выплата не наступит.
                </p>
                {message && (
                  <p className="form-note is-error" role="alert">
                    {message}
                  </p>
                )}
                {!wallet && !isMockTelegram() ? (
                  <button className="primary-button" onClick={() => void tonConnectUI.openModal()}>
                    ПОДКЛЮЧИТЬ КОШЕЛЁК
                  </button>
                ) : (
                  <button
                    className="primary-button"
                    disabled={!preview}
                    onClick={() => void confirmPosition()}
                  >
                    {preview ? 'ПОДПИСАТЬ В КОШЕЛЬКЕ' : 'СЧИТАЕМ СУММУ…'}
                  </button>
                )}
              </>
            )}
            {wizard === 'waiting' && (
              <>
                <div className="waiting-step">
                  <span className="waiting-ring" />
                  <h3>Ждём подтверждение сети</h3>
                  <p>Может занять пару минут — можно закрыть и вернуться позже.</p>
                </div>
                <button className="secondary-button" onClick={() => setWizard(null)}>
                  ЗАКРЫТЬ
                </button>
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </motion.section>
    );
  }

  return (
    <section className="screen bank-screen" aria-labelledby="bank-title">
      <header className="mode-header">
        <p className="eyebrow">ФИНАНСОВАЯ ПИРАМИДА</p>
        <h1 id="bank-title">BANK</h1>
      </header>

      <button
        className={`bank-object ${position ? 'is-active' : 'is-empty'}`}
        onClick={() => {
          if (position) {
            setDetails(true);
          } else {
            setMessage('');
            setWizard('amount');
          }
        }}
        aria-label={
          position
            ? `Открыть позицию BANK, собрано ${Math.round(progressPercent)}%`
            : 'Создать позицию BANK'
        }
      >
        <motion.div
          className="bank-vessel"
          aria-hidden="true"
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 115, damping: 23 }}
        >
          <img className="bank-jar-shell" src="/assets/empty-jar.webp" alt="" />
          {position && (
            <span className="bank-sand-chamber">
              <JarBalls fill={progressPercent} />
            </span>
          )}
          {position && <img className="bank-jar-glass" src="/assets/empty-jar.webp" alt="" />}
        </motion.div>
      </button>

      {position ? (
        <div className="bank-state bank-active-state">
          <strong>{Math.round(shownPercent)}%</strong>
          <p className="bank-queue-note">{queueNote(ahead, aheadNano, etaSeconds, position)}</p>
          {pulseCopy && <BankLivePulse copy={pulseCopy} />}
          <div className="bank-cycle-metrics">
            <CycleMetric
              value={position.queue_position ? `#${position.queue_position}` : '—'}
              label="ТВОЁ МЕСТО"
            />
            <CycleMetric value={pulse?.active_bank ?? '—'} label="В ОЧЕРЕДИ" />
          </div>
          <button className="primary-button" onClick={() => setDetails(true)}>
            СМОТРЕТЬ ПОЗИЦИЮ
          </button>
        </div>
      ) : (
        <div className="bank-state bank-empty-state">
          {pulseCopy && <BankLivePulse copy={pulseCopy} />}
          <div className="bank-cycle-metrics is-empty">
            <CycleMetric value={pulse?.active_bank ?? '—'} label="В ОЧЕРЕДИ" />
            <CycleMetric value={pulse?.active_participants ?? '—'} label="СЕЙЧАС В LOOP" />
          </div>
          <button
            className="primary-button"
            onClick={() => {
              setMessage('');
              setWizard('amount');
            }}
          >
            СОЗДАТЬ ПОЗИЦИЮ
          </button>
        </div>
      )}

      {queuePulse?.wave && (
        <button className="bank-wave-teaser" onClick={() => setWaveOpen(true)}>
          <span>{waveTeaser(queuePulse.wave, clock)}</span>
          <ArrowRight aria-hidden="true" />
        </button>
      )}

      <AnimatePresence>
        {waveOpen && queuePulse?.wave && (
          <motion.div
            className="sheet-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setWaveOpen(false)}
          >
            <motion.div
              className="sheet bank-wave-sheet"
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', stiffness: 260, damping: 30 }}
              onClick={(event) => event.stopPropagation()}
            >
              <SheetTitle
                title={queuePulse.wave.id === LAST_MOVE_EVENT_ID ? 'Воскресный BANK' : 'Волна'}
                onClose={() => setWaveOpen(false)}
              />
              <BankWaveDetails
                wave={queuePulse.wave}
                onEnter={() => {
                  setWaveOpen(false);
                  if (
                    !position &&
                    ['active', 'goal_reached'].includes(queuePulse.wave?.state ?? '')
                  ) {
                    setMessage('');
                    setWizard('amount');
                  }
                }}
              />
            </motion.div>
          </motion.div>
        )}
        {details && position && (
          <motion.div
            className="sheet-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setDetails(false)}
          >
            <motion.div
              className="sheet"
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', stiffness: 260, damping: 30 }}
              onClick={(event) => event.stopPropagation()}
            >
              <SheetTitle title="Позиция BANK" onClose={() => setDetails(false)} />
              <p className="bank-details-intro">
                Банка — сколько собрано в твою позицию. Первым в неё попадает остаток твоего взноса
                за вычетом комиссии, дальше её наполняют новые участники.
              </p>
              <div className="big-progress">{Math.round(progressPercent)}%</div>
              <div className="progress-track">
                <span style={{ width: `${progressPercent}%` }} />
              </div>
              <dl className="detail-list">
                <Detail
                  label="Твой взнос"
                  value={`${formatGram(position.principal_nano, 3)} GRAM`}
                />
                <Detail
                  label="Целевая выплата"
                  value={`${formatGram(position.target_payout_nano, 3)} GRAM`}
                />
                <Detail
                  label="Собрано, включая твой взнос"
                  value={`${formatGram(position.funded_amount_nano, 3)} GRAM`}
                />
                <Detail
                  label="Осталось собрать"
                  value={`${formatGram(position.remaining_amount_nano, 3)} GRAM`}
                />
                <Detail
                  label="Место в очереди"
                  value={
                    position.queue_position === null
                      ? 'Подтверждается'
                      : `#${position.queue_position}`
                  }
                />
                <Detail label="Состояние" value={statusCopy[position.current_status]} />
              </dl>
              <div className="contract-truth compact">
                <strong>Как работает очередь</strong>
                <p>
                  Новые взносы идут ранним позициям. Без них выплата может не наступить; досрочной
                  отмены нет.
                </p>
              </div>
              {position.proof_url && (
                <a
                  className="secondary-button"
                  href={position.proof_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  ПОСМОТРЕТЬ ОПЕРАЦИЮ
                  <ArrowSquareOut aria-hidden="true" />
                </a>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function BankWaveDetails({ wave, onEnter }: { wave: BankWave; onEnter: () => void }) {
  const active = wave.state === 'active' || wave.state === 'goal_reached';
  const completed = wave.state === 'completed';
  const isLastMoveEvent = wave.id === LAST_MOVE_EVENT_ID;
  const closer = wave.closer_username
    ? `@${wave.closer_username}`
    : wave.closer_name || 'последний участник';
  const shareText = encodeURIComponent(
    `Я закрыл Волну LOOP. ${wave.goal} участников — и LOOP добавил ${formatGram(wave.boost_nano, 0)} GRAM в BANK.`,
  );

  return (
    <div className="bank-wave-content">
      <p className="eyebrow">
        {isLastMoveEvent ? 'ВОСКРЕСЕНЬЕ · С 20:00 МСК' : 'ВОСКРЕСЕНЬЕ · 20:00–20:30 МСК'}
      </p>
      {active ? (
        <div className="bank-wave-count">
          <strong>{Math.min(wave.participants, wave.goal)}</strong>
          <span>ИЗ {wave.goal}</span>
        </div>
      ) : completed ? (
        <div className="bank-wave-count is-complete">
          <strong>{closer}</strong>
          <span>ЗАКРЫЛ ВОЛНУ</span>
        </div>
      ) : (
        <h3>{isLastMoveEvent ? 'Последний ход.' : 'Полчаса, чтобы войти вместе.'}</h3>
      )}
      {isLastMoveEvent ? (
        <div className="bank-event-rules">
          <div className="bank-last-move-clock" aria-live="polite">
            <strong>{lastMoveClock(wave, Date.now())}</strong>
            <span>{lastMoveClockLabel(wave, Date.now())}</span>
          </div>
          <p className="bank-wave-rule">
            <strong>{formatGram(LAST_MOVE_PRIZE_NANO, 0)} GRAM за последний ход.</strong>
            Каждый новый взнос запускает 30 минут заново. Если его никто не перебьёт, приз получает
            автор последнего взноса.
          </p>
          <p className="bank-wave-rule">
            <strong>+{formatGram(wave.boost_nano, 0)} GRAM в очередь.</strong>
            До 20:30 должны войти {wave.goal} разных участников.
          </p>
        </div>
      ) : (
        <p className="bank-wave-rule">
          Если войдут {wave.goal} человек, LOOP внесёт {formatGram(wave.boost_nano, 0)} GRAM в BANK.
          Последний участник закроет Волну.
        </p>
      )}
      {wave.state === 'missed' && (
        <p className="bank-wave-status">В этот раз Волна не собралась.</p>
      )}
      {wave.state === 'awaiting_boost' && (
        <p className="bank-wave-status">Цель собрана. Взнос LOOP готовится.</p>
      )}
      {completed && wave.proof_url && (
        <a className="secondary-button" href={wave.proof_url} target="_blank" rel="noreferrer">
          ПРОВЕРИТЬ ВЗНОС LOOP
          <ArrowSquareOut aria-hidden="true" />
        </a>
      )}
      {wave.is_closer && completed ? (
        <a
          className="primary-button"
          href={`https://t.me/share/url?url=${encodeURIComponent(window.location.origin)}&text=${shareText}`}
          target="_blank"
          rel="noreferrer"
        >
          <ShareNetwork aria-hidden="true" />
          ПОДЕЛИТЬСЯ
        </a>
      ) : (
        <button className="primary-button" onClick={onEnter}>
          {active ? (isLastMoveEvent ? 'УЧАСТВОВАТЬ' : 'ВОЙТИ В ВОЛНУ') : 'ПОНЯТНО'}
        </button>
      )}
    </div>
  );
}

function SheetTitle({
  title,
  titleId,
  onClose,
}: {
  title: string;
  titleId?: string;
  onClose: () => void;
}) {
  return (
    <div className="sheet-title-row">
      <div>
        <p className="eyebrow">LOOP</p>
        <h2 id={titleId}>{title}</h2>
      </div>
      <button className="round-icon-button" onClick={onClose} aria-label="Закрыть">
        <X aria-hidden="true" />
      </button>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function CycleMetric({ value, label }: { value: string | number; label: string }) {
  return (
    <span>
      <b>{value}</b>
      <small>{label}</small>
    </span>
  );
}

function BankLivePulse({ copy }: { copy: string }) {
  return (
    <div className="bank-live-pulse" aria-live="polite">
      <i aria-hidden="true" />
      <span>{copy}</span>
    </div>
  );
}

function waveTeaser(wave: BankWave, now = Date.now()): string {
  if (wave.id === LAST_MOVE_EVENT_ID && wave.state === 'upcoming') {
    return `ДО СТАРТА · ${countdown(new Date(wave.starts_at).getTime() - now)} · ${formatGram(LAST_MOVE_PRIZE_NANO, 0)} GRAM`;
  }
  if (wave.id === LAST_MOVE_EVENT_ID) {
    if (!wave.last_move_deadline) return 'ПОСЛЕДНИЙ ХОД · ЖДЁМ ПЕРВЫЙ ВЗНОС';
    const left = new Date(wave.last_move_deadline).getTime() - now;
    return left > 0 ? `ПОСЛЕДНИЙ ХОД · ${countdown(left)}` : 'ПОСЛЕДНИЙ ХОД · ВРЕМЯ ВЫШЛО';
  }
  if (wave.state === 'active' || wave.state === 'goal_reached') {
    const prefix = wave.id === LAST_MOVE_EVENT_ID ? 'ИВЕНТ' : 'ВОЛНА';
    return `${prefix} · ${Math.min(wave.participants, wave.goal)} ИЗ ${wave.goal} · ДО 20:30`;
  }
  if (wave.state === 'completed') return 'ВОЛНА ЗАКРЫТА · ВЗНОС LOOP ПОДТВЕРЖДЁН';
  if (wave.state === 'awaiting_boost') return 'ВОЛНА СОБРАНА · ГОТОВИМ ВЗНОС';
  if (wave.state === 'missed') return 'ВОЛНА ЗАВЕРШЕНА · СЛЕДУЮЩАЯ В ВОСКРЕСЕНЬЕ';
  return `ВОЛНА · ВС 20:00 · +${formatGram(wave.boost_nano, 0)} GRAM В BANK`;
}

function lastMoveClock(wave: BankWave, now: number): string {
  if (wave.state === 'upcoming') return countdown(new Date(wave.starts_at).getTime() - now);
  if (!wave.last_move_deadline) return '30:00';
  return countdown(new Date(wave.last_move_deadline).getTime() - now);
}

function lastMoveClockLabel(wave: BankWave, now: number): string {
  if (wave.state === 'upcoming') return 'ДО СТАРТА';
  if (!wave.last_move_deadline) return 'ЖДЁМ ПЕРВЫЙ ВЗНОС';
  return new Date(wave.last_move_deadline).getTime() > now ? 'ДО ПОБЕДЫ' : 'ХОД УДЕРЖАН';
}

function countdown(milliseconds: number): string {
  const total = Math.max(0, Math.ceil(milliseconds / 1_000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function queuePulseCopy(pulse: BankQueuePulse | null): string | null {
  if (!pulse) return null;
  if (pulse.active_positions === 0) return 'Очередь ждёт первую позицию';
  if (pulse.minimum_entry_payouts === 1) return 'Следующий вход закроет ближайшую позицию';
  if (pulse.minimum_entry_payouts > 1) {
    return `Следующий вход закроет ${pulse.minimum_entry_payouts} ${positionsWord(pulse.minimum_entry_payouts)}`;
  }
  return null;
}

function positionsWord(count: number): string {
  if (count % 10 === 1 && count % 100 !== 11) return 'позицию';
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return 'позиции';
  return 'позиций';
}
