// Property tests for DuelEscrow, run over randomised inputs.
//
// The other suites assert behaviour at points a human chose. These assert
// invariants that must hold for every input the contract accepts, which is the
// class of bug that hand-picked cases miss: an unlucky combination of stake,
// chance, boost size and timing rather than a wrong branch.
//
// Every property below is about value, because value is what cannot be
// recovered if it is wrong.

import "@acton/crypto"
import "@acton/emulation/network"
import "@acton/emulation/testing"
import "@acton/testing/expect"
import "@acton/testing/fuzz"
import "@wrappers/DuelEscrow.gen"
import "@contracts/duel/errors"
import "@contracts/duel/messages"
import "@contracts/duel/storage"

const P_COMMIT = 0x4C4F4F60
const P_NET: int32 = -3
const P_SEED: uint256 = 0x102030405060708090A0B0C0D0E0F00112233445566778899AABBCCDDEEFF00
const P_SA: uint256 = 0x1111222233334444555566667777888899990000AAAABBBBCCCCDDDDEEEEFFFF
const P_SB: uint256 = 0xFFFFEEEEDDDDCCCCBBBBAAAA00009999888877776666555544443333222211

fun commitment(c: DuelEscrow, offerId: uint64, owner: address, secret: uint256): uint256 {
    return beginCell()
        .storeUint(P_COMMIT, 32)
        .storeInt(P_NET, 32)
        .storeAddress(c.address)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(secret, 256)
        .hash();
}

fun freshDuel(feeBps: uint16): (DuelEscrow, Treasury, Treasury, Treasury) {
    testing.setNow(1_900_000_000);
    val owner = testing.treasury("prop-owner");
    val treasury = testing.treasury("prop-treasury");
    val a = testing.treasury("prop-a");
    val b = testing.treasury("prop-b");
    val c = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: treasury.address,
        feeBps,
        networkId: P_NET,
        inviteSignerPublicKey: crypto.seedToKeyPair(P_SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    expect(c.deploy(owner.address, { value: ton("2") })).toHaveSuccessfulDeploy();
    return (c, treasury, a, b);
}

/// Opens a matched equal pair for an arbitrary legal pool.
fun openPair(c: DuelEscrow, a: Treasury, b: Treasury, pool: coins): void {
    val expiresAt: uint32 = testing.getNow() + 900;
    val stake = pool / 2;
    expect(
        c.sendOpenOffer(
            a.address,
            11,
            11,
            commitment(c, 11, a.address, P_SA),
            5_000,
            pool,
            expiresAt,
            0,
            null,
            { value: stake + ton("0.06") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        c.sendOpenOffer(
            b.address,
            12,
            12,
            commitment(c, 12, b.address, P_SB),
            5_000,
            pool,
            expiresAt,
            11,
            null,
            { value: stake + ton("0.06") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
}

/// The contract must never owe more than it holds. Checked across an arbitrary
/// pool and an arbitrary boost, at every step of the duel.
@test.fuzz(48)
get fun `test locked value never exceeds the contract balance`(rawPool: int, rawBoost: int) {
    val pool = fuzz.bound(rawPool, 1, 25) * ton("1") * 4 / 4;
    val boost = fuzz.bound(rawBoost, 1, 40) * ton("0.1");
    val (c, _, a, b) = freshDuel(250);
    openPair(c, a, b, pool);
    expect(c.contractConfig().locked <= testing.getAccountBalance(c.address)).toEqual(true);

    c.sendBoostDuel(
        a.address,
        21,
        12,
        11,
        boost,
        0,
        1_000,
        c.duelData(12).hardDeadline,
        { value: boost + ton("0.06") },
    );
    // A boost either applies or is refused; either way the contract may never
    // report more locked value than it actually holds.
    expect(c.contractConfig().locked <= testing.getAccountBalance(c.address)).toEqual(true);
    val view = c.duelBoostData(12);
    expect(view.stakeA + view.stakeB).toEqual(c.contractConfig().locked);
}

/// Whatever the pool and the fee, a settled duel releases exactly the pool:
/// payout plus fee, never more, never less, and locked returns to zero.
@test.fuzz(48)
get fun `test settlement conserves the pool exactly`(rawPool: int, rawFee: int) {
    val pool = fuzz.bound(rawPool, 1, 25) * ton("1");
    val feeBps = fuzz.bound(rawFee, 0, 1_000) as uint16;
    val (c, treasury, a, b) = freshDuel(feeBps);
    openPair(c, a, b, pool);
    val locked = c.contractConfig().locked;
    expect(locked).toEqual(pool);

    testing.setNow(c.duelData(12).boostDeadline + 1);
    expect(
        c.sendReveal(
            a.address,
            31,
            12,
            11,
            P_SA,
            { value: ton("0.03") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    val settled = c.sendReveal(
        b.address,
        32,
        12,
        12,
        P_SB,
        { value: ton("0.03") },
    );
    expect(settled).toHaveAllSuccessfulTxs();

    val fee = mulDivFloor(pool, feeBps, 10_000);
    expect(settled).toHaveSuccessfulTx<DuelPayout>({ value: pool - fee });
    if (fee > 0) {
        expect(settled).toHaveSuccessfulTx<ProtocolFee>({
            to: treasury.address,
            value: fee,
        });
    }
    expect(c.contractConfig().locked).toEqual(0);
}

/// No-reveal recovery must return each side exactly what it put in, for any
/// pool. Losing a nanogram here would be silent theft.
@test.fuzz(32)
get fun `test no-reveal refunds return each stake untouched`(rawPool: int) {
    val pool = fuzz.bound(rawPool, 1, 25) * ton("1");
    val (c, _, a, b) = freshDuel(250);
    openPair(c, a, b, pool);

    testing.setNow(c.duelData(12).revealDeadline + 1);
    val expired = c.sendExpireDuel(a.address, 41, 12, { value: ton("0.03") });
    expect(expired).toHaveAllSuccessfulTxs();
    expect(expired).toHaveSuccessfulTx<OfferRefund>({ to: a.address, value: pool / 2 });
    expect(expired).toHaveSuccessfulTx<OfferRefund>({ to: b.address, value: pool / 2 });
    expect(c.contractConfig().locked).toEqual(0);
}

/// Chance is the stake share, and both sides must always sum to the whole.
/// A rounding gap here would quietly bias every duel.
@test.fuzz(48)
get fun `test boosted chances always sum to the full range`(rawPool: int, rawBoost: int) {
    val pool = fuzz.bound(rawPool, 2, 25) * ton("1");
    val boost = fuzz.bound(rawBoost, 1, 30) * ton("0.1");
    val (c, _, a, b) = freshDuel(250);
    openPair(c, a, b, pool);

    val boosted = c.sendBoostDuel(
        a.address,
        51,
        12,
        11,
        boost,
        0,
        1_000,
        c.duelData(12).hardDeadline,
        { value: boost + ton("0.06") },
    );
    fuzz.assume(c.contractConfig().locked == pool + boost);

    val view = c.duelBoostData(12);
    expect(view.chanceABps + view.chanceBBps).toEqual(10_000);
    expect(view.stakeA + view.stakeB).toEqual(pool + boost);
    expect(c.contractConfig().locked).toEqual(pool + boost);
}
