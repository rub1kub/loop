import {
  ArrowSquareOut,
  ClockCounterClockwise,
  Infinity as InfinityIcon,
  ShieldCheck,
  X,
} from '@phosphor-icons/react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useState } from 'react';

import { haptic } from '../telegram';
import type { CycleEvent, Profile } from '../types';

const DAY_MS = 86_400_000;

function relativeTime(value: string, now: number): string {
  const elapsed = Math.max(0, now - Date.parse(value));
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return 'сейчас';
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч`;
  return `${Math.floor(hours / 24)} д`;
}

function ProofIcon({ event }: { event: CycleEvent }) {
  if (event.proof_type === 'telegram') return <InfinityIcon aria-hidden="true" />;
  if (event.proof_type.startsWith('ton_')) return <ShieldCheck aria-hidden="true" />;
  return <ClockCounterClockwise aria-hidden="true" />;
}

export function BankScreen({
  profile,
  onStart,
  onContinue,
}: {
  profile: Profile;
  onStart: () => Promise<void>;
  onContinue: () => void;
}) {
  const [starting, setStarting] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [now, setNow] = useState(0);

  useEffect(() => {
    const update = () => setNow(Date.now());
    update();
    const timer = window.setInterval(update, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const cycle = profile.bank;
  const active = cycle?.status === 'active';
  const completed = cycle?.status === 'completed';
  const progress = cycle?.progress_bps ?? 0;
  const day = useMemo(() => {
    if (!cycle) return 0;
    return Math.min(7, Math.max(1, Math.floor((now - Date.parse(cycle.started_at)) / DAY_MS) + 1));
  }, [cycle, now]);
  const latestEvent = cycle?.events[0];

  async function start() {
    try {
      setStarting(true);
      await onStart();
      haptic('success');
    } catch {
      haptic('error');
    } finally {
      setStarting(false);
    }
  }

  return (
    <section className="screen bank-screen" aria-labelledby="bank-title">
      <header className="bank-heading">
        <p className="eyebrow">
          {active
            ? `ЦИКЛ ${String(cycle.sequence_number).padStart(2, '0')}`
            : completed
              ? `ЦИКЛ ${String(cycle.sequence_number).padStart(2, '0')} ЗАВЕРШЁН`
              : 'ТВОЙ ЦИКЛ'}
        </p>
        <h1 id="bank-title">
          {active ? `ДЕНЬ ${day} ИЗ 7` : completed ? 'ЦИКЛ ЗАВЕРШЁН' : 'НАЧАТЬ ЦИКЛ'}
        </h1>
      </header>

      <motion.div
        className={`bank-jar ${active || completed ? 'is-filled' : 'is-empty'}`}
        initial={{ scale: 0.92, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 110, damping: 22 }}
      >
        <img
          src={active || completed ? '/assets/living-jar.webp' : '/assets/empty-jar.webp'}
          alt={active || completed ? 'Банка активного цикла' : 'Пустая банка'}
        />
      </motion.div>

      {cycle && (active || completed) ? (
        <div className="bank-cycle-summary">
          <button className="progress-row" onClick={() => setHistoryOpen(true)}>
            <strong>{Math.round(progress / 100)}%</strong>
            <span>·</span>
            <b>{cycle.event_count} СОБЫТИЙ</b>
          </button>
          {latestEvent && (
            <button className="latest-event" onClick={() => setHistoryOpen(true)}>
              <span className="event-proof-icon">
                <ProofIcon event={latestEvent} />
              </span>
              <span>
                {latestEvent.title}
                <time> · {relativeTime(latestEvent.created_at, now)}</time>
              </span>
            </button>
          )}
          <button
            className="primary-button"
            onClick={completed ? () => void start() : onContinue}
            disabled={starting}
          >
            {starting ? 'ЗАПУСКАЕМ' : completed ? 'НОВЫЙ ЦИКЛ' : 'ПРОДОЛЖИТЬ ЦИКЛ'}
          </button>
        </div>
      ) : (
        <div className="bank-empty-copy">
          <p>Семь дней. События, вызовы и on-chain подтверждения — в одном живом цикле.</p>
          <button className="primary-button" onClick={() => void start()} disabled={starting}>
            {starting ? 'ЗАПУСКАЕМ' : 'НАЧАТЬ ЦИКЛ'}
          </button>
        </div>
      )}

      <AnimatePresence>
        {historyOpen && cycle && (
          <motion.div
            className="sheet-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setHistoryOpen(false)}
          >
            <motion.div
              className="sheet history-sheet"
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', stiffness: 260, damping: 30 }}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="sheet-title-row">
                <div>
                  <p className="eyebrow">ЦИКЛ {String(cycle.sequence_number).padStart(2, '0')}</p>
                  <h2>События</h2>
                </div>
                <button className="round-icon-button" onClick={() => setHistoryOpen(false)}>
                  <X aria-label="Закрыть" />
                </button>
              </div>
              <div className="event-list">
                {cycle.events.map((event) => {
                  const content = (
                    <>
                      <span className="event-proof-icon">
                        <ProofIcon event={event} />
                      </span>
                      <div>
                        <strong>{event.title}</strong>
                        <small>
                          {event.proof_type.startsWith('ton_')
                            ? 'Подтверждено в TON'
                            : event.proof_type === 'telegram'
                              ? 'Подтверждено Telegram'
                              : 'Событие LOOP'}
                        </small>
                      </div>
                      <span className="event-meta">
                        <time>{relativeTime(event.created_at, now)}</time>
                        {event.proof_url && <ArrowSquareOut aria-hidden="true" />}
                      </span>
                    </>
                  );
                  return event.proof_url ? (
                    <a
                      className="event-row"
                      href={event.proof_url}
                      target="_blank"
                      rel="noreferrer"
                      key={event.id}
                      onClick={() => haptic('light')}
                    >
                      {content}
                    </a>
                  ) : (
                    <article className="event-row" key={event.id}>
                      {content}
                    </article>
                  );
                })}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
