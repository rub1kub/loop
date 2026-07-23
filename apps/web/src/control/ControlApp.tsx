import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import {
  ArrowClockwise,
  ArrowSquareOut,
  Bank,
  CheckCircle,
  CircleNotch,
  LockKey,
  Pause,
  Play,
  ShieldCheck,
  SignOut,
  Users,
  Warning,
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
  onAction: (input: ControlActionInput) => Promise<void>;
};

function ContractCard({ contract, busy, onAction }: ContractCardProps) {
  const [reserveAmount, setReserveAmount] = useState('');
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [feeBps, setFeeBps] = useState(String(contract.fee_bps));
  const [treasury, setTreasury] = useState(contract.treasury);
  const [owner, setOwner] = useState('');
  const enabled = !busy && !contract.error && contract.owner_matches_session;
  const canConfigure = enabled && contract.extended_controls && contract.paused;

  const amountAction = async (action: 'fund_reserve' | 'withdraw_surplus', value: string) => {
    const amount = nanoFromInput(value);
    if (!amount) {
      window.alert('Укажи корректную сумму GRAM');
      return;
    }
    if (action === 'withdraw_surplus' && !window.confirm(`Вывести ${gram(amount)} GRAM в казну?`))
      return;
    await onAction({ mode: contract.mode, action, amount_nano: amount });
    if (action === 'fund_reserve') setReserveAmount('');
    else setWithdrawAmount('');
  };

  return (
    <article className="control-contract">
      <header className="contract-head">
        <div>
          <span className="eyebrow">КОНТРАКТ</span>
          <h2>{contract.mode.toUpperCase()}</h2>
        </div>
        <span
          className={`status-pill ${
            contract.error || !contract.code_hash_matches
              ? 'danger'
              : contract.paused
                ? 'paused'
                : ''
          }`}
        >
          {contract.error
            ? 'НЕТ СВЯЗИ'
            : !contract.code_hash_matches
              ? 'КОД НЕ СОВПАЛ'
              : contract.paused
                ? 'ПАУЗА'
                : 'РАБОТАЕТ'}
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
              <span>Баланс</span>
              <strong>{gram(contract.balance_nano)} GRAM</strong>
            </div>
            <div>
              <span>Заблокировано</span>
              <strong>{gram(contract.locked_nano)} GRAM</strong>
            </div>
            <div>
              <span>Можно вывести</span>
              <strong>{gram(contract.withdrawable_nano)} GRAM</strong>
            </div>
            <div>
              <span>Комиссия</span>
              <strong>{contract.fee_bps / 100}%</strong>
            </div>
          </div>

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

          {!contract.owner_matches_session && (
            <div className="inline-warning">
              <LockKey size={20} />
              <span>Подключённый кошелёк не является владельцем этого контракта.</span>
            </div>
          )}
          {!contract.extended_controls && (
            <div className="inline-warning">
              <Warning size={20} />
              <span>
                Доступна только пауза. Для остальных команд нужна текущая версия контракта.
              </span>
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
            <summary>РЕЗЕРВ И НАСТРОЙКИ</summary>
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
                <span>Вывести свободный резерв, GRAM</span>
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
                <small>Только в казну. Средства участников недоступны для вывода.</small>
              </label>

              <label>
                <span>Комиссия, базисные пункты</span>
                <div className="field-action">
                  <input
                    inputMode="numeric"
                    value={feeBps}
                    onChange={(event) => setFeeBps(event.target.value)}
                  />
                  <button
                    disabled={!canConfigure}
                    onClick={() => {
                      const fee = Number(feeBps);
                      if (!Number.isInteger(fee) || fee < 0 || fee > 1000) {
                        window.alert('Комиссия должна быть от 0 до 1000');
                        return;
                      }
                      void onAction({ mode: contract.mode, action: 'set_fee', fee_bps: fee });
                    }}
                  >
                    СОХРАНИТЬ
                  </button>
                </div>
              </label>

              <label>
                <span>Адрес казны</span>
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
              </label>
            </div>

            <details className="danger-zone">
              <summary>ПЕРЕДАТЬ УПРАВЛЕНИЕ</summary>
              <p>После подтверждения текущий кошелёк потеряет доступ к контракту.</p>
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
  const proofRequest = useRef<Promise<void> | null>(null);
  const verifiedProof = useRef<string | null>(null);

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
      window.setTimeout(() => void refresh().catch(() => undefined), 4_000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Команда не выполнена');
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
    await controlApi.logout().catch(() => undefined);
    await tonConnectUI.disconnect().catch(() => undefined);
    setAuthenticatedWallet(null);
    setOverview(null);
    proofRequest.current = null;
    await prepareProof().catch(() => undefined);
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
          <span className="eyebrow">LOOP · ПАНЕЛЬ УПРАВЛЕНИЯ</span>
          <h1>Контроль без Telegram.</h1>
          <p>
            Открой кошелёк владельца и подпиши одноразовое подтверждение. Средства не переводятся.
          </p>
          <button
            className="button light login-button"
            disabled={busy}
            onClick={() => void connect()}
          >
            <ShieldCheck size={21} weight="fill" />
            {busy ? 'ПРОВЕРЯЕМ…' : 'ВОЙТИ ЧЕРЕЗ TON CONNECT'}
          </button>
          {error && <div className="login-error">{error}</div>}
          <small className="login-note">
            Сессия хранится в защищённой cookie и действует один час.
          </small>
        </section>
      </main>
    );
  }

  return (
    <main className="control-shell">
      <aside className="control-rail">
        <div>
          <div className="rail-brand">∞</div>
          <span>LOOP</span>
        </div>
        <nav aria-label="Разделы">
          <a href="#overview">Обзор</a>
          <a href="#application">Приложение</a>
          <a href="#contracts">Контракты</a>
          <a href="#history">История</a>
        </nav>
        <button className="rail-logout" onClick={() => void logout()}>
          <SignOut size={18} />
          Выйти
        </button>
      </aside>

      <div className="control-content">
        <header className="control-topbar">
          <div>
            <span className="eyebrow">ПАНЕЛЬ УПРАВЛЕНИЯ</span>
            <h1>Состояние LOOP</h1>
          </div>
          <div className="owner-chip" title={authenticatedWallet}>
            <span className="live-dot" />
            {shortAddress(authenticatedWallet)}
          </div>
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

        <section id="overview" className="overview-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">СЕЙЧАС</span>
              <h2>Главные показатели</h2>
            </div>
            <button className="icon-button" disabled={busy} onClick={() => void refresh()}>
              <ArrowClockwise size={20} className={busy ? 'spin' : ''} />
              Обновить
            </button>
          </div>
          <div className="metric-grid">
            <article>
              <Users size={22} />
              <strong>{overview.metrics.users}</strong>
              <span>участников</span>
            </article>
            <article>
              <Bank size={22} />
              <strong>{overview.metrics.active_bank_positions}</strong>
              <span>активных циклов</span>
            </article>
            <article>
              <span className="metric-symbol">∞</span>
              <strong>{overview.metrics.active_duels}</strong>
              <span>активных дуэлей</span>
            </article>
            <article>
              <ShieldCheck size={22} />
              <strong>{overview.metrics.worker_healthy ? 'Да' : 'Нет'}</strong>
              <span>синхронизация работает</span>
            </article>
          </div>
        </section>

        <section id="application" className="application-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">ПРИЛОЖЕНИЕ</span>
              <h2>Приём новых действий</h2>
            </div>
          </div>
          <div className="switch-panel">
            <AppSwitch
              label="Общая пауза"
              description="Остановить создание новых циклов и дуэлей"
              checked={overview.application.maintenance_enabled}
              disabled={busy}
              onChange={(value) => void updateApplication({ maintenance_enabled: value })}
            />
            <AppSwitch
              label="Новые циклы BANK"
              description="Разрешить пользователям открывать новые позиции"
              checked={overview.application.bank_enabled}
              disabled={busy || overview.application.maintenance_enabled}
              onChange={(value) => void updateApplication({ bank_enabled: value })}
            />
            <AppSwitch
              label="Новые DUEL"
              description="Разрешить поиск и принятие новых вызовов"
              checked={overview.application.duel_enabled}
              disabled={busy || overview.application.maintenance_enabled}
              onChange={(value) => void updateApplication({ duel_enabled: value })}
            />
          </div>
          <p className="safety-note">
            Пауза приложения не мешает завершить уже открытые операции и получить выплату.
          </p>
        </section>

        <section id="contracts" className="contracts-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">СЕТЬ</span>
              <h2>Контракты</h2>
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

        <section id="history" className="history-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">ЖУРНАЛ</span>
              <h2>Последние действия</h2>
            </div>
          </div>
          <div className="history-list">
            {overview.audit.length === 0 ? (
              <p className="empty-history">Административных действий пока нет.</p>
            ) : (
              overview.audit.map((event) => (
                <article key={event.id}>
                  <span className={`history-status ${event.status}`} />
                  <div>
                    <strong>{actionLabel(event.action)}</strong>
                    <small>{new Date(event.created_at).toLocaleString('ru-RU')}</small>
                  </div>
                  <span>{event.status === 'confirmed' ? 'ПОДТВЕРЖДЕНО' : 'ПОДГОТОВЛЕНО'}</span>
                </article>
              ))
            )}
          </div>
        </section>

        <footer className="control-footer">
          <span>LOOP · ПАНЕЛЬ ВЛАДЕЛЬЦА</span>
          <a href="/" target="_blank" rel="noreferrer">
            Открыть приложение <ArrowSquareOut size={15} />
          </a>
        </footer>
      </div>
    </main>
  );
}
