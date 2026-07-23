import { CheckCircle, ShieldCheck, UsersThree } from '@phosphor-icons/react';
import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';

import type { Rating, RatingEntry } from '../../types';

type RatingList = 'all' | 'circle';

export function RatingScreen({ rating }: { rating: Rating | null }) {
  const [list, setList] = useState<RatingList>('all');

  if (!rating) {
    return (
      <section className="screen rating-screen" aria-labelledby="rating-title">
        <header className="mode-header">
          <p className="eyebrow">ON-CHAIN REPUTATION</p>
          <h1 id="rating-title">RATING</h1>
        </header>
        <div className="rating-unavailable">
          <span className="waiting-ring" aria-hidden="true" />
          <strong>Собираем подтверждённые действия.</strong>
          <p>Рейтинг появится, когда индексатор синхронизируется с TON.</p>
        </div>
      </section>
    );
  }

  const entries = list === 'all' ? rating.leaderboard : rating.circle;

  return (
    <section className="screen rating-screen" aria-labelledby="rating-title">
      <header className="mode-header">
        <p className="eyebrow">SEASON · {rating.season_name}</p>
        <h1 id="rating-title">RATING</h1>
      </header>

      <div className="rating-score">
        <p className="eyebrow">ТВОЙ LOOP SCORE</p>
        <strong>{rating.me.score}</strong>
        <div className="rating-badges">
          <span>{rating.me.level}</span>
          <span>#{rating.me.rank} В СЕЗОНЕ</span>
        </div>
        <p>Репутация участия, а не баланс. Суммы, прибыль и поражения на место не влияют.</p>
      </div>

      <div className="rating-proof-line" aria-label="Надёжность рейтинга">
        <div>
          <strong>{rating.me.proofs}</strong>
          <span>ON-CHAIN PROOFS</span>
        </div>
        <div>
          <strong>{Math.round(rating.me.reliability_bps / 100)}%</strong>
          <span>БЕЗ ТАЙМАУТА</span>
        </div>
      </div>

      <div className="section-label">
        <span>СИСТЕМА СЕЙЧАС</span>
        <small>LIVE</small>
      </div>
      <div className="rating-pulse">
        <Metric value={rating.pulse.active_participants} label="УЧАСТНИКОВ" />
        <Metric value={rating.pulse.active_bank} label="В BANK" />
        <Metric value={rating.pulse.active_duels} label="В DUEL" />
        <Metric value={rating.pulse.proofs_24h} label="PROOFS · 24Ч" />
      </div>

      <div className="rating-list-switch" aria-label="Вид рейтинга">
        <button className={list === 'all' ? 'active' : ''} onClick={() => setList('all')}>
          ВСЕ
        </button>
        <button className={list === 'circle' ? 'active' : ''} onClick={() => setList('circle')}>
          <UsersThree aria-hidden="true" /> МОЙ КРУГ
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
              <strong>Круг ещё не замкнулся.</strong>
              <p>Здесь появятся друзья, которые совершили подтверждённое on-chain действие.</p>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <details className="rating-formula">
        <summary>
          <span>
            <ShieldCheck aria-hidden="true" />
            КАК СЧИТАЕТСЯ SCORE
          </span>
          <small>ПРОЗРАЧНО</small>
        </summary>
        <p>Считаются только события, которые LOOP уже сверил с финализированным блоком TON.</p>
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
          {entry.level} · {entry.proofs} PROOFS
        </small>
      </div>
      <b>{entry.score}</b>
    </article>
  );
}
