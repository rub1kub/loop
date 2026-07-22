import { Address, beginCell, Cell } from '@ton/core';
import { describe, expect, it } from 'vitest';

import type { ActionIntent, OfferQuote } from './types';
import {
  ACCEPT_DIRECT_OFFER_OPCODE,
  assertOpenOfferQuoteContext,
  buildActionTransaction,
  buildOpenOfferTransaction,
  COMMITMENT_DOMAIN,
  commitmentForOffer,
  newOfferId,
  OPEN_DIRECT_OFFER_OPCODE,
  parseGram,
  REVEAL_OPCODE,
} from './ton';

describe('TON duel encoding', () => {
  it('creates the canonical commitment cell hash', () => {
    const walletAddress = `0:${'11'.repeat(32)}`;
    const contractAddress = `0:${'22'.repeat(32)}`;
    const secret = 42n;
    const expected = beginCell()
      .storeUint(COMMITMENT_DOMAIN, 32)
      .storeInt(-3, 32)
      .storeAddress(Address.parse(contractAddress))
      .storeUint(77, 64)
      .storeAddress(Address.parse(walletAddress))
      .storeUint(secret, 256)
      .endCell()
      .hash()
      .toString('hex');
    expect(commitmentForOffer(77, walletAddress, secret, -3, contractAddress)).toBe(expected);
  });

  it('encodes direct creation and address-bound acceptance with separate opcodes', () => {
    const base: OfferQuote = {
      offer: {
        id: 'offer',
        onchain_offer_id: 77,
        chance_bps: 5000,
        total_pool_nano: 2_000_000_000,
        stake_nano: 1_000_000_000,
        opponent_stake_nano: 1_000_000_000,
        fee_bps: 250,
        payout_nano: 1_950_000_000,
        net_profit_nano: 950_000_000,
        mode: 'direct',
        direct_opponent_wallet: null,
        state: 'pending_funding',
        expires_at: new Date(2_000_000_000 * 1000).toISOString(),
        funding_tx_hash: null,
        funding_proof_url: null,
      },
      transaction: {
        operation: 'open_direct_offer',
        query_id: 77,
        offer_id: 77,
        counter_offer_id: 0,
        contract_address: `0:${'22'.repeat(32)}`,
        amount_nano: '1050000000',
        valid_until: 2_000_000_000,
        network: -3,
        chance_bps: 5000,
        stake_nano: '1000000000',
        opponent_stake_nano: '1000000000',
        total_pool_nano: '2000000000',
        commitment_hex: '11'.repeat(32),
        expires_at: 2_000_000_000,
        commitment_domain: COMMITMENT_DOMAIN,
        fee_bps: 250,
        invite_id_hex: '33'.repeat(32),
        direct_counter_offer_id: 0,
        direct_valid_until: 0,
        direct_signature_hex: null,
      },
    };
    const expectedContext = {
      operation: 'open_direct_offer' as const,
      offerId: 77,
      commitmentHex: '11'.repeat(32),
      chanceBps: 5000,
      stakeNano: 1_000_000_000,
      opponentStakeNano: 1_000_000_000,
      totalPoolNano: 2_000_000_000,
      network: -3,
      contractAddress: `0:${'22'.repeat(32)}`,
    };
    expect(() => assertOpenOfferQuoteContext(base, expectedContext)).not.toThrow();
    expect(() =>
      assertOpenOfferQuoteContext(
        {
          ...base,
          transaction: { ...base.transaction, amount_nano: '999999999999' },
        },
        expectedContext,
      ),
    ).toThrow('Контекст DUEL изменился');
    const created = buildOpenOfferTransaction(base, `0:${'11'.repeat(32)}`, '-3');
    const createdPayload = created.messages?.[0]?.payload;
    if (!createdPayload) throw new Error('missing direct creation payload');
    const createdSlice = Cell.fromBoc(Buffer.from(createdPayload, 'base64'))[0].beginParse();
    expect(createdSlice.loadUint(32)).toBe(OPEN_DIRECT_OFFER_OPCODE);
    createdSlice.skip(64 + 64 + 256 + 16);
    expect(createdSlice.loadCoins()).toBe(2_000_000_000n);
    expect(createdSlice.loadUint(32)).toBe(2_000_000_000);
    expect(createdSlice.loadUintBig(256)).toBe(BigInt(`0x${'33'.repeat(32)}`));

    const accepted: OfferQuote = {
      ...base,
      transaction: {
        ...base.transaction,
        operation: 'accept_direct_offer',
        invite_id_hex: null,
        direct_counter_offer_id: 76,
        direct_valid_until: 1_999_999_999,
        direct_signature_hex: '00'.repeat(63) + '2a',
      },
    };
    const acceptance = buildOpenOfferTransaction(accepted, `0:${'11'.repeat(32)}`, '-3');
    const acceptancePayload = acceptance.messages?.[0]?.payload;
    if (!acceptancePayload) throw new Error('missing direct acceptance payload');
    const acceptedSlice = Cell.fromBoc(Buffer.from(acceptancePayload, 'base64'))[0].beginParse();
    expect(acceptedSlice.loadUint(32)).toBe(ACCEPT_DIRECT_OFFER_OPCODE);
    acceptedSlice.skip(64 + 64 + 256 + 16);
    acceptedSlice.loadCoins();
    acceptedSlice.loadUint(32);
    const permit = acceptedSlice.loadRef().beginParse();
    expect(permit.loadUintBig(64)).toBe(76n);
    expect(permit.loadUint(32)).toBe(1_999_999_999);
    expect(permit.loadUintBig(512)).toBe(42n);
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
      network: -3,
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
