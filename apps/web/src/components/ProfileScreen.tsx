import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { api } from '../api';
import { haptic, isMockTelegram, telegram } from '../telegram';
import type { Duel, Offer, Profile, Referral } from '../types';

function shortAddress(address: string): string {
  return `${address.slice(0, 6)}…${address.slice(-6)}`;
}

export function ProfileScreen({
  profile,
  offers,
  duels,
  onReplay,
}: {
  profile: Profile;
  offers: Offer[];
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

  return (
    <section className="screen profile-screen" aria-labelledby="profile-title">
      <header className="profile-identity">
        <div className="avatar">{profile.user.first_name.slice(0, 1).toUpperCase()}</div>
        <div>
          <p className="eyebrow">PROFILE</p>
          <h1 id="profile-title">{profile.user.first_name}</h1>
          <span>{profile.user.username ? `@${profile.user.username}` : 'Telegram user'}</span>
        </div>
        <button
          className="icon-button"
          aria-label="Настройки"
          onClick={() => setSettingsOpen(true)}
        >
          ⋯
        </button>
      </header>

      <button className="wallet-row" onClick={() => void tonConnectUI.openModal()}>
        <span className="wallet-dot" />
        <div>
          <b>{wallet ? shortAddress(wallet.account.address) : 'Кошелёк не подключён'}</b>
          <span>{profile.wallet ? 'Владение подтверждено' : 'TON Connect'}</span>
        </div>
        <span>›</span>
      </button>

      {profile.plush_brick_holder && (
        <div className="holder-badge">
          <span>◆</span>
          <div>
            <b>PLUSH BRICK</b>
            <small>Особые комнаты · сниженная комиссия</small>
          </div>
        </div>
      )}

      <div className="profile-stats">
        <div>
          <strong>{duels.length}</strong>
          <span>ДУЭЛИ</span>
        </div>
        <div>
          <strong>
            {
              duels.filter(
                (duel) =>
                  duel.state === 'settled' && duel.winner_wallet === profile.wallet?.address,
              ).length
            }
          </strong>
          <span>ПОБЕДЫ</span>
        </div>
        <div>
          <strong>{referral?.invited ?? 0}</strong>
          <span>ДРУЗЬЯ</span>
        </div>
      </div>

      <div className="section-label">
        <span>РЕФЕРАЛЫ</span>
        <small>{referral?.reward_points ?? 0} LOOP POINTS</small>
      </div>
      <button className="referral-row" onClick={() => void shareReferral()} disabled={!referral}>
        <span>∞</span>
        <div>
          <b>Пригласить в LOOP</b>
          <small>Награды — только после on-chain дуэли</small>
        </div>
        <span>↗</span>
      </button>

      <div className="section-label">
        <span>ДОСТИЖЕНИЯ</span>
      </div>
      <div className="achievement-row">
        <div className={offers.length ? 'unlocked' : ''}>∞</div>
        <div>
          <b>ПЕРВЫЙ ЦИКЛ</b>
          <small>{offers.length ? 'Открыто' : 'Заверши первую дуэль'}</small>
        </div>
      </div>

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
              onClick={(event) => event.stopPropagation()}
            >
              <span className="sheet-handle" />
              <h2>Настройки</h2>
              <button
                className="settings-row"
                onClick={() => {
                  setSettingsOpen(false);
                  onReplay();
                }}
              >
                <span>Повторить историю</span>
                <span>›</span>
              </button>
              <button className="settings-row" onClick={() => void tonConnectUI.disconnect()}>
                <span>Отключить кошелёк</span>
                <span>›</span>
              </button>
              <p>LOOP · testnet release</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
