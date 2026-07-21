import { Address, beginCell, Cell } from '@ton/core';
import { describe, expect, it } from 'vitest';

import type { ActionIntent } from './types';
import {
  buildActionTransaction,
  COMMITMENT_DOMAIN,
  commitmentForOffer,
  newOfferId,
  parseGram,
  REVEAL_OPCODE,
} from './ton';

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

  it('encodes reveal without sending the secret through the backend', () => {
    const intent: ActionIntent = {
      operation: 'reveal',
      query_id: 9,
      offer_id: 77,
      duel_id: 88,
      contract_address: `0:${'22'.repeat(32)}`,
      amount_nano: '30000000',
      valid_until: 2_000_000_000,
    };
    const request = buildActionTransaction(
      intent,
      `0:${'11'.repeat(32)}`,
      '-3',
      '00'.repeat(31) + '2a',
    );
    const payload = request.messages?.[0]?.payload;
    expect(payload).toBeTypeOf('string');
    if (!payload) throw new Error('missing payload');
    const slice = Cell.fromBoc(Buffer.from(payload, 'base64'))[0].beginParse();
    expect(slice.loadUint(32)).toBe(REVEAL_OPCODE);
    expect(slice.loadUintBig(64)).toBe(9n);
    expect(slice.loadUintBig(64)).toBe(88n);
    expect(slice.loadUintBig(64)).toBe(77n);
    expect(slice.loadUintBig(256)).toBe(42n);
  });
});
