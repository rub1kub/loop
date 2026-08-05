import { Address } from '@ton/core';

const MAINNET_NETWORK_ID = -239;

export const WALLET_MISMATCH_MESSAGE =
  'В TON Connect выбран другой кошелёк. Подключи кошелёк из профиля заново.';

/**
 * The API stores raw addresses in upper case, TON Connect hands them back in
 * lower case, and comparing the two as plain strings never matches. That made
 * the app treat an already-linked wallet as a new one and re-verify it on every
 * open, burning a one-time challenge and disconnecting the wallet when the
 * server refused the reused proof.
 */
export function rawAddress(value: string): string {
  try {
    return Address.parse(value).toRawString();
  } catch {
    return value.trim().toLowerCase();
  }
}

export function sameAddress(left: string | null | undefined, right: string | null | undefined) {
  if (!left || !right) return false;
  return rawAddress(left) === rawAddress(right);
}

export function sameWalletConnection(
  linked: { address: string; network: number } | null | undefined,
  connected: { address: string; chain: string } | null | undefined,
): boolean {
  if (!linked || !connected) return false;
  return (
    linked.network === Number(connected.chain) && sameAddress(linked.address, connected.address)
  );
}

/**
 * A TON Connect session belongs to a browser, while the verified wallet
 * belongs to the Telegram profile. Never let a restored browser session sign
 * an operation prepared for another verified wallet.
 */
export function requireLinkedWallet(
  linked: { address: string; network: number } | null | undefined,
  connected: { address: string; chain: string } | null | undefined,
): string {
  if (!sameWalletConnection(linked, connected)) throw new Error(WALLET_MISMATCH_MESSAGE);
  return connected!.address;
}

/** Wallets are shown the way every TON wallet shows them: non-bounceable. */
export function friendlyAddress(value: string, network: number): string {
  try {
    return Address.parse(value).toString({
      urlSafe: true,
      bounceable: false,
      testOnly: network !== MAINNET_NETWORK_ID,
    });
  } catch {
    return value;
  }
}
