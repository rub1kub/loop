import { motion, useReducedMotion } from 'motion/react';

export type ChancePhase = 'idle' | 'searching' | 'live' | 'won' | 'lost';

/** Seconds left below which the clock stops being information and becomes pressure. */
const URGENT_SECONDS = 10;

/**
 * The one object DUEL was missing.
 *
 * BANK has a jar; DUEL had a number. The odds are the whole point of a duel and
 * the only thing here worth showing as a shape rather than as text: your share
 * of the bar *is* your chance, so an opponent's boost is something you watch
 * take ground rather than read about afterwards.
 *
 * It carries every state, which is why the screen around it could lose the
 * "50/50 РАВНЫЙ СТАРТ" block, the "ТЫ / СОПЕРНИК" caption and the bare timer
 * line: each of those said in words what the bar says by moving.
 */
export function ChanceBar({
  mine,
  phase,
  remainingMs,
  drain,
  caption,
}: {
  /** Own share of the pool, 0..1. */
  mine: number;
  phase: ChancePhase;
  /** Time left in the current window, or null when nothing is running. */
  remainingMs?: number | null;
  /**
   * How much of the phase's absolute headroom is left, 0..1, or null when the
   * phase has no known end beyond its own clock. A boost pushes the deadline
   * out, so the edge visibly refills — which is what an extension means.
   */
  drain?: number | null;
  /** What the clock is counting down to, said once, next to it. */
  caption?: string;
}) {
  const reduced = useReducedMotion();
  const settled = phase === 'won' || phase === 'lost';
  // Победа забирает всю полосу, поражение отдаёт её целиком: банк уходит одному.
  const share = phase === 'won' ? 1 : phase === 'lost' ? 0 : Math.min(1, Math.max(0, mine));
  const seconds = remainingMs == null ? null : Math.max(0, Math.ceil(remainingMs / 1000));
  const urgent = phase === 'live' && seconds !== null && seconds <= URGENT_SECONDS;
  const left = drain == null ? 1 : Math.min(1, Math.max(0, drain));

  return (
    <div
      className={`chance-bar phase-${phase}${urgent ? ' is-urgent' : ''}`}
      role="img"
      aria-label={
        settled
          ? phase === 'won'
            ? 'Победа: банк твой'
            : 'Поражение: банк ушёл сопернику'
          : `Твой шанс ${Math.round(share * 100)} процентов`
      }
    >
      <motion.div
        className="chance-bar-track"
        animate={
          reduced || phase !== 'lost'
            ? { x: 0 }
            : // Одно вздрагивание на проигрыш. Добивать не нужно.
              { x: [0, -7, 6, -3, 0] }
        }
        transition={{ duration: 0.42, ease: 'easeOut' }}
      >
        <motion.div
          className="chance-bar-mine"
          initial={false}
          animate={{ width: `${share * 100}%` }}
          transition={
            settled
              ? { duration: 0.55, ease: [0.22, 1, 0.36, 1] }
              : { type: 'spring', stiffness: 120, damping: 18 }
          }
        />
        {phase === 'searching' && !reduced && (
          <motion.div
            className="chance-bar-scan"
            animate={{ x: ['-40%', '140%'] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: 'linear' }}
          />
        )}
        {drain != null && (
          <div className="chance-bar-drain" style={{ transform: `scaleX(${left})` }} />
        )}
        <motion.div
          className="chance-bar-split"
          initial={false}
          animate={{
            left: `${share * 100}%`,
            opacity: settled ? 0 : 1,
            scaleY: phase === 'idle' && !reduced ? [1, 1.14, 1] : 1,
          }}
          transition={{
            left: { type: 'spring', stiffness: 120, damping: 18 },
            opacity: { duration: 0.3 },
            scaleY: { duration: 2.6, repeat: phase === 'idle' ? Infinity : 0, ease: 'easeInOut' },
          }}
        />
      </motion.div>

      {phase === 'live' && seconds !== null && (
        <div className="chance-bar-clock">
          <span>
            <b>{`${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`}</b>
            {caption ? ` ${caption}` : ''}
          </span>
        </div>
      )}

      {!settled && (
        <div className="chance-bar-readout">
          <b>{Math.round(share * 100)}</b>
          <i>/</i>
          <span>{100 - Math.round(share * 100)}</span>
        </div>
      )}
    </div>
  );
}
