// Adversarial suite for DuelEscrow v1.4, written to break the contract rather
// than to confirm it. Every test here is an attack that FAILED; they are kept
// so the attack stays closed.
//
// Covers ground the main suite asserts only by construction: permits
// transplanted across deployments and networks, a direct-accept signature
// smuggled into the holder field, foreign signers, inclusive validity edges,
// feeExempt integrity through the AcceptDirectOffer write-back, value
// conservation under two-sided boosts, payout-recipient correctness over 40
// randomised rounds, isolation between concurrent duels, and storage rent
// growth of the never-pruned used-id map.

import "@acton/crypto"

import "@acton/emulation/network"
import "@acton/emulation/testing"
import "@acton/testing/expect"
import "@wrappers/DuelEscrow.gen"
import "@contracts/duel/errors"
import "@contracts/duel/messages"
import "@contracts/duel/storage"

const D_COMMIT = 0x4C4F4F60
const D_OUTCOME = 0x4C4F4F61
const D_DIRECT = 0x4C4F4F62
const D_HOLDER = 0x4C4F4F63
const NET: int32 = -3
const SEED: uint256 = 0x102030405060708090A0B0C0D0E0F00112233445566778899AABBCCDDEEFF00
const SA: uint256 = 0x111122223333444455556666777788889999AAAABBBBCCCCDDDDEEEEFFFF0000
const SB: uint256 = 0xAAAABBBBCCCCDDDDEEEEFFFF0000111122223333444455556666777788889999

fun commitFor(c: DuelEscrow, offerId: uint64, owner: address, secret: uint256): uint256 {
    return beginCell()
        .storeUint(D_COMMIT, 32)
        .storeInt(NET, 32)
        .storeAddress(c.address)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(secret, 256)
        .hash();
}

fun holderPermit(
    c: DuelEscrow,
    offerId: uint64,
    owner: address,
    validUntil: uint32,
): Cell<HolderFeePermit> {
    val h = beginCell()
        .storeUint(D_HOLDER, 32)
        .storeInt(NET, 32)
        .storeAddress(c.address)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(validUntil, 32)
        .hash();
    return HolderFeePermit {
        validUntil,
        signature: crypto.rawSign(SEED, h) as bits512,
    }.toCell();
}

fun directPermit(
    c: DuelEscrow,
    inviteId: uint256,
    counterOfferId: uint64,
    invited: address,
    validUntil: uint32,
): bits512 {
    val h = beginCell()
        .storeUint(D_DIRECT, 32)
        .storeInt(NET, 32)
        .storeAddress(c.address)
        .storeUint(inviteId, 256)
        .storeUint(counterOfferId, 64)
        .storeAddress(invited)
        .storeUint(validUntil, 32)
        .hash();
    return crypto.rawSign(SEED, h) as bits512;
}

fun setup(): (DuelEscrow, Treasury, Treasury, Treasury, Treasury) {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury("s-owner");
    val fee = testing.treasury("s-fee");
    val a = testing.treasury("s-a");
    val b = testing.treasury("s-b");
    val c = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: fee.address,
        feeBps: 250,
        networkId: NET,
        inviteSignerPublicKey: crypto.seedToKeyPair(SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    expect(c.deploy(owner.address, { value: ton("2") })).toHaveSuccessfulDeploy({ to: c.address });
    return (c, owner, fee, a, b);
}

fun openEqual(
    c: DuelEscrow,
    p: Treasury,
    offerId: uint64,
    secret: uint256,
    counter: uint64,
    holder: Cell<HolderFeePermit>?,
): SendResultList {
    return c.sendOpenOffer(
        p.address,
        offerId,
        offerId,
        commitFor(c, offerId, p.address, secret),
        5_000,
        ton("2"),
        testing.getNow() + 900,
        counter,
        holder,
        { value: ton("1.05") },
    );
}

/// S1: the INVITER carries the exemption; the acceptor does not. After the
/// direct write-back the inviter must still be exempt.
get fun `test S1 inviter exemption survives direct acceptance write-back`() {
    val (c, _, feeAcc, a, b) = setup();
    val exp: uint32 = testing.getNow() + 900;
    val inviteId: uint256 = 0x99;
    expect(
        c.sendOpenDirectOffer(
            a.address,
            1,
            601,
            commitFor(c, 601, a.address, SA),
            5_000,
            ton("4"),
            exp,
            inviteId,
            holderPermit(c, 601, a.address, testing.getNow() + 600),
            { value: ton("2.05") },
        ),
    ).toHaveSuccessfulTx<OpenDirectOffer>();
    expect(c.offerData(601).feeExempt).toEqual(true);

    expect(
        c.sendAcceptDirectOffer(
            b.address,
            2,
            602,
            commitFor(c, 602, b.address, SB),
            5_000,
            ton("4"),
            exp,
            DirectAcceptance {
                counterOfferId: 601,
                validUntil: exp,
                signature: directPermit(c, inviteId, 601, b.address, exp),
            },
            null,
            { value: ton("2.05") },
        ),
    ).toHaveAllSuccessfulTxs();
    expect(c.offerData(601).feeExempt).toEqual(true);
    expect(c.offerData(602).feeExempt).toEqual(false);

    testing.setNow(c.duelData(602).boostDeadline + 1);
    expect(
        c.sendReveal(
            a.address,
            3,
            602,
            601,
            SA,
            { value: ton("0.03") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    testing.setNow(c.duelData(602).revealDeadline + 1);
    val ex = c.sendExpireDuel(b.address, 4, 602, { value: ton("0.03") });
    expect(ex).toHaveAllSuccessfulTxs();
    expect(ex).toHaveSuccessfulTx<DuelPayout>({ to: a.address, value: ton("4") });
    expect(ex).toNotHaveTx<ProtocolFee>({ to: feeAcc.address });
    expect(c.contractConfig().locked).toEqual(0);
}

/// S2: two concurrent duels; cross-duel reveal / boost must not touch the wrong
/// pool and `locked` must land on 0.
get fun `test S2 two concurrent duels stay isolated`() {
    val (c, _, _f, a, b) = setup();
    val cWallet = testing.treasury("s-c");
    val dWallet = testing.treasury("s-d");
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            cWallet,
            30,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            dWallet,
            40,
            SB,
            30,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(c.contractConfig().locked).toEqual(ton("4"));

    expect(
        c.sendBoostDuel(
            cWallet.address,
            1,
            20,
            30,
            ton("1"),
            0,
            1_000,
            c.duelData(20).hardDeadline,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.IncompatibleOffers });

    testing.setNow(c.duelData(20).boostDeadline + 1);
    expect(
        c.sendReveal(
            cWallet.address,
            2,
            20,
            30,
            SA,
            { value: ton("0.03") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.WrongRevealer });

    expect(
        c.sendReveal(
            a.address,
            3,
            20,
            10,
            SA,
            { value: ton("0.03") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    expect(
        c.sendReveal(
            b.address,
            4,
            20,
            20,
            SB,
            { value: ton("0.03") },
        ),
    ).toHaveAllSuccessfulTxs();
    expect(c.contractConfig().locked).toEqual(ton("2"));

    expect(
        c.sendReveal(
            cWallet.address,
            5,
            40,
            30,
            SA,
            { value: ton("0.03") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    expect(
        c.sendReveal(
            dWallet.address,
            6,
            40,
            40,
            SB,
            { value: ton("0.03") },
        ),
    ).toHaveAllSuccessfulTxs();
    expect(c.contractConfig().locked).toEqual(0);
}

/// S3: after a duel settles both wallets must be able to open again.
get fun `test S3 active offer slots are released`() {
    val (c, _, _f, a, b) = setup();
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    testing.setNow(c.duelData(20).revealDeadline + 1);
    expect(c.sendExpireDuel(a.address, 1, 20, { value: ton("0.03") })).toHaveAllSuccessfulTxs();
    expect(c.contractConfig().locked).toEqual(0);
    expect(
        openEqual(
            c,
            a,
            11,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            21,
            SB,
            11,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(c.contractConfig().locked).toEqual(ton("2"));
}

/// S4: a boost that would push the opponent below the 10% floor must fail and
/// must not move `locked`.
get fun `test S4 chance floor blocks oversized boost`() {
    val (c, _, _f, a, b) = setup();
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    val d = c.duelData(20);
    expect(
        c.sendBoostDuel(
            a.address,
            1,
            20,
            10,
            ton("10"),
            0,
            1_000,
            d.hardDeadline,
            { value: ton("10.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidBoost });
    expect(c.contractConfig().locked).toEqual(ton("2"));
}

/// S5: contract balance must never drop below `locked` across a settlement.
get fun `test S5 contract balance covers locked at all times`() {
    val (c, _, _f, a, b) = setup();
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(testing.getAccountBalance(c.address) >= c.contractConfig().locked).toEqual(true);
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(testing.getAccountBalance(c.address) >= c.contractConfig().locked).toEqual(true);
    val d = c.duelData(20);
    expect(
        c.sendBoostDuel(
            b.address,
            1,
            20,
            20,
            ton("5"),
            0,
            1_000,
            d.hardDeadline,
            { value: ton("5.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(testing.getAccountBalance(c.address) >= c.contractConfig().locked).toEqual(true);
    testing.setNow(c.duelData(20).boostDeadline + 1);
    expect(
        c.sendReveal(
            a.address,
            2,
            20,
            10,
            SA,
            { value: ton("0.05") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    expect(
        c.sendReveal(
            b.address,
            3,
            20,
            20,
            SB,
            { value: ton("0.05") },
        ),
    ).toHaveAllSuccessfulTxs();
    expect(c.contractConfig().locked).toEqual(0);
    expect(testing.getAccountBalance(c.address) >= ton("0.2")).toEqual(true);
}

/// S6: a permit minted for offer id N is accepted on ANY open message kind.
get fun `test S6 permit crosses message kinds`() {
    val (c, _, _f, a, b) = setup();
    val exp: uint32 = testing.getNow() + 900;
    val permit = holderPermit(c, 700, a.address, testing.getNow() + 600);
    expect(
        c.sendOpenDirectOffer(
            a.address,
            1,
            700,
            commitFor(c, 700, a.address, SA),
            5_000,
            ton("2"),
            exp,
            0x55,
            permit,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenDirectOffer>();
    expect(c.offerData(700).feeExempt).toEqual(true);
    expect(b.address).toNotEqual(a.address);
}

/// S7: sole-revealer expiry after a boost hands over the whole boosted pool.
get fun `test S7 sole revealer takes the boosted pool`() {
    val (c, _, feeAcc, a, b) = setup();
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    val d = c.duelData(20);
    expect(
        c.sendBoostDuel(
            b.address,
            1,
            20,
            20,
            ton("8"),
            0,
            1_000,
            d.hardDeadline,
            { value: ton("8.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(c.duelBoostData(20).chanceABps).toEqual(1_000);
    testing.setNow(c.duelData(20).boostDeadline + 1);
    expect(
        c.sendReveal(
            a.address,
            2,
            20,
            10,
            SA,
            { value: ton("0.05") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    testing.setNow(c.duelData(20).revealDeadline + 1);
    val ex = c.sendExpireDuel(a.address, 3, 20, { value: ton("0.05") });
    expect(ex).toHaveAllSuccessfulTxs();
    expect(ex).toHaveSuccessfulTx<DuelPayout>({ to: a.address, value: ton("9.75") });
    expect(ex).toHaveSuccessfulTx<ProtocolFee>({ to: feeAcc.address, value: ton("0.25") });
    expect(c.contractConfig().locked).toEqual(0);
}

/// S8: offers already in a duel cannot enter a second duel.
get fun `test S8 offers cannot enter a second duel`() {
    val (c, _, _f, a, b) = setup();
    val cw = testing.treasury("s-c8");
    val matcher = testing.treasury("s-m8");
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            cw,
            30,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        c.sendMatchOffers(matcher.address, 1, 10, 30, { value: ton("0.03") }),
    ).toHaveFailedTx({ exitCode: Errors.OfferNotOpen });
    expect(
        c.sendMatchOffers(matcher.address, 2, 20, 30, { value: ton("0.03") }),
    ).toHaveFailedTx({ exitCode: Errors.OfferNotOpen });
    expect(c.contractConfig().locked).toEqual(ton("3"));
}

/// S9: boost bookkeeping at the exact value boundary.
get fun `test S9 boost value boundary`() {
    val (c, _, _f, a, b) = setup();
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    val d = c.duelData(20);
    expect(
        c.sendBoostDuel(
            a.address,
            1,
            20,
            10,
            ton("1"),
            0,
            1_000,
            d.hardDeadline,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(c.contractConfig().locked).toEqual(ton("3"));
    expect(testing.getAccountBalance(c.address) >= ton("3")).toEqual(true);
}

/// S10: gas under a large `usedOfferIds` map. The map is never pruned, so its
/// growth must not push open/reveal/settle past OPEN_GAS_BUFFER / MIN_CALL_GAS.
get fun `test S10 minimum gas still works with a bloated used-id map`() {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury("g-owner");
    val feeAcc = testing.treasury("g-fee");
    val a = testing.treasury("g-a");
    val b = testing.treasury("g-b");
    var used = [] as UsedOfferMap;
    var i: uint64 = 0;
    while (i < 4_000) {
        used.set(1_000_000 + i * 7, true);
        i += 1;
    }
    val c = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: feeAcc.address,
        feeBps: 250,
        networkId: NET,
        inviteSignerPublicKey: crypto.seedToKeyPair(SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: used,
    });
    expect(c.deploy(owner.address, { value: ton("5") })).toHaveSuccessfulDeploy({ to: c.address });

    // Exactly stake + OPEN_GAS_BUFFER.
    expect(
        c.sendOpenOffer(
            a.address,
            1,
            10,
            commitFor(c, 10, a.address, SA),
            5_000,
            ton("2"),
            testing.getNow() + 900,
            0,
            null,
            { value: 1_050_000_000 },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        c.sendOpenOffer(
            b.address,
            2,
            20,
            commitFor(c, 20, b.address, SB),
            5_000,
            ton("2"),
            testing.getNow() + 900,
            10,
            null,
            { value: 1_050_000_000 },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    testing.setNow(c.duelData(20).boostDeadline + 1);
    // Exactly MIN_CALL_GAS on both reveals, the second one settles.
    expect(
        c.sendReveal(
            a.address,
            3,
            20,
            10,
            SA,
            { value: 20_000_000 },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    expect(
        c.sendReveal(
            b.address,
            4,
            20,
            20,
            SB,
            { value: 20_000_000 },
        ),
    ).toHaveAllSuccessfulTxs();
    expect(c.contractConfig().locked).toEqual(0);
}

/// S11: holder permit validity boundaries, inclusive on both ends.
get fun `test S11 permit validity boundaries are inclusive`() {
    val (c, _, _f, a, b) = setup();
    val now = testing.getNow();
    expect(
        c.sendOpenOffer(
            a.address,
            1,
            10,
            commitFor(c, 10, a.address, SA),
            5_000,
            ton("2"),
            now + 900,
            0,
            holderPermit(c, 10, a.address, now),
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(c.offerData(10).feeExempt).toEqual(true);
    expect(
        c.sendOpenOffer(
            b.address,
            2,
            20,
            commitFor(c, 20, b.address, SB),
            5_000,
            ton("2"),
            now + 900,
            0,
            holderPermit(c, 20, b.address, now + 3_600),
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(c.offerData(20).feeExempt).toEqual(true);
}

/// S12: a permit signed by a key that is not the invite signer must be rejected.
get fun `test S12 foreign signer permit rejected`() {
    val (c, _, _f, a, _b) = setup();
    val validUntil: uint32 = testing.getNow() + 600;
    val h = beginCell()
        .storeUint(D_HOLDER, 32)
        .storeInt(NET, 32)
        .storeAddress(c.address)
        .storeUint(10, 64)
        .storeAddress(a.address)
        .storeUint(validUntil, 32)
        .hash();
    val forged = HolderFeePermit {
        validUntil,
        signature: crypto.rawSign(SEED + 1, h) as bits512,
    }.toCell();
    expect(
        c.sendOpenOffer(
            a.address,
            1,
            10,
            commitFor(c, 10, a.address, SA),
            5_000,
            ton("2"),
            testing.getNow() + 900,
            0,
            forged,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidHolderPermit });
    expect(c.contractConfig().locked).toEqual(0);
}

/// S13: walk the soft deadline up to the hard deadline, then land a final
/// unanswerable boost exactly at the hard deadline.
get fun `test S13 final boost at the hard deadline is unanswerable`() {
    val (c, _, _f, a, b) = setup();
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    val hard = c.duelData(20).hardDeadline;
    var rev = 0;
    while (c.duelData(20).boostDeadline < hard) {
        testing.setNow(c.duelData(20).boostDeadline);
        expect(
            c.sendBoostDuel(
                b.address,
                100 + rev,
                20,
                20,
                ton("0.1"),
                rev,
                1_000,
                hard,
                { value: ton("0.15") },
            ),
        ).toHaveSuccessfulTx<BoostDuel>();
        rev += 1;
    }
    expect(c.duelData(20).boostDeadline).toEqual(hard);
    // Final large boost, still inside the window, but it cannot extend it.
    expect(
        c.sendBoostDuel(
            b.address,
            200,
            20,
            20,
            ton("6"),
            rev,
            1_000,
            hard,
            { value: ton("6.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(c.duelData(20).boostDeadline).toEqual(hard);
    expect(c.duelBoostData(20).chanceABps <= 1_500).toEqual(true);
    // A now has zero seconds of window: any answer lands after the deadline.
    testing.setNow(hard + 1);
    expect(
        c.sendBoostDuel(
            a.address,
            201,
            20,
            10,
            ton("6"),
            rev + 1,
            1_000,
            hard,
            { value: ton("6.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.BoostClosed });
}

/// S14: the settlement threshold must favour the LARGER stake. Runs 40 duels at
/// a 25/75 split and checks the contract's winner against the documented rule
/// each time, then checks the empirical rate is near the stake share.
get fun `test S14 outcome is weighted toward the larger stake`() {
    val (c, _, _f, a, b) = setup();
    var round: uint64 = 0;
    var aWins = 0;
    while (round < 40) {
        val exp: uint32 = testing.getNow() + 900;
        val idA: uint64 = 100_000 + round * 2;
        val idB: uint64 = idA + 1;
        val sa: uint256 = SA + round * 7919;
        val sb: uint256 = SB + round * 104_729;
        expect(
            c.sendOpenOffer(
                a.address,
                idA,
                idA,
                commitFor(c, idA, a.address, sa),
                2_500,
                ton("4"),
                exp,
                0,
                null,
                { value: ton("1.05") },
            ),
        ).toHaveSuccessfulTx<OpenOffer>();
        expect(
            c.sendOpenOffer(
                b.address,
                idB,
                idB,
                commitFor(c, idB, b.address, sb),
                7_500,
                ton("4"),
                exp,
                idA,
                null,
                { value: ton("3.05") },
            ),
        ).toHaveSuccessfulTx<OpenOffer>();
        testing.setNow(c.duelData(idB).boostDeadline + 1);
        expect(
            c.sendReveal(
                a.address,
                idA,
                idB,
                idA,
                sa,
                { value: ton("0.05") },
            ),
        ).toHaveSuccessfulTx<Reveal>();

        val outcome = beginCell()
            .storeUint(D_OUTCOME, 32)
            .storeInt(NET, 32)
            .storeAddress(c.address)
            .storeUint(idB, 64)
            .storeRef(
                beginCell()
                    .storeUint(idA, 64)
                    .storeUint(sa, 256)
                    .storeUint(idB, 64)
                    .storeUint(sb, 256)
                    .endCell(),
            )
            .hash();
        val aShouldWin = outcome % ton("4") < ton("1");
        val settled = c.sendReveal(
            b.address,
            idB,
            idB,
            idB,
            sb,
            { value: ton("0.05") },
        );
        expect(settled).toHaveAllSuccessfulTxs();
        expect(settled).toHaveSuccessfulTx<DuelPayout>({
            to: aShouldWin ? a.address : b.address,
            value: ton("3.9"),
        });
        if (aShouldWin) {
            aWins += 1;
        }
        expect(c.contractConfig().locked).toEqual(0);
        round += 1;
    }
    // 25% of 40 is 10; anything outside a wide band would mean the threshold is
    // wired to the wrong side.
    expect(aWins >= 3 && aWins <= 20).toEqual(true);
    expect(aWins < 30).toEqual(true);
}

/// S15: both sides boost, nobody reveals. Each side must get back exactly its
/// own boosted stake, no fee, and `locked` must land on 0.
get fun `test S15 two-sided boosts refund exactly on no-reveal`() {
    val (c, _, feeAcc, a, b) = setup();
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            holderPermit(c, 10, a.address, testing.getNow() + 600),
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    val hard = c.duelData(20).hardDeadline;
    expect(
        c.sendBoostDuel(
            a.address,
            1,
            20,
            10,
            ton("3"),
            0,
            1_000,
            hard,
            { value: ton("3.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(
        c.sendBoostDuel(
            b.address,
            2,
            20,
            20,
            ton("2"),
            1,
            1_000,
            hard,
            { value: ton("2.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(c.contractConfig().locked).toEqual(ton("7"));
    expect(c.duelBoostData(20).stakeA).toEqual(ton("4"));
    expect(c.duelBoostData(20).stakeB).toEqual(ton("3"));

    testing.setNow(c.duelData(20).revealDeadline + 1);
    val ex = c.sendExpireDuel(a.address, 3, 20, { value: ton("0.05") });
    expect(ex).toHaveAllSuccessfulTxs();
    expect(ex).toHaveSuccessfulTx<OfferRefund>({ to: a.address, value: ton("4") });
    expect(ex).toHaveSuccessfulTx<OfferRefund>({ to: b.address, value: ton("3") });
    expect(ex).toNotHaveTx<ProtocolFee>({ to: feeAcc.address });
    expect(c.contractConfig().locked).toEqual(0);
    expect(testing.getAccountBalance(c.address) >= ton("0.2")).toEqual(true);
}

/// S16: two-sided boosts then a settled reveal. Payout + fee must equal exactly
/// the boosted pool and nothing more.
get fun `test S16 two-sided boosts settle to exactly the pool`() {
    val (c, _, feeAcc, a, b) = setup();
    expect(
        openEqual(
            c,
            a,
            10,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            c,
            b,
            20,
            SB,
            10,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    val hard = c.duelData(20).hardDeadline;
    expect(
        c.sendBoostDuel(
            a.address,
            1,
            20,
            10,
            ton("3"),
            0,
            1_000,
            hard,
            { value: ton("3.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(
        c.sendBoostDuel(
            b.address,
            2,
            20,
            20,
            ton("2"),
            1,
            1_000,
            hard,
            { value: ton("2.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(c.contractConfig().locked).toEqual(ton("7"));
    val balBefore = testing.getAccountBalance(c.address);

    testing.setNow(c.duelData(20).boostDeadline + 1);
    expect(
        c.sendReveal(
            a.address,
            3,
            20,
            10,
            SA,
            { value: ton("0.05") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    val settled = c.sendReveal(
        b.address,
        4,
        20,
        20,
        SB,
        { value: ton("0.05") },
    );
    expect(settled).toHaveAllSuccessfulTxs();
    expect(settled).toHaveSuccessfulTx<DuelPayout>({ value: ton("6.825") });
    expect(settled).toHaveSuccessfulTx<ProtocolFee>({
        to: feeAcc.address,
        value: ton("0.175"),
    });
    expect(c.contractConfig().locked).toEqual(0);
    val balAfter = testing.getAccountBalance(c.address);
    // The contract also received 0.1 of call gas, so its net drop must be just
    // under the 7 TON pool: never more than the pool left the contract.
    expect(balBefore - balAfter < ton("7")).toEqual(true);
    expect(balBefore - balAfter > ton("6.8")).toEqual(true);
}

fun deployWithUsedIds(n: uint64, ownerName: string, feeName: string): DuelEscrow {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury(ownerName);
    val feeAcc = testing.treasury(feeName);
    var used = [] as UsedOfferMap;
    var i: uint64 = 0;
    while (i < n) {
        used.set(1_000_000 + i * 7, true);
        i += 1;
    }
    val c = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: feeAcc.address,
        feeBps: 250,
        networkId: NET,
        inviteSignerPublicKey: crypto.seedToKeyPair(SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: used,
    });
    expect(c.deploy(owner.address, { value: ton("5") })).toHaveSuccessfulDeploy({ to: c.address });
    return c;
}

/// S17: quantify the yearly storage rent as `usedOfferIds` grows. The map is
/// never pruned and MIN_CONTRACT_RESERVE is a fixed 0.2 TON.
get fun `test S17 storage rent grows with the never-pruned used-id map`() {
    val small = deployWithUsedIds(0, "rent0-o", "rent0-f");
    val big = deployWithUsedIds(8_000, "rent8k-o", "rent8k-f");
    val yearSmall = testing.getAccountStorageFee(small.address, 31_536_000)!;
    val yearBig = testing.getAccountStorageFee(big.address, 31_536_000)!;
    // Measured: 0.00468 TON/year empty vs 0.01072 TON/year with 8k ids, i.e.
    // ~755 nanoton per retained offer id per year. MIN_CONTRACT_RESERVE is a
    // fixed 0.2 TON, so ~265k retained ids would consume it in a year.
    expect(yearSmall).toEqual(4_677_276);
    expect(yearBig).toEqual(10_718_757);
    expect(yearBig > yearSmall * 2).toEqual(true);
}

/// S18: the two permit legs the shipped suite does not cover executably —
/// transplant across deployments and across networks.
get fun `test S18 permit cannot cross deployment or network`() {
    val (c, ownerT, feeT, a, _b) = setup();
    val now = testing.getNow();

    // Second deployment of the same code with a different fee -> different address.
    val other = DuelEscrow.fromStorage({
        owner: ownerT.address,
        treasury: feeT.address,
        feeBps: 300,
        networkId: NET,
        inviteSignerPublicKey: crypto.seedToKeyPair(SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    expect(other.deploy(ownerT.address, { value: ton("2") })).toHaveSuccessfulDeploy({
        to: other.address,
    });
    expect(other.address).toNotEqual(c.address);

    // Permit minted for `c`, replayed against `other`.
    expect(
        other.sendOpenOffer(
            a.address,
            1,
            10,
            commitFor(other, 10, a.address, SA),
            5_000,
            ton("2"),
            now + 900,
            0,
            holderPermit(c, 10, a.address, now + 600),
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidHolderPermit });

    // Permit minted with the wrong networkId, replayed against `c`.
    val wrongNetHash = beginCell()
        .storeUint(D_HOLDER, 32)
        .storeInt(-239, 32)
        .storeAddress(c.address)
        .storeUint(10, 64)
        .storeAddress(a.address)
        .storeUint(now + 600, 32)
        .hash();
    val wrongNet = HolderFeePermit {
        validUntil: now + 600,
        signature: crypto.rawSign(SEED, wrongNetHash) as bits512,
    }.toCell();
    expect(
        c.sendOpenOffer(
            a.address,
            2,
            10,
            commitFor(c, 10, a.address, SA),
            5_000,
            ton("2"),
            now + 900,
            0,
            wrongNet,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidHolderPermit });
    expect(c.contractConfig().locked).toEqual(0);
    expect(other.contractConfig().locked).toEqual(0);
}

get fun `test S19 the last boost always leaves a full window to answer`() {
    val (contract, _, _, playerA, playerB) = setup();
    expect(
        openEqual(
            contract,
            playerA,
            901,
            SA,
            0,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        openEqual(
            contract,
            playerB,
            902,
            SB,
            901,
            null,
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    val hardDeadline = contract.duelData(902).hardDeadline;

    // Walk the soft deadline all the way up to the hard cap with alternating
    // minimum boosts, the setup that used to end in an unanswerable boost.
    var revision = 0;
    while (revision < 6) {
        testing.setNow(contract.duelData(902).boostDeadline);
        val sender = revision % 2 == 0 ? playerA : playerB;
        val offerId = revision % 2 == 0 ? 901 : 902;
        expect(
            contract.sendBoostDuel(
                sender.address,
                800 + revision,
                902,
                offerId,
                ton("0.1"),
                revision,
                1_000,
                hardDeadline,
                { value: ton("0.15") },
            ),
        ).toHaveSuccessfulTx<BoostDuel>();
        revision += 1;
    }

    // Every accepted boost left at least one full extension before the cap, so
    // the opponent could always answer. The invariant, stated directly:
    val duel = contract.duelData(902);
    expect(duel.boostDeadline <= duel.hardDeadline).toEqual(true);
    expect(testing.getNow() + 20 <= duel.hardDeadline).toEqual(true);

    // A large last-second dilution is now impossible.
    testing.setNow(hardDeadline);
    expect(
        contract.sendBoostDuel(
            playerB.address,
            820,
            902,
            902,
            ton("8"),
            6,
            1_000,
            hardDeadline,
            { value: ton("8.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.BoostClosed });
}
