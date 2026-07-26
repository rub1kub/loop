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

function storeTolkBitsN(v: c.Slice, nBits: number, b: c.Builder): void {
    if (v.remainingBits !== nBits) { throw new Error(`expected ${nBits} bits, got ${v.remainingBits}`); }
    if (v.remainingRefs !== 0) { throw new Error(`expected 0 refs, got ${v.remainingRefs}`); }
    b.storeSlice(v);
}

function loadTolkBitsN(s: c.Slice, nBits: number): c.Slice {
    return new c.Slice(new c.BitReader(s.loadBits(nBits)), []);
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

    readNullable<T>(readFn_T: (r: StackReader) => T): T | null {
        if (this.tuple[0].type === 'null') {
            this.tuple.shift();
            return null;
        }
        return readFn_T(this);
    }

    readCellRef<T>(loadFn_T: LoadCallback<T>): CellRef<T> {
        return { ref: loadFn_T(this.readCell().beginParse()) };
    }
}

// ————————————————————————————————————————————
//   auto-generated serializers to/from cells
//

type coins = bigint

type int32 = bigint

type uint8 = bigint
type uint16 = bigint
type uint32 = bigint
type uint64 = bigint
type uint256 = bigint

type bits512 = c.Slice

/**
 > struct HolderFeePermit {
 >     validUntil: uint32
 >     signature: bits512
 > }
 */
export interface HolderFeePermit {
    readonly $: 'HolderFeePermit'
    validUntil: uint32
    signature: bits512
}

export const HolderFeePermit = {
    create(args: {
        validUntil: uint32
        signature: bits512
    }): HolderFeePermit {
        return {
            $: 'HolderFeePermit',
            ...args
        }
    },
    fromSlice(s: c.Slice): HolderFeePermit {
        return {
            $: 'HolderFeePermit',
            validUntil: s.loadUintBig(32),
            signature: loadTolkBitsN(s, 512),
        }
    },
    store(self: HolderFeePermit, b: c.Builder): void {
        b.storeUint(self.validUntil, 32);
        storeTolkBitsN(self.signature, 512, b);
    },
    toCell(self: HolderFeePermit): c.Cell {
        return makeCellFrom<HolderFeePermit>(self, HolderFeePermit.store);
    }
}

/**
 > struct (0x4c4f4f01) OpenOffer {
 >     queryId: uint64
 >     offerId: uint64
 >     commitment: uint256
 >     chanceBps: uint16
 >     totalPool: coins
 >     expiresAt: uint32
 >     counterOfferId: uint64
 >     holder: Cell<HolderFeePermit>?
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
    holder: CellRef<HolderFeePermit> | null
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
        holder: CellRef<HolderFeePermit> | null
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
            holder: s.loadBoolean() ? loadCellRef<HolderFeePermit>(s, HolderFeePermit.fromSlice) : null,
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
        storeTolkNullable<CellRef<HolderFeePermit>>(self.holder, b,
            (v,b) => storeCellRef<HolderFeePermit>(v, b, HolderFeePermit.store)
        );
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
 > struct (0x4c4f4f08) OpenDirectOffer {
 >     queryId: uint64
 >     offerId: uint64
 >     commitment: uint256
 >     chanceBps: uint16
 >     totalPool: coins
 >     expiresAt: uint32
 >     inviteId: uint256
 >     holder: Cell<HolderFeePermit>?
 > }
 */
export interface OpenDirectOffer {
    readonly $: 'OpenDirectOffer'
    queryId: uint64
    offerId: uint64
    commitment: uint256
    chanceBps: uint16
    totalPool: coins
    expiresAt: uint32
    inviteId: uint256
    holder: CellRef<HolderFeePermit> | null
}

export const OpenDirectOffer = {
    PREFIX: 0x4c4f4f08,

    create(args: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        inviteId: uint256
        holder: CellRef<HolderFeePermit> | null
    }): OpenDirectOffer {
        return {
            $: 'OpenDirectOffer',
            ...args
        }
    },
    fromSlice(s: c.Slice): OpenDirectOffer {
        loadAndCheckPrefix32(s, 0x4c4f4f08, 'OpenDirectOffer');
        return {
            $: 'OpenDirectOffer',
            queryId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
            commitment: s.loadUintBig(256),
            chanceBps: s.loadUintBig(16),
            totalPool: s.loadCoins(),
            expiresAt: s.loadUintBig(32),
            inviteId: s.loadUintBig(256),
            holder: s.loadBoolean() ? loadCellRef<HolderFeePermit>(s, HolderFeePermit.fromSlice) : null,
        }
    },
    store(self: OpenDirectOffer, b: c.Builder): void {
        b.storeUint(0x4c4f4f08, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.offerId, 64);
        b.storeUint(self.commitment, 256);
        b.storeUint(self.chanceBps, 16);
        b.storeCoins(self.totalPool);
        b.storeUint(self.expiresAt, 32);
        b.storeUint(self.inviteId, 256);
        storeTolkNullable<CellRef<HolderFeePermit>>(self.holder, b,
            (v,b) => storeCellRef<HolderFeePermit>(v, b, HolderFeePermit.store)
        );
    },
    toCell(self: OpenDirectOffer): c.Cell {
        return makeCellFrom<OpenDirectOffer>(self, OpenDirectOffer.store);
    }
}

/**
 > struct DirectAcceptance {
 >     counterOfferId: uint64
 >     validUntil: uint32
 >     signature: bits512
 > }
 */
export interface DirectAcceptance {
    readonly $: 'DirectAcceptance'
    counterOfferId: uint64
    validUntil: uint32
    signature: bits512
}

export const DirectAcceptance = {
    create(args: {
        counterOfferId: uint64
        validUntil: uint32
        signature: bits512
    }): DirectAcceptance {
        return {
            $: 'DirectAcceptance',
            ...args
        }
    },
    fromSlice(s: c.Slice): DirectAcceptance {
        return {
            $: 'DirectAcceptance',
            counterOfferId: s.loadUintBig(64),
            validUntil: s.loadUintBig(32),
            signature: loadTolkBitsN(s, 512),
        }
    },
    store(self: DirectAcceptance, b: c.Builder): void {
        b.storeUint(self.counterOfferId, 64);
        b.storeUint(self.validUntil, 32);
        storeTolkBitsN(self.signature, 512, b);
    },
    toCell(self: DirectAcceptance): c.Cell {
        return makeCellFrom<DirectAcceptance>(self, DirectAcceptance.store);
    }
}

/**
 > struct (0x4c4f4f09) AcceptDirectOffer {
 >     queryId: uint64
 >     offerId: uint64
 >     commitment: uint256
 >     chanceBps: uint16
 >     totalPool: coins
 >     expiresAt: uint32
 >     acceptance: Cell<DirectAcceptance>
 >     holder: Cell<HolderFeePermit>?
 > }
 */
export interface AcceptDirectOffer {
    readonly $: 'AcceptDirectOffer'
    queryId: uint64
    offerId: uint64
    commitment: uint256
    chanceBps: uint16
    totalPool: coins
    expiresAt: uint32
    acceptance: CellRef<DirectAcceptance>
    holder: CellRef<HolderFeePermit> | null
}

export const AcceptDirectOffer = {
    PREFIX: 0x4c4f4f09,

    create(args: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        acceptance: CellRef<DirectAcceptance>
        holder: CellRef<HolderFeePermit> | null
    }): AcceptDirectOffer {
        return {
            $: 'AcceptDirectOffer',
            ...args
        }
    },
    fromSlice(s: c.Slice): AcceptDirectOffer {
        loadAndCheckPrefix32(s, 0x4c4f4f09, 'AcceptDirectOffer');
        return {
            $: 'AcceptDirectOffer',
            queryId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
            commitment: s.loadUintBig(256),
            chanceBps: s.loadUintBig(16),
            totalPool: s.loadCoins(),
            expiresAt: s.loadUintBig(32),
            acceptance: loadCellRef<DirectAcceptance>(s, DirectAcceptance.fromSlice),
            holder: s.loadBoolean() ? loadCellRef<HolderFeePermit>(s, HolderFeePermit.fromSlice) : null,
        }
    },
    store(self: AcceptDirectOffer, b: c.Builder): void {
        b.storeUint(0x4c4f4f09, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.offerId, 64);
        b.storeUint(self.commitment, 256);
        b.storeUint(self.chanceBps, 16);
        b.storeCoins(self.totalPool);
        b.storeUint(self.expiresAt, 32);
        storeCellRef<DirectAcceptance>(self.acceptance, b, DirectAcceptance.store);
        storeTolkNullable<CellRef<HolderFeePermit>>(self.holder, b,
            (v,b) => storeCellRef<HolderFeePermit>(v, b, HolderFeePermit.store)
        );
    },
    toCell(self: AcceptDirectOffer): c.Cell {
        return makeCellFrom<AcceptDirectOffer>(self, AcceptDirectOffer.store);
    }
}

/**
 > struct (0x4c4f4f0a) DuelFundReserve {
 >     queryId: uint64
 >     amount: coins
 > }
 */
export interface DuelFundReserve {
    readonly $: 'DuelFundReserve'
    queryId: uint64
    amount: coins
}

export const DuelFundReserve = {
    PREFIX: 0x4c4f4f0a,

    create(args: {
        queryId: uint64
        amount: coins
    }): DuelFundReserve {
        return {
            $: 'DuelFundReserve',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelFundReserve {
        loadAndCheckPrefix32(s, 0x4c4f4f0a, 'DuelFundReserve');
        return {
            $: 'DuelFundReserve',
            queryId: s.loadUintBig(64),
            amount: s.loadCoins(),
        }
    },
    store(self: DuelFundReserve, b: c.Builder): void {
        b.storeUint(0x4c4f4f0a, 32);
        b.storeUint(self.queryId, 64);
        b.storeCoins(self.amount);
    },
    toCell(self: DuelFundReserve): c.Cell {
        return makeCellFrom<DuelFundReserve>(self, DuelFundReserve.store);
    }
}

/**
 > struct (0x4c4f4f0b) DuelWithdrawSurplus {
 >     queryId: uint64
 >     amount: coins
 > }
 */
export interface DuelWithdrawSurplus {
    readonly $: 'DuelWithdrawSurplus'
    queryId: uint64
    amount: coins
}

export const DuelWithdrawSurplus = {
    PREFIX: 0x4c4f4f0b,

    create(args: {
        queryId: uint64
        amount: coins
    }): DuelWithdrawSurplus {
        return {
            $: 'DuelWithdrawSurplus',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelWithdrawSurplus {
        loadAndCheckPrefix32(s, 0x4c4f4f0b, 'DuelWithdrawSurplus');
        return {
            $: 'DuelWithdrawSurplus',
            queryId: s.loadUintBig(64),
            amount: s.loadCoins(),
        }
    },
    store(self: DuelWithdrawSurplus, b: c.Builder): void {
        b.storeUint(0x4c4f4f0b, 32);
        b.storeUint(self.queryId, 64);
        b.storeCoins(self.amount);
    },
    toCell(self: DuelWithdrawSurplus): c.Cell {
        return makeCellFrom<DuelWithdrawSurplus>(self, DuelWithdrawSurplus.store);
    }
}

/**
 > struct (0x4c4f4f0c) DuelSetFee {
 >     queryId: uint64
 >     feeBps: uint16
 > }
 */
export interface DuelSetFee {
    readonly $: 'DuelSetFee'
    queryId: uint64
    feeBps: uint16
}

export const DuelSetFee = {
    PREFIX: 0x4c4f4f0c,

    create(args: {
        queryId: uint64
        feeBps: uint16
    }): DuelSetFee {
        return {
            $: 'DuelSetFee',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelSetFee {
        loadAndCheckPrefix32(s, 0x4c4f4f0c, 'DuelSetFee');
        return {
            $: 'DuelSetFee',
            queryId: s.loadUintBig(64),
            feeBps: s.loadUintBig(16),
        }
    },
    store(self: DuelSetFee, b: c.Builder): void {
        b.storeUint(0x4c4f4f0c, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.feeBps, 16);
    },
    toCell(self: DuelSetFee): c.Cell {
        return makeCellFrom<DuelSetFee>(self, DuelSetFee.store);
    }
}

/**
 > struct (0x4c4f4f0d) DuelSetTreasury {
 >     queryId: uint64
 >     treasury: address
 > }
 */
export interface DuelSetTreasury {
    readonly $: 'DuelSetTreasury'
    queryId: uint64
    treasury: c.Address
}

export const DuelSetTreasury = {
    PREFIX: 0x4c4f4f0d,

    create(args: {
        queryId: uint64
        treasury: c.Address
    }): DuelSetTreasury {
        return {
            $: 'DuelSetTreasury',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelSetTreasury {
        loadAndCheckPrefix32(s, 0x4c4f4f0d, 'DuelSetTreasury');
        return {
            $: 'DuelSetTreasury',
            queryId: s.loadUintBig(64),
            treasury: s.loadAddress(),
        }
    },
    store(self: DuelSetTreasury, b: c.Builder): void {
        b.storeUint(0x4c4f4f0d, 32);
        b.storeUint(self.queryId, 64);
        b.storeAddress(self.treasury);
    },
    toCell(self: DuelSetTreasury): c.Cell {
        return makeCellFrom<DuelSetTreasury>(self, DuelSetTreasury.store);
    }
}

/**
 > struct (0x4c4f4f0e) DuelSetOwner {
 >     queryId: uint64
 >     owner: address
 > }
 */
export interface DuelSetOwner {
    readonly $: 'DuelSetOwner'
    queryId: uint64
    owner: c.Address
}

export const DuelSetOwner = {
    PREFIX: 0x4c4f4f0e,

    create(args: {
        queryId: uint64
        owner: c.Address
    }): DuelSetOwner {
        return {
            $: 'DuelSetOwner',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelSetOwner {
        loadAndCheckPrefix32(s, 0x4c4f4f0e, 'DuelSetOwner');
        return {
            $: 'DuelSetOwner',
            queryId: s.loadUintBig(64),
            owner: s.loadAddress(),
        }
    },
    store(self: DuelSetOwner, b: c.Builder): void {
        b.storeUint(0x4c4f4f0e, 32);
        b.storeUint(self.queryId, 64);
        b.storeAddress(self.owner);
    },
    toCell(self: DuelSetOwner): c.Cell {
        return makeCellFrom<DuelSetOwner>(self, DuelSetOwner.store);
    }
}

/**
 > struct (0x4c4f4f0f) BoostDuel {
 >     queryId: uint64
 >     duelId: uint64
 >     offerId: uint64
 >     amount: coins
 >     expectedRevision: uint16
 >     minChanceBps: uint16
 >     validUntil: uint32
 > }
 */
export interface BoostDuel {
    readonly $: 'BoostDuel'
    queryId: uint64
    duelId: uint64
    offerId: uint64
    amount: coins
    expectedRevision: uint16
    minChanceBps: uint16
    validUntil: uint32
}

export const BoostDuel = {
    PREFIX: 0x4c4f4f0f,

    create(args: {
        queryId: uint64
        duelId: uint64
        offerId: uint64
        amount: coins
        expectedRevision: uint16
        minChanceBps: uint16
        validUntil: uint32
    }): BoostDuel {
        return {
            $: 'BoostDuel',
            ...args
        }
    },
    fromSlice(s: c.Slice): BoostDuel {
        loadAndCheckPrefix32(s, 0x4c4f4f0f, 'BoostDuel');
        return {
            $: 'BoostDuel',
            queryId: s.loadUintBig(64),
            duelId: s.loadUintBig(64),
            offerId: s.loadUintBig(64),
            amount: s.loadCoins(),
            expectedRevision: s.loadUintBig(16),
            minChanceBps: s.loadUintBig(16),
            validUntil: s.loadUintBig(32),
        }
    },
    store(self: BoostDuel, b: c.Builder): void {
        b.storeUint(0x4c4f4f0f, 32);
        b.storeUint(self.queryId, 64);
        b.storeUint(self.duelId, 64);
        b.storeUint(self.offerId, 64);
        b.storeCoins(self.amount);
        b.storeUint(self.expectedRevision, 16);
        b.storeUint(self.minChanceBps, 16);
        b.storeUint(self.validUntil, 32);
    },
    toCell(self: BoostDuel): c.Cell {
        return makeCellFrom<BoostDuel>(self, BoostDuel.store);
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
 > struct (0x4c4f4f14) DuelAdminWithdrawal {
 >     queryId: uint64
 >     amount: coins
 > }
 */
export interface DuelAdminWithdrawal {
    readonly $: 'DuelAdminWithdrawal'
    queryId: uint64
    amount: coins
}

export const DuelAdminWithdrawal = {
    PREFIX: 0x4c4f4f14,

    create(args: {
        queryId: uint64
        amount: coins
    }): DuelAdminWithdrawal {
        return {
            $: 'DuelAdminWithdrawal',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelAdminWithdrawal {
        loadAndCheckPrefix32(s, 0x4c4f4f14, 'DuelAdminWithdrawal');
        return {
            $: 'DuelAdminWithdrawal',
            queryId: s.loadUintBig(64),
            amount: s.loadCoins(),
        }
    },
    store(self: DuelAdminWithdrawal, b: c.Builder): void {
        b.storeUint(0x4c4f4f14, 32);
        b.storeUint(self.queryId, 64);
        b.storeCoins(self.amount);
    },
    toCell(self: DuelAdminWithdrawal): c.Cell {
        return makeCellFrom<DuelAdminWithdrawal>(self, DuelAdminWithdrawal.store);
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
 > struct DirectOfferData {
 >     inviteId: uint256
 >     opponent: address?
 > }
 */
export interface DirectOfferData {
    readonly $: 'DirectOfferData'
    inviteId: uint256
    opponent: c.Address | null
}

export const DirectOfferData = {
    create(args: {
        inviteId: uint256
        opponent: c.Address | null
    }): DirectOfferData {
        return {
            $: 'DirectOfferData',
            ...args
        }
    },
    fromSlice(s: c.Slice): DirectOfferData {
        return {
            $: 'DirectOfferData',
            inviteId: s.loadUintBig(256),
            opponent: s.loadMaybeAddress(),
        }
    },
    store(self: DirectOfferData, b: c.Builder): void {
        b.storeUint(self.inviteId, 256);
        b.storeAddress(self.opponent);
    },
    toCell(self: DirectOfferData): c.Cell {
        return makeCellFrom<DirectOfferData>(self, DirectOfferData.store);
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
 >     feeExempt: bool
 >     direct: Cell<DirectOfferData>
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
    feeExempt: boolean
    direct: CellRef<DirectOfferData>
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
        feeExempt: boolean
        direct: CellRef<DirectOfferData>
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
            feeExempt: s.loadBoolean(),
            direct: loadCellRef<DirectOfferData>(s, DirectOfferData.fromSlice),
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
        b.storeBit(self.feeExempt);
        storeCellRef<DirectOfferData>(self.direct, b, DirectOfferData.store);
    },
    toCell(self: OfferData): c.Cell {
        return makeCellFrom<OfferData>(self, OfferData.store);
    }
}

/**
 > struct DuelData {
 >     offerAId: uint64
 >     offerBId: uint64
 >     boostDeadline: uint32
 >     hardDeadline: uint32
 >     revealDeadline: uint32
 >     boostRevision: uint16
 >     secretA: uint256
 >     secretB: uint256
 >     revealedMask: uint8
 > }
 */
export interface DuelData {
    readonly $: 'DuelData'
    offerAId: uint64
    offerBId: uint64
    boostDeadline: uint32
    hardDeadline: uint32
    revealDeadline: uint32
    boostRevision: uint16
    secretA: uint256
    secretB: uint256
    revealedMask: uint8
}

export const DuelData = {
    create(args: {
        offerAId: uint64
        offerBId: uint64
        boostDeadline: uint32
        hardDeadline: uint32
        revealDeadline: uint32
        boostRevision: uint16
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
            boostDeadline: s.loadUintBig(32),
            hardDeadline: s.loadUintBig(32),
            revealDeadline: s.loadUintBig(32),
            boostRevision: s.loadUintBig(16),
            secretA: s.loadUintBig(256),
            secretB: s.loadUintBig(256),
            revealedMask: s.loadUintBig(8),
        }
    },
    store(self: DuelData, b: c.Builder): void {
        b.storeUint(self.offerAId, 64);
        b.storeUint(self.offerBId, 64);
        b.storeUint(self.boostDeadline, 32);
        b.storeUint(self.hardDeadline, 32);
        b.storeUint(self.revealDeadline, 32);
        b.storeUint(self.boostRevision, 16);
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
 >     networkId: int32
 >     inviteSignerPublicKey: uint256
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
    networkId: int32
    inviteSignerPublicKey: uint256
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
        networkId: int32
        inviteSignerPublicKey: uint256
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
            networkId: s.loadIntBig(32),
            inviteSignerPublicKey: s.loadUintBig(256),
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
        b.storeInt(self.networkId, 32);
        b.storeUint(self.inviteSignerPublicKey, 256);
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
 >     networkId: int32
 >     inviteSignerPublicKey: uint256
 >     contractAddress: address
 >     paused: bool
 >     locked: coins
 >     holderFeeSupported: bool
 > }
 */
export interface ContractConfigView {
    readonly $: 'ContractConfigView'
    owner: c.Address
    treasury: c.Address
    feeBps: uint16
    networkId: int32
    inviteSignerPublicKey: uint256
    contractAddress: c.Address
    paused: boolean
    locked: coins
    holderFeeSupported: boolean
}

export const ContractConfigView = {
    create(args: {
        owner: c.Address
        treasury: c.Address
        feeBps: uint16
        networkId: int32
        inviteSignerPublicKey: uint256
        contractAddress: c.Address
        paused: boolean
        locked: coins
        holderFeeSupported: boolean
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
            networkId: s.loadIntBig(32),
            inviteSignerPublicKey: s.loadUintBig(256),
            contractAddress: s.loadAddress(),
            paused: s.loadBoolean(),
            locked: s.loadCoins(),
            holderFeeSupported: s.loadBoolean(),
        }
    },
    store(self: ContractConfigView, b: c.Builder): void {
        b.storeAddress(self.owner);
        b.storeAddress(self.treasury);
        b.storeUint(self.feeBps, 16);
        b.storeInt(self.networkId, 32);
        b.storeUint(self.inviteSignerPublicKey, 256);
        b.storeAddress(self.contractAddress);
        b.storeBit(self.paused);
        b.storeCoins(self.locked);
        b.storeBit(self.holderFeeSupported);
    },
    toCell(self: ContractConfigView): c.Cell {
        return makeCellFrom<ContractConfigView>(self, ContractConfigView.store);
    }
}

/**
 > struct DuelAdminStateView {
 >     owner: address
 >     treasury: address
 >     feeBps: uint16
 >     paused: bool
 >     locked: coins
 > }
 */
export interface DuelAdminStateView {
    readonly $: 'DuelAdminStateView'
    owner: c.Address
    treasury: c.Address
    feeBps: uint16
    paused: boolean
    locked: coins
}

export const DuelAdminStateView = {
    create(args: {
        owner: c.Address
        treasury: c.Address
        feeBps: uint16
        paused: boolean
        locked: coins
    }): DuelAdminStateView {
        return {
            $: 'DuelAdminStateView',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelAdminStateView {
        return {
            $: 'DuelAdminStateView',
            owner: s.loadAddress(),
            treasury: s.loadAddress(),
            feeBps: s.loadUintBig(16),
            paused: s.loadBoolean(),
            locked: s.loadCoins(),
        }
    },
    store(self: DuelAdminStateView, b: c.Builder): void {
        b.storeAddress(self.owner);
        b.storeAddress(self.treasury);
        b.storeUint(self.feeBps, 16);
        b.storeBit(self.paused);
        b.storeCoins(self.locked);
    },
    toCell(self: DuelAdminStateView): c.Cell {
        return makeCellFrom<DuelAdminStateView>(self, DuelAdminStateView.store);
    }
}

/**
 > struct DuelBoostView {
 >     stakeA: coins
 >     stakeB: coins
 >     chanceABps: uint16
 >     chanceBBps: uint16
 >     boostDeadline: uint32
 >     hardDeadline: uint32
 >     revealDeadline: uint32
 >     boostRevision: uint16
 > }
 */
export interface DuelBoostView {
    readonly $: 'DuelBoostView'
    stakeA: coins
    stakeB: coins
    chanceABps: uint16
    chanceBBps: uint16
    boostDeadline: uint32
    hardDeadline: uint32
    revealDeadline: uint32
    boostRevision: uint16
}

export const DuelBoostView = {
    create(args: {
        stakeA: coins
        stakeB: coins
        chanceABps: uint16
        chanceBBps: uint16
        boostDeadline: uint32
        hardDeadline: uint32
        revealDeadline: uint32
        boostRevision: uint16
    }): DuelBoostView {
        return {
            $: 'DuelBoostView',
            ...args
        }
    },
    fromSlice(s: c.Slice): DuelBoostView {
        return {
            $: 'DuelBoostView',
            stakeA: s.loadCoins(),
            stakeB: s.loadCoins(),
            chanceABps: s.loadUintBig(16),
            chanceBBps: s.loadUintBig(16),
            boostDeadline: s.loadUintBig(32),
            hardDeadline: s.loadUintBig(32),
            revealDeadline: s.loadUintBig(32),
            boostRevision: s.loadUintBig(16),
        }
    },
    store(self: DuelBoostView, b: c.Builder): void {
        b.storeCoins(self.stakeA);
        b.storeCoins(self.stakeB);
        b.storeUint(self.chanceABps, 16);
        b.storeUint(self.chanceBBps, 16);
        b.storeUint(self.boostDeadline, 32);
        b.storeUint(self.hardDeadline, 32);
        b.storeUint(self.revealDeadline, 32);
        b.storeUint(self.boostRevision, 16);
    },
    toCell(self: DuelBoostView): c.Cell {
        return makeCellFrom<DuelBoostView>(self, DuelBoostView.store);
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
        'Errors.DirectInviteRequired': 120,
        'Errors.InvalidDirectPermit': 121,
        'Errors.DirectPermitExpired': 122,
        'Errors.InvalidAdminAmount': 123,
        'Errors.InsufficientSurplus': 124,
        'Errors.MustBePaused': 125,
        'Errors.InvalidTreasury': 126,
        'Errors.InvalidOwner': 127,
        'Errors.ActiveValueLocked': 129,
        'Errors.BoostClosed': 130,
        'Errors.InvalidBoost': 131,
        'Errors.StaleBoost': 132,
        'Errors.RevealNotOpen': 133,
        'Errors.InvalidHolderPermit': 134,
        'Errors.HolderPermitExpired': 135,
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
        networkId: int32
        inviteSignerPublicKey: uint256
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
        holder: CellRef<HolderFeePermit> | null
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

    static createCellOfOpenDirectOffer(body: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        inviteId: uint256
        holder: CellRef<HolderFeePermit> | null
    }) {
        return OpenDirectOffer.toCell(OpenDirectOffer.create(body));
    }

    static createCellOfAcceptDirectOffer(body: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        acceptance: CellRef<DirectAcceptance>
        holder: CellRef<HolderFeePermit> | null
    }) {
        return AcceptDirectOffer.toCell(AcceptDirectOffer.create(body));
    }

    static createCellOfDuelFundReserve(body: {
        queryId: uint64
        amount: coins
    }) {
        return DuelFundReserve.toCell(DuelFundReserve.create(body));
    }

    static createCellOfDuelWithdrawSurplus(body: {
        queryId: uint64
        amount: coins
    }) {
        return DuelWithdrawSurplus.toCell(DuelWithdrawSurplus.create(body));
    }

    static createCellOfDuelSetFee(body: {
        queryId: uint64
        feeBps: uint16
    }) {
        return DuelSetFee.toCell(DuelSetFee.create(body));
    }

    static createCellOfDuelSetTreasury(body: {
        queryId: uint64
        treasury: c.Address
    }) {
        return DuelSetTreasury.toCell(DuelSetTreasury.create(body));
    }

    static createCellOfDuelSetOwner(body: {
        queryId: uint64
        owner: c.Address
    }) {
        return DuelSetOwner.toCell(DuelSetOwner.create(body));
    }

    static createCellOfBoostDuel(body: {
        queryId: uint64
        duelId: uint64
        offerId: uint64
        amount: coins
        expectedRevision: uint16
        minChanceBps: uint16
        validUntil: uint32
    }) {
        return BoostDuel.toCell(BoostDuel.create(body));
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
        holder: CellRef<HolderFeePermit> | null
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

    async sendOpenDirectOffer(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        inviteId: uint256
        holder: CellRef<HolderFeePermit> | null
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: OpenDirectOffer.toCell(OpenDirectOffer.create(body)),
            ...extraOptions
        });
    }

    async sendAcceptDirectOffer(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        offerId: uint64
        commitment: uint256
        chanceBps: uint16
        totalPool: coins
        expiresAt: uint32
        acceptance: CellRef<DirectAcceptance>
        holder: CellRef<HolderFeePermit> | null
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: AcceptDirectOffer.toCell(AcceptDirectOffer.create(body)),
            ...extraOptions
        });
    }

    async sendDuelFundReserve(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        amount: coins
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: DuelFundReserve.toCell(DuelFundReserve.create(body)),
            ...extraOptions
        });
    }

    async sendDuelWithdrawSurplus(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        amount: coins
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: DuelWithdrawSurplus.toCell(DuelWithdrawSurplus.create(body)),
            ...extraOptions
        });
    }

    async sendDuelSetFee(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        feeBps: uint16
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: DuelSetFee.toCell(DuelSetFee.create(body)),
            ...extraOptions
        });
    }

    async sendDuelSetTreasury(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        treasury: c.Address
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: DuelSetTreasury.toCell(DuelSetTreasury.create(body)),
            ...extraOptions
        });
    }

    async sendDuelSetOwner(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        owner: c.Address
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: DuelSetOwner.toCell(DuelSetOwner.create(body)),
            ...extraOptions
        });
    }

    async sendBoostDuel(provider: ContractProvider, via: Sender, msgValue: coins, body: {
        queryId: uint64
        duelId: uint64
        offerId: uint64
        amount: coins
        expectedRevision: uint16
        minChanceBps: uint16
        validUntil: uint32
    }, extraOptions?: ExtraSendOptions) {
        return provider.internal(via, {
            value: msgValue,
            body: BoostDuel.toCell(BoostDuel.create(body)),
            ...extraOptions
        });
    }

    async getContractConfig(provider: ContractProvider): Promise<ContractConfigView> {
        const r = StackReader.fromGetMethod(9, await provider.get('contractConfig', []));
        return ({
            $: 'ContractConfigView',
            owner: r.readSlice().loadAddress(),
            treasury: r.readSlice().loadAddress(),
            feeBps: r.readBigInt(),
            networkId: r.readBigInt(),
            inviteSignerPublicKey: r.readBigInt(),
            contractAddress: r.readSlice().loadAddress(),
            paused: r.readBoolean(),
            locked: r.readBigInt(),
            holderFeeSupported: r.readBoolean(),
        });
    }

    async getOfferData(provider: ContractProvider, offerId: uint64): Promise<OfferData> {
        const r = StackReader.fromGetMethod(9, await provider.get('offerData', [
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
            feeExempt: r.readBoolean(),
            direct: r.readCellRef<DirectOfferData>(DirectOfferData.fromSlice),
        });
    }

    async getDuelData(provider: ContractProvider, duelId: uint64): Promise<DuelData> {
        const r = StackReader.fromGetMethod(9, await provider.get('duelData', [
            { type: 'int', value: duelId },
        ]));
        return ({
            $: 'DuelData',
            offerAId: r.readBigInt(),
            offerBId: r.readBigInt(),
            boostDeadline: r.readBigInt(),
            hardDeadline: r.readBigInt(),
            revealDeadline: r.readBigInt(),
            boostRevision: r.readBigInt(),
            secretA: r.readBigInt(),
            secretB: r.readBigInt(),
            revealedMask: r.readBigInt(),
        });
    }

    async getDuelBoostData(provider: ContractProvider, duelId: uint64): Promise<DuelBoostView> {
        const r = StackReader.fromGetMethod(8, await provider.get('duelBoostData', [
            { type: 'int', value: duelId },
        ]));
        return ({
            $: 'DuelBoostView',
            stakeA: r.readBigInt(),
            stakeB: r.readBigInt(),
            chanceABps: r.readBigInt(),
            chanceBBps: r.readBigInt(),
            boostDeadline: r.readBigInt(),
            hardDeadline: r.readBigInt(),
            revealDeadline: r.readBigInt(),
            boostRevision: r.readBigInt(),
        });
    }

    async getDirectOfferData(provider: ContractProvider, offerId: uint64): Promise<DirectOfferData> {
        const r = StackReader.fromGetMethod(2, await provider.get('directOfferData', [
            { type: 'int', value: offerId },
        ]));
        return ({
            $: 'DirectOfferData',
            inviteId: r.readBigInt(),
            opponent: r.readNullable<c.Address>(
                (r) => r.readSlice().loadAddress()
            ),
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

    async getAdminState(provider: ContractProvider): Promise<DuelAdminStateView> {
        const r = StackReader.fromGetMethod(5, await provider.get('adminState', []));
        return ({
            $: 'DuelAdminStateView',
            owner: r.readSlice().loadAddress(),
            treasury: r.readSlice().loadAddress(),
            feeBps: r.readBigInt(),
            paused: r.readBoolean(),
            locked: r.readBigInt(),
        });
    }
}
