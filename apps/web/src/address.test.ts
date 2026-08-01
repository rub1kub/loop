import { describe, expect, it } from 'vitest';

import { friendlyAddress, rawAddress, sameAddress } from './address';

const RAW_UPPER = '0:B9B8FA17119EFE7F4296A489567FCF5776F9271823FAD26486E93D743F4093A5';
const RAW_LOWER = RAW_UPPER.toLowerCase();

describe('address', () => {
  it('treats the same account as the same however it is written', () => {
    // This is the whole bug: the API stores raw addresses upper case and TON
    // Connect returns them lower case. Comparing the strings said "different
    // wallet", so the app re-verified an already-linked one on every open,
    // spent a single-use challenge and disconnected when the server refused.
    expect(RAW_UPPER === RAW_LOWER).toBe(false);
    expect(sameAddress(RAW_UPPER, RAW_LOWER)).toBe(true);
    expect(rawAddress(RAW_UPPER)).toBe(rawAddress(RAW_LOWER));
  });

  it('matches a raw address against its user-friendly form', () => {
    expect(sameAddress(RAW_UPPER, friendlyAddress(RAW_UPPER, -239))).toBe(true);
  });

  it('never claims two different accounts are the same', () => {
    const other = `0:${'42'.repeat(32)}`;
    expect(sameAddress(RAW_UPPER, other)).toBe(false);
    expect(sameAddress(RAW_UPPER, null)).toBe(false);
    expect(sameAddress(undefined, RAW_LOWER)).toBe(false);
  });

  it('shows wallets the way wallets show themselves', () => {
    expect(friendlyAddress(RAW_UPPER, -239).startsWith('UQ')).toBe(true);
    expect(friendlyAddress(RAW_UPPER, -3).startsWith('0Q')).toBe(true);
  });

  it('returns the input untouched when it cannot be parsed', () => {
    expect(friendlyAddress('не адрес', -239)).toBe('не адрес');
    expect(rawAddress('не адрес')).toBe('не адрес');
  });
});
