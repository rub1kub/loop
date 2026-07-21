// AUTO-GENERATED, do not edit
// It's a TypeScript wrapper for a DuelEscrow contract in Tolk.
/* eslint-disable */

import * as c from '@ton/core';
import { beginCell, ContractProvider, Sender, SendMode } from '@ton/core';

// ————————————————————————————————————————————
//   predefined types and functions
//

type StoreCallback<T> = (obj: T, b: c.Builder) => void
type LoadCallback<T> = (s: c.Slice) => T

export type CellRef<T> = {
    ref: T
}

function makeCellFrom<T>(self: T, storeFn_T: StoreCallback<T>): c.Cell {
    let b = beginCell();
    storeFn_T(self, b);
    return b.endCell();
}

function loadAndCheckPrefix32(s: c.Slice, expected: number, structName: string): void {
    let prefix = s.loadUint(32);
    if (prefix !== expected) {
        throw new Error(`Incorrect prefix for '${structName}': expected 0x${expected.toString(16).padStart(8, '0')}, got 0x${prefix.toString(16).padStart(8, '0')}`);
    }
}

function lookupPrefix(s: c.Slice, expected: number, prefixLen: number): boolean {
    return s.remainingBits >= prefixLen && s.preloadUint(prefixLen) === expected;
}

function throwNonePrefixMatch(fieldPath: string): never {
    throw new Error(`Incorrect prefix for '${fieldPath}': none of variants matched`);
}

function storeCellRef<T>(cell: CellRef<T>, b: c.Builder, storeFn_T: StoreCallback<T>): void {
    let b_ref = c.beginCell();
    storeFn_T(cell.ref, b_ref);
    b.storeRef(b_ref.endCell());
}

function loadCellRef<T>(s: c.Slice, loadFn_T: LoadCallback<T>): CellRef<T> {
    let s_ref = s.loadRef().beginParse();
    return { ref: loadFn_T(s_ref) };
}

function storeTolkNullable<T>(v: T | null, b: c.Builder, storeFn_T: StoreCallback<T>): void {
    if (v === null) {
        b.storeUint(0, 1);
    } else {
        b.storeUint(1, 1);
        storeFn_T(v, b);
    }
}

function createDictionaryValue<V>(loadFn_V: LoadCallback<V>, storeFn_V: StoreCallback<V>): c.DictionaryValue<V> {
    return {
        serialize(self: V, b: c.Builder) {
            storeFn_V(self, b);
        },
        parse(s: c.Slice): V {
            const value = loadFn_V(s);
            s.endParse();
            return value;
        }
    }
}

// ————————————————————————————————————————————
//   parse get methods result from a TVM stack
//

class StackReader {
    constructor(private tuple: c.TupleItem[]) {
    }

    static fromGetMethod(expectedN: number, getMethodResult: { stack: c.TupleReader }): StackReader {
        let tuple = [] as c.TupleItem[];
        while (getMethodResult.stack.remaining) {
            tuple.push(getMethodResult.stack.pop());
        }
        if (tuple.length !== expectedN) {
            throw new Error(`expected ${expectedN} stack width, got ${tuple.length}`);
        }
        return new StackReader(tuple);
    }

    private popExpecting<ItemT>(itemType: string): ItemT {
        const item = this.tuple.shift();
        if (item?.type === itemType) {
            return item as ItemT;
        }
        throw new Error(`not '${itemType}' on a stack`);
    }

    private popCellLike(): c.Cell {
        const item = this.tuple.shift();
        if (item && (item.type === 'cell' || item.type === 'slice' || item.type === 'builder')) {
            return item.cell;
        }
        throw new Error(`not cell/slice on a stack`);
    }

    readBigInt(): bigint {
        return this.popExpecting<c.TupleItemInt>('int').value;
    }

    readBoolean(): boolean {
        return this.popExpecting<c.TupleItemInt>('int').value !== 0n;
    }

    readCell(): c.Cell {
        return this.popCellLike();
    }

    readSlice(): c.Slice {
        return this.popCellLike().beginParse();
    }
}

// ————————————————————————————————————————————
//   auto-generated serializers to/from cells
//

type coins = bigint

type uint8 = bigint
type uint16 = bigint
type uint32 = bigint
type uint64 = bigint
type uint256 = bigint

/**
 > struct (0x4c4f4f01) OpenOffer {
 >     queryId: uint64
 >     offerId: uint64
 >     commitment: uint256
 >     chanceBps: uint16
 >     totalPool: coins
 >     expiresAt: uint32
 >     counterOfferId: uint64
 > }
 */
export interface OpenOffer {
    readonly $: 'OpenOffer'
    queryId: uint64
    offerId: uint64
    commitment: uint256
    chanceBps: uint16
    totalPool: coins
    expiresAt: uint32
    counterOfferId: uint64
}

export const OpenOffer = {
    PREFIX: 0x4c4f4f01,

    create(args: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        counterOfferId: uint64
    }): OpenOffer {
        return {
            $: 'OpenOffer',
            ...args
        }
    },
    fromSlice(s: c.Slice): OpenOffer {
        loadAndCheckPrefix32(s, 0x4c4f4f01, 'OpenOffer');
        return {
            $: 'OpenOffer',
            queryId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
            commitment: s.loadUintBig(256),
            chanceBps: s.loadUintBig(16),
            totalPool: s.loadCoins(),
            expiresAt: s.loadUintBig(32),
            counterOfferId: s.loadUintBig(64),
        }
    },
    store(self: OpenOffer, b: c.Builder): void {
        b.storeUint(0x4c4f4f01, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.offerId, 64);
        b.storeUint(self.commitment, 256);
        b.storeUint(self.chanceBps, 16);
        b.storeCoins(self.totalPool);
        b.storeUint(self.expiresAt, 32);
        b.storeUint(self.counterOfferId, 64);
    },
    toCell(self: OpenOffer): c.Cell {
        return makeCellFrom<OpenOffer>(self, OpenOffer.store);
    }
}

/**
 > struct (0x4c4f4f02) CancelOffer {
 >     queryId: uint64
 >     offerId: uint64
 > }
 */
export interface CancelOffer {
    readonly $: 'CancelOffer'
    queryId: uint64
    offerId: uint64
}

export const CancelOffer = {
    PREFIX: 0x4c4f4f02,

    create(args: {
        queryId: uint64
        offerId: uint64
    }): CancelOffer {
        return {
            $: 'CancelOffer',
            ...args
        }
    },
    fromSlice(s: c.Slice): CancelOffer {
        loadAndCheckPrefix32(s, 0x4c4f4f02, 'CancelOffer');
        return {
            $: 'CancelOffer',
            queryId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
        }
    },
    store(self: CancelOffer, b: c.Builder): void {
        b.storeUint(0x4c4f4f02, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.offerId, 64);
    },
    toCell(self: CancelOffer): c.Cell {
        return makeCellFrom<CancelOffer>(self, CancelOffer.store);
    }
}

/**
 > struct (0x4c4f4f03) MatchOffers {
 >     queryId: uint64
 >     firstOfferId: uint64
 >     secondOfferId: uint64
 > }
 */
export interface MatchOffers {
    readonly $: 'MatchOffers'
    queryId: uint64
    firstOfferId: uint64
    secondOfferId: uint64
}

export const MatchOffers = {
    PREFIX: 0x4c4f4f03,

    create(args: {
        queryId: uint64
        firstOfferId: uint64
        secondOfferId: uint64
    }): MatchOffers {
        return {
            $: 'MatchOffers',
            ...args
        }
    },
    fromSlice(s: c.Slice): MatchOffers {
        loadAndCheckPrefix32(s, 0x4c4f4f03, 'MatchOffers');
        return {
            $: 'MatchOffers',
            queryId: s.loadUintBig(64),
            firstOfferId: s.loadUintBig(64),
            secondOfferId: s.loadUintBig(64),
        }
    },
    store(self: MatchOffers, b: c.Builder): void {
        b.storeUint(0x4c4f4f03, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.firstOfferId, 64);
        b.storeUint(self.secondOfferId, 64);
    },
    toCell(self: MatchOffers): c.Cell {
        return makeCellFrom<MatchOffers>(self, MatchOffers.store);
    }
}

/**
 > struct (0x4c4f4f04) Reveal {
 >     queryId: uint64
 >     duelId: uint64
 >     offerId: uint64
 >     secret: uint256
 > }
 */
export interface Reveal {
    readonly $: 'Reveal'
    queryId: uint64
    duelId: uint64
    offerId: uint64
    secret: uint256
}

export const Reveal = {
    PREFIX: 0x4c4f4f04,

    create(args: {
        queryId: uint64
        duelId: uint64
        offerId: uint64
        secret: uint256
    }): Reveal {
        return {
            $: 'Reveal',
            ...args
        }
    },
    fromSlice(s: c.Slice): Reveal {
        loadAndCheckPrefix32(s, 0x4c4f4f04, 'Reveal');
        return {
            $: 'Reveal',
            queryId: s.loadUintBig(64),
            duelId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
            secret: s.loadUintBig(256),
        }
    },
    store(self: Reveal, b: c.Builder): void {
        b.storeUint(0x4c4f4f04, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.duelId, 64);
        b.storeUint(self.offerId, 64);
        b.storeUint(self.secret, 256);
    },
    toCell(self: Reveal): c.Cell {
        return makeCellFrom<Reveal>(self, Reveal.store);
    }
}

/**
 > struct (0x4c4f4f05) ExpireOffer {
 >     queryId: uint64
 >     offerId: uint64
 > }
 */
export interface ExpireOffer {
    readonly $: 'ExpireOffer'
    queryId: uint64
    offerId: uint64
}

export const ExpireOffer = {
    PREFIX: 0x4c4f4f05,

    create(args: {
        queryId: uint64
        offerId: uint64
    }): ExpireOffer {
        return {
            $: 'ExpireOffer',
            ...args
        }
    },
    fromSlice(s: c.Slice): ExpireOffer {
        loadAndCheckPrefix32(s, 0x4c4f4f05, 'ExpireOffer');
        return {
            $: 'ExpireOffer',
            queryId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
        }
    },
    store(self: ExpireOffer, b: c.Builder): void {
        b.storeUint(0x4c4f4f05, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.offerId, 64);
    },
    toCell(self: ExpireOffer): c.Cell {
        return makeCellFrom<ExpireOffer>(self, ExpireOffer.store);
    }
}

/**
 > struct (0x4c4f4f06) ExpireDuel {
 >     queryId: uint64
 >     duelId: uint64
 > }
 */
export interface ExpireDuel {
    readonly $: 'ExpireDuel'
    queryId: uint64
    duelId: uint64
}

export const ExpireDuel = {
    PREFIX: 0x4c4f4f06,

    create(args: {
        queryId: uint64
        duelId: uint64
    }): ExpireDuel {
        return {
            $: 'ExpireDuel',
            ...args
        }
    },
    fromSlice(s: c.Slice): ExpireDuel {
        loadAndCheckPrefix32(s, 0x4c4f4f06, 'ExpireDuel');
        return {
            $: 'ExpireDuel',
            queryId: s.loadUintBig(64),
            duelId: s.loadUintBig(64),
        }
    },
    store(self: ExpireDuel, b: c.Builder): void {
        b.storeUint(0x4c4f4f06, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.duelId, 64);
    },
    toCell(self: ExpireDuel): c.Cell {
        return makeCellFrom<ExpireDuel>(self, ExpireDuel.store);
    }
}

/**
 > struct (0x4c4f4f07) SetPaused {
 >     queryId: uint64
 >     paused: bool
 > }
 */
export interface SetPaused {
    readonly $: 'SetPaused'
    queryId: uint64
    paused: boolean
}

export const SetPaused = {
    PREFIX: 0x4c4f4f07,

    create(args: {
        queryId: uint64
        paused: boolean
    }): SetPaused {
        return {
            $: 'SetPaused',
            ...args
        }
    },
    fromSlice(s: c.Slice): SetPaused {
        loadAndCheckPrefix32(s, 0x4c4f4f07, 'SetPaused');
        return {
            $: 'SetPaused',
            queryId: s.loadUintBig(64),
            paused: s.loadBoolean(),
        }
    },
    store(self: SetPaused, b: c.Builder): void {
        b.storeUint(0x4c4f4f07, 32);
        b.storeUint(self.queryId, 64);
        b.storeBit(self.paused);
    },
    toCell(self: SetPaused): c.Cell {
        return makeCellFrom<SetPaused>(self, SetPaused.store);
    }
}

/**
 > struct (0x4c4f4f11) DuelPayout {
 >     queryId: uint64
 >     duelId: uint64
 >     offerId: uint64
 >     reason: uint8
 > }
 */
export interface DuelPayout {
    readonly $: 'DuelPayout'
    queryId: uint64
    duelId: uint64
    offerId: uint64
    reason: uint8
}

export const DuelPayout = {
    PREFIX: 0x4c4f4f11,

    create(args: {
        queryId: uint64
        duelId: uint64
        offerId: uint64
        reason: uint8
    }): DuelPayout {
        return {
            $: 'DuelPayout',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelPayout {
        loadAndCheckPrefix32(s, 0x4c4f4f11, 'DuelPayout');
        return {
            $: 'DuelPayout',
            queryId: s.loadUintBig(64),
            duelId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
            reason: s.loadUintBig(8),
        }
    },
    store(self: DuelPayout, b: c.Builder): void {
        b.storeUint(0x4c4f4f11, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.duelId, 64);
        b.storeUint(self.offerId, 64);
        b.storeUint(self.reason, 8);
    },
    toCell(self: DuelPayout): c.Cell {
        return makeCellFrom<DuelPayout>(self, DuelPayout.store);
    }
}

/**
 > struct (0x4c4f4f12) OfferRefund {
 >     queryId: uint64
 >     offerId: uint64
 >     reason: uint8
 > }
 */
export interface OfferRefund {
    readonly $: 'OfferRefund'
    queryId: uint64
    offerId: uint64
    reason: uint8
}

export const OfferRefund = {
    PREFIX: 0x4c4f4f12,

    create(args: {
        queryId: uint64
        offerId: uint64
        reason: uint8
    }): OfferRefund {
        return {
            $: 'OfferRefund',
            ...args
        }
    },
    fromSlice(s: c.Slice): OfferRefund {
        loadAndCheckPrefix32(s, 0x4c4f4f12, 'OfferRefund');
        return {
            $: 'OfferRefund',
            queryId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
            reason: s.loadUintBig(8),
        }
    },
    store(self: OfferRefund, b: c.Builder): void {
        b.storeUint(0x4c4f4f12, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.offerId, 64);
        b.storeUint(self.reason, 8);
    },
    toCell(self: OfferRefund): c.Cell {
        return makeCellFrom<OfferRefund>(self, OfferRefund.store);
    }
}

/**
 > struct (0x4c4f4f13) ProtocolFee {
 >     queryId: uint64
 >     duelId: uint64
 > }
 */
export interface ProtocolFee {
    readonly $: 'ProtocolFee'
    queryId: uint64
    duelId: uint64
}

export const ProtocolFee = {
    PREFIX: 0x4c4f4f13,

    create(args: {
        queryId: uint64
        duelId: uint64
    }): ProtocolFee {
        return {
            $: 'ProtocolFee',
            ...args
        }
    },
    fromSlice(s: c.Slice): ProtocolFee {
        loadAndCheckPrefix32(s, 0x4c4f4f13, 'ProtocolFee');
        return {
            $: 'ProtocolFee',
            queryId: s.loadUintBig(64),
            duelId: s.loadUintBig(64),
        }
    },
    store(self: ProtocolFee, b: c.Builder): void {
        b.storeUint(0x4c4f4f13, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.duelId, 64);
    },
    toCell(self: ProtocolFee): c.Cell {
        return makeCellFrom<ProtocolFee>(self, ProtocolFee.store);
    }
}

/**
 > type OfferMap = map<uint64, Cell<OfferData>>
 */
export type OfferMap = c.Dictionary<uint64, CellRef<OfferData>>

export const OfferMap = {
    fromSlice(s: c.Slice): OfferMap {
        return c.Dictionary.load<uint64, CellRef<OfferData>>(c.Dictionary.Keys.BigUint(64), createDictionaryValue<CellRef<OfferData>>(
            (s) => loadCellRef<OfferData>(s, OfferData.fromSlice),
            (v,b) => storeCellRef<OfferData>(v, b, OfferData.store)
        ), s);
    },
    store(self: OfferMap, b: c.Builder): void {
        b.storeDict<uint64, CellRef<OfferData>>(self, c.Dictionary.Keys.BigUint(64), createDictionaryValue<CellRef<OfferData>>(
            (s) => loadCellRef<OfferData>(s, OfferData.fromSlice),
            (v,b) => storeCellRef<OfferData>(v, b, OfferData.store)
        ));
    },
    toCell(self: OfferMap): c.Cell {
        return makeCellFrom<OfferMap>(self, OfferMap.store);
    }
}

/**
 > type DuelMap = map<uint64, Cell<DuelData>>
 */
export type DuelMap = c.Dictionary<uint64, CellRef<DuelData>>

export const DuelMap = {
    fromSlice(s: c.Slice): DuelMap {
        return c.Dictionary.load<uint64, CellRef<DuelData>>(c.Dictionary.Keys.BigUint(64), createDictionaryValue<CellRef<DuelData>>(
            (s) => loadCellRef<DuelData>(s, DuelData.fromSlice),
            (v,b) => storeCellRef<DuelData>(v, b, DuelData.store)
        ), s);
    },
    store(self: DuelMap, b: c.Builder): void {
        b.storeDict<uint64, CellRef<DuelData>>(self, c.Dictionary.Keys.BigUint(64), createDictionaryValue<CellRef<DuelData>>(
            (s) => loadCellRef<DuelData>(s, DuelData.fromSlice),
            (v,b) => storeCellRef<DuelData>(v, b, DuelData.store)
        ));
    },
    toCell(self: DuelMap): c.Cell {
        return makeCellFrom<DuelMap>(self, DuelMap.store);
    }
}

/**
 > type ActiveOfferMap = map<address, uint64>
 */
export type ActiveOfferMap = c.Dictionary<c.Address, uint64>

export const ActiveOfferMap = {
    fromSlice(s: c.Slice): ActiveOfferMap {
        return c.Dictionary.load<c.Address, uint64>(c.Dictionary.Keys.Address(), c.Dictionary.Values.BigUint(64), s);
    },
    store(self: ActiveOfferMap, b: c.Builder): void {
        b.storeDict<c.Address, uint64>(self, c.Dictionary.Keys.Address(), c.Dictionary.Values.BigUint(64));
    },
    toCell(self: ActiveOfferMap): c.Cell {
        return makeCellFrom<ActiveOfferMap>(self, ActiveOfferMap.store);
    }
}

/**
 > type UsedOfferMap = map<uint64, bool>
 */
export type UsedOfferMap = c.Dictionary<uint64, boolean>

export const UsedOfferMap = {
    fromSlice(s: c.Slice): UsedOfferMap {
        return c.Dictionary.load<uint64, boolean>(c.Dictionary.Keys.BigUint(64), c.Dictionary.Values.Bool(), s);
    },
    store(self: UsedOfferMap, b: c.Builder): void {
        b.storeDict<uint64, boolean>(self, c.Dictionary.Keys.BigUint(64), c.Dictionary.Values.Bool());
    },
    toCell(self: UsedOfferMap): c.Cell {
        return makeCellFrom<UsedOfferMap>(self, UsedOfferMap.store);
    }
}

/**
 > struct OfferData {
 >     owner: address
 >     commitment: uint256
 >     chanceBps: uint16
 >     totalPool: coins
 >     stake: coins
 >     expiresAt: uint32
 >     state: uint8
 > }
 */
export interface OfferData {
    readonly $: 'OfferData'
    owner: c.Address
    commitment: uint256
    chanceBps: uint16
    totalPool: coins
    stake: coins
    expiresAt: uint32
    state: uint8
}

export const OfferData = {
    create(args: {
        owner: c.Address
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        stake: coins
        expiresAt: uint32
        state: uint8
    }): OfferData {
        return {
            $: 'OfferData',
            ...args
        }
    },
    fromSlice(s: c.Slice): OfferData {
        return {
            $: 'OfferData',
            owner: s.loadAddress(),
            commitment: s.loadUintBig(256),
            chanceBps: s.loadUintBig(16),
            totalPool: s.loadCoins(),
            stake: s.loadCoins(),
            expiresAt: s.loadUintBig(32),
            state: s.loadUintBig(8),
        }
    },
    store(self: OfferData, b: c.Builder): void {
        b.storeAddress(self.owner);
        b.storeUint(self.commitment, 256);
        b.storeUint(self.chanceBps, 16);
        b.storeCoins(self.totalPool);
        b.storeCoins(self.stake);
        b.storeUint(self.expiresAt, 32);
        b.storeUint(self.state, 8);
    },
    toCell(self: OfferData): c.Cell {
        return makeCellFrom<OfferData>(self, OfferData.store);
    }
}

/**
 > struct DuelData {
 >     offerAId: uint64
 >     offerBId: uint64
 >     revealDeadline: uint32
 >     secretA: uint256
 >     secretB: uint256
 >     revealedMask: uint8
 > }
 */
export interface DuelData {
    readonly $: 'DuelData'
    offerAId: uint64
    offerBId: uint64
    revealDeadline: uint32
    secretA: uint256
    secretB: uint256
    revealedMask: uint8
}

export const DuelData = {
    create(args: {
        offerAId: uint64
        offerBId: uint64
        revealDeadline: uint32
        secretA: uint256
        secretB: uint256
        revealedMask: uint8
    }): DuelData {
        return {
            $: 'DuelData',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelData {
        return {
            $: 'DuelData',
            offerAId: s.loadUintBig(64),
            offerBId: s.loadUintBig(64),
            revealDeadline: s.loadUintBig(32),
            secretA: s.loadUintBig(256),
            secretB: s.loadUintBig(256),
            revealedMask: s.loadUintBig(8),
        }
    },
    store(self: DuelData, b: c.Builder): void {
        b.storeUint(self.offerAId, 64);
        b.storeUint(self.offerBId, 64);
        b.storeUint(self.revealDeadline, 32);
        b.storeUint(self.secretA, 256);
        b.storeUint(self.secretB, 256);
        b.storeUint(self.revealedMask, 8);
    },
    toCell(self: DuelData): c.Cell {
        return makeCellFrom<DuelData>(self, DuelData.store);
    }
}

/**
 > struct Storage {
 >     owner: address
 >     treasury: address
 >     feeBps: uint16
 >     paused: bool
 >     locked: coins
 >     offers: OfferMap
 >     duels: DuelMap
 >     activeOffers: ActiveOfferMap
 >     usedOfferIds: UsedOfferMap
 > }
 */
export interface Storage {
    readonly $: 'Storage'
    owner: c.Address
    treasury: c.Address
    feeBps: uint16
    paused: boolean
    locked: coins
    offers: OfferMap
    duels: DuelMap
    activeOffers: ActiveOfferMap
    usedOfferIds: UsedOfferMap
}

export const Storage = {
    create(args: {
        owner: c.Address
        treasury: c.Address
        feeBps: uint16
        paused: boolean
        locked: coins
        offers: OfferMap
        duels: DuelMap
        activeOffers: ActiveOfferMap
        usedOfferIds: UsedOfferMap
    }): Storage {
        return {
            $: 'Storage',
            ...args
        }
    },
    fromSlice(s: c.Slice): Storage {
        return {
            $: 'Storage',
            owner: s.loadAddress(),
            treasury: s.loadAddress(),
            feeBps: s.loadUintBig(16),
            paused: s.loadBoolean(),
            locked: s.loadCoins(),
            offers: OfferMap.fromSlice(s),
            duels: DuelMap.fromSlice(s),
            activeOffers: ActiveOfferMap.fromSlice(s),
            usedOfferIds: UsedOfferMap.fromSlice(s),
        }
    },
    store(self: Storage, b: c.Builder): void {
        b.storeAddress(self.owner);
        b.storeAddress(self.treasury);
        b.storeUint(self.feeBps, 16);
        b.storeBit(self.paused);
        b.storeCoins(self.locked);
        OfferMap.store(self.offers, b);
        DuelMap.store(self.duels, b);
        ActiveOfferMap.store(self.activeOffers, b);
        UsedOfferMap.store(self.usedOfferIds, b);
    },
    toCell(self: Storage): c.Cell {
        return makeCellFrom<Storage>(self, Storage.store);
    }
}

/**
 > struct ContractConfigView {
 >     owner: address
 >     treasury: address
 >     feeBps: uint16
 >     paused: bool
 >     locked: coins
 > }
 */
export interface ContractConfigView {
    readonly $: 'ContractConfigView'
    owner: c.Address
    treasury: c.Address
    feeBps: uint16
    paused: boolean
    locked: coins
}

export const ContractConfigView = {
    create(args: {
        owner: c.Address
        treasury: c.Address
        feeBps: uint16
        paused: boolean
        locked: coins
    }): ContractConfigView {
        return {
            $: 'ContractConfigView',
            ...args
        }
    },
    fromSlice(s: c.Slice): ContractConfigView {
        return {
            $: 'ContractConfigView',
            owner: s.loadAddress(),
            treasury: s.loadAddress(),
            feeBps: s.loadUintBig(16),
            paused: s.loadBoolean(),
            locked: s.loadCoins(),
        }
    },
    store(self: ContractConfigView, b: c.Builder): void {
        b.storeAddress(self.owner);
        b.storeAddress(self.treasury);
        b.storeUint(self.feeBps, 16);
        b.storeBit(self.paused);
        b.storeCoins(self.locked);
    },
    toCell(self: ContractConfigView): c.Cell {
        return makeCellFrom<ContractConfigView>(self, ContractConfigView.store);
    }
}

// ————————————————————————————————————————————
//    class DuelEscrow
//

interface ExtraSendOptions {
    bounce?: boolean                    // default: false
    sendMode?: SendMode                 // default: SendMode.PAY_GAS_SEPARATELY
    extraCurrencies?: c.ExtraCurrency   // default: empty dict
}

interface DeployedAddrOptions {
    workchain?: number                  // default: 0 (basechain)
    toShard?: { fixedPrefixLength: number; closeTo: c.Address }
    overrideContractCode?: c.Cell
}

function calculateDeployedAddress(code: c.Cell, data: c.Cell, options: DeployedAddrOptions): c.Address {
    const stateInitCell = beginCell().store(c.storeStateInit({
        code,
        data,
        splitDepth: options.toShard?.fixedPrefixLength,
        special: null,
        libraries: null,
    })).endCell();

    let addrHash = stateInitCell.hash();
    if (options.toShard) {
        const shardDepth = options.toShard.fixedPrefixLength;
        addrHash = beginCell()
            .storeBits(new c.BitString(options.toShard.closeTo.hash, 0, shardDepth))
            .storeBits(new c.BitString(stateInitCell.hash(), shardDepth, 256 - shardDepth))
            .endCell()
            .beginParse().loadBuffer(32);
    }

    return new c.Address(options.workchain ?? 0, addrHash);
}

export class DuelEscrow implements c.Contract {
    static CodeCell = c.Cell.fromBase64('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');

    static Errors = {
        'Errors.NotOwner': 100,
        'Errors.Paused': 101,
        'Errors.OfferAlreadyUsed': 102,
        'Errors.OwnerAlreadyActive': 103,
        'Errors.OfferMissing': 104,
        'Errors.OfferNotOpen': 105,
        'Errors.DuelMissing': 106,
        'Errors.InvalidChance': 107,
        'Errors.InvalidPool': 108,
        'Errors.InvalidExpiry': 109,
        'Errors.InsufficientValue': 110,
        'Errors.IncompatibleOffers': 111,
        'Errors.SameOwner': 112,
        'Errors.RevealClosed': 113,
        'Errors.WrongRevealer': 114,
        'Errors.AlreadyRevealed': 115,
        'Errors.InvalidCommitment': 116,
        'Errors.TooEarly': 117,
        'Errors.InvalidFee': 118,
        'Errors.InvalidOfferId': 119,
        'Errors.InvalidMessage': 65535,
    }

    readonly address: c.Address
    readonly init: { code: c.Cell, data: c.Cell } | undefined

    protected constructor(address: c.Address, init?: { code: c.Cell, data: c.Cell }) {
        this.address = address;
        this.init = init;
    }

    static fromAddress(address: c.Address) {
        return new DuelEscrow(address);
    }

    static fromStorage(emptyStorage: {
        owner: c.Address
        treasury: c.Address
        feeBps: uint16
        paused: boolean
        locked: coins
        offers: OfferMap
        duels: DuelMap
        activeOffers: ActiveOfferMap
        usedOfferIds: UsedOfferMap
    }, deployedOptions?: DeployedAddrOptions) {
        const initialState = {
            code: deployedOptions?.overrideContractCode ?? DuelEscrow.CodeCell,
            data: Storage.toCell(Storage.create(emptyStorage)),
        };
        const address = calculateDeployedAddress(initialState.code, initialState.data, deployedOptions ?? {});
        return new DuelEscrow(address, initialState);
    }

    static createCellOfOpenOffer(body: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        counterOfferId: uint64
    }) {
        return OpenOffer.toCell(OpenOffer.create(body));
    }

    static createCellOfCancelOffer(body: {
        queryId: uint64
        offerId: uint64
    }) {
        return CancelOffer.toCell(CancelOffer.create(body));
    }

    static createCellOfMatchOffers(body: {
        queryId: uint64
        firstOfferId: uint64
        secondOfferId: uint64
    }) {
        return MatchOffers.toCell(MatchOffers.create(body));
    }

    static createCellOfReveal(body: {
        queryId: uint64
        duelId: uint64
        offerId: uint64
        secret: uint256
    }) {
        return Reveal.toCell(Reveal.create(body));
    }

    static createCellOfExpireOffer(body: {
        queryId: uint64
        offerId: uint64
    }) {
        return ExpireOffer.toCell(ExpireOffer.create(body));
    }

    static createCellOfExpireDuel(body: {
        queryId: uint64
        duelId: uint64
    }) {
        return ExpireDuel.toCell(ExpireDuel.create(body));
    }

    static createCellOfSetPaused(body: {
        queryId: uint64
        paused: boolean
    }) {
        return SetPaused.toCell(SetPaused.create(body));
    }

    async sendDeploy(provider: ContractProvider, via: Sender, msgValue: coins, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: c.Cell.EMPTY,
            ...extraOptions
        });
    }

    async sendOpenOffer(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        counterOfferId: uint64
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: OpenOffer.toCell(OpenOffer.create(body)),
            ...extraOptions
        });
    }

    async sendCancelOffer(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        offerId: uint64
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: CancelOffer.toCell(CancelOffer.create(body)),
            ...extraOptions
        });
    }

    async sendMatchOffers(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        firstOfferId: uint64
        secondOfferId: uint64
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: MatchOffers.toCell(MatchOffers.create(body)),
            ...extraOptions
        });
    }

    async sendReveal(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        duelId: uint64
        offerId: uint64
        secret: uint256
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: Reveal.toCell(Reveal.create(body)),
            ...extraOptions
        });
    }

    async sendExpireOffer(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        offerId: uint64
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: ExpireOffer.toCell(ExpireOffer.create(body)),
            ...extraOptions
        });
    }

    async sendExpireDuel(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        duelId: uint64
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: ExpireDuel.toCell(ExpireDuel.create(body)),
            ...extraOptions
        });
    }

    async sendSetPaused(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        paused: boolean
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: SetPaused.toCell(SetPaused.create(body)),
            ...extraOptions
        });
    }

    async getContractConfig(provider: ContractProvider): Promise<ContractConfigView> {
        const r = StackReader.fromGetMethod(5, await provider.get('contractConfig', []));
        return ({
            $: 'ContractConfigView',
            owner: r.readSlice().loadAddress(),
            treasury: r.readSlice().loadAddress(),
            feeBps: r.readBigInt(),
            paused: r.readBoolean(),
            locked: r.readBigInt(),
        });
    }

    async getOfferData(provider: ContractProvider, offerId: uint64): Promise<OfferData> {
        const r = StackReader.fromGetMethod(7, await provider.get('offerData', [
            { type: 'int', value: offerId },
        ]));
        return ({
            $: 'OfferData',
            owner: r.readSlice().loadAddress(),
            commitment: r.readBigInt(),
            chanceBps: r.readBigInt(),
            totalPool: r.readBigInt(),
            stake: r.readBigInt(),
            expiresAt: r.readBigInt(),
            state: r.readBigInt(),
        });
    }

    async getDuelData(provider: ContractProvider, duelId: uint64): Promise<DuelData> {
        const r = StackReader.fromGetMethod(6, await provider.get('duelData', [
            { type: 'int', value: duelId },
        ]));
        return ({
            $: 'DuelData',
            offerAId: r.readBigInt(),
            offerBId: r.readBigInt(),
            revealDeadline: r.readBigInt(),
            secretA: r.readBigInt(),
            secretB: r.readBigInt(),
            revealedMask: r.readBigInt(),
        });
    }

    async getActiveOffer(provider: ContractProvider, owner: c.Address): Promise<uint64> {
        const r = StackReader.fromGetMethod(1, await provider.get('activeOffer', [
            { type: 'slice', cell: makeCellFrom<c.Address>(owner,
                (v,b) => b.storeAddress(v)
            ) },
        ]));
        return r.readBigInt();
    }
}
