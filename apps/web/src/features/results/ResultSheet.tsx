import { ArrowSquareOut, ShareNetwork, X } from '@phosphor-icons/react';
import { motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { api } from '../../api';
import {
  haptic,
  isMockTelegram,
  openPlatformLink,
  setBackAction,
  sharePreparedResult,
} from '../../telegram';
import { formatGram } from '../../ton';
import type { ResultCard } from '../../types';

import { celebrate } from '../../celebrate';
import { humanError } from '../../errors';

export function ResultSheet({
  card,
  onClose,
  onError,
}: {
  card: ResultCard;
  onClose: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [sharing, setSharing] = useState(false);

  // Telegram's own Close sits in the same corner as ours and wins the tap.
  // Its Back button is the one control guaranteed not to overlap, and here it
  // means the same thing: dismiss the card, return to BANK.
  useEffect(() => setBackAction(() => void onClose()), [onClose]);

  // The card only appears for a settled result, so its arrival is the moment
  // worth marking.
  useEffect(() => {
    if (card.mode !== 'bank_entry') celebrate();
  }, [card.mode]);
  const entry = card.mode === 'bank_entry';
  const modeLabel = entry
    ? 'Ты в LOOP.'
    : card.mode === 'bank'
      ? 'Цикл замкнулся.'
      : 'DUEL завершён.';

  async function share() {
    if (sharing) return;
    setSharing(true);
    try {
      if (!isMockTelegram()) {
        const prepared = await api.prepareResultShare(card.id);
        const opened = await sharePreparedResult(
          prepared.prepared_message_id,
          prepared.fallback_query,
        );
        if (!opened) throw new Error('Не удалось открыть выбор получателя');
      }
      haptic('success');
    } catch (error) {
      haptic('error');
      onError(humanError(error, 'Не удалось поделиться результатом') ?? '');
    } finally {
      setSharing(false);
    }
  }

  return (
    <motion.div
      className="result-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.section
        className="result-sheet"
        aria-labelledby="result-title"
        initial={{ opacity: 0, y: 24, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.99 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        <button className="result-close" aria-label="Закрыть" onClick={() => void onClose()}>
          <X aria-hidden="true" />
        </button>

        {card.image_url ? (
          <img className="result-card-image" src={card.image_url} alt="Карточка результата LOOP" />
        ) : (
          <div className="result-card-image result-card-demo" aria-hidden="true">
            <span>∞ LOOP</span>
            <i>∞</i>
            <b>
              {entry
                ? 'ВЗНОС В ФИНАНСОВУЮ ПИРАМИДУ'
                : card.mode === 'bank'
                  ? 'МОЙ ЦИКЛ ЗАМКНУЛСЯ'
                  : 'ПУЛ МОЙ'}
            </b>
            <strong>
              {entry
                ? `${formatGram(card.contributed_nano, 3)} GRAM`
                : `+${formatGram(card.payout_nano, 3)} GRAM`}
            </strong>
            <small>{entry ? 'ВЫПЛАЧЕНО 0 GRAM' : 'ВЫПЛАТА'}</small>
          </div>
        )}

        <div className="result-copy">
          <p className="eyebrow">{entry ? 'BANK · ВЗНОС' : card.mode.toUpperCase()}</p>
          <h2 id="result-title">{modeLabel}</h2>
          <strong>
            {entry
              ? `${formatGram(card.contributed_nano, 3)} GRAM`
              : `+${formatGram(card.payout_nano, 3)} GRAM`}
          </strong>
          <span>
            {entry
              ? `Взнос подтверждён сетью${card.queue_position ? `, ты №${card.queue_position} в очереди` : ''}.`
              : 'Выплата подтверждена сетью.'}
          </span>
        </div>

        <button
          className="primary-button result-share"
          disabled={sharing}
          onClick={() => void share()}
        >
          <ShareNetwork aria-hidden="true" />
          {sharing ? 'ГОТОВИМ…' : entry ? 'ПЕРЕДАТЬ ХОД' : 'ПОДЕЛИТЬСЯ'}
        </button>
        <button className="result-proof" onClick={() => openPlatformLink(card.proof_url)}>
          ПРОВЕРИТЬ
          <ArrowSquareOut aria-hidden="true" />
        </button>
      </motion.section>
    </motion.div>
  );
}
