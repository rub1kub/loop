import {
  ArrowRight,
  GearSix,
  Infinity as InfinityIcon,
  Link,
  PaperPlaneTilt,
  ShieldCheck,
  Trophy,
  UsersThree,
  Wallet,
  X,
} from '@phosphor-icons/react';
import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { api } from '../api';
import { haptic, isMockTelegram, telegram } from '../telegram';
import type { Duel, Profile, Referral } from '../types';

function shortAddress(address: string): string {
  return `${address.slice(0, 6)}…${address.slice(-6)}`;
}

export function ProfileScreen({
  profile,
  duels,
  onReplay,
}: {
  profile: Profile;
  duels: Duel[];
  onReplay: () => void;
}) {
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [referral, setReferral] = useState<Referral | null>(() =>
    isMockTelegram()
      ? {
          code: 'LOOPDEMO',
          url: 'https://t.me/loop?startapp=ref_LOOPDEMO',
          invited: 3,
          qualified: 1,
          reward_points: 100,
        }
      : null,
  );

  useEffect(() => {
    if (isMockTelegram()) return;
    void api
      .referrals()
      .then(setReferral)
      .catch(() => undefined);
  }, []);

  async function shareReferral() {
    if (!referral) return;
    haptic('light');
    const url = `https://t.me/share/url?url=${encodeURIComponent(referral.url)}&text=${encodeURIComponent('Встретимся в LOOP.')}`;
    if (telegram()) telegram()?.openTelegramLink(url);
    else await navigator.clipboard.writeText(referral.url);
  }

  const wins = duels.filter(
    (duel) => duel.state === 'settled' && duel.winner_wallet === profile.wallet?.address,
  ).length;
  const cycleEvents = profile.bank?.event_count ?? 0;

  return (
    <section className="screen profile-screen" aria-labelledby="profile-title">
      <header className="profile-identity">
        {profile.user.photo_url ? (
          <img className="avatar" src={profile.user.photo_url} alt="" />
        ) : (
          <div className="avatar" aria-hidden="true">
            {profile.user.first_name.slice(0, 1).toUpperCase()}
          </div>
        )}
        <div>
          <p className="eyebrow">В LOOP</p>
          <h1 id="profile-title">{profile.user.first_name}</h1>
          <span>{profile.user.username ? `@${profile.user.username}` : 'Telegram user'}</span>
        </div>
        <button
          className="round-icon-button"
          aria-label="Настройки"
          onClick={() => setSettingsOpen(true)}
        >
          <GearSix aria-hidden="true" />
        </button>
      </header>

      <div className="profile-stats" aria-label="Статистика LOOP">
        <div>
          <strong>{cycleEvents}</strong>
          <span>СОБЫТИЙ</span>
        </div>
        <div>
          <strong>{duels.length}</strong>
          <span>ДУЭЛЕЙ</span>
        </div>
        <div>
          <strong>{referral?.invited ?? 0}</strong>
          <span>ДРУЗЕЙ</span>
        </div>
      </div>

      <div className="profile-highlight">
        <span className="profile-highlight-icon">
          {wins ? <Trophy aria-hidden="true" /> : <InfinityIcon aria-hidden="true" />}
        </span>
        <div>
          <p className="eyebrow">ТВОЙ СЛЕД</p>
          <strong>{wins ? `${wins} побед в этом LOOP` : 'Первый цикл уже живёт'}</strong>
          <small>
            {profile.bank
              ? `Цикл ${String(profile.bank.sequence_number).padStart(2, '0')}`
              : 'Начни с BANK'}
          </small>
        </div>
      </div>

      <div className="section-label">
        <span>SOCIAL</span>
        <small>{referral?.reward_points ?? 0} LOOP POINTS</small>
      </div>
      <button className="profile-row" onClick={() => void shareReferral()} disabled={!referral}>
        <span className="row-icon">
          <UsersThree aria-hidden="true" />
        </span>
        <div>
          <b>Позвать друга в LOOP</b>
          <small>Новый человек — новое событие цикла</small>
        </div>
        <PaperPlaneTilt aria-hidden="true" />
      </button>

      <div className="section-label">
        <span>ПОДТВЕРЖДЕНИЯ</span>
      </div>
      <button className="profile-row proof-row" onClick={() => void tonConnectUI.openModal()}>
        <span className="row-icon">
          {profile.wallet ? <ShieldCheck aria-hidden="true" /> : <Wallet aria-hidden="true" />}
        </span>
        <div>
          <b>{profile.wallet ? 'Внешний кошелёк подтверждён' : 'Подключить внешний кошелёк'}</b>
          <small>
            {wallet
              ? shortAddress(wallet.account.address)
              : 'Только для транзакций и получения результата'}
          </small>
        </div>
        <ArrowRight aria-hidden="true" />
      </button>

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
                <button className="round-icon-button" onClick={() => setSettingsOpen(false)}>
                  <X aria-label="Закрыть" />
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
                  <InfinityIcon aria-hidden="true" />
                  Повторить вступление
                </span>
                <ArrowRight aria-hidden="true" />
              </button>
              {wallet && (
                <button className="settings-row" onClick={() => void tonConnectUI.disconnect()}>
                  <span>
                    <Link aria-hidden="true" />
                    Отключить внешний кошелёк
                  </span>
                  <ArrowRight aria-hidden="true" />
                </button>
              )}
              <p>LOOP · TESTNET</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
