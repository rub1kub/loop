import { Address, beginCell } from '@ton/core';
import type { SendTransactionRequest } from '@tonconnect/ui-react';

import type { ActionIntent, BankQuote, OfferQuote } from './types';

export const BANK_CREATE_POSITION_OPCODE = 0x4c424e01;
export const OPEN_OFFER_OPCODE = 0x4c4f4f01;
export const CANCEL_OFFER_OPCODE = 0x4c4f4f02;
export const REVEAL_OPCODE = 0x4c4f4f04;
export const EXPIRE_OFFER_OPCODE = 0x4c4f4f05;
export const EXPIRE_DUEL_OPCODE = 0x4c4f4f06;
export const COMMITMENT_DOMAIN = 0x4c4f4f50;

export function newOfferId(random = crypto.getRandomValues(new Uint32Array(2))): number {
  const high = random[0] & 0x1fffff;
  const value = high * 0x1_0000_0000 + random[1];
  return value || 1;
}

export function newSecret(): bigint {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return BigInt(`0x${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}`);
}

function requireTestnet(network: string): asserts network is '-3' {
  if (network !== '-3') throw new Error('LOOP работает только в TON testnet');
}

export function buildBankPositionTransaction(
  quote: BankQuote,
  from: string,
  network: string,
): SendTransactionRequest {
  requireTestnet(network);
  const tx = quote.transaction;
  const payload = beginCell()
    .storeUint(BANK_CREATE_POSITION_OPCODE, 32)
    .storeUint(tx.query_id, 64)
    .storeUint(tx.position_id, 64)
    .storeCoins(BigInt(tx.principal_nano))
    .storeUint(tx.multiplier_bps, 16)
    .endCell()
    .toBoc()
    .toString('base64');
  return {
    validUntil: tx.valid_until,
    network,
    from,
    messages: [{ address: tx.contract_address, amount: tx.amount_nano, payload }],
  };
}

export function commitmentForOffer(offerId: number, walletAddress: string, secret: bigint): string {
  return beginCell()
    .storeUint(COMMITMENT_DOMAIN, 32)
    .storeUint(offerId, 64)
    .storeAddress(Address.parse(walletAddress))
    .storeUint(secret, 256)
    .endCell()
    .hash()
    .toString('hex');
}

export function buildOpenOfferTransaction(
  quote: OfferQuote,
  from: string,
  network: string,
): SendTransactionRequest {
  requireTestnet(network);
  const tx = quote.transaction;
  const payload = beginCell()
    .storeUint(OPEN_OFFER_OPCODE, 32)
    .storeUint(tx.query_id, 64)
    .storeUint(tx.offer_id, 64)
    .storeUint(BigInt(`0x${tx.commitment_hex}`), 256)
    .storeUint(tx.chance_bps, 16)
    .storeCoins(BigInt(tx.total_pool_nano))
    .storeUint(tx.expires_at, 32)
    .storeUint(tx.counter_offer_id, 64)
    .endCell()
    .toBoc()
    .toString('base64');
  return {
    validUntil: tx.valid_until,
    network,
    from,
    messages: [{ address: tx.contract_address, amount: tx.amount_nano, payload }],
  };
}

export function buildActionTransaction(
  intent: ActionIntent,
  from: string,
  network: string,
  secretHex?: string,
): SendTransactionRequest {
  requireTestnet(network);
  const body = beginCell();
  if (intent.operation === 'reveal') {
    if (!secretHex || !/^[0-9a-f]{64}$/i.test(secretHex)) {
      throw new Error('Секрет дуэли недоступен на этом устройстве');
    }
    body
      .storeUint(REVEAL_OPCODE, 32)
      .storeUint(intent.query_id, 64)
      .storeUint(intent.duel_id, 64)
      .storeUint(intent.offer_id, 64)
      .storeUint(BigInt(`0x${secretHex}`), 256);
  } else if (intent.operation === 'cancel_offer' || intent.operation === 'expire_offer') {
    body
      .storeUint(
        intent.operation === 'cancel_offer' ? CANCEL_OFFER_OPCODE : EXPIRE_OFFER_OPCODE,
        32,
      )
      .storeUint(intent.query_id, 64)
      .storeUint(intent.offer_id, 64);
  } else {
    body
      .storeUint(EXPIRE_DUEL_OPCODE, 32)
      .storeUint(intent.query_id, 64)
      .storeUint(intent.duel_id, 64);
  }
  return {
    validUntil: intent.valid_until,
    network,
    from,
    messages: [
      {
        address: intent.contract_address,
        amount: intent.amount_nano,
        payload: body.endCell().toBoc().toString('base64'),
      },
    ],
  };
}

export function formatGram(nano: number | bigint | null, precision = 2): string {
  if (nano === null) return '—';
  const value = typeof nano === 'bigint' ? Number(nano) : nano;
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: precision,
    minimumFractionDigits: 0,
  }).format(value / 1_000_000_000);
}

export function parseGram(value: string): number {
  const normalized = value.trim().replace(',', '.');
  if (!/^\d+(?:\.\d{0,9})?$/.test(normalized)) throw new Error('Введите сумму в GRAM');
  const [whole, fraction = ''] = normalized.split('.');
  const nano = BigInt(whole) * 1_000_000_000n + BigInt(fraction.padEnd(9, '0'));
  if (nano > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error('Сумма слишком велика');
  return Number(nano);
}
