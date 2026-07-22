import { ArrowRight, ArrowSquareOut, Check, X } from '@phosphor-icons/react';
import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import type { CSSProperties } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../../api';
import { haptic, isMockTelegram, setBackAction } from '../../telegram';
import { buildBankPositionTransaction, formatGram, newOfferId, parseGram } from '../../ton';
import type { BankPosition, BankPreview, Profile } from '../../types';

type WizardStep = 'amount' | 'multiplier' | 'confirm' | 'waiting';
const multipliers = [12500, 15000, 20000] as const;

const statusCopy: Record<BankPosition['current_status'], string> = {
  pending_confirmation: 'Подтверждаем вклад в TON',
  queued: 'Банка ждёт пополнения',
  partially_funded: 'Банка наполняется',
  completed: 'Цель собрана',
  payout_sent: 'Выплата отправлена',
  failed: 'Вклад не подтверждён',
};

export function BankScreen({
  profile,
  position,
  onRefresh,
  onMockCreated,
}: {
  profile: Profile;
  position: BankPosition | null;
  onRefresh: () => Promise<void>;
  onMockCreated: (position: BankPosition) => void;
}) {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  const [wizard, setWizard] = useState<WizardStep | null>(null);
  const [details, setDetails] = useState(false);
  const [amount, setAmount] = useState('2');
  const [multiplier, setMultiplier] = useState<(typeof multipliers)[number]>(15000);
  const [preview, setPreview] = useState<BankPreview | null>(null);
  const [message, setMessage] = useState('');
  const locked = useRef(false);

  const principalNano = useMemo(() => {
    try {
      return parseGram(amount);
    } catch {
      return 0;
    }
  }, [amount]);

  useEffect(() => {
    if (!wizard) return setBackAction();
    return setBackAction(() => {
      if (wizard === 'amount') setWizard(null);
      else if (wizard === 'multiplier') setWizard('amount');
      else if (wizard === 'confirm') setWizard('multiplier');
    });
  }, [wizard]);

  async function showConfirmation() {
    if (principalNano < 1_000_000_000) {
      setMessage('Минимальная сумма — 1 GRAM');
      haptic('warning');
      return;
    }
    if (isMockTelegram()) {
      setPreview({
        principal_nano: principalNano,
        multiplier_bps: multiplier,
        target_payout_nano: (principalNano * multiplier) / 10_000,
        fee_nano: principalNano / 100,
        gas_nano: 80_000_000,
        transaction_amount_nano: principalNano + 80_000_000,
        contract_address: `0:${'12'.repeat(32)}`,
        network: -3,
      });
      setWizard('confirm');
      return;
    }
    if (!wallet) {
      await tonConnectUI.openModal();
      return;
    }
    if (wallet.account.chain !== '-3') {
      setMessage('LOOP работает только в TON testnet');
      haptic('error');
      return;
    }
    if (!profile.wallet) {
      setMessage('Подтверждаем владение внешним кошельком…');
      return;
    }
    try {
      const result = await api.previewBankPosition({
        principal_nano: principalNano,
        multiplier_bps: multiplier,
      });
      setPreview(result);
      setWizard('confirm');
      haptic('light');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось рассчитать позицию');
      haptic('error');
    }
  }

  async function confirmPosition() {
    if (locked.current || !preview) return;
    locked.current = true;
    try {
      if (isMockTelegram()) {
        const created: BankPosition = {
          id: `bank-${Date.now()}`,
          position_id: newOfferId(),
          owner_wallet: profile.wallet?.address ?? `0:${'42'.repeat(32)}`,
          principal_nano: preview.principal_nano,
          multiplier_bps: multiplier,
          target_payout_nano: preview.target_payout_nano,
          funded_amount_nano: 0,
          remaining_amount_nano: preview.target_payout_nano,
          progress_bps: 0,
          queue_index: 18,
          current_status: 'queued',
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
      if (!wallet || wallet.account.chain !== '-3') {
        throw new Error('Подключите внешний кошелёк TON testnet');
      }
      const quote = await api.quoteBankPosition({
        position_id: newOfferId(),
        principal_nano: preview.principal_nano,
        multiplier_bps: preview.multiplier_bps,
      });
      setWizard('waiting');
      await tonConnectUI.sendTransaction(
        buildBankPositionTransaction(quote, wallet.account.address, wallet.account.chain),
      );
      setMessage('Транзакция отправлена. Ждём подтверждённый блок TON.');
      await onRefresh();
      haptic('success');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось создать позицию');
      setWizard('confirm');
      haptic('error');
    } finally {
      locked.current = false;
    }
  }

  const progress = position?.progress_bps ?? 0;
  const progressPercent = Math.min(100, Math.max(0, progress / 100));
  const sandStyle = { '--bank-fill': `${progressPercent}%` } as CSSProperties;
  const fundingCopy = position
    ? `Собрано ${formatGram(position.funded_amount_nano, 3)} из ${formatGram(position.target_payout_nano, 3)} GRAM. На 100% контракт отправит выплату.`
    : '';

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
                <p className="eyebrow">ШАГ 1 ИЗ 3 · СУММА</p>
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
                  Это твой вклад в позицию. Только testnet GRAM, минимум 1 GRAM.
                </p>
                <button className="primary-button" onClick={() => setWizard('multiplier')}>
                  ДАЛЬШЕ
                  <ArrowRight aria-hidden="true" />
                </button>
              </>
            )}
            {wizard === 'multiplier' && (
              <>
                <p className="eyebrow">ШАГ 2 ИЗ 3 · ЦЕЛЬ</p>
                <h3>Сколько должна собрать банка?</h3>
                <div className="choice-list">
                  {multipliers.map((value) => (
                    <button
                      key={value}
                      className={multiplier === value ? 'active' : ''}
                      onClick={() => {
                        setMultiplier(value);
                        haptic('selection');
                      }}
                    >
                      <span>×{value / 10_000}</span>
                      <strong>{formatGram((principalNano * value) / 10_000, 3)} GRAM</strong>
                      {multiplier === value && <Check aria-hidden="true" />}
                    </button>
                  ))}
                </div>
                <p className="form-note">
                  Чем выше цель, тем дольше позиция может ждать в очереди.
                </p>
                <button className="primary-button" onClick={() => void showConfirmation()}>
                  ПРОВЕРИТЬ
                </button>
              </>
            )}
            {wizard === 'confirm' && preview && (
              <>
                <p className="eyebrow">ШАГ 3 ИЗ 3 · ПОДТВЕРЖДЕНИЕ</p>
                <h3>Проверь, как будет работать позиция.</h3>
                <dl className="detail-list">
                  <Detail
                    label="Вносится"
                    value={`${formatGram(preview.principal_nano, 3)} GRAM`}
                  />
                  <Detail
                    label="Целевая выплата"
                    value={`${formatGram(preview.target_payout_nano, 3)} GRAM`}
                  />
                  <Detail label="Комиссия BANK" value={`${formatGram(preview.fee_nano, 4)} GRAM`} />
                  <Detail label="Сеть" value="TON testnet" />
                  <Detail
                    label="Контракт"
                    value={`${preview.contract_address.slice(0, 7)}…${preview.contract_address.slice(-5)}`}
                  />
                </dl>
                {message && <p className="form-note is-error">{message}</p>}
                <button className="primary-button" onClick={() => void confirmPosition()}>
                  ПОДТВЕРДИТЬ В TON
                </button>
              </>
            )}
            {wizard === 'waiting' && (
              <>
                <div className="waiting-step">
                  <span className="waiting-ring" />
                  <h3>Подтверждаем в TON</h3>
                  <p>Callback кошелька не считается успехом. LOOP ждёт транзакцию в блоке.</p>
                  {message && <p className="form-note">{message}</p>}
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
        <p className="eyebrow">TESTNET · ОЧЕРЕДЬ</p>
        <h1 id="bank-title">BANK</h1>
      </header>

      <button
        className={`bank-object ${position ? 'is-active' : 'is-empty'}`}
        onClick={() => (position ? setDetails(true) : setWizard('amount'))}
        aria-label={
          position
            ? `Открыть позицию BANK, собрано ${Math.round(progressPercent)} процентов`
            : 'Начать цикл и создать позицию BANK'
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
              <span className="bank-sand-level" data-testid="bank-sand-level" style={sandStyle}>
                <img className="bank-sand-material" src="/assets/bank-sand-wave.webp" alt="" />
              </span>
            </span>
          )}
          {position && <img className="bank-jar-glass" src="/assets/empty-jar.webp" alt="" />}
        </motion.div>
      </button>

      {position ? (
        <div className="bank-state bank-active-state">
          <strong>{Math.round(progressPercent)}%</strong>
          <span>{statusCopy[position.current_status]}</span>
          <p>{fundingCopy}</p>
          <button className="primary-button" onClick={() => setDetails(true)}>
            СМОТРЕТЬ ПОЗИЦИЮ
          </button>
        </div>
      ) : (
        <div className="bank-state bank-empty-state">
          <h2>Твоя очередь. Твоя банка.</h2>
          <p>
            Внеси GRAM и создай позицию. Новые участники будут наполнять её; 100% — контракт
            отправит целевую выплату.
          </p>
          <button className="primary-button" onClick={() => setWizard('amount')}>
            НАЧАТЬ ЦИКЛ
          </button>
        </div>
      )}

      <AnimatePresence>
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
                Банка показывает, сколько уже собрано до твоей целевой выплаты.
              </p>
              <div className="big-progress">{Math.round(progressPercent)}%</div>
              <div className="progress-track">
                <span style={{ width: `${progressPercent}%` }} />
              </div>
              <dl className="detail-list">
                <Detail
                  label="Твой вклад"
                  value={`${formatGram(position.principal_nano, 3)} GRAM`}
                />
                <Detail
                  label="Целевая выплата"
                  value={`${formatGram(position.target_payout_nano, 3)} GRAM`}
                />
                <Detail
                  label="Уже собрано"
                  value={`${formatGram(position.funded_amount_nano, 3)} GRAM`}
                />
                <Detail
                  label="Осталось собрать"
                  value={`${formatGram(position.remaining_amount_nano, 3)} GRAM`}
                />
                <Detail
                  label="Место в очереди"
                  value={
                    position.queue_index === null
                      ? 'Подтверждается'
                      : `#${position.queue_index + 1}`
                  }
                />
                <Detail label="Статус" value={statusCopy[position.current_status]} />
              </dl>
              {position.proof_url && (
                <a
                  className="secondary-button"
                  href={position.proof_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  ПРОВЕРИТЬ В TON
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
        <p className="eyebrow">LOOP · TESTNET</p>
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
