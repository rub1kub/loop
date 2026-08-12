/**
 * Turns anything thrown — by a wallet, by an SDK, or by us — into a sentence a
 * person can act on.
 *
 * Two things reached players verbatim before this existed: Telegram's bare
 * "UNSUPPORTED" from a storage tier their client lacks, and TON Connect's
 * "[TON_CONNECT_SDK_ERROR] UserRejectsError: …" after they simply changed their
 * mind in the wallet. Neither is a sentence, and the second is not even a
 * failure.
 */

/** Refusing in the wallet is a decision, not an error worth reporting back. */
const REFUSAL = /userrejectserror|user (?:rejects?|declined)|wallet declined|отклон(?:ен|ил)[^\n]*(?:пользовател|кошелёк)|пользовател[^\n]*отмен/i;

/**
 * Our own copy is written in Russian; a library's is not. Cyrillic is therefore
 * a reliable marker of "somebody wrote this for a person to read", and anything
 * without it is machine noise that should be replaced rather than shown.
 */
const WRITTEN_FOR_PEOPLE = /[Ѐ-ӿ]/;

function messageOf(error: unknown): string {
  if (error instanceof Error) return `${error.name}: ${error.message}`;
  if (typeof error === 'string') return error;
  return '';
}

/** True when the person declined in their wallet rather than hitting a problem. */
export function isWalletRefusal(error: unknown): boolean {
  return (error instanceof Error && error.name === 'UserRejectsError') || REFUSAL.test(messageOf(error));
}

/**
 * The sentence to show, or null when there is nothing worth saying — which is
 * the right answer for a refusal the person made deliberately.
 */
export function humanError(error: unknown, fallback: string): string | null {
  if (isWalletRefusal(error)) return null;
  const raw = error instanceof Error ? error.message : typeof error === 'string' ? error : '';
  return WRITTEN_FOR_PEOPLE.test(raw) ? raw : fallback;
}
