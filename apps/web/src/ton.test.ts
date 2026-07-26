import { Address, beginCell, Cell } from '@ton/core';
import { describe, expect, it } from 'vitest';

import type { ActionIntent, BankQuote, DuelBoostIntent, OfferQuote } from './types';
import {
  ACCEPT_DIRECT_OFFER_OPCODE,
  assertOpenOfferQuoteContext,
  buildActionTransaction,
  buildBankPositionTransaction,
  buildBoostTransaction,
  buildOpenOfferTransaction,
  COMMITMENT_DOMAIN,
  BOOST_DUEL_OPCODE,
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

  it('binds a boost to duel, offer, revision, chance floor and amount', () => {
    const contractAddress = `0:${'22'.repeat(32)}`;
    const intent: DuelBoostIntent = {
      operation: 'boost_duel',
      query_id: 11,
      duel_id: 88,
      offer_id: 77,
      contract_address: contractAddress,
      amount_nano: '550000000',
      boost_nano: '500000000',
      expected_revision: 3,
      min_chance_bps: 6_000,
      valid_until: 2_000_000_000,
      network: -3,
    };
    const request = buildBoostTransaction(intent, `0:${'11'.repeat(32)}`, '-3', {
      duelId: 88,
      offerId: 77,
      amountNano: 500_000_000,
      revision: 3,
      minChanceBps: 6_000,
      contractAddress,
    });
    const payload = request.messages?.[0]?.payload;
    if (!payload) throw new Error('missing boost payload');
    const slice = Cell.fromBoc(Buffer.from(payload, 'base64'))[0].beginParse();
    expect(slice.loadUint(32)).toBe(BOOST_DUEL_OPCODE);
    expect(slice.loadUintBig(64)).toBe(11n);
    expect(slice.loadUintBig(64)).toBe(88n);
    expect(slice.loadUintBig(64)).toBe(77n);
    expect(slice.loadCoins()).toBe(500_000_000n);
    expect(slice.loadUint(16)).toBe(3);
    expect(slice.loadUint(16)).toBe(6_000);
    expect(slice.loadUint(32)).toBe(2_000_000_000);
    expect(() =>
      buildBoostTransaction({ ...intent, expected_revision: 4 }, `0:${'11'.repeat(32)}`, '-3', {
        duelId: 88,
        offerId: 77,
        amountNano: 500_000_000,
        revision: 3,
        minChanceBps: 6_000,
        contractAddress,
      }),
    ).toThrow('Состояние DUEL изменилось');
  });

  it('accepts mainnet only when the signed quote uses the same network', () => {
    const bankQuote: BankQuote = {
      position: {
        id: 'position',
        position_id: 91,
        owner_wallet: `0:${'11'.repeat(32)}`,
        principal_nano: 1_000_000_000,
        multiplier_bps: 12500,
        target_payout_nano: 1_250_000_000,
        funded_amount_nano: 0,
        remaining_amount_nano: 1_250_000_000,
        progress_bps: 0,
        queue_index: null,
        queue_position: null,
        current_status: 'pending_confirmation',
        funding_transaction: null,
        payout_transaction: null,
        proof_url: null,
        created_at: new Date(0).toISOString(),
        completed_at: null,
      },
      transaction: {
        operation: 'create_bank_position',
        query_id: 91,
        position_id: 91,
        contract_address: `0:${'22'.repeat(32)}`,
        amount_nano: '1080000000',
        principal_nano: '1000000000',
        multiplier_bps: 12500,
        valid_until: 2_000_000_000,
        network: -239,
        fee_nano: '10000000',
      },
    };
    const request = buildBankPositionTransaction(bankQuote, `0:${'11'.repeat(32)}`, '-239');
    expect(request.network).toBe('-239');
    expect(() =>
      buildBankPositionTransaction(
        { ...bankQuote, transaction: { ...bankQuote.transaction, network: -3 } },
        `0:${'11'.repeat(32)}`,
        '-239',
      ),
    ).toThrow('Сеть BANK изменилась');
  });

  it('rejects a DUEL intent when the wallet and backend networks differ', () => {
    const intent: ActionIntent = {
      operation: 'expire_offer',
      query_id: 9,
      offer_id: 77,
      duel_id: 0,
      contract_address: `0:${'22'.repeat(32)}`,
      amount_nano: '30000000',
      valid_until: 2_000_000_000,
      network: -3,
    };
    expect(() => buildActionTransaction(intent, `0:${'11'.repeat(32)}`, '-239')).toThrow(
      'Сеть DUEL изменилась',
    );
  });
});
