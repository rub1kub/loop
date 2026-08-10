import { NavigationArrow, User } from '@phosphor-icons/react';
import { motion, useReducedMotion } from 'motion/react';

export type DuelOrbitPhase = 'boosting' | 'ready' | 'waiting' | 'won' | 'lost';

const URGENT_SECONDS = 10;
const RESULT_TURNS = 4;
const START_ANGLE = 90;

function clampShare(value: number): number {
  return Math.min(0.9, Math.max(0.1, value));
}

function clock(remainingMs?: number | null): string | null {
  if (remainingMs == null) return null;
  const seconds = Math.max(0, Math.ceil(remainingMs / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

function Avatar({ image, fallback }: { image: string | null; fallback: string }) {
  return (
    <span className="duel-orbit-avatar" aria-hidden="true">
      {image ? <img src={image} alt="" /> : fallback ? <b>{fallback}</b> : <User weight="thin" />}
    </span>
  );
}

/**
 * The live DUEL object. The ring is a chart of contract-confirmed shares; the
 * needle is only a result reveal and always lands inside the already-known
 * winner's sector. It never produces or changes the outcome.
 */
export function DuelOrbit({
  mine,
  phase,
  remainingMs,
  pool,
  mineAvatar,
  mineFallback,
  opponentAvatar,
  opponentFallback,
  opponentName,
  latestEvent,
  resultAmount,
  revealResult = false,
  compact = false,
  setup = false,
}: {
  mine: number;
  phase: DuelOrbitPhase;
  remainingMs?: number | null;
  pool: string;
  mineAvatar: string | null;
  mineFallback: string;
  opponentAvatar: string | null;
  opponentFallback: string;
  opponentName?: string | null;
  latestEvent?: string | null;
  resultAmount?: string | null;
  /** Animate only when this mounted screen actually observed the duel settle. */
  revealResult?: boolean;
  compact?: boolean;
  setup?: boolean;
}) {
  const reduced = useReducedMotion();
  const share = clampShare(mine);
  const minePercent = Math.round(share * 100);
  const opponentPercent = 100 - minePercent;
  const time = clock(remainingMs);
  const seconds = remainingMs == null ? null : Math.max(0, Math.ceil(remainingMs / 1000));
  const urgent = phase === 'boosting' && seconds !== null && seconds <= URGENT_SECONDS;
  const settled = phase === 'won' || phase === 'lost';
  const revealing = settled && revealResult;
  const spinning = phase === 'waiting';
  const mineSweep = share * 360;
  const targetAngle =
    phase === 'lost'
      ? START_ANGLE + mineSweep + (360 - mineSweep) / 2
      : START_ANGLE + mineSweep / 2;
  const markerAngle = START_ANGLE + mineSweep;
  const markerRadians = (markerAngle * Math.PI) / 180;
  const markerX = 100 + Math.cos(markerRadians) * 82;
  const markerY = 100 + Math.sin(markerRadians) * 82;
  const label = settled
    ? `Результат дуэли: ${resultAmount ?? (phase === 'won' ? 'выигрыш' : 'проигрыш')}`
    : `Твой шанс ${minePercent} процентов`;

  return (
    <div
      className={`duel-orbit phase-${phase}${revealing ? ' is-revealing' : ''}${urgent ? ' is-urgent' : ''}${compact ? ' is-compact' : ''}${setup ? ' is-setup' : ''}`}
      role="img"
      aria-label={label}
    >
      <div className="duel-orbit-players">
        <div className="duel-orbit-player is-mine">
          <Avatar image={mineAvatar} fallback={mineFallback} />
          <span>ТЫ</span>
          <strong>{minePercent}%</strong>
        </div>
        <div className="duel-orbit-player">
          <Avatar image={opponentAvatar} fallback={opponentFallback} />
          <span>{opponentName ?? 'СОПЕРНИК'}</span>
          <strong>{opponentPercent}%</strong>
        </div>
      </div>

      <div className="duel-orbit-stage">
        {revealing && <p className="duel-orbit-resolving-label">ОПРЕДЕЛЯЕМ ПОБЕДИТЕЛЯ</p>}
        <svg className="duel-orbit-chart" viewBox="0 0 200 200" aria-hidden="true">
          <circle className="duel-orbit-outer" cx="100" cy="100" r="95" />
          <circle className="duel-orbit-track" cx="100" cy="100" r="82" />
          <motion.circle
            className="duel-orbit-mine"
            cx="100"
            cy="100"
            r="82"
            pathLength="1"
            initial={false}
            animate={{ pathLength: share }}
            transition={{ type: 'spring', stiffness: 90, damping: 18 }}
          />
          <motion.circle
            className="duel-orbit-marker"
            r="4.5"
            initial={false}
            animate={{ cx: markerX, cy: markerY }}
            transition={{ type: 'spring', stiffness: 90, damping: 18 }}
          />
        </svg>

        {(spinning || revealing) && (
          <motion.div
            className={`duel-orbit-needle${spinning ? ' is-waiting' : ''}`}
            initial={
              reduced ? { rotate: targetAngle } : { rotate: targetAngle - RESULT_TURNS * 360 }
            }
            animate={
              spinning && !reduced
                ? { rotate: [targetAngle, targetAngle + 360] }
                : { rotate: targetAngle }
            }
            transition={
              spinning && !reduced
                ? { duration: 1.35, ease: 'linear', repeat: Infinity }
                : reduced
                  ? { duration: 0 }
                  : { duration: 2.35, ease: [0.12, 0.78, 0.16, 1] }
            }
            aria-hidden="true"
          >
            <NavigationArrow weight="regular" />
          </motion.div>
        )}

        <div className="duel-orbit-centre" aria-hidden={settled || undefined}>
          <strong>{pool}</strong>
          <span>GRAM</span>
          {!settled && time && (
            <small>
              <b>{time}</b>
              <span>{phase === 'boosting' ? 'ДО КОНЦА СТАВОК' : 'ДО РЕЗУЛЬТАТА'}</span>
            </small>
          )}
        </div>

        {settled && (
          <div className={`duel-orbit-verdict${phase === 'lost' ? ' is-lost' : ''}`}>
            {resultAmount && <strong>{resultAmount}</strong>}
            <small>{phase === 'won' ? 'ПРИШЛО В КОШЕЛЁК' : 'СТАВКА УШЛА'}</small>
          </div>
        )}
      </div>

      {!settled && latestEvent && <p className="duel-orbit-event">{latestEvent}</p>}
    </div>
  );
}
