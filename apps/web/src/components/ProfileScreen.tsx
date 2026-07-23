import {
  ArrowRight,
  ArrowSquareOut,
  GearSix,
  Infinity as InfinityIcon,
  Link,
  PaperPlaneTilt,
  ShieldCheck,
  UsersThree,
  Wallet,
  X,
} from '@phosphor-icons/react';
import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { api } from '../api';
import { haptic, isMockTelegram, telegram } from '../telegram';
import { formatGram } from '../ton';
import type { BankPosition, Duel, Profile, Rating, Referral } from '../types';

function shortAddress(address: string): string {
  return `${address.slice(0, 7)}…${address.slice(-5)}`;
}

const demoReferral: Referral = {
  code: 'LOOPDEMO',
  url: 'https://t.me/getloopbot?startapp=ref_LOOPDEMO',
  invited: 3,
  qualified: 1,
  reward_points: 100,
  history: [],
};

export function ProfileScreen({
  profile,
  rating,
  bankHistory,
  duels,
  onReplay,
  onSetOnboarding,
}: {
  profile: Profile;
  rating: Rating | null;
  bankHistory: BankPosition[];
  duels: Duel[];
  onReplay: () => void;
  onSetOnboarding: (enabled: boolean) => Promise<void>;
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
    const url = `https://t.me/share/url?url=${encodeURIComponent(referral.url)}&text=${encodeURIComponent('Попробуй BANK и DUEL в LOOP testnet.')}`;
    if (telegram()) telegram()?.openTelegramLink(url);
    else await navigator.clipboard.writeText(referral.url);
  }

  const recentBank = bankHistory.find((item) => item.proof_url);
  const recentDuel = duels.find((item) => item.settlement_proof_url);

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
          <p className="eyebrow">PROFILE</p>
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

      <div className="profile-summary" aria-label="Главная статистика LOOP">
        <article>
          <strong>{rating?.me.score ?? '—'}</strong>
          <span>LOOP SCORE</span>
          <small>{rating ? `#${rating.me.rank} в сезоне` : 'синхронизация'}</small>
        </article>
        <article>
          <strong>{profile.bank.completed}</strong>
          <span>ВЫПЛАТ BANK</span>
          <small>{profile.bank.active ? `${profile.bank.active} активно` : 'нет активных'}</small>
        </article>
        <article>
          <strong>{profile.duel.completed}</strong>
          <span>DUEL</span>
          <small>{profile.duel.active ? `${profile.duel.active} активно` : 'нет активных'}</small>
        </article>
      </div>

      <div className="section-label">
        <span>ТВОЙ КРУГ</span>
        <small>{referral?.reward_points ?? 0} POINTS</small>
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
            КОШЕЛЁК И ON-CHAIN PROOFS
          </span>
          <small>{profile.wallet ? 'ПОДТВЕРЖДЁН' : 'НЕ ПОДКЛЮЧЁН'}</small>
        </summary>
        <div className="profile-proof-content">
          <div className="section-label">
            <span>ВНЕШНИЙ КОШЕЛЁК</span>
          </div>
          <button className="profile-row" onClick={() => void tonConnectUI.openModal()}>
            <span className="row-icon">{profile.wallet ? <ShieldCheck /> : <Wallet />}</span>
            <div>
              <b>{profile.wallet ? 'Адрес подтверждён' : 'Подключить TON Connect'}</b>
              <small>
                {profile.wallet
                  ? shortAddress(profile.wallet.address)
                  : 'Для транзакций и получения выплат'}
              </small>
            </div>
            <ArrowRight aria-hidden="true" />
          </button>

          <div className="section-label">
            <span>PLUSH BRICK</span>
          </div>
          <div className="profile-row static-row">
            <span className="row-icon">
              <InfinityIcon />
            </span>
            <div>
              <b>{profile.plush_brick.holder ? 'Holder подтверждён' : 'Jetton не найден'}</b>
              <small>
                {profile.plush_brick.verified
                  ? `Комиссия DUEL ${profile.plush_brick.duel_fee_bps / 100}%${profile.plush_brick.fee_discount_active ? ' со скидкой' : ''}`
                  : 'Проверка временно недоступна'}
              </small>
            </div>
            <ShieldCheck aria-hidden="true" />
          </div>

          <div className="section-label">
            <span>ПОСЛЕДНИЕ PROOFS</span>
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
                  ? `${formatGram(recentDuel.payout_nano, 3)} GRAM · settlement`
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
                  <p className="eyebrow">LOOP · TESTNET</p>
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
              <label className="settings-toggle">
                <span>
                  <InfinityIcon /> Показывать onboarding
                </span>
                <input
                  type="checkbox"
                  checked={profile.user.onboarding_enabled}
                  onChange={(event) => void onSetOnboarding(event.target.checked)}
                />
              </label>
              <button
                className="settings-row"
                onClick={() => {
                  setSettingsOpen(false);
                  onReplay();
                }}
              >
                <span>
                  <InfinityIcon /> Повторить onboarding
                </span>
                <ArrowRight />
              </button>
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
