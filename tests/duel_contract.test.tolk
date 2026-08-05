import "@acton/crypto"

import "@acton/emulation/network"
import "@acton/emulation/testing"
import "@acton/testing/expect"
import "@wrappers/DuelEscrow.gen"
import "@contracts/duel/errors"
import "@contracts/duel/messages"
import "@contracts/duel/storage"

const TEST_COMMITMENT_DOMAIN = 0x4C4F4F60
const TEST_OUTCOME_DOMAIN = 0x4C4F4F61
const TEST_DIRECT_ACCEPT_DOMAIN = 0x4C4F4F62
const TEST_NETWORK_ID: int32 = -3
const INVITE_SIGNER_SEED: uint256 = 0x102030405060708090A0B0C0D0E0F00112233445566778899AABBCCDDEEFF00
const OFFER_A_ID: uint64 = 101
const OFFER_B_ID: uint64 = 202
const SECRET_A: uint256 = 0x111122223333444455556666777788889999AAAABBBBCCCCDDDDEEEEFFFF0000
const SECRET_B: uint256 = 0xAAAABBBBCCCCDDDDEEEEFFFF0000111122223333444455556666777788889999
const PYTHON_VECTOR_PUBLIC_KEY: uint256 = 0x42A8ADA72BBD29EC106CC16AACA1B6D6D572962F7B8DE922C295B30B5594BFFD
const PYTHON_VECTOR_HASH: uint256 = 0x5D356A032E13417B1460166493548C3F6013AFF54E8DE5BDCCD6AFFB284C3474
const PYTHON_VECTOR_SIGNATURE_HIGH: uint256 = 0xA32ABEFA46F5DFB000B08FDCCF2AD643F162FA244FBC5041C33BF7E87C57E98F
const PYTHON_VECTOR_SIGNATURE_LOW: uint256 = 0x48CC2794CEE98FDCDF4C2EA5A58C9A41837227309872CFA2A6DC107DCAEE840A

fun commitmentForContext(
    contractAddress: address,
    networkId: int32,
    offerId: uint64,
    owner: address,
    secret: uint256,
): uint256 {
    return beginCell()
        .storeUint(TEST_COMMITMENT_DOMAIN, 32)
        .storeInt(networkId, 32)
        .storeAddress(contractAddress)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(secret, 256)
        .hash();
}

fun testCommitment(
    contract: DuelEscrow,
    offerId: uint64,
    owner: address,
    secret: uint256,
): uint256 {
    return commitmentForContext(contract.address, TEST_NETWORK_ID, offerId, owner, secret);
}

fun testDirectPermit(
    contract: DuelEscrow,
    inviteId: uint256,
    counterOfferId: uint64,
    invitedAddress: address,
    validUntil: uint32,
): bits512 {
    val permitHash = beginCell()
        .storeUint(TEST_DIRECT_ACCEPT_DOMAIN, 32)
        .storeInt(TEST_NETWORK_ID, 32)
        .storeAddress(contract.address)
        .storeUint(inviteId, 256)
        .storeUint(counterOfferId, 64)
        .storeAddress(invitedAddress)
        .storeUint(validUntil, 32)
        .hash();
    return crypto.rawSign(INVITE_SIGNER_SEED, permitHash) as bits512;
}

fun storedOffer(
    owner: address,
    commitment: uint256,
    chanceBps: uint16,
    totalPool: coins,
    expiresAt: uint32,
    state: uint8,
    direct: DirectOfferData,
): Cell<OfferData> {
    return OfferData {
        owner,
        commitment,
        chanceBps,
        totalPool,
        stake: mulDivFloor(totalPool, chanceBps, 10_000),
        expiresAt,
        state,
        feeExempt: false,
        direct: direct.toCell(),
    }.toCell();
}

const TEST_HOLDER_FEE_DOMAIN = 0x4C4F4F63

fun testHolderPermitHash(
    contract: DuelEscrow,
    offerId: uint64,
    owner: address,
    validUntil: uint32,
): uint256 {
    return beginCell()
        .storeUint(TEST_HOLDER_FEE_DOMAIN, 32)
        .storeInt(TEST_NETWORK_ID, 32)
        .storeAddress(contract.address)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(validUntil, 32)
        .hash();
}

fun testHolderPermit(
    contract: DuelEscrow,
    offerId: uint64,
    owner: address,
    validUntil: uint32,
): Cell<HolderFeePermit> {
    return HolderFeePermit {
        validUntil,
        signature: crypto.rawSign(
            INVITE_SIGNER_SEED,
            testHolderPermitHash(contract, offerId, owner, validUntil),
        ) as bits512,
    }.toCell();
}

fun deployStoredDuel(
    owner: Treasury,
    treasury: Treasury,
    feeBps: uint16,
    paused: bool,
    locked: coins,
    offers: OfferMap,
    duels: DuelMap,
    activeOffers: ActiveOfferMap,
    usedOfferIds: UsedOfferMap,
): DuelEscrow {
    val contract = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: treasury.address,
        feeBps,
        networkId: TEST_NETWORK_ID,
        inviteSignerPublicKey: crypto.seedToKeyPair(INVITE_SIGNER_SEED).publicKey,
        paused,
        locked,
        offers,
        duels,
        activeOffers,
        usedOfferIds,
    });
    expect(contract.deploy(owner.address, { value: ton("2") })).toHaveSuccessfulDeploy({
        to: contract.address,
    });
    return contract;
}

get fun `test Python permit encoding and signature match Tolk`() {
    val permitHash = beginCell()
        .storeUint(TEST_DIRECT_ACCEPT_DOMAIN, 32)
        .storeInt(TEST_NETWORK_ID, 32)
        .storeAddress(address("0:1111111111111111111111111111111111111111111111111111111111111111"))
        .storeUint(
            0x2222222222222222222222222222222222222222222222222222222222222222,
            256,
        )
        .storeUint(77, 64)
        .storeAddress(address("0:3333333333333333333333333333333333333333333333333333333333333333"))
        .storeUint(2_000_000_000, 32)
        .hash();
    expect(permitHash).toEqual(PYTHON_VECTOR_HASH);
    val signature = beginCell()
        .storeUint(PYTHON_VECTOR_SIGNATURE_HIGH, 256)
        .storeUint(PYTHON_VECTOR_SIGNATURE_LOW, 256)
        .endCell()
        .beginParse();
    expect(
        isSignatureValid(
            permitHash,
            signature,
            PYTHON_VECTOR_PUBLIC_KEY,
        ),
    ).toEqual(true);
}

fun openPair(contract: DuelEscrow, playerA: Treasury, playerB: Treasury): void {
    val expiresAt: uint32 = testing.getNow() + 900;
    val first = contract.sendOpenOffer(
        playerA.address,
        OFFER_A_ID,
        OFFER_A_ID,
        testCommitment(contract, OFFER_A_ID, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("1.05") },
    );
    expect(first).toHaveSuccessfulTx<OpenOffer>({
        from: playerA.address,
        to: contract.address,
    });

    val second = contract.sendOpenOffer(
        playerB.address,
        OFFER_B_ID,
        OFFER_B_ID,
        testCommitment(contract, OFFER_B_ID, playerB.address, SECRET_B),
        7_500,
        ton("4"),
        expiresAt,
        OFFER_A_ID,
        null,
        { value: ton("3.05") },
    );
    expect(second).toHaveSuccessfulTx<OpenOffer>({
        from: playerB.address,
        to: contract.address,
    });
}

fun openEqualPair(contract: DuelEscrow, playerA: Treasury, playerB: Treasury): void {
    val expiresAt: uint32 = testing.getNow() + 900;
    expect(
        contract.sendOpenOffer(
            playerA.address,
            OFFER_A_ID,
            OFFER_A_ID,
            testCommitment(contract, OFFER_A_ID, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendOpenOffer(
            playerB.address,
            OFFER_B_ID,
            OFFER_B_ID,
            testCommitment(contract, OFFER_B_ID, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            OFFER_A_ID,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
}

fun openEqualPairWithIds(
    contract: DuelEscrow,
    playerA: Treasury,
    playerB: Treasury,
    firstOfferId: uint64,
    secondOfferId: uint64,
): void {
    val expiresAt: uint32 = testing.getNow() + 900;
    expect(
        contract.sendOpenOffer(
            playerA.address,
            firstOfferId,
            firstOfferId,
            testCommitment(contract, firstOfferId, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendOpenOffer(
            playerB.address,
            secondOfferId,
            secondOfferId,
            testCommitment(contract, secondOfferId, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            firstOfferId,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
}

fun advancePastBoost(contract: DuelEscrow, duelId: uint64): void {
    testing.setNow(contract.duelData(duelId).boostDeadline + 1);
}

fun advancePastReveal(contract: DuelEscrow, duelId: uint64): void {
    testing.setNow(contract.duelData(duelId).revealDeadline + 1);
}

get fun `test opens and canonically matches complementary offers`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    openPair(contract, playerA, playerB);

    val offerA = contract.offerData(OFFER_A_ID);
    val offerB = contract.offerData(OFFER_B_ID);
    val duel = contract.duelData(OFFER_B_ID);
    expect(offerA.owner).toEqual(playerA.address);
    expect(offerA.state).toEqual(OFFER_MATCHED);
    expect(offerB.owner).toEqual(playerB.address);
    expect(offerB.state).toEqual(OFFER_MATCHED);
    expect(duel.offerAId).toEqual(OFFER_A_ID);
    expect(duel.offerBId).toEqual(OFFER_B_ID);
    expect(contract.contractConfig().locked).toEqual(ton("4"));
}

get fun `test matched DUEL opens a bounded boost window before either reveal`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val matchedAt = testing.getNow();
    openEqualPair(contract, playerA, playerB);
    val duel = contract.duelData(OFFER_B_ID);

    expect(duel.boostDeadline).toEqual(matchedAt + 60);
    expect(duel.hardDeadline).toEqual(matchedAt + 180);
    expect(duel.revealDeadline).toEqual(matchedAt + 360);
    expect(duel.boostRevision).toEqual(0);
    expect(
        contract.sendReveal(
            playerA.address,
            290,
            OFFER_B_ID,
            OFFER_A_ID,
            SECRET_A,
            { value: ton("0.03") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.RevealNotOpen });
}

get fun `test confirmed boosts move chance by stake share and extend only the soft deadline`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    openEqualPair(contract, playerA, playerB);
    val initial = contract.duelData(OFFER_B_ID);
    testing.setNow(initial.boostDeadline - 5);

    expect(
        contract.sendBoostDuel(
            playerA.address,
            291,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("1"),
            0,
            6_600,
            initial.hardDeadline,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();

    val boosted = contract.duelBoostData(OFFER_B_ID);
    expect(boosted.stakeA).toEqual(ton("2"));
    expect(boosted.stakeB).toEqual(ton("1"));
    expect(boosted.chanceABps).toEqual(6_666);
    expect(boosted.chanceBBps).toEqual(3_334);
    expect(boosted.boostDeadline).toEqual(testing.getNow() + 20);
    expect(boosted.hardDeadline).toEqual(initial.hardDeadline);
    expect(boosted.revealDeadline).toEqual(boosted.boostDeadline + 300);
    expect(boosted.boostRevision).toEqual(1);
    expect(contract.contractConfig().locked).toEqual(ton("3"));

    expect(
        contract.sendBoostDuel(
            playerB.address,
            292,
            OFFER_B_ID,
            OFFER_B_ID,
            ton("1"),
            0,
            5_000,
            initial.hardDeadline,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.StaleBoost });
    expect(contract.contractConfig().locked).toEqual(ton("3"));
}

get fun `test boost boundaries reject dust stale ownership expiry and chance above ninety percent`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val attacker = testing.treasury("boost-attacker");
    openEqualPair(contract, playerA, playerB);
    val duel = contract.duelData(OFFER_B_ID);

    expect(
        contract.sendBoostDuel(
            attacker.address,
            293,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            0,
            5_000,
            duel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.NotOwner });
    expect(
        contract.sendBoostDuel(
            playerA.address,
            294,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.099999999"),
            0,
            5_000,
            duel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidBoost });
    expect(
        contract.sendBoostDuel(
            playerA.address,
            295,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("8"),
            0,
            9_000,
            duel.hardDeadline,
            { value: ton("8.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(contract.duelBoostData(OFFER_B_ID).chanceABps).toEqual(9_000);
    expect(
        contract.sendBoostDuel(
            playerA.address,
            296,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            1,
            9_000,
            duel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidBoost });

    testing.setNow(duel.boostDeadline + 1);
    expect(
        contract.sendBoostDuel(
            playerB.address,
            297,
            OFFER_B_ID,
            OFFER_B_ID,
            ton("0.1"),
            1,
            1_000,
            duel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.BoostClosed });
}

get fun `test boost security guards fail with their exact reason`() {
    val (contract, owner, _, playerA, playerB) = setupTest();
    openEqualPair(contract, playerA, playerB);
    val duel = contract.duelData(OFFER_B_ID);

    expect(
        contract.sendSetPaused(owner.address, 298, true, { value: ton("0.02") }),
    ).toHaveSuccessfulTx<SetPaused>();
    expect(
        contract.sendBoostDuel(
            playerA.address,
            299,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            0,
            5_000,
            duel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.Paused });
    expect(
        contract.sendSetPaused(owner.address, 300, false, { value: ton("0.02") }),
    ).toHaveSuccessfulTx<SetPaused>();

    expect(
        contract.sendBoostDuel(
            playerA.address,
            301,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            0,
            5_000,
            testing.getNow() - 1,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidExpiry });
    expect(
        contract.sendBoostDuel(
            playerA.address,
            302,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            0,
            5_000,
            duel.hardDeadline + 1,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidExpiry });
    expect(
        contract.sendBoostDuel(
            playerA.address,
            303,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            0,
            5_000,
            duel.hardDeadline,
            { value: ton("0.149999999") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(
        contract.sendBoostDuel(
            playerA.address,
            304,
            OFFER_B_ID,
            999,
            ton("0.1"),
            0,
            5_000,
            duel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.IncompatibleOffers });
    expect(
        contract.sendBoostDuel(
            playerA.address,
            305,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            0,
            6_000,
            duel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidBoost });
}

get fun `test an early boost accepts exact validity without shrinking the window`() {
    val (early, _, _, earlyA, earlyB) = setupTest();
    openEqualPair(early, earlyA, earlyB);
    val initial = early.duelData(OFFER_B_ID);
    expect(
        early.sendBoostDuel(
            earlyB.address,
            306,
            OFFER_B_ID,
            OFFER_B_ID,
            ton("0.1"),
            0,
            5_200,
            testing.getNow(),
            { value: ton("0.15") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(early.duelData(OFFER_B_ID).boostDeadline).toEqual(initial.boostDeadline);
    expect(early.duelBoostData(OFFER_B_ID).stakeB).toEqual(ton("1.1"));
}

get fun `test boost and reveal enforce the exact hard deadline`() {
    val (hard, _, _, playerA, playerB) = setupTest();
    openEqualPair(hard, playerA, playerB);
    val hardDeadline = hard.duelData(OFFER_B_ID).hardDeadline;
    var revision = 0;
    while (revision < 6) {
        val current = hard.duelData(OFFER_B_ID);
        testing.setNow(current.boostDeadline);
        val sender = revision % 2 == 0 ? playerA : playerB;
        val offerId = revision % 2 == 0 ? OFFER_A_ID : OFFER_B_ID;
        expect(
            hard.sendBoostDuel(
                sender.address,
                310 + revision,
                OFFER_B_ID,
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
    // The soft deadline has now been walked to exactly one extension short of
    // the hard cap: this is the last moment a boost can still leave the
    // opponent a full window to answer in.
    expect(testing.getNow()).toEqual(hardDeadline - 20);
    expect(hard.duelData(OFFER_B_ID).boostRevision).toEqual(6);

    // One second later no boost can be answered, so none is accepted. Without
    // this the final boost would land in the same second the window shuts.
    testing.setNow(hardDeadline - 19);
    expect(
        hard.sendBoostDuel(
            playerA.address,
            330,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            6,
            1_000,
            hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.BoostClosed });

    testing.setNow(hardDeadline);
    expect(
        hard.sendBoostDuel(
            playerB.address,
            331,
            OFFER_B_ID,
            OFFER_B_ID,
            ton("0.1"),
            6,
            1_000,
            hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.BoostClosed });

    expect(
        hard.sendReveal(
            playerA.address,
            320,
            OFFER_B_ID,
            OFFER_A_ID,
            SECRET_A,
            { value: ton("0.03") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.RevealNotOpen });
}

get fun `test both chance edges are inclusive`() {
    val (chanceContract, _, _, chanceA, chanceB) = setupTest();
    openEqualPair(chanceContract, chanceA, chanceB);
    val chanceDuel = chanceContract.duelData(OFFER_B_ID);
    expect(
        chanceContract.sendBoostDuel(
            chanceB.address,
            321,
            OFFER_B_ID,
            OFFER_B_ID,
            ton("8"),
            0,
            9_000,
            chanceDuel.hardDeadline,
            { value: ton("8.05") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(chanceContract.duelBoostData(OFFER_B_ID).chanceABps).toEqual(1_000);
    expect(chanceContract.duelBoostData(OFFER_B_ID).chanceBBps).toEqual(9_000);
}

get fun `test maximum boosted pool is inclusive`() {
    val (poolContract, _, _, poolA, poolB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    expect(
        poolContract.sendOpenOffer(
            poolA.address,
            OFFER_A_ID,
            OFFER_A_ID,
            testCommitment(poolContract, OFFER_A_ID, poolA.address, SECRET_A),
            5_000,
            ton("99.9"),
            expiresAt,
            0,
            null,
            { value: ton("50") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        poolContract.sendOpenOffer(
            poolB.address,
            OFFER_B_ID,
            OFFER_B_ID,
            testCommitment(poolContract, OFFER_B_ID, poolB.address, SECRET_B),
            5_000,
            ton("99.9"),
            expiresAt,
            OFFER_A_ID,
            null,
            { value: ton("50") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    val poolDuel = poolContract.duelData(OFFER_B_ID);
    expect(
        poolContract.sendBoostDuel(
            poolA.address,
            322,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            0,
            5_000,
            poolDuel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveSuccessfulTx<BoostDuel>();
    expect(poolContract.offerData(OFFER_A_ID).totalPool).toEqual(ton("100"));
    expect(
        poolContract.sendBoostDuel(
            poolB.address,
            323,
            OFFER_B_ID,
            OFFER_B_ID,
            ton("0.1"),
            1,
            1_000,
            poolDuel.hardDeadline,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidPool });
}

get fun `test boost rejects a corrupted half-matched pair`() {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury("boost-state-owner");
    val treasury = testing.treasury("boost-state-treasury");
    val playerA = testing.treasury("boost-state-a");
    val playerB = testing.treasury("boost-state-b");
    val expiresAt: uint32 = testing.getNow() + 900;
    var offers = [] as OfferMap;
    offers.set(
        OFFER_A_ID,
        storedOffer(
            playerA.address,
            1,
            5_000,
            ton("2"),
            expiresAt,
            OFFER_MATCHED,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    offers.set(
        OFFER_B_ID,
        storedOffer(
            playerB.address,
            2,
            5_000,
            ton("2"),
            expiresAt,
            OFFER_OPEN,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    var duels = [] as DuelMap;
    duels.set(
        OFFER_B_ID,
        DuelData {
            offerAId: OFFER_A_ID,
            offerBId: OFFER_B_ID,
            boostDeadline: testing.getNow() + 60,
            hardDeadline: testing.getNow() + 180,
            revealDeadline: testing.getNow() + 360,
            boostRevision: 0,
            secretA: 0,
            secretB: 0,
            revealedMask: 0,
        }.toCell(),
    );
    var active = [] as ActiveOfferMap;
    active.set(playerA.address, OFFER_A_ID);
    active.set(playerB.address, OFFER_B_ID);
    var used = [] as UsedOfferMap;
    used.set(OFFER_A_ID, true);
    used.set(OFFER_B_ID, true);
    val contract = deployStoredDuel(
        owner,
        treasury,
        250,
        false,
        ton("2"),
        offers,
        duels,
        active,
        used,
    );
    expect(
        contract.sendBoostDuel(
            playerA.address,
            324,
            OFFER_B_ID,
            OFFER_A_ID,
            ton("0.1"),
            0,
            5_000,
            testing.getNow() + 180,
            { value: ton("0.15") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.OfferNotOpen });
}

get fun `test both valid reveals settle once with weighted payout and fee`() {
    val (contract, _, feeCollector, playerA, playerB) = setupTest();
    openPair(contract, playerA, playerB);
    advancePastBoost(contract, OFFER_B_ID);

    val firstReveal = contract.sendReveal(
        playerA.address,
        301,
        OFFER_B_ID,
        OFFER_A_ID,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(firstReveal).toHaveSuccessfulTx<Reveal>({
        from: playerA.address,
        to: contract.address,
    });
    expect(contract.duelData(OFFER_B_ID).revealedMask).toEqual(REVEALED_A);

    val outcome = beginCell()
        .storeUint(TEST_OUTCOME_DOMAIN, 32)
        .storeInt(TEST_NETWORK_ID, 32)
        .storeAddress(contract.address)
        .storeUint(OFFER_B_ID, 64)
        .storeRef(
            beginCell()
                .storeUint(OFFER_A_ID, 64)
                .storeUint(SECRET_A, 256)
                .storeUint(OFFER_B_ID, 64)
                .storeUint(SECRET_B, 256)
                .endCell(),
        )
        .hash();
    val expectedWinner = outcome % ton("4") < ton("1") ? playerA.address : playerB.address;

    val secondReveal = contract.sendReveal(
        playerB.address,
        302,
        OFFER_B_ID,
        OFFER_B_ID,
        SECRET_B,
        { value: ton("0.03") },
    );
    expect(secondReveal).toHaveAllSuccessfulTxs();
    expect(secondReveal).toHaveSuccessfulTx<DuelPayout>({
        from: contract.address,
        to: expectedWinner,
        value: ton("3.9"),
    });
    expect(secondReveal).toHaveSuccessfulTx<ProtocolFee>({
        from: contract.address,
        to: feeCollector.address,
        value: ton("0.1"),
    });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test invalid reveal cannot change duel state`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    openPair(contract, playerA, playerB);
    advancePastBoost(contract, OFFER_B_ID);

    val result = contract.sendReveal(
        playerA.address,
        303,
        OFFER_B_ID,
        OFFER_A_ID,
        SECRET_B,
        { value: ton("0.03") },
    );
    expect(result).toHaveFailedTx({
        from: playerA.address,
        to: contract.address,
        exitCode: Errors.InvalidCommitment,
    });
    expect(contract.duelData(OFFER_B_ID).revealedMask).toEqual(0);
    expect(contract.contractConfig().locked).toEqual(ton("4"));
}

get fun `test sole revealer wins after deadline`() {
    val (contract, _, feeCollector, playerA, playerB) = setupTest();
    openPair(contract, playerA, playerB);
    advancePastBoost(contract, OFFER_B_ID);
    val reveal = contract.sendReveal(
        playerA.address,
        304,
        OFFER_B_ID,
        OFFER_A_ID,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(reveal).toHaveSuccessfulTx<Reveal>();

    testing.setNow(testing.getNow() + 301);
    val expire = contract.sendExpireDuel(
        playerB.address,
        305,
        OFFER_B_ID,
        { value: ton("0.03") },
    );
    expect(expire).toHaveAllSuccessfulTxs();
    expect(expire).toHaveSuccessfulTx<DuelPayout>({
        from: contract.address,
        to: playerA.address,
        value: ton("3.9"),
    });
    expect(expire).toHaveSuccessfulTx<ProtocolFee>({
        from: contract.address,
        to: feeCollector.address,
        value: ton("0.1"),
    });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test no reveals refund both principals after deadline`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    openPair(contract, playerA, playerB);
    advancePastReveal(contract, OFFER_B_ID);

    val expire = contract.sendExpireDuel(
        playerA.address,
        306,
        OFFER_B_ID,
        { value: ton("0.03") },
    );
    expect(expire).toHaveAllSuccessfulTxs();
    expect(expire).toHaveSuccessfulTx<OfferRefund>({
        from: contract.address,
        to: playerA.address,
        value: ton("1"),
    });
    expect(expire).toHaveSuccessfulTx<OfferRefund>({
        from: contract.address,
        to: playerB.address,
        value: ton("3"),
    });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test owner cancellation refunds and offer id remains replay protected`() {
    val (contract, _, _, playerA, _) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val opened = contract.sendOpenOffer(
        playerA.address,
        401,
        401,
        testCommitment(contract, 401, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("1.05") },
    );
    expect(opened).toHaveSuccessfulTx<OpenOffer>();

    val cancelled = contract.sendCancelOffer(
        playerA.address,
        402,
        401,
        { value: ton("0.03") },
    );
    expect(cancelled).toHaveAllSuccessfulTxs();
    expect(cancelled).toHaveSuccessfulTx<OfferRefund>({
        from: contract.address,
        to: playerA.address,
        value: ton("1"),
    });

    // A second wallet confirmation for the same offer must be harmless: the
    // first cancellation removed the offer before sending its only refund.
    val duplicateCancel = contract.sendCancelOffer(
        playerA.address,
        403,
        401,
        { value: ton("0.03") },
    );
    expect(duplicateCancel).toHaveFailedTx({ exitCode: Errors.OfferMissing });
    expect(duplicateCancel).toNotHaveTx<OfferRefund>({
        from: contract.address,
        to: playerA.address,
    });

    val replay = contract.sendOpenOffer(
        playerA.address,
        401,
        401,
        testCommitment(contract, 401, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("1.05") },
    );
    expect(replay).toHaveFailedTx({ exitCode: Errors.OfferAlreadyUsed });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test permissionless expiry refunds an unmatched offer`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 60;
    val opened = contract.sendOpenOffer(
        playerA.address,
        501,
        501,
        testCommitment(contract, 501, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(opened).toHaveSuccessfulTx<OpenOffer>();
    testing.setNow(expiresAt + 1);

    val expired = contract.sendExpireOffer(
        playerB.address,
        502,
        501,
        { value: ton("0.03") },
    );
    expect(expired).toHaveAllSuccessfulTxs();
    expect(expired).toHaveSuccessfulTx<OfferRefund>({
        from: contract.address,
        to: playerA.address,
        value: ton("2"),
    });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test pause blocks new offers but preserves recovery`() {
    val (contract, owner, _, playerA, _) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val opened = contract.sendOpenOffer(
        playerA.address,
        601,
        601,
        testCommitment(contract, 601, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(opened).toHaveSuccessfulTx<OpenOffer>();
    val paused = contract.sendSetPaused(owner.address, 602, true, { value: ton("0.03") });
    expect(paused).toHaveSuccessfulTx<SetPaused>();

    val cancelled = contract.sendCancelOffer(
        playerA.address,
        603,
        601,
        { value: ton("0.03") },
    );
    expect(cancelled).toHaveSuccessfulTx<CancelOffer>();

    val blocked = contract.sendOpenOffer(
        playerA.address,
        604,
        604,
        testCommitment(contract, 604, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(blocked).toHaveFailedTx({ exitCode: Errors.Paused });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test one owner cannot create concurrent offers`() {
    val (contract, _, _, playerA, _) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val first = contract.sendOpenOffer(
        playerA.address,
        701,
        701,
        testCommitment(contract, 701, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(first).toHaveSuccessfulTx<OpenOffer>();
    val second = contract.sendOpenOffer(
        playerA.address,
        702,
        702,
        testCommitment(contract, 702, playerA.address, SECRET_B),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(second).toHaveFailedTx({ exitCode: Errors.OwnerAlreadyActive });
    expect(contract.contractConfig().locked).toEqual(ton("2"));
}

get fun `test operational calls reject dust before spending contract reserve`() {
    val (contract, _, _, playerA, _) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val opened = contract.sendOpenOffer(
        playerA.address,
        801,
        801,
        testCommitment(contract, 801, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(opened).toHaveSuccessfulTx<OpenOffer>();
    val dust = contract.sendCancelOffer(playerA.address, 802, 801, { value: ton("0.01") });
    expect(dust).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(contract.contractConfig().locked).toEqual(ton("2"));
}

get fun `test permissionless matcher cannot alter terms or ordering`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val matcher = testing.treasury("matcher");
    val expiresAt: uint32 = testing.getNow() + 900;
    val first = contract.sendOpenOffer(
        playerA.address,
        901,
        901,
        testCommitment(contract, 901, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("1.05") },
    );
    val second = contract.sendOpenOffer(
        playerB.address,
        902,
        902,
        testCommitment(contract, 902, playerB.address, SECRET_B),
        7_500,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("3.05") },
    );
    expect(first).toHaveSuccessfulTx<OpenOffer>();
    expect(second).toHaveSuccessfulTx<OpenOffer>();

    val matched = contract.sendMatchOffers(
        matcher.address,
        903,
        902,
        901,
        { value: ton("0.03") },
    );
    expect(matched).toHaveSuccessfulTx<MatchOffers>();
    val duel = contract.duelData(902);
    expect(duel.offerAId).toEqual(901);
    expect(duel.offerBId).toEqual(902);
}

get fun `test unauthorized recovery and pause attempts fail`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val opened = contract.sendOpenOffer(
        playerA.address,
        1_001,
        1_001,
        testCommitment(contract, 1_001, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(opened).toHaveSuccessfulTx<OpenOffer>();
    val cancelled = contract.sendCancelOffer(
        playerB.address,
        1_002,
        1_001,
        { value: ton("0.03") },
    );
    expect(cancelled).toHaveFailedTx({ exitCode: Errors.NotOwner });
    val expired = contract.sendExpireOffer(
        playerB.address,
        1_003,
        1_001,
        { value: ton("0.03") },
    );
    expect(expired).toHaveFailedTx({ exitCode: Errors.TooEarly });
    val paused = contract.sendSetPaused(
        playerB.address,
        1_004,
        true,
        { value: ton("0.03") },
    );
    expect(paused).toHaveFailedTx({ exitCode: Errors.NotOwner });
    expect(contract.contractConfig().locked).toEqual(ton("2"));
}

get fun `test reveal sender and replay checks are fail closed`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    openPair(contract, playerA, playerB);
    advancePastBoost(contract, OFFER_B_ID);
    val impersonation = contract.sendReveal(
        playerB.address,
        1_101,
        OFFER_B_ID,
        OFFER_A_ID,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(impersonation).toHaveFailedTx({ exitCode: Errors.WrongRevealer });

    val reveal = contract.sendReveal(
        playerA.address,
        1_102,
        OFFER_B_ID,
        OFFER_A_ID,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(reveal).toHaveSuccessfulTx<Reveal>();
    val replay = contract.sendReveal(
        playerA.address,
        1_103,
        OFFER_B_ID,
        OFFER_A_ID,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(replay).toHaveFailedTx({ exitCode: Errors.AlreadyRevealed });
    expect(contract.duelData(OFFER_B_ID).revealedMask).toEqual(REVEALED_A);
}

get fun `test malformed offers and unsafe deployment fee cannot lock value`() {
    val (contract, owner, feeCollector, playerA, _) = setupTest();
    val unsafeContract = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: feeCollector.address,
        feeBps: 1_001,
        networkId: TEST_NETWORK_ID,
        inviteSignerPublicKey: crypto.seedToKeyPair(INVITE_SIGNER_SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    val deployed = unsafeContract.deploy(owner.address, { value: ton("1") });
    expect(deployed).toHaveSuccessfulDeploy({ to: unsafeContract.address });
    val expiresAt: uint32 = testing.getNow() + 900;
    val unsafeFee = unsafeContract.sendOpenOffer(
        playerA.address,
        1_201,
        1_201,
        testCommitment(unsafeContract, 1_201, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(unsafeFee).toHaveFailedTx({ exitCode: Errors.InvalidFee });

    val invalidChance = contract.sendOpenOffer(
        playerA.address,
        1_202,
        1_202,
        testCommitment(contract, 1_202, playerA.address, SECRET_A),
        3_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(invalidChance).toHaveFailedTx({ exitCode: Errors.InvalidChance });
    val zeroId = contract.sendOpenOffer(
        playerA.address,
        1_203,
        0,
        testCommitment(contract, 0, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(zeroId).toHaveFailedTx({ exitCode: Errors.InvalidOfferId });
}

get fun `test offer boundaries fail before any value is locked`() {
    val (contract, _, _, playerA, _) = setupTest();
    val now = testing.getNow();
    val tooSmall = contract.sendOpenOffer(
        playerA.address,
        1_301,
        1_301,
        testCommitment(contract, 1_301, playerA.address, SECRET_A),
        5_000,
        999_999_996,
        now + 900,
        0,
        null,
        { value: ton("0.55") },
    );
    expect(tooSmall).toHaveFailedTx({ exitCode: Errors.InvalidPool });

    val tooLarge = contract.sendOpenOffer(
        playerA.address,
        1_302,
        1_302,
        testCommitment(contract, 1_302, playerA.address, SECRET_A),
        5_000,
        100_000_000_004,
        now + 900,
        0,
        null,
        { value: ton("50.05") },
    );
    expect(tooLarge).toHaveFailedTx({ exitCode: Errors.InvalidPool });

    val uneven = contract.sendOpenOffer(
        playerA.address,
        1_303,
        1_303,
        testCommitment(contract, 1_303, playerA.address, SECRET_A),
        5_000,
        1_000_000_002,
        now + 900,
        0,
        null,
        { value: ton("0.55") },
    );
    expect(uneven).toHaveFailedTx({ exitCode: Errors.InvalidPool });

    val tooSoon = contract.sendOpenOffer(
        playerA.address,
        1_304,
        1_304,
        testCommitment(contract, 1_304, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        now + 29,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(tooSoon).toHaveFailedTx({ exitCode: Errors.InvalidExpiry });

    val tooLate = contract.sendOpenOffer(
        playerA.address,
        1_305,
        1_305,
        testCommitment(contract, 1_305, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        now + 3_601,
        0,
        null,
        { value: ton("2.05") },
    );
    expect(tooLate).toHaveFailedTx({ exitCode: Errors.InvalidExpiry });

    val underfunded = contract.sendOpenOffer(
        playerA.address,
        1_306,
        1_306,
        testCommitment(contract, 1_306, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        now + 900,
        0,
        null,
        { value: 2_049_999_999 },
    );
    expect(underfunded).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test inclusive fee pool and expiry boundaries are accepted`() {
    val (_, owner, feeCollector, playerA, _) = setupTest();
    val contract = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: feeCollector.address,
        feeBps: 1_000,
        networkId: TEST_NETWORK_ID,
        inviteSignerPublicKey: crypto.seedToKeyPair(INVITE_SIGNER_SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    expect(contract.deploy(owner.address, { value: ton("1") })).toHaveSuccessfulDeploy({
        to: contract.address,
    });
    val now = testing.getNow();
    expect(
        contract.sendOpenOffer(
            playerA.address,
            1_311,
            1_311,
            testCommitment(contract, 1_311, playerA.address, SECRET_A),
            5_000,
            1_000_000_000,
            now + 30,
            0,
            null,
            { value: 550_000_000 },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendCancelOffer(playerA.address, 1_312, 1_311, { value: ton("0.03") }),
    ).toHaveSuccessfulTx<CancelOffer>();
    expect(
        contract.sendOpenOffer(
            playerA.address,
            1_313,
            1_313,
            testCommitment(contract, 1_313, playerA.address, SECRET_A),
            5_000,
            100_000_000_000,
            now + 3_600,
            0,
            null,
            { value: 50_050_000_000 },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
}

get fun `test matching rejects duplicate incompatible stale and terminal offers`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val matcher = testing.treasury("validation-matcher");
    val now = testing.getNow();
    val first = contract.sendOpenOffer(
        playerA.address,
        1_401,
        1_401,
        testCommitment(contract, 1_401, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        now + 120,
        0,
        null,
        { value: ton("1.05") },
    );
    expect(first).toHaveSuccessfulTx<OpenOffer>();
    val same = contract.sendMatchOffers(
        matcher.address,
        1_402,
        1_401,
        1_401,
        { value: ton("0.03") },
    );
    expect(same).toHaveFailedTx({ exitCode: Errors.IncompatibleOffers });

    val wrongChance = contract.sendOpenOffer(
        playerB.address,
        1_403,
        1_403,
        testCommitment(contract, 1_403, playerB.address, SECRET_B),
        2_500,
        ton("4"),
        now + 900,
        0,
        null,
        { value: ton("1.05") },
    );
    expect(wrongChance).toHaveSuccessfulTx<OpenOffer>();
    val incompatibleChance = contract.sendMatchOffers(
        matcher.address,
        1_404,
        1_401,
        1_403,
        { value: ton("0.03") },
    );
    expect(incompatibleChance).toHaveFailedTx({ exitCode: Errors.IncompatibleOffers });
    expect(
        contract.sendCancelOffer(playerB.address, 1_405, 1_403, { value: ton("0.03") }),
    ).toHaveSuccessfulTx<CancelOffer>();

    val wrongPool = contract.sendOpenOffer(
        playerB.address,
        1_406,
        1_406,
        testCommitment(contract, 1_406, playerB.address, SECRET_B),
        7_500,
        ton("8"),
        now + 900,
        0,
        null,
        { value: ton("6.05") },
    );
    expect(wrongPool).toHaveSuccessfulTx<OpenOffer>();
    val incompatiblePool = contract.sendMatchOffers(
        matcher.address,
        1_407,
        1_401,
        1_406,
        { value: ton("0.03") },
    );
    expect(incompatiblePool).toHaveFailedTx({ exitCode: Errors.IncompatibleOffers });
    expect(
        contract.sendCancelOffer(playerB.address, 1_408, 1_406, { value: ton("0.03") }),
    ).toHaveSuccessfulTx<CancelOffer>();

    val compatible = contract.sendOpenOffer(
        playerB.address,
        1_409,
        1_409,
        testCommitment(contract, 1_409, playerB.address, SECRET_B),
        7_500,
        ton("4"),
        now + 900,
        0,
        null,
        { value: ton("3.05") },
    );
    expect(compatible).toHaveSuccessfulTx<OpenOffer>();
    testing.setNow(now + 121);
    val stale = contract.sendMatchOffers(
        matcher.address,
        1_410,
        1_401,
        1_409,
        { value: ton("0.03") },
    );
    expect(stale).toHaveFailedTx({ exitCode: Errors.InvalidExpiry });
}

get fun `test operational guards reject dust pause wrong state and early calls`() {
    val (contract, owner, _, playerA, playerB) = setupTest();
    val matcher = testing.treasury("guard-matcher");
    val expiresAt: uint32 = testing.getNow() + 900;
    expect(
        contract.sendOpenOffer(
            playerA.address,
            1_501,
            1_501,
            testCommitment(contract, 1_501, playerA.address, SECRET_A),
            2_500,
            ton("4"),
            expiresAt,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendOpenOffer(
            playerB.address,
            1_502,
            1_502,
            testCommitment(contract, 1_502, playerB.address, SECRET_B),
            7_500,
            ton("4"),
            expiresAt,
            0,
            null,
            { value: ton("3.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();

    val dustMatch = contract.sendMatchOffers(
        matcher.address,
        1_503,
        1_501,
        1_502,
        { value: ton("0.01") },
    );
    expect(dustMatch).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    val dustOfferExpiry = contract.sendExpireOffer(
        matcher.address,
        1_504,
        1_501,
        { value: ton("0.01") },
    );
    expect(dustOfferExpiry).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(
        contract.sendSetPaused(owner.address, 1_505, true, { value: ton("0.03") }),
    ).toHaveSuccessfulTx<SetPaused>();
    val pausedMatch = contract.sendMatchOffers(
        matcher.address,
        1_506,
        1_501,
        1_502,
        { value: ton("0.03") },
    );
    expect(pausedMatch).toHaveFailedTx({ exitCode: Errors.Paused });
    expect(
        contract.sendSetPaused(owner.address, 1_507, false, { value: ton("0.03") }),
    ).toHaveSuccessfulTx<SetPaused>();
    expect(
        contract.sendMatchOffers(
            matcher.address,
            1_508,
            1_501,
            1_502,
            { value: ton("0.03") },
        ),
    ).toHaveSuccessfulTx<MatchOffers>();

    val replayMatch = contract.sendMatchOffers(
        matcher.address,
        1_509,
        1_501,
        1_502,
        { value: ton("0.03") },
    );
    expect(replayMatch).toHaveFailedTx({ exitCode: Errors.OfferNotOpen });
    val matchedCancel = contract.sendCancelOffer(
        playerA.address,
        1_510,
        1_501,
        { value: ton("0.03") },
    );
    expect(matchedCancel).toHaveFailedTx({ exitCode: Errors.OfferNotOpen });
    val matchedExpiry = contract.sendExpireOffer(
        matcher.address,
        1_511,
        1_501,
        { value: ton("0.03") },
    );
    expect(matchedExpiry).toHaveFailedTx({ exitCode: Errors.OfferNotOpen });
    val earlyDuel = contract.sendExpireDuel(
        matcher.address,
        1_512,
        1_502,
        { value: ton("0.03") },
    );
    expect(earlyDuel).toHaveFailedTx({ exitCode: Errors.TooEarly });
    val dustDuel = contract.sendExpireDuel(
        matcher.address,
        1_513,
        1_502,
        { value: ton("0.01") },
    );
    expect(dustDuel).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    val dustReveal = contract.sendReveal(
        playerA.address,
        1_514,
        1_502,
        1_501,
        SECRET_A,
        { value: ton("0.01") },
    );
    expect(dustReveal).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    advancePastBoost(contract, 1_502);
    val wrongOffer = contract.sendReveal(
        playerA.address,
        1_515,
        1_502,
        9_999,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(wrongOffer).toHaveFailedTx({ exitCode: Errors.WrongRevealer });
    advancePastReveal(contract, 1_502);
    val closedReveal = contract.sendReveal(
        playerA.address,
        1_516,
        1_502,
        1_501,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(closedReveal).toHaveFailedTx({ exitCode: Errors.RevealClosed });
}

get fun `test second revealer wins alone and duplicate second reveal is rejected`() {
    val (contract, _, feeCollector, playerA, playerB) = setupTest();
    openPair(contract, playerA, playerB);
    advancePastBoost(contract, OFFER_B_ID);
    val reveal = contract.sendReveal(
        playerB.address,
        1_601,
        OFFER_B_ID,
        OFFER_B_ID,
        SECRET_B,
        { value: ton("0.03") },
    );
    expect(reveal).toHaveSuccessfulTx<Reveal>();
    val replay = contract.sendReveal(
        playerB.address,
        1_602,
        OFFER_B_ID,
        OFFER_B_ID,
        SECRET_B,
        { value: ton("0.03") },
    );
    expect(replay).toHaveFailedTx({ exitCode: Errors.AlreadyRevealed });
    testing.setNow(testing.getNow() + 301);
    val expired = contract.sendExpireDuel(
        playerA.address,
        1_603,
        OFFER_B_ID,
        { value: ton("0.03") },
    );
    expect(expired).toHaveAllSuccessfulTxs();
    expect(expired).toHaveSuccessfulTx<DuelPayout>({
        from: contract.address,
        to: playerB.address,
        value: ton("3.9"),
    });
    expect(expired).toHaveSuccessfulTx<ProtocolFee>({
        from: contract.address,
        to: feeCollector.address,
        value: ton("0.1"),
    });
}

get fun `test malformed opcode and dust admin call fail closed`() {
    val (contract, owner, _, playerA, _) = setupTest();
    val malformed = contract.sendAny(
        playerA.address,
        beginCell().storeUint(0xDEADBEEF, 32).endCell(),
        { value: ton("0.03") },
    );
    expect(malformed).toHaveFailedTx({ exitCode: Errors.InvalidMessage });
    val dustPause = contract.sendSetPaused(owner.address, 1_701, true, { value: ton("0.01") });
    expect(dustPause).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(contract.contractConfig().paused).toEqual(false);
}

get fun `test direct invite permit binds the accepting wallet on chain`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val attacker = testing.treasury("direct-attacker");
    val matcher = testing.treasury("direct-matcher");
    val expiresAt: uint32 = testing.getNow() + 900;
    val inviteId: uint256 = 0xD1EC700000000000000000000000000000000000000000000000000000000001;

    expect(
        contract.sendOpenDirectOffer(
            playerA.address,
            1_801,
            1_801,
            testCommitment(contract, 1_801, playerA.address, SECRET_A),
            2_500,
            ton("4"),
            expiresAt,
            inviteId,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenDirectOffer>();
    expect(
        contract.sendOpenOffer(
            attacker.address,
            1_802,
            1_802,
            testCommitment(contract, 1_802, attacker.address, SECRET_B),
            7_500,
            ton("4"),
            expiresAt,
            0,
            null,
            { value: ton("3.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendMatchOffers(
            matcher.address,
            1_803,
            1_801,
            1_802,
            { value: ton("0.03") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.IncompatibleOffers });

    val accepted = contract.sendAcceptDirectOffer(
        playerB.address,
        1_804,
        1_804,
        testCommitment(contract, 1_804, playerB.address, SECRET_B),
        7_500,
        ton("4"),
        expiresAt,
        DirectAcceptance {
            counterOfferId: 1_801,
            validUntil: expiresAt,
            signature: testDirectPermit(
                contract,
                inviteId,
                1_801,
                playerB.address,
                expiresAt,
            ),
        },
        null,
        { value: ton("3.05") },
    );
    expect(accepted).toHaveSuccessfulTx<AcceptDirectOffer>();
    expect(contract.directOfferData(1_801).opponent!).toEqual(playerB.address);
    expect(contract.directOfferData(1_804).opponent!).toEqual(playerA.address);
    expect(contract.duelData(1_804).offerAId).toEqual(1_801);
    expect(contract.contractConfig().locked).toEqual(ton("7"));
}

get fun `test direct permit cannot be replayed by another wallet`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val attacker = testing.treasury("permit-replay-attacker");
    val expiresAt: uint32 = testing.getNow() + 900;
    val inviteId: uint256 = 0xD1EC700000000000000000000000000000000000000000000000000000000002;
    expect(
        contract.sendOpenDirectOffer(
            playerA.address,
            1_811,
            1_811,
            testCommitment(contract, 1_811, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            inviteId,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenDirectOffer>();

    val stolen = contract.sendAcceptDirectOffer(
        attacker.address,
        1_812,
        1_812,
        testCommitment(contract, 1_812, attacker.address, SECRET_B),
        5_000,
        ton("2"),
        expiresAt,
        DirectAcceptance {
            counterOfferId: 1_811,
            validUntil: expiresAt,
            signature: testDirectPermit(
                contract,
                inviteId,
                1_811,
                playerB.address,
                expiresAt,
            ),
        },
        null,
        { value: ton("1.05") },
    );
    expect(stolen).toHaveFailedTx({ exitCode: Errors.InvalidDirectPermit });
    expect(contract.contractConfig().locked).toEqual(ton("1"));
    expect(contract.directOfferData(1_811).opponent).toEqual(null);
}

get fun `test direct offer creation and acceptance honor pause`() {
    val (contract, owner, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val inviteId: uint256 = 0xD1EC700000000000000000000000000000000000000000000000000000000003;
    expect(
        contract.sendSetPaused(owner.address, 1_841, true, { value: ton("0.03") }),
    ).toHaveAllSuccessfulTxs();
    expect(
        contract.sendOpenDirectOffer(
            playerA.address,
            1_842,
            1_842,
            testCommitment(contract, 1_842, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            inviteId,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.Paused });
    expect(
        contract.sendSetPaused(owner.address, 1_843, false, { value: ton("0.03") }),
    ).toHaveAllSuccessfulTxs();
    expect(
        contract.sendOpenDirectOffer(
            playerA.address,
            1_844,
            1_844,
            testCommitment(contract, 1_844, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            inviteId,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenDirectOffer>();
    expect(
        contract.sendSetPaused(owner.address, 1_845, true, { value: ton("0.03") }),
    ).toHaveAllSuccessfulTxs();
    expect(
        contract.sendAcceptDirectOffer(
            playerB.address,
            1_846,
            1_846,
            testCommitment(contract, 1_846, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            DirectAcceptance {
                counterOfferId: 1_844,
                validUntil: expiresAt,
                signature: testDirectPermit(
                    contract,
                    inviteId,
                    1_844,
                    playerB.address,
                    expiresAt,
                ),
            },
            null,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.Paused });
}

get fun `test direct path rejects zero invite and AFK counter`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    expect(
        contract.sendOpenDirectOffer(
            playerA.address,
            1_851,
            1_851,
            testCommitment(contract, 1_851, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.DirectInviteRequired });
    expect(
        contract.sendOpenOffer(
            playerA.address,
            1_852,
            1_852,
            testCommitment(contract, 1_852, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendAcceptDirectOffer(
            playerB.address,
            1_853,
            1_853,
            testCommitment(contract, 1_853, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            DirectAcceptance {
                counterOfferId: 1_852,
                validUntil: expiresAt,
                signature: testDirectPermit(contract, 0, 1_852, playerB.address, expiresAt),
            },
            null,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.DirectInviteRequired });
}

get fun `test direct permit enforces owner and both expiry boundaries`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val inviteId: uint256 = 0xD1EC700000000000000000000000000000000000000000000000000000000004;
    expect(
        contract.sendOpenDirectOffer(
            playerA.address,
            1_861,
            1_861,
            testCommitment(contract, 1_861, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            inviteId,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenDirectOffer>();

    expect(
        contract.sendAcceptDirectOffer(
            playerA.address,
            1_862,
            1_862,
            testCommitment(contract, 1_862, playerA.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            DirectAcceptance {
                counterOfferId: 1_861,
                validUntil: expiresAt,
                signature: testDirectPermit(
                    contract,
                    inviteId,
                    1_861,
                    playerA.address,
                    expiresAt,
                ),
            },
            null,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.SameOwner });

    val expiredPermit: uint32 = testing.getNow() - 1;
    expect(
        contract.sendAcceptDirectOffer(
            playerB.address,
            1_863,
            1_863,
            testCommitment(contract, 1_863, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            DirectAcceptance {
                counterOfferId: 1_861,
                validUntil: expiredPermit,
                signature: testDirectPermit(
                    contract,
                    inviteId,
                    1_861,
                    playerB.address,
                    expiredPermit,
                ),
            },
            null,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.DirectPermitExpired });

    val tooLatePermit = expiresAt + 1;
    expect(
        contract.sendAcceptDirectOffer(
            playerB.address,
            1_864,
            1_864,
            testCommitment(contract, 1_864, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            DirectAcceptance {
                counterOfferId: 1_861,
                validUntil: tooLatePermit,
                signature: testDirectPermit(
                    contract,
                    inviteId,
                    1_861,
                    playerB.address,
                    tooLatePermit,
                ),
            },
            null,
            { value: ton("1.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.DirectPermitExpired });

    val exactNow = testing.getNow();
    expect(
        contract.sendAcceptDirectOffer(
            playerB.address,
            1_865,
            1_865,
            testCommitment(contract, 1_865, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            DirectAcceptance {
                counterOfferId: 1_861,
                validUntil: exactNow,
                signature: testDirectPermit(
                    contract,
                    inviteId,
                    1_861,
                    playerB.address,
                    exactNow,
                ),
            },
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<AcceptDirectOffer>();
}

get fun `test commitment cannot cross network domains`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    expect(
        contract.sendOpenOffer(
            playerA.address,
            1_821,
            1_821,
            commitmentForContext(contract.address, -239, 1_821, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendOpenOffer(
            playerB.address,
            1_822,
            1_822,
            testCommitment(contract, 1_822, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            1_821,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    advancePastBoost(contract, 1_822);
    expect(
        contract.sendReveal(
            playerA.address,
            1_823,
            1_822,
            1_821,
            SECRET_A,
            { value: ton("0.03") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidCommitment });
}

get fun `test commitment cannot cross contract addresses`() {
    val (contract, owner, feeCollector, playerA, playerB) = setupTest();
    val other = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: feeCollector.address,
        feeBps: 251,
        networkId: TEST_NETWORK_ID,
        inviteSignerPublicKey: crypto.seedToKeyPair(INVITE_SIGNER_SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    expect(other.deploy(owner.address, { value: ton("1") })).toHaveSuccessfulDeploy();
    val expiresAt: uint32 = testing.getNow() + 900;
    expect(
        contract.sendOpenOffer(
            playerA.address,
            1_831,
            1_831,
            commitmentForContext(other.address, TEST_NETWORK_ID, 1_831, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            expiresAt,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendOpenOffer(
            playerB.address,
            1_832,
            1_832,
            testCommitment(contract, 1_832, playerB.address, SECRET_B),
            5_000,
            ton("2"),
            expiresAt,
            1_831,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    advancePastBoost(contract, 1_832);
    expect(
        contract.sendReveal(
            playerA.address,
            1_833,
            1_832,
            1_831,
            SECRET_A,
            { value: ton("0.03") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidCommitment });
}

get fun `test DUEL owner can fund reserve and withdraw only free balance while paused`() {
    val (contract, owner, feeCollector, _, _) = setupTest();
    expect(
        contract.sendDuelFundReserve(
            owner.address,
            1_901,
            ton("1"),
            { value: ton("1.02") },
        ),
    ).toHaveSuccessfulTx<DuelFundReserve>();
    expect(
        contract.sendDuelWithdrawSurplus(
            owner.address,
            1_902,
            ton("0.5"),
            { value: ton("0.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.MustBePaused });
    expect(
        contract.sendSetPaused(
            owner.address,
            1_903,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetPaused>();
    val withdrawal = contract.sendDuelWithdrawSurplus(
        owner.address,
        1_904,
        ton("0.5"),
        { value: ton("0.05") },
    );
    expect(withdrawal).toHaveSuccessfulTx<DuelAdminWithdrawal>({
        from: contract.address,
        to: feeCollector.address,
        value: ton("0.5"),
    });
}

get fun `test DUEL admin changes cannot alter active locked stakes`() {
    val (contract, owner, _, playerA, _) = setupTest();
    val offerId: uint64 = 1_911;
    expect(
        contract.sendOpenOffer(
            playerA.address,
            offerId,
            offerId,
            testCommitment(contract, offerId, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            testing.getNow() + 900,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    expect(
        contract.sendSetPaused(
            owner.address,
            1_912,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetPaused>();
    expect(
        contract.sendDuelSetFee(
            owner.address,
            1_913,
            300,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.ActiveValueLocked });
    expect(contract.adminState().locked).toEqual(ton("1"));
    expect(
        contract.sendDuelWithdrawSurplus(
            owner.address,
            1_914,
            ton("10"),
            { value: ton("0.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientSurplus });
    expect(contract.contractConfig().locked).toEqual(ton("1"));
}

get fun `test DUEL configuration changes require the paused owner`() {
    val (contract, owner, _, playerA, playerB) = setupTest();
    expect(
        contract.sendDuelSetFee(
            owner.address,
            1_921,
            300,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.MustBePaused });
    expect(
        contract.sendSetPaused(
            owner.address,
            1_922,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetPaused>();
    expect(
        contract.sendDuelSetFee(
            playerA.address,
            1_923,
            300,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.NotOwner });
    expect(
        contract.sendDuelSetFee(
            owner.address,
            1_924,
            1_001,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidFee });
    expect(
        contract.sendDuelSetTreasury(
            owner.address,
            1_925,
            playerB.address,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<DuelSetTreasury>();
    expect(
        contract.sendDuelSetFee(
            owner.address,
            1_926,
            300,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<DuelSetFee>();
    expect(
        contract.sendDuelSetOwner(
            owner.address,
            1_927,
            playerA.address,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<DuelSetOwner>();
    val admin = contract.adminState();
    expect(admin.owner).toEqual(playerA.address);
    expect(admin.treasury).toEqual(playerB.address);
    expect(admin.feeBps).toEqual(300);
    expect(
        contract.sendSetPaused(
            owner.address,
            1_928,
            false,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.NotOwner });
    expect(
        contract.sendSetPaused(
            playerA.address,
            1_929,
            false,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetPaused>();
}

get fun `test matching rejects a corrupted same-owner pair`() {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury("same-owner-admin");
    val treasury = testing.treasury("same-owner-treasury");
    val player = testing.treasury("same-owner-player");
    val matcher = testing.treasury("same-owner-matcher");
    val expiresAt: uint32 = testing.getNow() + 900;
    var offers = [] as OfferMap;
    offers.set(
        2_001,
        storedOffer(
            player.address,
            1,
            5_000,
            ton("2"),
            expiresAt,
            OFFER_OPEN,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    offers.set(
        2_002,
        storedOffer(
            player.address,
            2,
            5_000,
            ton("2"),
            expiresAt,
            OFFER_OPEN,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    var activeOffers = [] as ActiveOfferMap;
    activeOffers.set(player.address, 2_002);
    var usedOfferIds = [] as UsedOfferMap;
    usedOfferIds.set(2_001, true);
    usedOfferIds.set(2_002, true);
    val contract = deployStoredDuel(
        owner,
        treasury,
        250,
        false,
        ton("2"),
        offers,
        [] as DuelMap,
        activeOffers,
        usedOfferIds,
    );

    expect(
        contract.sendMatchOffers(
            matcher.address,
            2_003,
            2_001,
            2_002,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.SameOwner });
}

get fun `test locked-value invariants stop every refund path`() {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury("locked-admin");
    val treasury = testing.treasury("locked-treasury");
    val playerA = testing.treasury("locked-player-a");
    val playerB = testing.treasury("locked-player-b");
    val caller = testing.treasury("locked-caller");
    val expiresAt: uint32 = testing.getNow() + 60;

    var cancelOffers = [] as OfferMap;
    cancelOffers.set(
        2_101,
        storedOffer(
            playerA.address,
            1,
            5_000,
            ton("2"),
            expiresAt,
            OFFER_OPEN,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    var cancelActive = [] as ActiveOfferMap;
    cancelActive.set(playerA.address, 2_101);
    var cancelUsed = [] as UsedOfferMap;
    cancelUsed.set(2_101, true);
    val cancelContract = deployStoredDuel(
        owner,
        treasury,
        250,
        false,
        0,
        cancelOffers,
        [] as DuelMap,
        cancelActive,
        cancelUsed,
    );
    expect(
        cancelContract.sendCancelOffer(
            playerA.address,
            2_102,
            2_101,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });

    testing.setNow(expiresAt + 1);
    expect(
        cancelContract.sendExpireOffer(
            caller.address,
            2_103,
            2_101,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });

    var matchedOffers = [] as OfferMap;
    matchedOffers.set(
        2_111,
        storedOffer(
            playerA.address,
            1,
            5_000,
            ton("2"),
            expiresAt + 900,
            OFFER_MATCHED,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    matchedOffers.set(
        2_112,
        storedOffer(
            playerB.address,
            2,
            5_000,
            ton("2"),
            expiresAt + 900,
            OFFER_MATCHED,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    var matchedDuels = [] as DuelMap;
    matchedDuels.set(
        2_112,
        DuelData {
            offerAId: 2_111,
            offerBId: 2_112,
            boostDeadline: testing.getNow() - 2,
            hardDeadline: testing.getNow() - 2,
            revealDeadline: testing.getNow() - 1,
            boostRevision: 0,
            secretA: 0,
            secretB: 0,
            revealedMask: 0,
        }.toCell(),
    );
    var matchedActive = [] as ActiveOfferMap;
    matchedActive.set(playerA.address, 2_111);
    matchedActive.set(playerB.address, 2_112);
    var matchedUsed = [] as UsedOfferMap;
    matchedUsed.set(2_111, true);
    matchedUsed.set(2_112, true);
    val matchedContract = deployStoredDuel(
        owner,
        treasury,
        250,
        false,
        ton("1"),
        matchedOffers,
        matchedDuels,
        matchedActive,
        matchedUsed,
    );
    expect(
        matchedContract.sendExpireDuel(
            caller.address,
            2_113,
            2_112,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
}

get fun `test every DUEL admin boundary fails closed`() {
    val (contract, owner, _, playerA, _) = setupTest();
    expect(
        contract.sendDuelFundReserve(
            owner.address,
            2_201,
            0,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidAdminAmount });
    expect(
        contract.sendDuelFundReserve(
            owner.address,
            2_202,
            ton("1"),
            { value: 1_019_999_999 },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(
        contract.sendDuelWithdrawSurplus(
            owner.address,
            2_203,
            1,
            { value: 49_999_999 },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(
        contract.sendDuelSetTreasury(
            owner.address,
            2_204,
            playerA.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.MustBePaused });
    expect(
        contract.sendDuelSetOwner(
            owner.address,
            2_205,
            playerA.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.MustBePaused });
    expect(
        contract.sendSetPaused(
            owner.address,
            2_206,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetPaused>();
    expect(
        contract.sendDuelWithdrawSurplus(
            owner.address,
            2_207,
            0,
            { value: ton("0.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidAdminAmount });
    expect(
        contract.sendDuelSetFee(
            owner.address,
            2_208,
            300,
            { value: 19_999_999 },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(
        contract.sendDuelSetTreasury(
            owner.address,
            2_209,
            playerA.address,
            { value: 19_999_999 },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(
        contract.sendDuelSetTreasury(
            owner.address,
            2_210,
            contract.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidTreasury });
    expect(
        contract.sendDuelSetOwner(
            owner.address,
            2_211,
            playerA.address,
            { value: 19_999_999 },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientValue });
    expect(
        contract.sendDuelSetOwner(
            owner.address,
            2_212,
            owner.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidOwner });
    expect(
        contract.sendDuelSetOwner(
            owner.address,
            2_213,
            contract.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InvalidOwner });
}

get fun `test DUEL withdrawal boundary excludes locked value and inbound gas`() {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury("withdraw-boundary-owner");
    val treasury = testing.treasury("withdraw-boundary-treasury");
    val lockedContract = deployStoredDuel(
        owner,
        treasury,
        250,
        true,
        ton("1"),
        [] as OfferMap,
        [] as DuelMap,
        [] as ActiveOfferMap,
        [] as UsedOfferMap,
    );
    val lockedBalance = testing.getAccountBalance(lockedContract.address);
    val lockedFree = lockedBalance - ton("1") - ton("0.2");
    expect(
        lockedContract.sendDuelWithdrawSurplus(
            owner.address,
            2_221,
            lockedFree + 1,
            { value: ton("0.05") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.InsufficientSurplus });

    val exactContract = deployStoredDuel(
        owner,
        treasury,
        300,
        true,
        0,
        [] as OfferMap,
        [] as DuelMap,
        [] as ActiveOfferMap,
        [] as UsedOfferMap,
    );
    val exactFree = testing.getAccountBalance(exactContract.address) - ton("0.2");
    expect(
        exactContract.sendDuelWithdrawSurplus(
            owner.address,
            2_222,
            exactFree,
            { value: ton("0.05") },
        ),
    ).toHaveSuccessfulTx<DuelAdminWithdrawal>({
        from: exactContract.address,
        to: treasury.address,
        value: exactFree,
    });
}

get fun `test matching rejects a pair when either offer is not open`() {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury("state-pair-owner");
    val treasury = testing.treasury("state-pair-treasury");
    val playerA = testing.treasury("state-pair-a");
    val playerB = testing.treasury("state-pair-b");
    val matcher = testing.treasury("state-pair-matcher");
    val expiresAt: uint32 = testing.getNow() + 900;
    var offers = [] as OfferMap;
    offers.set(
        2_231,
        storedOffer(
            playerA.address,
            1,
            5_000,
            ton("2"),
            expiresAt,
            OFFER_OPEN,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    offers.set(
        2_232,
        storedOffer(
            playerB.address,
            2,
            5_000,
            ton("2"),
            expiresAt,
            OFFER_MATCHED,
            DirectOfferData {
                inviteId: 0,
                opponent: null,
            },
        ),
    );
    var active = [] as ActiveOfferMap;
    active.set(playerA.address, 2_231);
    active.set(playerB.address, 2_232);
    var used = [] as UsedOfferMap;
    used.set(2_231, true);
    used.set(2_232, true);
    val contract = deployStoredDuel(
        owner,
        treasury,
        250,
        false,
        ton("2"),
        offers,
        [] as DuelMap,
        active,
        used,
    );
    expect(
        contract.sendMatchOffers(
            matcher.address,
            2_233,
            2_231,
            2_232,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.OfferNotOpen });
}

get fun `test exact expiry reveal and call-gas boundaries are enforced`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val offerExpiry: uint32 = testing.getNow() + 60;
    expect(
        contract.sendOpenOffer(
            playerA.address,
            2_241,
            2_241,
            testCommitment(contract, 2_241, playerA.address, SECRET_A),
            5_000,
            ton("2"),
            offerExpiry,
            0,
            null,
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
    testing.setNow(offerExpiry);
    expect(
        contract.sendExpireOffer(
            playerB.address,
            2_242,
            2_241,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.TooEarly });
    testing.setNow(offerExpiry + 1);
    expect(
        contract.sendExpireOffer(
            playerB.address,
            2_243,
            2_241,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<OfferRefund>();

    openEqualPairWithIds(contract, playerA, playerB, 2_244, 2_245);
    val revealDeadline = contract.duelData(2_245).revealDeadline;
    testing.setNow(revealDeadline);
    expect(
        contract.sendReveal(
            playerA.address,
            2_246,
            2_245,
            2_244,
            SECRET_A,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    expect(
        contract.sendReveal(
            playerB.address,
            2_247,
            2_245,
            2_245,
            SECRET_B,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<DuelPayout>();

    openEqualPairWithIds(contract, playerA, playerB, 2_248, 2_249);
    val secondRevealDeadline = contract.duelData(2_249).revealDeadline;
    testing.setNow(secondRevealDeadline);
    expect(
        contract.sendExpireDuel(
            playerA.address,
            2_250,
            2_249,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: Errors.TooEarly });
    testing.setNow(secondRevealDeadline + 1);
    expect(
        contract.sendExpireDuel(
            playerA.address,
            2_251,
            2_249,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<OfferRefund>();
}

get fun `test zero-fee settlement emits no fee message`() {
    val (_, owner, treasury, playerA, playerB) = setupTest();
    val contract = deployStoredDuel(
        owner,
        treasury,
        0,
        false,
        0,
        [] as OfferMap,
        [] as DuelMap,
        [] as ActiveOfferMap,
        [] as UsedOfferMap,
    );
    openPair(contract, playerA, playerB);
    advancePastBoost(contract, OFFER_B_ID);
    expect(
        contract.sendReveal(
            playerA.address,
            2_301,
            OFFER_B_ID,
            OFFER_A_ID,
            SECRET_A,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    val settled = contract.sendReveal(
        playerB.address,
        2_302,
        OFFER_B_ID,
        OFFER_B_ID,
        SECRET_B,
        { value: ton("0.02") },
    );
    expect(settled).toHaveAllSuccessfulTxs();
    expect(settled).toNotHaveTx<ProtocolFee>({
        from: contract.address,
        to: treasury.address,
    });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test 64 consecutive duels settle without locked value or active offer leaks`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    var round: uint64 = 0;

    while (round < 64) {
        val expiresAt: uint32 = testing.getNow() + 900;
        val offerAId: uint64 = 10_000 + round * 2;
        val offerBId: uint64 = offerAId + 1;
        val secretA: uint256 = SECRET_A + round;
        val secretB: uint256 = SECRET_B + round;

        expect(
            contract.sendOpenOffer(
                playerA.address,
                offerAId,
                offerAId,
                testCommitment(contract, offerAId, playerA.address, secretA),
                5_000,
                ton("2"),
                expiresAt,
                0,
                null,
                { value: ton("1.05") },
            ),
        ).toHaveSuccessfulTx<OpenOffer>();
        expect(
            contract.sendOpenOffer(
                playerB.address,
                offerBId,
                offerBId,
                testCommitment(contract, offerBId, playerB.address, secretB),
                5_000,
                ton("2"),
                expiresAt,
                offerAId,
                null,
                { value: ton("1.05") },
            ),
        ).toHaveSuccessfulTx<OpenOffer>();
        advancePastBoost(contract, offerBId);
        expect(
            contract.sendReveal(
                playerA.address,
                offerAId,
                offerBId,
                offerAId,
                secretA,
                { value: ton("0.03") },
            ),
        ).toHaveSuccessfulTx<Reveal>();
        expect(
            contract.sendReveal(
                playerB.address,
                offerBId,
                offerBId,
                offerBId,
                secretB,
                { value: ton("0.03") },
            ),
        ).toHaveAllSuccessfulTxs();
        expect(contract.contractConfig().locked).toEqual(0);
        round += 1;
    }
}

fun setupTest(): (DuelEscrow, Treasury, Treasury, Treasury, Treasury) {
    testing.setNow(1_800_000_000);
    val owner = testing.treasury("owner");
    val feeCollector = testing.treasury("feeCollector");
    val playerA = testing.treasury("playerA");
    val playerB = testing.treasury("playerB");
    val contract = DuelEscrow.fromStorage({
        owner: owner.address,
        treasury: feeCollector.address,
        feeBps: 250,
        networkId: TEST_NETWORK_ID,
        inviteSignerPublicKey: crypto.seedToKeyPair(INVITE_SIGNER_SEED).publicKey,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    val deployed = contract.deploy(owner.address, { value: ton("2") });
    expect(deployed).toHaveSuccessfulDeploy({ to: contract.address });
    return (contract, owner, feeCollector, playerA, playerB);
}

fun openPairWithExemptA(contract: DuelEscrow, playerA: Treasury, playerB: Treasury): void {
    val expiresAt: uint32 = testing.getNow() + 900;
    val first = contract.sendOpenOffer(
        playerA.address,
        OFFER_A_ID,
        OFFER_A_ID,
        testCommitment(contract, OFFER_A_ID, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        testHolderPermit(contract, OFFER_A_ID, playerA.address, testing.getNow() + 600),
        { value: ton("1.05") },
    );
    expect(first).toHaveSuccessfulTx<OpenOffer>({
        from: playerA.address,
        to: contract.address,
    });
    expect(contract.offerData(OFFER_A_ID).feeExempt).toEqual(true);

    val second = contract.sendOpenOffer(
        playerB.address,
        OFFER_B_ID,
        OFFER_B_ID,
        testCommitment(contract, OFFER_B_ID, playerB.address, SECRET_B),
        7_500,
        ton("4"),
        expiresAt,
        OFFER_A_ID,
        null,
        { value: ton("3.05") },
    );
    expect(second).toHaveSuccessfulTx<OpenOffer>({
        from: playerB.address,
        to: contract.address,
    });
    expect(contract.offerData(OFFER_B_ID).feeExempt).toEqual(false);
}

get fun `test exempt sole winner receives the full pool without a fee message`() {
    val (contract, _, _feeCollector, playerA, playerB) = setupTest();
    openPairWithExemptA(contract, playerA, playerB);
    advancePastBoost(contract, OFFER_B_ID);

    val reveal = contract.sendReveal(
        playerA.address,
        401,
        OFFER_B_ID,
        OFFER_A_ID,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(reveal).toHaveSuccessfulTx<Reveal>();

    testing.setNow(testing.getNow() + 301);
    val expire = contract.sendExpireDuel(
        playerB.address,
        402,
        OFFER_B_ID,
        { value: ton("0.03") },
    );
    expect(expire).toHaveAllSuccessfulTxs();
    expect(expire).toHaveSuccessfulTx<DuelPayout>({
        from: contract.address,
        to: playerA.address,
        value: ton("4"),
    });
    expect(expire).toNotHaveTx<ProtocolFee>({ from: contract.address });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test opponent exemption does not waive the fee of a non-exempt winner`() {
    val (contract, _, feeCollector, playerA, playerB) = setupTest();
    openPairWithExemptA(contract, playerA, playerB);
    advancePastBoost(contract, OFFER_B_ID);

    val reveal = contract.sendReveal(
        playerB.address,
        403,
        OFFER_B_ID,
        OFFER_B_ID,
        SECRET_B,
        { value: ton("0.03") },
    );
    expect(reveal).toHaveSuccessfulTx<Reveal>();

    testing.setNow(testing.getNow() + 301);
    val expire = contract.sendExpireDuel(
        playerA.address,
        404,
        OFFER_B_ID,
        { value: ton("0.03") },
    );
    expect(expire).toHaveAllSuccessfulTxs();
    expect(expire).toHaveSuccessfulTx<DuelPayout>({
        from: contract.address,
        to: playerB.address,
        value: ton("3.9"),
    });
    expect(expire).toHaveSuccessfulTx<ProtocolFee>({
        from: contract.address,
        to: feeCollector.address,
        value: ton("0.1"),
    });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test both exempt players settle the full pool on weighted reveal`() {
    val (contract, _, _feeCollector, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val first = contract.sendOpenOffer(
        playerA.address,
        OFFER_A_ID,
        OFFER_A_ID,
        testCommitment(contract, OFFER_A_ID, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        testHolderPermit(contract, OFFER_A_ID, playerA.address, testing.getNow() + 600),
        { value: ton("1.05") },
    );
    expect(first).toHaveSuccessfulTx<OpenOffer>();
    val second = contract.sendOpenOffer(
        playerB.address,
        OFFER_B_ID,
        OFFER_B_ID,
        testCommitment(contract, OFFER_B_ID, playerB.address, SECRET_B),
        7_500,
        ton("4"),
        expiresAt,
        OFFER_A_ID,
        testHolderPermit(contract, OFFER_B_ID, playerB.address, testing.getNow() + 600),
        { value: ton("3.05") },
    );
    expect(second).toHaveSuccessfulTx<OpenOffer>();
    advancePastBoost(contract, OFFER_B_ID);

    expect(
        contract.sendReveal(
            playerA.address,
            405,
            OFFER_B_ID,
            OFFER_A_ID,
            SECRET_A,
            { value: ton("0.03") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    val settle = contract.sendReveal(
        playerB.address,
        406,
        OFFER_B_ID,
        OFFER_B_ID,
        SECRET_B,
        { value: ton("0.03") },
    );
    expect(settle).toHaveAllSuccessfulTxs();
    expect(settle).toHaveSuccessfulTx<DuelPayout>({
        from: contract.address,
        value: ton("4"),
    });
    expect(settle).toNotHaveTx<ProtocolFee>({ from: contract.address });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test holder permit boundaries fail closed before locking value`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;

    // Signature over a different offer id is not transferable.
    val wrongOffer = contract.sendOpenOffer(
        playerA.address,
        501,
        501,
        testCommitment(contract, 501, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        testHolderPermit(contract, 999, playerA.address, testing.getNow() + 600),
        { value: ton("1.05") },
    );
    expect(wrongOffer).toHaveFailedTx({
        from: playerA.address,
        to: contract.address,
        exitCode: Errors.InvalidHolderPermit,
    });

    // A permit signed for another wallet cannot be attached by the sender.
    val wrongWallet = contract.sendOpenOffer(
        playerA.address,
        502,
        502,
        testCommitment(contract, 502, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        testHolderPermit(contract, 502, playerB.address, testing.getNow() + 600),
        { value: ton("1.05") },
    );
    expect(wrongWallet).toHaveFailedTx({
        from: playerA.address,
        to: contract.address,
        exitCode: Errors.InvalidHolderPermit,
    });

    // An expired permit is rejected outright instead of silently charging.
    val expired = contract.sendOpenOffer(
        playerA.address,
        503,
        503,
        testCommitment(contract, 503, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        testHolderPermit(contract, 503, playerA.address, testing.getNow() - 1),
        { value: ton("1.05") },
    );
    expect(expired).toHaveFailedTx({
        from: playerA.address,
        to: contract.address,
        exitCode: Errors.HolderPermitExpired,
    });

    // A permit living longer than the maximum expiry delay is rejected too.
    val eternal = contract.sendOpenOffer(
        playerA.address,
        504,
        504,
        testCommitment(contract, 504, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
        testHolderPermit(contract, 504, playerA.address, testing.getNow() + 3_601),
        { value: ton("1.05") },
    );
    expect(eternal).toHaveFailedTx({
        from: playerA.address,
        to: contract.address,
        exitCode: Errors.HolderPermitExpired,
    });

    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test direct acceptance carries the acceptor holder exemption on chain`() {
    val (contract, _, _feeCollector, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    val inviteId: uint256 = 0x77;
    val opened = contract.sendOpenDirectOffer(
        playerA.address,
        601,
        601,
        testCommitment(contract, 601, playerA.address, SECRET_A),
        5_000,
        ton("4"),
        expiresAt,
        inviteId,
        null,
        { value: ton("2.05") },
    );
    expect(opened).toHaveSuccessfulTx<OpenDirectOffer>();

    val accepted = contract.sendAcceptDirectOffer(
        playerB.address,
        602,
        602,
        testCommitment(contract, 602, playerB.address, SECRET_B),
        5_000,
        ton("4"),
        expiresAt,
        DirectAcceptance {
            counterOfferId: 601,
            validUntil: expiresAt,
            signature: testDirectPermit(contract, inviteId, 601, playerB.address, expiresAt),
        },
        testHolderPermit(contract, 602, playerB.address, testing.getNow() + 600),
        { value: ton("2.05") },
    );
    expect(accepted).toHaveAllSuccessfulTxs();
    expect(contract.offerData(601).feeExempt).toEqual(false);
    expect(contract.offerData(602).feeExempt).toEqual(true);

    advancePastBoost(contract, 602);
    expect(
        contract.sendReveal(
            playerB.address,
            603,
            602,
            602,
            SECRET_B,
            { value: ton("0.03") },
        ),
    ).toHaveSuccessfulTx<Reveal>();
    testing.setNow(testing.getNow() + 301);
    val expire = contract.sendExpireDuel(
        playerA.address,
        604,
        602,
        { value: ton("0.03") },
    );
    expect(expire).toHaveAllSuccessfulTxs();
    expect(expire).toHaveSuccessfulTx<DuelPayout>({
        from: contract.address,
        to: playerB.address,
        value: ton("4"),
    });
    expect(expire).toNotHaveTx<ProtocolFee>({ from: contract.address });
    expect(contract.contractConfig().locked).toEqual(0);
}

get fun `test a stale v1.3 client body is rejected without touching state`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    // Byte-for-byte the v1.3 OpenOffer layout: it ends after counterOfferId,
    // without the holder maybe-bit that v1.4 appends. A cached Mini App bundle
    // keeps sending exactly this after a cutover.
    val staleBody = beginCell()
        .storeUint(0x4C4F4F01, 32)
        .storeUint(OFFER_A_ID, 64)
        .storeUint(OFFER_A_ID, 64)
        .storeUint(testCommitment(contract, OFFER_A_ID, playerA.address, SECRET_A), 256)
        .storeUint(5_000, 16)
        .storeCoins(ton("2"))
        .storeUint(expiresAt, 32)
        .storeUint(0, 64)
        .endCell();

    val stale = contract.sendAny(playerA.address, staleBody, { value: ton("1.05") });
    // Truncated body: the union deserializer runs off the end of the slice, so
    // TVM aborts with a cell underflow before any storage write.
    expect(stale).toHaveFailedTx({
        from: playerA.address,
        to: contract.address,
        exitCode: 9,
    });
    expect(contract.contractConfig().locked).toEqual(0);

    // The rejected attempt must not have consumed the offer id or the owner
    // slot: the same wallet can immediately open the same offer correctly.
    val retry = contract.sendOpenOffer(
        playerA.address,
        OFFER_A_ID,
        OFFER_A_ID,
        testCommitment(contract, OFFER_A_ID, playerA.address, SECRET_A),
        5_000,
        ton("2"),
        expiresAt,
        0,
        null,
        { value: ton("1.05") },
    );
    expect(retry).toHaveSuccessfulTx<OpenOffer>({
        from: playerA.address,
        to: contract.address,
    });
    expect(contract.contractConfig().locked).toEqual(ton("1"));
    expect(contract.offerData(OFFER_A_ID).feeExempt).toEqual(false);
    expect(playerB.address).toNotEqual(playerA.address);
}
