import { Copy, ShareNetwork, TrendUp } from '@phosphor-icons/react';
import { useEffect, useMemo, useState } from 'react';

import { haptic, openPlatformLink, telegram } from '../telegram';
import type { Prelaunch } from '../types';

const SHARE_TEXT = 'LOOP открывается 8 августа в 19:00 МСК. Займи место до толпы — вот моя ссылка.';

// The same deep links the onboarding uses — one referral market per button.
const PLUSH_MARKETS = [
  {
    name: 'dTrade',
    url: 'https://t.me/dtrade?start=1IPvnLpaEN_EQAJ40p3zlCoomgANMQ4u5eIktLMZtWP87GGKDKlyW_EZBwt',
  },
  {
    name: 'RedoTrade',
    url: 'https://t.me/redotrade?start=rubikub-EQAJ40p3zlCoomgANMQ4u5eIktLMZtWP87GGKDKlyW_EZBwt',
  },
] as const;

interface Remaining {
  days: string;
  hours: string;
  minutes: string;
  seconds: string;
}

function remainingUntil(target: number, now: number): Remaining {
  const seconds = Math.floor(Math.max(0, target - now) / 1000);
  const pad = (value: number) => String(value).padStart(2, '0');
  return {
    days: pad(Math.floor(seconds / 86_400)),
    hours: pad(Math.floor((seconds % 86_400) / 3600)),
    minutes: pad(Math.floor((seconds % 3600) / 60)),
    seconds: pad(seconds % 60),
  };
}

/**
 * What the door shows while it is closed: the clock, your link, the race.
 *
 * Everyone here is already signed in — the referral link is personal and every
 * invitation is being counted. When the countdown reaches zero the page
 * reloads itself and the server, which gates by the same clock, lets the
 * person straight in: launch happens without anyone touching a keyboard.
 */
export function PrelaunchScreen({ prelaunch }: { prelaunch: Prelaunch }) {
  const target = useMemo(
    () => (prelaunch.launch_at ? Date.parse(prelaunch.launch_at) : null),
    [prelaunch.launch_at],
  );
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (target !== null && now >= target) window.location.reload();
  }, [now, target]);

  const left = target === null ? null : remainingUntil(target, now);

  const share = () => {
    haptic('selection');
    const url = `https://t.me/share/url?url=${encodeURIComponent(prelaunch.referral_url)}&text=${encodeURIComponent(SHARE_TEXT)}`;
    const app = telegram();
    if (app?.openTelegramLink) app.openTelegramLink(url);
    else window.open(url, '_blank', 'noopener');
  };

  const copy = async () => {
    haptic('selection');
    await navigator.clipboard.writeText(prelaunch.referral_url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <main className="prelaunch" aria-labelledby="prelaunch-title">
      <section className="prelaunch-hero">
        <p className="eyebrow">ФИНАНСОВАЯ ПИРАМИДА</p>
        <h1 id="prelaunch-title">LOOP</h1>
        {left && (
          <div className="prelaunch-clock" role="timer" aria-live="off">
            <div>
              <strong>{left.days}</strong>
              <small>ДНЕЙ</small>
            </div>
            <span>:</span>
            <div>
              <strong>{left.hours}</strong>
              <small>ЧАСОВ</small>
            </div>
            <span>:</span>
            <div>
              <strong>{left.minutes}</strong>
              <small>МИНУТ</small>
            </div>
            <span>:</span>
            <div>
              <strong>{left.seconds}</strong>
              <small>СЕКУНД</small>
            </div>
          </div>
        )}
        <p className="prelaunch-date">8 АВГУСТА · 19:00 МСК</p>
      </section>

      <section className="prelaunch-referral">
        <h2>2% с каждого взноса приглашённых. Навсегда.</h2>
        <div className="prelaunch-link-actions">
          <button className="primary-button" onClick={share}>
            <ShareNetwork size={18} aria-hidden="true" /> ПРИГЛАСИТЬ
          </button>
          <button
            className="secondary-button"
            onClick={() => void copy()}
            aria-label="Скопировать ссылку"
          >
            <Copy size={18} aria-hidden="true" /> {copied ? 'ЕСТЬ' : 'КОПИЯ'}
          </button>
        </div>
        <p className="prelaunch-mine">
          Приглашено: <b>{prelaunch.invited}</b>
          {prelaunch.rank !== null ? ` · место №${prelaunch.rank}` : ''}
        </p>
      </section>

      <section className="prelaunch-board">
        <header className="prelaunch-board-head">
          <h2>Гонка приглашений</h2>
          <small>Уже внутри: {prelaunch.participants}</small>
        </header>
        {prelaunch.leaderboard.length === 0 ? (
          <p className="prelaunch-empty">Первое место свободно — забирай.</p>
        ) : (
          <ol className="prelaunch-leaders">
            {prelaunch.leaderboard.slice(0, 5).map((leader, index) => (
              <li
                key={`${leader.username ?? leader.first_name}-${index}`}
                className={leader.is_me ? 'is-me' : ''}
              >
                <span className="prelaunch-rank">{index + 1}</span>
                <span className="prelaunch-name">
                  <b>{leader.first_name || 'Без имени'}</b>
                  {leader.username && <small>@{leader.username}</small>}
                </span>
                <span className="prelaunch-count">
                  <TrendUp size={14} aria-hidden="true" /> {leader.invited}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="prelaunch-plush">
        <h2>PLUSH BRICK · комиссия 0%</h2>
        <p>Держателям LOOP не стоит ничего. Токен выкупается с рынка.</p>
        <div className="prelaunch-markets">
          {PLUSH_MARKETS.map((market) => (
            <button
              key={market.name}
              className="secondary-button"
              onClick={() => openPlatformLink(market.url, true)}
            >
              {market.name}
            </button>
          ))}
        </div>
      </section>

      <footer className="prelaunch-footer">
        <button
          className="prelaunch-channel"
          onClick={() => openPlatformLink('https://t.me/rubikub', true)}
        >
          КАНАЛ РАЗРАБОТКИ · @rubikub
        </button>
      </footer>
    </main>
  );
}
