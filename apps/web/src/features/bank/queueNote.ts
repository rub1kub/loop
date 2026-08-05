import { formatGram } from '../../ton';
import type { BankPosition } from '../../types';

/** Roughly how long a wait is, said the way a person would say it. */
export function spokenWait(seconds: number): string {
  if (seconds < 90) return 'меньше минуты';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `около ${minutes} мин`;
  const hours = Math.round(seconds / 3600);
  if (hours < 24) return `около ${hours} ч`;
  return `около ${Math.round(hours / 24)} дн`;
}

/**
 * What the percentage above actually means right now.
 *
 * The wait has two halves and the jar covers both: the queue walking towards
 * you, then your own position filling. Saying which half you are in is the
 * difference between a number and an explanation — and the first half is the
 * one where somebody else's deposit is what moves you.
 */
export function queueNote(
  ahead: number,
  aheadNano: number,
  etaSeconds: number | null,
  position: BankPosition,
): string {
  if (position.current_status === 'payout_sent' || position.remaining_amount_nano <= 0) {
    return 'Выплата отправлена';
  }
  if (ahead > 0) {
    const need = `Впереди ${ahead} ${ahead === 1 ? 'позиция' : 'позиций'} — им нужно ${formatGram(aheadNano, 2)} GRAM`;
    return etaSeconds === null ? need : `${need} · ${spokenWait(etaSeconds)}`;
  }
  return `Твоя очередь: собрано ${formatGram(position.funded_amount_nano, 2)} из ${formatGram(position.target_payout_nano, 2)} GRAM`;
}
