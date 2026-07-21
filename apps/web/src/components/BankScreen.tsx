import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';

import { api } from '../api';
import { haptic, isMockTelegram } from '../telegram';
import { formatGram, parseGram } from '../ton';
import type { Profile } from '../types';

export function BankScreen({
  profile,
  onRefresh,
  onConnect,
}: {
  profile: Profile;
  onRefresh: () => Promise<void>;
  onConnect: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [target, setTarget] = useState('25');
  const [saving, setSaving] = useState(false);
  const balance = profile.balance_nano ?? 0;
  const goal = profile.bank?.target_nano ?? 0;
  const progress = goal ? Math.min(balance / goal, 1) : 0;

  async function save() {
    try {
      setSaving(true);
      const nano = parseGram(target);
      if (!isMockTelegram()) await api.setBankTarget(nano);
      haptic('success');
      await onRefresh();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="screen bank-screen" aria-labelledby="bank-title">
      <header className="screen-header">
        <p className="eyebrow">ТВОЙ ЦИКЛ</p>
        <h1 id="bank-title">BANK</h1>
      </header>

      <div
        className="jar-wrap"
        aria-label={goal ? `Прогресс ${Math.round(progress * 100)}%` : 'Пустая банка'}
      >
        <motion.div
          className="jar"
          initial={{ scale: 0.94, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 130, damping: 20 }}
        >
          <div className="jar-rim" />
          <div className="jar-glass">
            <motion.div
              className="jar-fill"
              animate={{ height: `${Math.max(progress * 100, goal ? 4 : 0)}%` }}
              transition={{ type: 'spring', stiffness: 60, damping: 18 }}
            >
              <span />
            </motion.div>
            <div className="jar-shine" />
          </div>
        </motion.div>
      </div>

      <div className="bank-summary">
        {goal ? (
          <>
            <strong>{formatGram(balance)} GRAM</strong>
            <span>из {formatGram(goal)} GRAM</span>
            <button className="text-button" onClick={() => setEditing(true)}>
              ИЗМЕНИТЬ ЦЕЛЬ
            </button>
          </>
        ) : (
          <>
            <strong>Пусто — и это начало.</strong>
            <span>Поставь цель. Средства останутся в твоём кошельке.</span>
            <button
              className="primary-button"
              onClick={() => (profile.wallet || isMockTelegram() ? setEditing(true) : onConnect())}
            >
              {profile.wallet || isMockTelegram() ? 'НАЧАТЬ' : 'ПОДКЛЮЧИТЬ КОШЕЛЁК'}
            </button>
          </>
        )}
      </div>

      <AnimatePresence>
        {editing && (
          <motion.div
            className="sheet-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setEditing(false)}
          >
            <motion.div
              className="sheet"
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', stiffness: 260, damping: 30 }}
              onClick={(event) => event.stopPropagation()}
            >
              <span className="sheet-handle" />
              <p className="eyebrow">ЦЕЛЬ</p>
              <label className="amount-input">
                <input
                  inputMode="decimal"
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                  aria-label="Цель в GRAM"
                />
                <span>GRAM</span>
              </label>
              <p className="sheet-note">LOOP ничего не блокирует и не хранит.</p>
              <button className="primary-button" disabled={saving} onClick={() => void save()}>
                {saving ? 'СОХРАНЯЕМ' : 'СОХРАНИТЬ'}
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
