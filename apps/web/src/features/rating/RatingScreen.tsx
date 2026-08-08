import { CheckCircle, ShieldCheck, UsersThree } from '@phosphor-icons/react';
import { AnimatePresence, motion } from 'motion/react';
import { formatGram } from '../../ton';
import { useState } from 'react';

import { DisclosureIndicator } from '../../components/DisclosureIndicator';
import type { Rating, RatingEntry } from '../../types';

type RatingList = 'all' | 'circle';

const levelThresholds = [
  { level: 'PULSE', score: 200 },
  { level: 'ORBIT', score: 500 },
  { level: 'LOOP', score: 1_000 },
] as const;

const levelLabels: Record<RatingEntry['level'], string> = {
  SIGNAL: 'СИГНАЛ',
  PULSE: 'ПУЛЬС',
  ORBIT: 'ОРБИТА',
  LOOP: 'LOOP',
};

const driverLabels: Record<string, string> = {
  bank_payout: 'выплаты BANK',
  duel_settlement: 'завершённые DUEL',
  timely_reveal: 'результаты без просрочек',
  qualified_referral: 'подтверждённые друзья',
};

export function RatingScreen({ rating }: { rating: Rating | null }) {
  const [list, setList] = useState<RatingList>('all');

  if (!rating) {
    return (
      <section className="screen rating-screen" aria-labelledby="rating-title">
        <header className="mode-header">
          <p className="eyebrow">ПОДТВЕРЖДЁННАЯ РЕПУТАЦИЯ</p>
          <h1 id="rating-title">РЕЙТИНГ</h1>
        </header>
        <div className="rating-unavailable">
          <span className="waiting-ring" aria-hidden="true" />
          <strong>Собираем подтверждённые действия.</strong>
          <p>Рейтинг появится, когда LOOP закончит проверку.</p>
        </div>
      </section>
    );
  }

  const entries = list === 'all' ? rating.leaderboard : rating.circle;
  const nextLevel = levelThresholds.find((item) => item.score > rating.me.score);
  const nextLevelProgress = nextLevel
    ? Math.min(100, Math.max(0, (rating.me.score / nextLevel.score) * 100))
    : 100;
  const formulaCounts: Record<string, number> = {
    bank_payout: rating.me.bank_payouts,
    duel_settlement: rating.me.duel_settlements,
    timely_reveal: rating.me.timely_reveals,
    qualified_referral: rating.me.qualified_referrals,
    missed_reveal: rating.me.missed_reveals,
  };
  const mainDriver = rating.formula
    .map((item) => ({ ...item, contribution: item.points * (formulaCounts[item.code] ?? 0) }))
    .filter((item) => item.contribution > 0)
    .sort((a, b) => b.contribution - a.contribution)[0];

  return (
    <section className="screen rating-screen" aria-labelledby="rating-title">
      <header className="mode-header">
        <p className="eyebrow">СЕЗОН · {rating.season_name}</p>
        <h1 id="rating-title">РЕЙТИНГ</h1>
      </header>

      <div className="rating-score">
        <p className="eyebrow">ТВОЙ СЧЁТ LOOP</p>
        <strong>{rating.me.score}</strong>
        <div className="rating-badges">
          <span>УРОВЕНЬ · {levelLabels[rating.me.level]}</span>
        </div>
        <div
          className="rating-progress"
          role="progressbar"
          aria-label={
            nextLevel ? `Прогресс до уровня ${levelLabels[nextLevel.level]}` : 'Уровень LOOP'
          }
          aria-valuemin={0}
          aria-valuemax={nextLevel?.score ?? rating.me.score}
          aria-valuenow={rating.me.score}
        >
          <span style={{ width: `${nextLevelProgress}%` }} />
        </div>
        <div className="rating-progress-copy">
          <span>#{rating.me.rank} В СЕЗОНЕ</span>
          <span>
            {nextLevel
              ? `${nextLevel.score - rating.me.score} ДО УРОВНЯ ${levelLabels[nextLevel.level]}`
              : 'МАКСИМАЛЬНЫЙ УРОВЕНЬ'}
          </span>
        </div>
      </div>

      <div className="rating-list-switch" aria-label="Вид рейтинга">
        <button className={list === 'all' ? 'active' : ''} onClick={() => setList('all')}>
          ВСЕ
        </button>
        <button className={list === 'circle' ? 'active' : ''} onClick={() => setList('circle')}>
          <UsersThree aria-hidden="true" /> ДРУЗЬЯ
        </button>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={list}
          className="rating-list"
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -6 }}
          transition={{ duration: 0.16 }}
        >
          {entries.map((entry) => (
            <RatingRow key={entry.user_id} entry={entry} />
          ))}
          {list === 'circle' && entries.length <= 1 && (
            <div className="rating-circle-empty">
              <UsersThree aria-hidden="true" />
              <strong>Здесь пока только ты.</strong>
              <p>Пригласи друзей — они появятся после первого завершённого действия.</p>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      {(rating.invite_race.length > 0 || (rating.invite_race_me?.invited ?? 0) > 0) && (
        <>
          <div className="section-label">
            <span>ГОНКА НЕДЕЛИ</span>
            <small>ЗА ВЗНОСЫ ПРИГЛАШЁННЫХ</small>
          </div>
          <div className="invite-race" aria-label="Гонка приглашающих за неделю">
            {rating.invite_race.map((entry) => (
              <div key={entry.rank} className={`invite-race-row${entry.is_me ? ' is-me' : ''}`}>
                <b>#{entry.rank}</b>
                <span>
                  {entry.is_me ? 'ТЫ' : entry.username ? `@${entry.username}` : entry.first_name}
                  <small>{entry.invited > 0 ? ` · привёл ${entry.invited}` : ''}</small>
                </span>
                <strong>{formatGram(entry.earned_nano, 2)} GRAM</strong>
              </div>
            ))}
            {rating.invite_race_me && !rating.invite_race.some((entry) => entry.is_me) && (
              <div className="invite-race-row is-me">
                <b>#{rating.invite_race_me.rank}</b>
                <span>ТЫ</span>
                <strong>{formatGram(rating.invite_race_me.earned_nano, 2)} GRAM</strong>
              </div>
            )}
          </div>
          <p className="invite-race-note">
            Считаются только настоящие взносы приглашённых. Каждый понедельник в 00:00 МСК — с нуля.
          </p>
        </>
      )}

      <details className="rating-details rating-formula">
        <summary>
          <span>
            <ShieldCheck aria-hidden="true" />
            МОЯ СТАТИСТИКА
          </span>
          <DisclosureIndicator />
        </summary>
        <p className="rating-driver">
          {mainDriver
            ? `Главный фактор: ${driverLabels[mainDriver.code] ?? mainDriver.label} · +${mainDriver.contribution}`
            : 'Первое завершённое действие запустит твой счёт.'}
        </p>
        <p className="rating-explainer">
          Счёт отражает участие и надёжность. Размер ставки, прибыль и поражения на место не влияют.
        </p>
        <div className="rating-proof-line" aria-label="Надёжность рейтинга">
          <div>
            <strong>{rating.me.proofs}</strong>
            <span>ЗАСЧИТАНО</span>
          </div>
          <div>
            <strong>{Math.round(rating.me.reliability_bps / 100)}%</strong>
            <span>БЕЗ ПРОСРОЧЕК</span>
          </div>
        </div>
        <p>Считаются только действия, которые LOOP уже подтвердил.</p>
        <dl>
          {rating.formula.map((item) => (
            <div key={item.code}>
              <dt>
                <CheckCircle aria-hidden="true" />
                {item.label}
              </dt>
              <dd>
                {item.points > 0 ? '+' : ''}
                {item.points}
              </dd>
            </div>
          ))}
        </dl>
        <p className="rating-pulse-label">СЕЙЧАС В LOOP</p>
        <div className="rating-pulse">
          <Metric value={rating.pulse.active_participants} label="В LOOP" />
          <Metric value={rating.pulse.active_bank} label="В BANK" />
          <Metric value={rating.pulse.active_duels} label="В DUEL" />
          <Metric value={rating.pulse.proofs_24h} label="ЗА 24Ч" />
        </div>
      </details>
    </section>
  );
}

function Metric({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function RatingRow({ entry }: { entry: RatingEntry }) {
  return (
    <article className={entry.is_me ? 'is-me' : undefined}>
      <span className="rating-rank">{entry.rank}</span>
      {entry.photo_url ? (
        <img src={entry.photo_url} alt="" />
      ) : (
        <span className="rating-avatar" aria-hidden="true">
          {entry.first_name.slice(0, 1).toUpperCase()}
        </span>
      )}
      <div>
        <strong>{entry.is_me ? 'ТЫ' : entry.first_name}</strong>
        <small>
          {/* A rating in a money product gets asked one silent question —
              "сколько он поднял" — so the row answers it instead of counting
              bureaucratic proofs at people. */}
          УРОВЕНЬ {levelLabels[entry.level]} ·{' '}
          {entry.earned_nano > 0
            ? `ПОЛУЧИЛ ${formatGram(entry.earned_nano, 2)} GRAM`
            : 'ПОКА 0 GRAM'}
        </small>
      </div>
      <b>{entry.score}</b>
    </article>
  );
}
