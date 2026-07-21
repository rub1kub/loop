import { Address, beginCell } from '@ton/core';
import { describe, expect, it } from 'vitest';

import { COMMITMENT_DOMAIN, commitmentForOffer, newOfferId, parseGram } from './ton';

describe('TON duel encoding', () => {
  it('creates the canonical commitment cell hash', () => {
    const address = `0:${'11'.repeat(32)}`;
    const secret = 42n;
    const expected = beginCell()
      .storeUint(COMMITMENT_DOMAIN, 32)
      .storeUint(77, 64)
      .storeAddress(Address.parse(address))
      .storeUint(secret, 256)
      .endCell()
      .hash()
      .toString('hex');
    expect(commitmentForOffer(77, address, secret)).toBe(expected);
  });

  it('keeps offer ids inside JavaScript safe integer range', () => {
    expect(newOfferId(new Uint32Array([0xffffffff, 0xffffffff]))).toBeLessThanOrEqual(
      Number.MAX_SAFE_INTEGER,
    );
  });

  it('parses GRAM without floating point rounding', () => {
    expect(parseGram('1.000000001')).toBe(1_000_000_001);
    expect(() => parseGram('-1')).toThrow();
  });
});
