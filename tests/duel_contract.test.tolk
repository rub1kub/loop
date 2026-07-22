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
        { value: ton("3.05") },
    );
    expect(second).toHaveSuccessfulTx<OpenOffer>({
        from: playerB.address,
        to: contract.address,
    });
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

get fun `test both valid reveals settle once with weighted payout and fee`() {
    val (contract, _, feeCollector, playerA, playerB) = setupTest();
    openPair(contract, playerA, playerB);

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
    testing.setNow(testing.getNow() + 301);

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

    val replay = contract.sendOpenOffer(
        playerA.address,
        401,
        401,
        testCommitment(contract, 401, playerA.address, SECRET_A),
        2_500,
        ton("4"),
        expiresAt,
        0,
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
    val wrongOffer = contract.sendReveal(
        playerA.address,
        1_515,
        1_502,
        9_999,
        SECRET_A,
        { value: ton("0.03") },
    );
    expect(wrongOffer).toHaveFailedTx({ exitCode: Errors.WrongRevealer });
    testing.setNow(testing.getNow() + 301);
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
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
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
            { value: ton("1.05") },
        ),
    ).toHaveSuccessfulTx<OpenOffer>();
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

get fun `test 64 consecutive duels settle without locked value or active offer leaks`() {
    val (contract, _, _, playerA, playerB) = setupTest();
    val expiresAt: uint32 = testing.getNow() + 900;
    var round: uint64 = 0;

    while (round < 64) {
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
                { value: ton("1.05") },
            ),
        ).toHaveSuccessfulTx<OpenOffer>();
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
