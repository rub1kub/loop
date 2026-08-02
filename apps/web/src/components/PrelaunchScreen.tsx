import { ArrowSquareOut, Copy, ShareNetwork, TrendUp, UsersThree } from '@phosphor-icons/react';
import { useEffect, useMemo, useState } from 'react';

import { haptic, openPlatformLink, telegram } from '../telegram';
import type { Prelaunch, Profile } from '../types';

const SHARE_TEXT = 'LOOP открывается 8 августа в 19:00 МСК. Займи место до толпы — вот моя ссылка.';

interface Remaining {
  days: string;
  hours: string;
  minutes: string;
  seconds: string;
  done: boolean;
}

function remainingUntil(target: number, now: number): Remaining {
  const left = Math.max(0, target - now);
  const seconds = Math.floor(left / 1000);
  const pad = (value: number) => String(value).padStart(2, '0');
  return {
    days: pad(Math.floor(seconds / 86_400)),
    hours: pad(Math.floor((seconds % 86_400) / 3600)),
    minutes: pad(Math.floor((seconds % 3600) / 60)),
    seconds: pad(seconds % 60),
    done: left === 0,
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
export function PrelaunchScreen({
  profile,
  prelaunch,
}: {
  profile: Profile;
  prelaunch: Prelaunch;
}) {
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
        <p className="prelaunch-date">ОТКРЫТИЕ · 8 АВГУСТА · 19:00 МСК</p>
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
        <p className="prelaunch-pulse">
          <UsersThree size={16} aria-hidden="true" />
          Уже внутри: <b>{prelaunch.participants}</b>
        </p>
      </section>

      <section className="prelaunch-referral">
        <header>
          <span className="eyebrow">ТВОЯ ССЫЛКА</span>
          <h2>2% с каждого взноса приглашённых. Навсегда.</h2>
          <p>
            Приведи людей до открытия — с первого дня каждый их взнос будет приносить тебе долю
            комиссии. Выплаты в GRAM.
          </p>
        </header>
        <div className="prelaunch-link" data-testid="referral-url">
          {prelaunch.referral_url.replace('https://', '')}
        </div>
        <div className="prelaunch-link-actions">
          <button className="primary-button" onClick={share}>
            <ShareNetwork size={18} aria-hidden="true" /> ПРИГЛАСИТЬ
          </button>
          <button
            className="secondary-button"
            onClick={() => void copy()}
            aria-label="Скопировать ссылку"
          >
            <Copy size={18} aria-hidden="true" /> {copied ? 'СКОПИРОВАНО' : 'КОПИЯ'}
          </button>
        </div>
        <p className="prelaunch-mine">
          Приглашено тобой: <b>{prelaunch.invited}</b>
          {prelaunch.rank !== null ? ` · место №${prelaunch.rank}` : ''}
        </p>
      </section>

      <section className="prelaunch-board">
        <header>
          <span className="eyebrow">ГОНКА ПРИГЛАШЕНИЙ</span>
          <h2>Кто приводит больше всех</h2>
        </header>
        {prelaunch.leaderboard.length === 0 ? (
          <p className="prelaunch-empty">
            Пока никто никого не привёл. Первое место свободно — забирай.
          </p>
        ) : (
          <ol className="prelaunch-leaders">
            {prelaunch.leaderboard.map((leader, index) => (
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
        <header>
          <span className="eyebrow">PLUSH BRICK</span>
          <h2>Держателям — комиссия 0%</h2>
          <p>
            Кирпич на кошельке в момент игры — и LOOP не берёт с тебя ничего. Успей до открытия.
          </p>
        </header>
        <button
          className="secondary-button prelaunch-plush-link"
          onClick={() => openPlatformLink('https://plushbrick.fun/')}
        >
          КУПИТЬ PLUSH BRICK <ArrowSquareOut size={16} aria-hidden="true" />
        </button>
      </section>

      <footer className="prelaunch-footer">
        <span>{profile.user.first_name ? `Ты в списке, ${profile.user.first_name}.` : ''}</span>
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
