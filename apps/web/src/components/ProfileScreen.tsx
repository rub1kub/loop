import {
  ArrowRight,
  ArrowSquareOut,
  BellRinging,
  GearSix,
  Infinity as InfinityIcon,
  Link,
  PaperPlaneTilt,
  ShieldCheck,
  UsersThree,
  Vibrate,
  Wallet,
  X,
} from '@phosphor-icons/react';
import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';

import { api } from '../api';
import { humanError } from '../errors';
import {
  haptic,
  isHapticsEnabled,
  isMockTelegram,
  setHapticsEnabled,
  sharePreparedResult,
  telegram,
} from '../telegram';
import { formatGram } from '../ton';
import type { BankPosition, Duel, Profile, Rating, Referral } from '../types';
import { DisclosureIndicator } from './DisclosureIndicator';

import { friendlyAddress } from '../address';
import { celebrate } from '../celebrate';

function shortAddress(address: string): string {
  return `${address.slice(0, 7)}…${address.slice(-5)}`;
}

const demoReferral: Referral = {
  code: 'LOOPDEMO',
  url: 'https://t.me/getloopbot?startapp=ref_LOOPDEMO',
  invited: 3,
  qualified: 2,
  turns_accepted: 2,
  reward_points: 200,
  reward_nano: 960_000_000,
  share_bps: 500,
  available_nano: 900_000_000,
  minimum_payout_nano: 500_000_000,
  pending_payout: null,
  history: [
    {
      cause: 'fee_share:demo-1',
      reward_points: 0,
      reward_nano: 600_000_000,
      payout_tx_hash: null,
      created_at: new Date().toISOString(),
      invitee_first_name: 'Иван',
      invitee_username: 'ivan_loop',
      deposit_nano: 20_000_000_000,
    },
    {
      cause: 'fee_share:demo-2',
      reward_points: 0,
      reward_nano: 360_000_000,
      payout_tx_hash: null,
      created_at: new Date(Date.now() - 3_600_000).toISOString(),
      invitee_first_name: 'Мария',
      invitee_username: null,
      deposit_nano: 12_000_000_000,
    },
  ],
};

export function ProfileScreen({
  profile,
  rating,
  bankHistory,
  duels,
  onReplay,
  onResultNotificationsChange,
}: {
  profile: Profile;
  rating: Rating | null;
  bankHistory: BankPosition[];
  duels: Duel[];
  onReplay: () => void;
  onResultNotificationsChange: (enabled: boolean) => Promise<void>;
}) {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  const [settingsOpen, setSettingsOpen] = useState(
    () =>
      isMockTelegram() && new URLSearchParams(window.location.search).get('screen') === 'settings',
  );
  const [referral, setReferral] = useState<Referral | null>(() =>
    isMockTelegram() ? demoReferral : null,
  );
  const [payoutOpen, setPayoutOpen] = useState(false);
  const [payoutAddress, setPayoutAddress] = useState('');
  const [payoutBusy, setPayoutBusy] = useState(false);
  const [payoutError, setPayoutError] = useState('');
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [vibrationEnabled, setVibrationEnabled] = useState(isHapticsEnabled);
  const [notificationPending, setNotificationPending] = useState(false);

  useEffect(() => {
    if (isMockTelegram()) return;
    void api
      .referrals()
      .then(setReferral)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (isMockTelegram()) return;
    let active = true;
    let objectUrl: string | null = null;
    void api
      .meAvatar()
      .then((avatar) => {
        if (!avatar || !active) return;
        objectUrl = URL.createObjectURL(avatar);
        setAvatarUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [profile.user.id, profile.user.photo_url]);

  async function submitPayout() {
    if (payoutBusy || !referral) return;
    setPayoutBusy(true);
    setPayoutError('');
    try {
      const payout = await api.requestReferralPayout(payoutAddress.trim());
      setReferral({ ...referral, available_nano: 0, pending_payout: payout });
      setPayoutOpen(false);
      setPayoutAddress('');
      haptic('success');
    } catch (error: unknown) {
      setPayoutError(humanError(error, 'Не удалось отправить заявку') ?? '');
      haptic('warning');
    } finally {
      setPayoutBusy(false);
    }
  }

  async function shareReferral() {
    if (!referral) return;
    haptic('light');
    // The same one-tap card the prelaunch screen sends: chat picker over the
    // app, referral code baked in. The bare link stays as the desktop fallback.
    try {
      const prepared = await api.prepareInviteShare();
      if (await sharePreparedResult(prepared.prepared_message_id, prepared.fallback_query)) return;
    } catch {
      // The card is a nicety; the link below still carries the code.
    }
    const url = `https://t.me/share/url?url=${encodeURIComponent(referral.url)}&text=${encodeURIComponent('Попробуй BANK и DUEL в LOOP.')}`;
    if (telegram()) telegram()?.openTelegramLink(url);
    else await navigator.clipboard.writeText(referral.url);
  }

  // Becoming a holder is the moment DUEL's fee drops to zero — worth a smaller
  // mark than a payout, but it should not pass in silence.
  const wasHolder = useRef(profile.plush_brick.holder);
  useEffect(() => {
    if (profile.plush_brick.holder && !wasHolder.current) celebrate('spark');
    wasHolder.current = profile.plush_brick.holder;
  }, [profile.plush_brick.holder]);

  const recentBank = bankHistory.find((item) => item.proof_url);
  const recentDuel = duels.find((item) => item.settlement_proof_url);
  const displayedAvatarUrl = isMockTelegram() ? profile.user.photo_url : avatarUrl;

  return (
    <section className="screen profile-screen" aria-labelledby="profile-title">
      <header className="profile-identity">
        {displayedAvatarUrl ? (
          <img
            className="avatar"
            src={displayedAvatarUrl}
            alt=""
            onError={() => {
              if (!isMockTelegram()) setAvatarUrl(null);
            }}
          />
        ) : (
          <div className="avatar" aria-hidden="true">
            {profile.user.first_name.slice(0, 1).toUpperCase()}
          </div>
        )}
        <div>
          <p className="eyebrow">ПРОФИЛЬ</p>
          <h1 id="profile-title">{profile.user.first_name}</h1>
          <span>
            {profile.user.username ? `@${profile.user.username}` : 'Пользователь Telegram'}
          </span>
        </div>
        <button
          className="round-icon-button"
          aria-label="Настройки"
          onClick={() => setSettingsOpen(true)}
        >
          <GearSix aria-hidden="true" />
        </button>
      </header>

      <div className="profile-summary" aria-label="Главная статистика LOOP">
        <article>
          <strong>{rating?.me.score ?? '—'}</strong>
          <span>СЧЁТ LOOP</span>
          <small>{rating ? `#${rating.me.rank} в сезоне` : 'обновляем данные'}</small>
        </article>
        <article>
          <strong>{profile.bank.completed}</strong>
          <span>BANK · ВЫПЛАЧЕНО</span>
          <small>{profile.bank.active ? `${profile.bank.active} в работе` : 'нет активных'}</small>
        </article>
        <article>
          <strong>{profile.duel.completed}</strong>
          <span>DUEL</span>
          <small>{profile.duel.active ? `${profile.duel.active} в работе` : 'нет активных'}</small>
        </article>
      </div>

      <div className="section-label">
        {/* The referral reward history and the monthly LOOP score are two
            different counters. Showing both as "ОЧКОВ" next to СЧЁТ LOOP read
            as one metric, so friends are reported as friends. */}
        <span>МОИ ЛЮДИ</span>
        <small>ПОДТВЕРЖДЕНО: {referral?.qualified ?? 0}</small>
      </div>
      <div className="referral-earnings">
        <strong>{formatGram(referral?.reward_nano ?? 0, 2)} GRAM</strong>
        <span>
          заработано на {String((referral?.share_bps ?? 500) / 100).replace('.', ',')}% со взносов
          приглашённых — навсегда
        </span>
        {referral?.pending_payout ? (
          <small>
            Заявка на {formatGram(referral.pending_payout.amount_nano, 3)} GRAM отправлена. Выплата
            придёт на указанный кошелёк.
          </small>
        ) : (referral?.available_nano ?? 0) >= (referral?.minimum_payout_nano ?? 0) &&
          (referral?.available_nano ?? 0) > 0 ? (
          <button className="referral-payout-open" onClick={() => setPayoutOpen((open) => !open)}>
            {payoutOpen ? 'ОТМЕНА' : `ВЫВЕСТИ ${formatGram(referral!.available_nano, 3)} GRAM`}
          </button>
        ) : (
          (referral?.reward_nano ?? 0) > 0 && (
            <small>
              Вывести можно от {formatGram(referral!.minimum_payout_nano, 2)} GRAM. Приглашай ещё.
            </small>
          )
        )}
      </div>
      {payoutOpen && referral && (
        <div className="referral-payout">
          <label className="stake-input">
            <span className="stake-input-heading">
              <span>КОШЕЛЁК ДЛЯ ВЫПЛАТЫ</span>
            </span>
            <div>
              <input
                value={payoutAddress}
                onChange={(event) => setPayoutAddress(event.target.value)}
                placeholder={profile.wallet?.address ? 'UQ…' : 'UQ…'}
                aria-label="Адрес кошелька для выплаты"
                autoComplete="off"
                spellCheck={false}
              />
            </div>
          </label>
          {profile.wallet && (
            // Подключённый кошелёк — самый вероятный ответ, но подставлять его
            // молча нельзя: деньги должны уйти туда, куда человек сказал сам.
            <button
              className="referral-payout-fill"
              onClick={() => setPayoutAddress(profile.wallet!.address)}
            >
              Подставить подключённый
            </button>
          )}
          <button
            className="primary-button"
            disabled={payoutBusy || payoutAddress.trim().length < 48}
            onClick={() => void submitPayout()}
          >
            {payoutBusy
              ? 'ОТПРАВЛЯЕМ…'
              : `ЗАПРОСИТЬ ${formatGram(referral.available_nano, 3)} GRAM`}
          </button>
          {payoutError && <p className="referral-payout-error">{payoutError}</p>}
          <p className="referral-payout-note">
            Выплата отправляется вручную. Проверь адрес — деньги уйдут именно на него.
          </p>
        </div>
      )}
      <button className="profile-row" onClick={() => void shareReferral()} disabled={!referral}>
        <span className="row-icon">
          <UsersThree />
        </span>
        <div>
          <b>Пригласить в LOOP</b>
          <small>
            {referral
              ? `Приглашено: ${referral.invited} · участвуют: ${referral.qualified}`
              : 'Загружаем ссылку'}
          </small>
        </div>
        <PaperPlaneTilt aria-hidden="true" />
      </button>
      {referral !== null && referral.history.length > 0 && (
        <ul className="referral-feed">
          {referral.history.slice(0, 8).map((entry) => (
            <li key={`${entry.cause}-${entry.created_at}`}>
              <span>
                {entry.invitee_username
                  ? `@${entry.invitee_username}`
                  : (entry.invitee_first_name ?? 'Приглашённый')}
                {entry.deposit_nano > 0
                  ? ` · взнос ${formatGram(entry.deposit_nano, 2)} GRAM`
                  : ' · квалификация'}
              </span>
              <b>
                {entry.reward_nano > 0
                  ? `+${formatGram(entry.reward_nano, 3)} GRAM`
                  : `+${entry.reward_points}`}
              </b>
            </li>
          ))}
        </ul>
      )}

      <details className="profile-proof-details">
        <summary>
          <span>
            <ShieldCheck aria-hidden="true" />
            ПОДКЛЮЧЕНИЕ И ИСТОРИЯ
          </span>
          <DisclosureIndicator />
        </summary>
        <div className="profile-proof-content">
          <div className="section-label">
            <span>ВНЕШНИЙ КОШЕЛЁК</span>
          </div>
          <button className="profile-row" onClick={() => void tonConnectUI.openModal()}>
            <span className="row-icon">{profile.wallet ? <ShieldCheck /> : <Wallet />}</span>
            <div>
              <b>{profile.wallet ? 'Кошелёк подключён' : 'Подключить кошелёк'}</b>
              <small>
                {profile.wallet
                  ? shortAddress(friendlyAddress(profile.wallet.address, profile.wallet.network))
                  : 'Для подписи операций и получения выплат'}
              </small>
            </div>
            <ArrowRight aria-hidden="true" />
          </button>

          <div className="section-label">
            <span>PLUSH BRICK</span>
          </div>
          <div className="profile-row static-row">
            <span className="row-icon row-icon-mark">
              <img src="/assets/plush-brick-mark-color.webp" alt="" width={40} height={40} />
            </span>
            <div>
              <b>{profile.plush_brick.holder ? 'Владение подтверждено' : 'Токен не найден'}</b>
              <small>
                {!profile.plush_brick.verified
                  ? 'Проверка временно недоступна'
                  : profile.plush_brick.fee_discount_active
                    ? 'Комиссия DUEL 0% — ты держатель PLUSH BRICK'
                    : `Комиссия DUEL ${String(profile.plush_brick.duel_fee_bps / 100).replace('.', ',')}%`}
              </small>
            </div>
            <ShieldCheck aria-hidden="true" />
          </div>

          <div className="section-label">
            <span>ПОСЛЕДНИЕ ОПЕРАЦИИ</span>
          </div>
          <div className="proof-history">
            <ProofRow
              mode="BANK"
              title={
                recentBank
                  ? `${formatGram(recentBank.principal_nano, 3)} GRAM · позиция`
                  : 'Операций пока нет'
              }
              url={recentBank?.proof_url ?? null}
            />
            <ProofRow
              mode="DUEL"
              title={
                recentDuel
                  ? `${formatGram(recentDuel.payout_nano, 3)} GRAM · результат`
                  : 'Операций пока нет'
              }
              url={recentDuel?.settlement_proof_url ?? null}
            />
          </div>
        </div>
      </details>

      <AnimatePresence>
        {settingsOpen && (
          <motion.div
            className="sheet-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSettingsOpen(false)}
          >
            <motion.div
              className="sheet settings-sheet"
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', stiffness: 260, damping: 30 }}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="sheet-title-row">
                <div>
                  <p className="eyebrow">LOOP</p>
                  <h2>Настройки</h2>
                </div>
                <button
                  className="round-icon-button"
                  onClick={() => setSettingsOpen(false)}
                  aria-label="Закрыть"
                >
                  <X aria-hidden="true" />
                </button>
              </div>
              <button
                className="settings-row"
                onClick={() => {
                  setSettingsOpen(false);
                  onReplay();
                }}
              >
                <span>
                  <InfinityIcon /> Повторить обучение
                </span>
                <ArrowRight />
              </button>
              <label className="settings-toggle">
                <span>
                  <Vibrate /> Вибрация
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  aria-label="Вибрация"
                  checked={vibrationEnabled}
                  onChange={(event) => {
                    const enabled = event.currentTarget.checked;
                    setHapticsEnabled(enabled);
                    setVibrationEnabled(enabled);
                    if (enabled) haptic('light');
                  }}
                />
              </label>
              <label className="settings-toggle">
                <span>
                  <BellRinging /> Сообщения в Telegram
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  aria-label="Сообщения в Telegram"
                  checked={profile.user.result_notifications_enabled}
                  disabled={notificationPending}
                  onChange={(event) => {
                    const enabled = event.currentTarget.checked;
                    setNotificationPending(true);
                    void onResultNotificationsChange(enabled)
                      .then(() => haptic(enabled ? 'success' : 'light'))
                      .finally(() => setNotificationPending(false));
                  }}
                />
              </label>
              {wallet && (
                <button className="settings-row" onClick={() => void tonConnectUI.disconnect()}>
                  <span>
                    <Link /> Отключить внешний кошелёк
                  </span>
                  <ArrowRight />
                </button>
              )}
              <p>LOOP НЕ ХРАНИТ ВНУТРЕННИЙ БАЛАНС</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function ProofRow({ mode, title, url }: { mode: string; title: string; url: string | null }) {
  const content = (
    <>
      <span>
        <b>{mode}</b>
        <small>{title}</small>
      </span>
      {url ? <ArrowSquareOut aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
    </>
  );
  return url ? (
    <a href={url} target="_blank" rel="noreferrer">
      {content}
    </a>
  ) : (
    <div>{content}</div>
  );
}
