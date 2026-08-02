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
import { haptic, isHapticsEnabled, isMockTelegram, setHapticsEnabled, telegram } from '../telegram';
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
  qualified: 1,
  reward_points: 100,
  reward_nano: 0,
  history: [],
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

  async function shareReferral() {
    if (!referral) return;
    haptic('light');
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
        <span>ТВОИ ДРУЗЬЯ</span>
        <small>ПОДТВЕРЖДЕНО: {referral?.qualified ?? 0}</small>
      </div>
      <button className="profile-row" onClick={() => void shareReferral()} disabled={!referral}>
        <span className="row-icon">
          <UsersThree />
        </span>
        <div>
          <b>Пригласить в LOOP</b>
          <small>
            {referral
              ? `${referral.qualified} подтверждено из ${referral.invited}`
              : 'Загружаем ссылку'}
          </small>
        </div>
        <PaperPlaneTilt aria-hidden="true" />
      </button>

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
              <img src="/assets/plush-brick-mark.webp" alt="" width={40} height={40} />
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
                  <BellRinging /> Карточки в Telegram
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  aria-label="Карточки в Telegram"
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
