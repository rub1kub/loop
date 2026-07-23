import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import {
  ArrowClockwise,
  ArrowRight,
  ArrowSquareOut,
  Bank,
  CaretDown,
  CheckCircle,
  CircleNotch,
  Coins,
  DownloadSimple,
  GearSix,
  LockKey,
  Pause,
  Play,
  ShieldCheck,
  SignOut,
  Users,
  Warning,
  X,
} from '@phosphor-icons/react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { controlApi, ControlApiError } from './api';
import type {
  ApplicationControl,
  ContractControl,
  ControlActionInput,
  ControlOverview,
} from './types';

const NANO = 1_000_000_000;

function shortAddress(value: string): string {
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value || '—';
}

function gram(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 4,
    minimumFractionDigits: 0,
  }).format(value / NANO);
}

function nanoFromInput(value: string): number | null {
  const normalized = value.trim().replace(',', '.');
  if (!/^\d+(?:\.\d{1,9})?$/.test(normalized)) return null;
  const amount = Math.round(Number(normalized) * NANO);
  return Number.isSafeInteger(amount) && amount > 0 ? amount : null;
}

function feeBpsFromPercent(value: string): number | null {
  const normalized = value.trim().replace(',', '.');
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) return null;
  const fee = Math.round(Number(normalized) * 100);
  return Number.isInteger(fee) && fee >= 0 && fee <= 1000 ? fee : null;
}

function contractStatus(contract: ContractControl): {
  label: string;
  tone: 'normal' | 'paused' | 'danger';
} {
  if (contract.error) return { label: 'Нет связи', tone: 'danger' };
  if (!contract.code_hash_matches) return { label: 'Нужна проверка', tone: 'danger' };
  if (contract.paused) return { label: 'На паузе', tone: 'paused' };
  return { label: 'Работает', tone: 'normal' };
}

function systemStatus(overview: ControlOverview): {
  eyebrow: string;
  title: string;
  description: string;
  tone: 'normal' | 'paused' | 'danger';
} {
  const hasContractProblem = overview.contracts.some(
    (contract) => contract.error || !contract.code_hash_matches,
  );
  if (!overview.metrics.worker_healthy || hasContractProblem) {
    return {
      eyebrow: 'НУЖНО ВНИМАНИЕ',
      title: 'Проверь LOOP',
      description:
        'Один из важных процессов не отвечает. Новые действия лучше временно остановить.',
      tone: 'danger',
    };
  }
  if (overview.application.maintenance_enabled) {
    return {
      eyebrow: 'НОВЫЕ ДЕЙСТВИЯ ОСТАНОВЛЕНЫ',
      title: 'LOOP на паузе',
      description: 'Открытые циклы и дуэли продолжают завершаться. Новые пока не создаются.',
      tone: 'paused',
    };
  }
  const hasLimits =
    !overview.application.bank_enabled ||
    !overview.application.duel_enabled ||
    overview.contracts.some((contract) => contract.paused);
  if (hasLimits) {
    return {
      eyebrow: 'ЕСТЬ ОГРАНИЧЕНИЯ',
      title: 'LOOP работает частично',
      description:
        'Часть функций остановлена. Ниже видно, что доступно пользователям прямо сейчас.',
      tone: 'paused',
    };
  }
  return {
    eyebrow: 'ВСЁ В ПОРЯДКЕ',
    title: 'LOOP работает',
    description: 'Пользователи могут открывать циклы и дуэли. Выплаты и проверка сети работают.',
    tone: 'normal',
  };
}

function actionLabel(action: string): string {
  const labels: Record<string, string> = {
    'bank.pause': 'BANK: изменение паузы',
    'bank.fund_reserve': 'BANK: пополнение резерва',
    'bank.withdraw_surplus': 'BANK: вывод свободного резерва',
    'bank.set_fee': 'BANK: изменение комиссии',
    'bank.set_treasury': 'BANK: изменение казны',
    'bank.set_owner': 'BANK: передача управления',
    'duel.pause': 'DUEL: изменение паузы',
    'duel.fund_reserve': 'DUEL: пополнение резерва',
    'duel.withdraw_surplus': 'DUEL: вывод свободного резерва',
    'duel.set_fee': 'DUEL: изменение комиссии',
    'duel.set_treasury': 'DUEL: изменение казны',
    'duel.set_owner': 'DUEL: передача управления',
    application_control: 'Настройки приложения',
  };
  return labels[action] ?? (action.startsWith('chain.') ? 'Подтверждено сетью' : action);
}

type ContractCardProps = {
  contract: ContractControl;
  busy: boolean;
  onAction: (input: ControlActionInput) => Promise<boolean>;
};

function ContractCard({ contract, busy, onAction }: ContractCardProps) {
  const [reserveAmount, setReserveAmount] = useState('');
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [feePercent, setFeePercent] = useState(String(contract.fee_bps / 100));
  const [treasury, setTreasury] = useState(contract.treasury);
  const [owner, setOwner] = useState('');
  const enabled = !busy && !contract.error && contract.owner_matches_session;
  const canConfigure = enabled && contract.extended_controls && contract.paused;
  const status = contractStatus(contract);

  const amountAction = async (action: 'fund_reserve' | 'withdraw_surplus', value: string) => {
    const amount = nanoFromInput(value);
    if (!amount) {
      window.alert('Укажи корректную сумму GRAM');
      return;
    }
    if (action === 'withdraw_surplus') {
      if (amount > contract.withdrawable_nano) {
        window.alert(`Можно вывести не больше ${gram(contract.withdrawable_nano)} GRAM`);
        return;
      }
      if (!window.confirm(`Вывести ${gram(amount)} GRAM в казну?`)) return;
    }
    const accepted = await onAction({ mode: contract.mode, action, amount_nano: amount });
    if (!accepted) return;
    if (action === 'fund_reserve') setReserveAmount('');
    else setWithdrawAmount('');
  };

  return (
    <article className="control-contract" id={`contract-${contract.mode}`}>
      <header className="contract-head">
        <div>
          <span className="eyebrow">РАСШИРЕННОЕ УПРАВЛЕНИЕ</span>
          <h2>{contract.mode.toUpperCase()}</h2>
        </div>
        <span className={`status-pill ${status.tone}`}>
          {status.label.toLocaleUpperCase('ru-RU')}
        </span>
      </header>

      {contract.error ? (
        <div className="inline-warning">
          <Warning size={20} />
          <span>{contract.error}</span>
        </div>
      ) : (
        <>
          <div className="contract-metrics">
            <div>
              <span>Всего</span>
              <strong>{gram(contract.balance_nano)} GRAM</strong>
            </div>
            <div>
              <span>Зарезервировано участникам</span>
              <strong>{gram(contract.locked_nano)} GRAM</strong>
            </div>
            <div>
              <span>Доступно владельцу</span>
              <strong>{gram(contract.withdrawable_nano)} GRAM</strong>
            </div>
            <div>
              <span>Комиссия</span>
              <strong>{contract.fee_bps / 100}%</strong>
            </div>
          </div>

          {!contract.owner_matches_session && (
            <div className="inline-warning">
              <LockKey size={20} />
              <span>Подключённый кошелёк не является владельцем этого раздела.</span>
            </div>
          )}
          {!contract.extended_controls && (
            <div className="inline-warning">
              <Warning size={20} />
              <span>Доступна только пауза. Остальные команды здесь не поддерживаются.</span>
            </div>
          )}

          <div className="primary-actions">
            <button
              className={contract.paused ? 'button light' : 'button outline'}
              disabled={!enabled}
              onClick={() =>
                void onAction({
                  mode: contract.mode,
                  action: 'pause',
                  paused: !contract.paused,
                })
              }
            >
              {contract.paused ? (
                <Play size={18} weight="fill" />
              ) : (
                <Pause size={18} weight="fill" />
              )}
              {contract.paused ? 'ВОЗОБНОВИТЬ' : 'ПОСТАВИТЬ НА ПАУЗУ'}
            </button>
          </div>

          <details className="contract-settings">
            <summary>ОПЕРАЦИИ И ПРАВИЛА</summary>
            <div className="settings-grid">
              <label>
                <span>Пополнить резерв, GRAM</span>
                <div className="field-action">
                  <input
                    inputMode="decimal"
                    value={reserveAmount}
                    onChange={(event) => setReserveAmount(event.target.value)}
                    placeholder="0"
                  />
                  <button
                    disabled={!enabled || !contract.extended_controls}
                    onClick={() => void amountAction('fund_reserve', reserveAmount)}
                  >
                    ПОПОЛНИТЬ
                  </button>
                </div>
              </label>

              <label>
                <span>Вывести доступное, GRAM</span>
                <div className="field-action">
                  <input
                    inputMode="decimal"
                    value={withdrawAmount}
                    onChange={(event) => setWithdrawAmount(event.target.value)}
                    placeholder={gram(contract.withdrawable_nano)}
                  />
                  <button
                    disabled={!canConfigure || contract.withdrawable_nano <= 0}
                    onClick={() => void amountAction('withdraw_surplus', withdrawAmount)}
                  >
                    ВЫВЕСТИ
                  </button>
                </div>
                <small>
                  Перевод идёт только в казну. Зарезервированные участникам средства не
                  затрагиваются.
                </small>
              </label>

              <label>
                <span>Комиссия, %</span>
                <div className="field-action">
                  <input
                    inputMode="decimal"
                    value={feePercent}
                    onChange={(event) => setFeePercent(event.target.value)}
                  />
                  <button
                    disabled={!canConfigure}
                    onClick={() => {
                      const fee = feeBpsFromPercent(feePercent);
                      if (fee === null) {
                        window.alert('Комиссия должна быть от 0 до 10%');
                        return;
                      }
                      void onAction({ mode: contract.mode, action: 'set_fee', fee_bps: fee });
                    }}
                  >
                    СОХРАНИТЬ
                  </button>
                </div>
                <small>Изменение доступно только на паузе.</small>
              </label>

              <label>
                <span>Кошелёк для поступлений</span>
                <div className="field-action">
                  <input value={treasury} onChange={(event) => setTreasury(event.target.value)} />
                  <button
                    disabled={!canConfigure || treasury === contract.treasury}
                    onClick={() =>
                      void onAction({
                        mode: contract.mode,
                        action: 'set_treasury',
                        address: treasury,
                      })
                    }
                  >
                    СМЕНИТЬ
                  </button>
                </div>
                <small>Изменение доступно только на паузе.</small>
              </label>
            </div>

            <details className="technical-details">
              <summary>ТЕХНИЧЕСКИЕ ДАННЫЕ</summary>
              <dl className="contract-facts">
                <div>
                  <dt>Владелец</dt>
                  <dd title={contract.owner}>{shortAddress(contract.owner)}</dd>
                </div>
                <div>
                  <dt>Казна</dt>
                  <dd title={contract.treasury}>{shortAddress(contract.treasury)}</dd>
                </div>
                <div>
                  <dt>Адрес</dt>
                  <dd title={contract.address}>{shortAddress(contract.address)}</dd>
                </div>
              </dl>
            </details>

            <details className="danger-zone">
              <summary>ПЕРЕДАТЬ УПРАВЛЕНИЕ</summary>
              <p>После подтверждения текущий кошелёк потеряет доступ к этому разделу.</p>
              <div className="field-action">
                <input
                  value={owner}
                  onChange={(event) => setOwner(event.target.value)}
                  placeholder="Адрес нового владельца"
                />
                <button
                  disabled={!canConfigure || !owner}
                  onClick={() => {
                    if (!window.confirm('Передать полный контроль новому владельцу?')) return;
                    void onAction({
                      mode: contract.mode,
                      action: 'set_owner',
                      address: owner,
                      confirmation: 'TRANSFER OWNER',
                    });
                  }}
                >
                  ПЕРЕДАТЬ
                </button>
              </div>
            </details>
          </details>
        </>
      )}
    </article>
  );
}

type QuickAction = 'fund' | 'withdraw';

function QuickActionSheet({
  action,
  contracts,
  busy,
  onClose,
  onAction,
  onOpenAdvanced,
}: {
  action: QuickAction;
  contracts: ContractControl[];
  busy: boolean;
  onClose: () => void;
  onAction: (input: ControlActionInput) => Promise<boolean>;
  onOpenAdvanced: (mode: ContractControl['mode']) => void;
}) {
  const [mode, setMode] = useState<ContractControl['mode']>(
    contracts.some((contract) => contract.mode === 'bank') ? 'bank' : 'duel',
  );
  const [amountText, setAmountText] = useState('');
  const [pauseRequested, setPauseRequested] = useState(false);
  const contract = contracts.find((item) => item.mode === mode) ?? contracts[0];

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [onClose]);

  if (!contract) return null;
  const amount = nanoFromInput(amountText);
  const enabled =
    !busy && !contract.error && contract.owner_matches_session && contract.extended_controls;
  const tooMuch = action === 'withdraw' && amount !== null && amount > contract.withdrawable_nano;
  const needsPause = action === 'withdraw' && !contract.paused;
  const waitingForPause = needsPause && pauseRequested;

  const submit = async () => {
    if (!amount || tooMuch) return;
    const accepted = await onAction({
      mode: contract.mode,
      action: action === 'fund' ? 'fund_reserve' : 'withdraw_surplus',
      amount_nano: amount,
    });
    if (accepted) onClose();
  };

  return (
    <dialog className="quick-dialog" open aria-labelledby="quick-action-title">
      <button className="dialog-backdrop" aria-label="Закрыть окно" onClick={onClose} />
      <section className="quick-sheet">
        <header>
          <div>
            <span className="eyebrow">{action === 'fund' ? 'ПОПОЛНЕНИЕ' : 'ВЫВОД'}</span>
            <h2 id="quick-action-title">
              {action === 'fund' ? 'Пополнить резерв' : 'Вывести доступное'}
            </h2>
          </div>
          <button className="dialog-close" aria-label="Закрыть" onClick={onClose}>
            <X size={21} />
          </button>
        </header>

        <div className="mode-picker" aria-label="Выбери раздел">
          {contracts.map((item) => (
            <button
              key={item.mode}
              className={item.mode === contract.mode ? 'selected' : ''}
              aria-pressed={item.mode === contract.mode}
              onClick={() => {
                setMode(item.mode);
                setAmountText('');
                setPauseRequested(false);
              }}
            >
              {item.mode.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="quick-balance">
          <span>
            {action === 'fund' ? 'Сейчас в резерве' : 'Можно вывести без средств участников'}
          </span>
          <strong>
            {gram(action === 'fund' ? contract.balance_nano : contract.withdrawable_nano)} GRAM
          </strong>
        </div>

        {!busy &&
          (contract.error || !contract.owner_matches_session || !contract.extended_controls) && (
            <div className="inline-warning">
              <Warning size={19} />
              <span>Эта операция сейчас недоступна. Проверь раздел в полном управлении.</span>
            </div>
          )}

        {needsPause ? (
          <div className="guided-step">
            <span>ШАГ 1 ИЗ 2</span>
            <h3>
              {waitingForPause
                ? `Подтверждаем паузу ${contract.mode.toUpperCase()}`
                : `Сначала поставь ${contract.mode.toUpperCase()} на паузу`}
            </h3>
            <p>
              {waitingForPause
                ? 'Как только сеть подтвердит действие, здесь появится ввод суммы.'
                : 'Так сумма не изменится во время вывода. Открытые выплаты останутся защищены.'}
            </p>
            <button
              className="button light"
              disabled={!enabled || waitingForPause}
              onClick={() => {
                void onAction({
                  mode: contract.mode,
                  action: 'pause',
                  paused: true,
                }).then((accepted) => {
                  if (accepted) setPauseRequested(true);
                });
              }}
            >
              {waitingForPause ? (
                <CircleNotch className="spin" size={18} />
              ) : (
                <Pause size={18} weight="fill" />
              )}
              {waitingForPause ? 'ЖДЁМ ПОДТВЕРЖДЕНИЕ…' : 'ПОСТАВИТЬ НА ПАУЗУ'}
            </button>
            <button className="text-button" onClick={() => onOpenAdvanced(contract.mode)}>
              Открыть полное управление <ArrowRight size={15} />
            </button>
          </div>
        ) : (
          <>
            <label className="quick-amount">
              <span>Сумма, GRAM</span>
              <input
                autoFocus
                inputMode="decimal"
                value={amountText}
                onChange={(event) => setAmountText(event.target.value)}
                placeholder="0"
              />
            </label>
            {tooMuch && (
              <p className="field-error">
                Доступно не больше {gram(contract.withdrawable_nano)} GRAM.
              </p>
            )}
            <p className="quick-note">
              {action === 'withdraw' && contract.withdrawable_nano === 0
                ? 'Сейчас свободного остатка нет.'
                : action === 'fund'
                  ? 'Кошелёк покажет точную сумму перед подтверждением.'
                  : 'Средства поступят в казну. Деньги участников вывести нельзя.'}
            </p>
            <button
              className="button light quick-submit"
              disabled={
                !enabled ||
                !amount ||
                tooMuch ||
                (contract.withdrawable_nano === 0 && action === 'withdraw')
              }
              onClick={() => void submit()}
            >
              {action === 'fund' ? <Coins size={19} /> : <DownloadSimple size={19} />}
              {busy ? 'ПОДОЖДИ…' : 'ПОДТВЕРДИТЬ В КОШЕЛЬКЕ'}
            </button>
          </>
        )}
      </section>
    </dialog>
  );
}

function ServiceSummary({
  contract,
  onManage,
}: {
  contract: ContractControl;
  onManage: (mode: ContractControl['mode']) => void;
}) {
  const status = contractStatus(contract);
  return (
    <article className="service-row">
      <div className="service-identity">
        <span className="service-symbol">{contract.mode === 'bank' ? '◇' : '∞'}</span>
        <div>
          <h3>{contract.mode.toUpperCase()}</h3>
          <span className={`service-status ${status.tone}`}>{status.label}</span>
        </div>
      </div>
      {contract.error ? (
        <p className="service-error">{contract.error}</p>
      ) : (
        <dl className="service-money">
          <div>
            <dt>Всего</dt>
            <dd>{gram(contract.balance_nano)} GRAM</dd>
          </div>
          <div>
            <dt>Участникам</dt>
            <dd>{gram(contract.locked_nano)} GRAM</dd>
          </div>
          <div>
            <dt>Можно вывести</dt>
            <dd>{gram(contract.withdrawable_nano)} GRAM</dd>
          </div>
        </dl>
      )}
      <button className="manage-button" onClick={() => onManage(contract.mode)}>
        Настроить <ArrowRight size={16} />
      </button>
    </article>
  );
}

function AppSwitch({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="app-switch">
      <span>
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <i aria-hidden="true" />
    </label>
  );
}

export default function ControlApp() {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  const [authenticatedWallet, setAuthenticatedWallet] = useState<string | null>(null);
  const [overview, setOverview] = useState<ControlOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quickAction, setQuickAction] = useState<QuickAction | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const proofRequest = useRef<Promise<void> | null>(null);
  const verifiedProof = useRef<string | null>(null);
  const refreshTimers = useRef<number[]>([]);

  const prepareProof = useCallback(() => {
    if (proofRequest.current) return proofRequest.current;
    tonConnectUI.setConnectRequestParameters({ state: 'loading' });
    proofRequest.current = controlApi
      .challenge()
      .then(({ payload }) => {
        tonConnectUI.setConnectRequestParameters({
          state: 'ready',
          value: { tonProof: payload },
        });
      })
      .catch((reason: unknown) => {
        proofRequest.current = null;
        throw reason;
      });
    return proofRequest.current;
  }, [tonConnectUI]);

  const refresh = useCallback(async () => {
    const result = await controlApi.overview();
    setOverview(result);
    setAuthenticatedWallet(result.wallet);
  }, []);

  useEffect(
    () => () => {
      refreshTimers.current.forEach((timer) => window.clearTimeout(timer));
    },
    [],
  );

  useEffect(() => {
    let alive = true;
    void controlApi
      .session()
      .then(async ({ wallet: sessionWallet }) => {
        if (!alive) return;
        setAuthenticatedWallet(sessionWallet);
        await refresh();
      })
      .catch(async (reason: unknown) => {
        if (!alive) return;
        if (!(reason instanceof ControlApiError) || reason.status !== 401) {
          setError(reason instanceof Error ? reason.message : 'Не удалось проверить вход');
        }
        await prepareProof().catch((challengeError: unknown) => {
          if (alive)
            setError(
              challengeError instanceof Error
                ? challengeError.message
                : 'Не удалось подготовить подтверждение',
            );
        });
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [prepareProof, refresh]);

  useEffect(() => {
    if (authenticatedWallet || !wallet || !wallet.account.publicKey) return;
    const proof = wallet.connectItems?.tonProof;
    if (!proof || !('proof' in proof)) return;
    const proofKey = `${wallet.account.address}:${proof.proof.payload}`;
    if (verifiedProof.current === proofKey) return;
    verifiedProof.current = proofKey;
    setBusy(true);
    setError(null);
    void controlApi
      .createSession({
        address: wallet.account.address,
        network: Number(wallet.account.chain),
        publicKey: wallet.account.publicKey,
        proof: proof.proof,
      })
      .then(async ({ wallet: sessionWallet }) => {
        setAuthenticatedWallet(sessionWallet);
        await refresh();
      })
      .catch(async (reason: unknown) => {
        verifiedProof.current = null;
        proofRequest.current = null;
        setError(reason instanceof Error ? reason.message : 'Подтверждение отклонено');
        await tonConnectUI.disconnect();
        await prepareProof().catch(() => undefined);
      })
      .finally(() => setBusy(false));
  }, [authenticatedWallet, prepareProof, refresh, tonConnectUI, wallet]);

  const connect = async () => {
    setError(null);
    if (wallet) await tonConnectUI.disconnect();
    proofRequest.current = null;
    await prepareProof();
    await tonConnectUI.openModal();
  };

  const runAction = async (input: ControlActionInput) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const transaction = await controlApi.transaction(input);
      await tonConnectUI.sendTransaction({
        validUntil: transaction.valid_until,
        network: String(transaction.network),
        messages: [
          {
            address: transaction.address,
            amount: transaction.amount_nano,
            payload: transaction.payload,
          },
        ],
      });
      setMessage('Команда подписана. Ждём подтверждение сети.');
      refreshTimers.current.forEach((timer) => window.clearTimeout(timer));
      refreshTimers.current = [4_000, 12_000, 30_000].map((delay) =>
        window.setTimeout(() => void refresh().catch(() => undefined), delay),
      );
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Команда не выполнена');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const updateApplication = async (change: Partial<ApplicationControl>) => {
    setBusy(true);
    setError(null);
    try {
      const application = await controlApi.updateApplication(change);
      setOverview((current) => (current ? { ...current, application } : current));
      setMessage('Настройки приложения сохранены.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Настройки не сохранены');
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    refreshTimers.current.forEach((timer) => window.clearTimeout(timer));
    refreshTimers.current = [];
    await controlApi.logout().catch(() => undefined);
    await tonConnectUI.disconnect().catch(() => undefined);
    setAuthenticatedWallet(null);
    setOverview(null);
    proofRequest.current = null;
    await prepareProof().catch(() => undefined);
  };

  const openAdvanced = (mode?: ContractControl['mode']) => {
    setQuickAction(null);
    setAdvancedOpen(true);
    window.requestAnimationFrame(() => {
      document
        .getElementById(mode ? `contract-${mode}` : 'advanced')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  if (loading) {
    return (
      <main className="control-center">
        <CircleNotch className="spin" size={32} />
        <span>Проверяем защищённый вход…</span>
      </main>
    );
  }

  if (!authenticatedWallet || !overview) {
    return (
      <main className="control-login">
        <section>
          <div className="control-mark">∞</div>
          <span className="eyebrow">LOOP · ДЛЯ ВЛАДЕЛЬЦА</span>
          <h1>Управление LOOP</h1>
          <p>Подключи кошелёк владельца. Подпись подтвердит вход — деньги никуда не переводятся.</p>
          <button
            className="button light login-button"
            disabled={busy}
            onClick={() => void connect()}
          >
            <ShieldCheck size={21} weight="fill" />
            {busy ? 'ПРОВЕРЯЕМ…' : 'ПОДКЛЮЧИТЬ КОШЕЛЁК'}
          </button>
          {error && <div className="login-error">{error}</div>}
          <small className="login-note">Доступ автоматически закроется через один час.</small>
        </section>
      </main>
    );
  }

  const currentStatus = systemStatus(overview);

  return (
    <main className="control-shell">
      <header className="control-header">
        <div className="control-brand">
          <div className="rail-brand">∞</div>
          <div>
            <strong>LOOP</strong>
            <span>Управление</span>
          </div>
        </div>
        <div className="header-actions">
          <a className="header-app-link" href="/" target="_blank" rel="noreferrer">
            Открыть LOOP <ArrowSquareOut size={15} />
          </a>
          <div className="owner-chip" title={authenticatedWallet}>
            <span className="live-dot" />
            {shortAddress(authenticatedWallet)}
          </div>
          <button className="header-logout" aria-label="Выйти" onClick={() => void logout()}>
            <SignOut size={19} />
            <span>Выйти</span>
          </button>
        </div>
      </header>

      <div className="control-content">
        <header className="control-topbar">
          <div>
            <span className={`system-label ${currentStatus.tone}`}>
              <span />
              {currentStatus.eyebrow}
            </span>
            <h1>{currentStatus.title}</h1>
            <p>{currentStatus.description}</p>
          </div>
          <button className="icon-button" disabled={busy} onClick={() => void refresh()}>
            <ArrowClockwise size={20} className={busy ? 'spin' : ''} />
            Обновить
          </button>
        </header>

        {(error || message) && (
          <button
            className={`control-toast ${error ? 'error' : ''}`}
            onClick={() => {
              setError(null);
              setMessage(null);
            }}
          >
            {error ? <Warning size={19} /> : <CheckCircle size={19} />}
            {error ?? message}
          </button>
        )}

        <section id="overview" className="command-section">
          <div className="command-actions">
            <button
              className="command-action"
              disabled={busy}
              onClick={() =>
                void updateApplication({
                  maintenance_enabled: !overview.application.maintenance_enabled,
                })
              }
            >
              <span className="command-icon">
                {overview.application.maintenance_enabled ? (
                  <Play size={22} weight="fill" />
                ) : (
                  <Pause size={22} weight="fill" />
                )}
              </span>
              <span>
                <strong>
                  {overview.application.maintenance_enabled
                    ? 'Возобновить работу'
                    : 'Остановить новые действия'}
                </strong>
                <small>
                  {overview.application.maintenance_enabled
                    ? 'Снова разрешить новые циклы и дуэли'
                    : 'Открытые операции продолжат завершаться'}
                </small>
              </span>
              <ArrowRight size={18} />
            </button>
            <button
              className="command-action primary"
              disabled={busy}
              onClick={() => setQuickAction('fund')}
            >
              <span className="command-icon">
                <Coins size={23} />
              </span>
              <span>
                <strong>Пополнить резерв</strong>
                <small>Добавить GRAM для выплат и работы LOOP</small>
              </span>
              <ArrowRight size={18} />
            </button>
            <button
              className="command-action"
              disabled={busy}
              onClick={() => setQuickAction('withdraw')}
            >
              <span className="command-icon">
                <DownloadSimple size={22} />
              </span>
              <span>
                <strong>Вывести доступное</strong>
                <small>Только остаток, который не принадлежит участникам</small>
              </span>
              <ArrowRight size={18} />
            </button>
          </div>
          <div className="metric-strip">
            <div>
              <Users size={20} />
              <span>Участников</span>
              <strong>{overview.metrics.users}</strong>
            </div>
            <div>
              <Bank size={20} />
              <span>Живых циклов</span>
              <strong>{overview.metrics.active_bank_positions}</strong>
            </div>
            <div>
              <span className="metric-symbol">∞</span>
              <span>Активных дуэлей</span>
              <strong>{overview.metrics.active_duels}</strong>
            </div>
          </div>
        </section>

        <section className="services-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">ДВА РАЗДЕЛА</span>
              <h2>BANK и DUEL</h2>
              <p>Сразу видно, сколько находится в работе и сколько можно вывести.</p>
            </div>
          </div>
          <div className="service-list">
            {overview.contracts.map((contract) => (
              <ServiceSummary key={contract.mode} contract={contract} onManage={openAdvanced} />
            ))}
          </div>
        </section>

        <section id="advanced" className={`advanced-section ${advancedOpen ? 'open' : ''}`}>
          <button
            className="advanced-toggle"
            aria-expanded={advancedOpen}
            aria-controls="advanced-content"
            onClick={() => setAdvancedOpen((value) => !value)}
          >
            <span className="advanced-icon">
              <GearSix size={23} />
            </span>
            <div>
              <strong>Расширенное управление</strong>
              <small>Отдельные паузы, комиссии, адреса и передача доступа</small>
            </div>
            <CaretDown size={20} className="advanced-caret" />
          </button>

          {advancedOpen && (
            <div id="advanced-content" className="advanced-content">
              <section id="application" className="application-section">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">ДОСТУПНОСТЬ</span>
                    <h2>Что могут делать пользователи</h2>
                  </div>
                </div>
                <div className="switch-panel">
                  <AppSwitch
                    label="Режим обслуживания"
                    description="Не принимать новые циклы и дуэли"
                    checked={overview.application.maintenance_enabled}
                    disabled={busy}
                    onChange={(value) => void updateApplication({ maintenance_enabled: value })}
                  />
                  <AppSwitch
                    label="Разрешить новые циклы"
                    description="Пользователи смогут начинать новые циклы BANK"
                    checked={overview.application.bank_enabled}
                    disabled={busy || overview.application.maintenance_enabled}
                    onChange={(value) => void updateApplication({ bank_enabled: value })}
                  />
                  <AppSwitch
                    label="Разрешить новые дуэли"
                    description="Пользователи смогут искать и принимать вызовы"
                    checked={overview.application.duel_enabled}
                    disabled={busy || overview.application.maintenance_enabled}
                    onChange={(value) => void updateApplication({ duel_enabled: value })}
                  />
                </div>
                <p className="safety-note">
                  Режим обслуживания не мешает завершить уже открытые операции и получить выплату.
                </p>
              </section>

              <section id="contracts" className="contracts-section">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">ДЕНЬГИ И ПРАВИЛА</span>
                    <h2>Управление BANK и DUEL</h2>
                    <p>Изменение комиссии, адресов и вывод доступны только после паузы.</p>
                  </div>
                </div>
                <div className="contracts-grid">
                  {overview.contracts.map((contract) => (
                    <ContractCard
                      key={contract.mode}
                      contract={contract}
                      busy={busy}
                      onAction={runAction}
                    />
                  ))}
                </div>
              </section>
            </div>
          )}
        </section>

        <details id="history" className="history-section history-disclosure">
          <summary>
            <div>
              <span className="eyebrow">ИСТОРИЯ</span>
              <strong>Последние действия</strong>
              <small>
                {overview.audit.length === 0
                  ? 'Пока пусто'
                  : `${overview.audit.length} ${overview.audit.length === 1 ? 'запись' : 'записей'}`}
              </small>
            </div>
            <CaretDown size={20} />
          </summary>
          <div className="history-list">
            {overview.audit.length === 0 ? (
              <p className="empty-history">Действий пока нет.</p>
            ) : (
              overview.audit.map((event) => (
                <article key={event.id}>
                  <span className={`history-status ${event.status}`} />
                  <div>
                    <strong>{actionLabel(event.action)}</strong>
                    <small>{new Date(event.created_at).toLocaleString('ru-RU')}</small>
                  </div>
                  <span>{event.status === 'confirmed' ? 'ПОДТВЕРЖДЕНО' : 'ОЖИДАЕТ'}</span>
                </article>
              ))
            )}
          </div>
        </details>

        <footer className="control-footer">
          <span>LOOP · ПАНЕЛЬ ВЛАДЕЛЬЦА</span>
          <a href="/" target="_blank" rel="noreferrer">
            Открыть приложение <ArrowSquareOut size={15} />
          </a>
        </footer>
      </div>

      {quickAction && (
        <QuickActionSheet
          action={quickAction}
          contracts={overview.contracts}
          busy={busy}
          onClose={() => setQuickAction(null)}
          onAction={runAction}
          onOpenAdvanced={openAdvanced}
        />
      )}
    </main>
  );
}
