import "@acton/crypto"
import "@acton/env"
import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/testing"
import "@acton/testing/expect"
import "@acton/types/big_array"
import "@acton/types/transaction"
import "@wrappers/DuelEscrow.gen"
import "@contracts/duel/messages"
import "@contracts/duel/storage"

const TESTNET_NETWORK_ID: int32 = -3
const MAINNET_NETWORK_ID: int32 = -239
const CANARY_COMMITMENT_DOMAIN = 0x4C4F4F60
const CANARY_DIRECT_ACCEPT_DOMAIN = 0x4C4F4F62
const CANARY_SECRET_A: uint256 = 0xCAAA000000000000000000000000000000000000000000000000000000000001
const CANARY_SECRET_B: uint256 = 0xCAAA000000000000000000000000000000000000000000000000000000000002

enum CanaryErrors {
    MissingSigner = 950
    SameWallet = 951
    WrongContract = 952
    UnexpectedLockedValue = 953
    MissingSettlement = 954
    WrongBinding = 955
    UnsupportedNetwork = 956
    CanaryStateBusy = 957
    InvalidPhase = 958
}

fun transactionAt(trace: SendResultList, account: address): TlbTransaction? {
    var index = 0;
    repeat (trace.size()) {
        val transaction = trace.at(index).tx.load();
        if (transaction.getAccountAddress() == account) {
            return transaction;
        }
        index += 1;
    }
    return null;
}

fun canaryCommitment(
    networkId: int32,
    duelAddress: address,
    offerId: uint64,
    owner: address,
    secret: uint256,
): uint256 {
    return beginCell()
        .storeUint(CANARY_COMMITMENT_DOMAIN, 32)
        .storeInt(networkId, 32)
        .storeAddress(duelAddress)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(secret, 256)
        .hash();
}

fun canaryPermit(
    signerSeed: uint256,
    networkId: int32,
    duelAddress: address,
    inviteId: uint256,
    counterOfferId: uint64,
    invitedAddress: address,
    validUntil: uint32,
): bits512 {
    val hash = beginCell()
        .storeUint(CANARY_DIRECT_ACCEPT_DOMAIN, 32)
        .storeInt(networkId, 32)
        .storeAddress(duelAddress)
        .storeUint(inviteId, 256)
        .storeUint(counterOfferId, 64)
        .storeAddress(invitedAddress)
        .storeUint(validUntil, 32)
        .hash();
    return crypto.rawSign(signerSeed, hash) as bits512;
}

fun requireCanaryContract(
    duelAddress: address,
    networkId: int32,
): uint256 {
    val signerSeed = env<int>("LOOP_DUEL_CANARY_SIGNING_SEED");
    println("DUEL_CANARY_SIGNER_READY present={}", signerSeed != null);
    assert (signerSeed != null) throw CanaryErrors.MissingSigner;
    assert (
        networkId == TESTNET_NETWORK_ID || networkId == MAINNET_NETWORK_ID
    ) throw CanaryErrors.UnsupportedNetwork;

    val duel = DuelEscrow.fromAddress(duelAddress);
    val config = duel.contractConfig();
    val signer = crypto.seedToKeyPair(signerSeed!);
    println(
        "DUEL_CANARY_BINDING network={} address={} signer={} active={}",
        config.networkId == networkId,
        config.contractAddress == duelAddress,
        config.inviteSignerPublicKey == signer.publicKey,
        !config.paused,
    );
    assert (
        config.networkId == networkId && config.contractAddress == duelAddress &&
        config.inviteSignerPublicKey == signer.publicKey &&
        !config.paused
    ) throw CanaryErrors.WrongContract;
    return signerSeed!;
}

fun runCanaryOpenAndBoost(
    duelAddress: address,
    networkId: int32,
    firstOfferId: uint64,
    secondOfferId: uint64,
    expiresAt: uint32,
    firstWallet: address,
    secondWallet: address,
) {
    println(
        "DUEL_CANARY_ENTRY network={} first_offer={} second_offer={}",
        networkId,
        firstOfferId,
        secondOfferId,
    );
    assert (firstWallet != secondWallet) throw CanaryErrors.SameWallet;
    assert (firstOfferId < secondOfferId) throw CanaryErrors.WrongContract;

    val duel = DuelEscrow.fromAddress(duelAddress);
    val signerSeed = requireCanaryContract(duelAddress, networkId);
    // Acton 1.0.0 remote scripts silently stop when `activeOffer` reads a
    // missing dictionary entry. Interrupted runs are recovered explicitly
    // with cancel/expire scripts using the offer IDs printed above.
    println("DUEL_CANARY_STATE_READY");
    val inviteId = beginCell()
        .storeUint(0x43414E59, 32)
        .storeAddress(duelAddress)
        .storeUint(firstOfferId, 64)
        .storeUint(secondOfferId, 64)
        .hash();

    val opened = duel.sendOpenDirectOffer(
        firstWallet,
        firstOfferId,
        firstOfferId,
        canaryCommitment(
            networkId,
            duelAddress,
            firstOfferId,
            firstWallet,
            CANARY_SECRET_A,
        ),
        5_000,
        ton("1"),
        expiresAt,
        inviteId,
        null,
        { value: ton("0.55") },
    );
    val openTrace = opened.waitForTrace();
    assert (openTrace != null) throw CanaryErrors.WrongContract;
    expect(openTrace!).toHaveAllSuccessfulTxs();
    assert (transactionAt(openTrace!, duelAddress) != null) throw CanaryErrors.WrongContract;

    val accepted = duel.sendAcceptDirectOffer(
        secondWallet,
        secondOfferId,
        secondOfferId,
        canaryCommitment(
            networkId,
            duelAddress,
            secondOfferId,
            secondWallet,
            CANARY_SECRET_B,
        ),
        5_000,
        ton("1"),
        expiresAt,
        DirectAcceptance {
            counterOfferId: firstOfferId,
            validUntil: expiresAt,
            signature: canaryPermit(
                signerSeed,
                networkId,
                duelAddress,
                inviteId,
                firstOfferId,
                secondWallet,
                expiresAt,
            ),
        },
        null,
        { value: ton("0.55") },
    );
    val acceptTrace = accepted.waitForTrace();
    assert (acceptTrace != null) throw CanaryErrors.WrongContract;
    expect(acceptTrace!).toHaveAllSuccessfulTxs();
    assert (transactionAt(acceptTrace!, duelAddress) != null) throw CanaryErrors.WrongContract;
    assert (
        duel.directOfferData(firstOfferId).opponent! == secondWallet &&
        duel.directOfferData(secondOfferId).opponent! == firstWallet
    ) throw CanaryErrors.WrongBinding;

    val initial = duel.duelBoostData(secondOfferId);
    val boosted = duel.sendBoostDuel(
        firstWallet,
        firstOfferId + 10,
        secondOfferId,
        firstOfferId,
        ton("0.1"),
        0,
        5_400,
        initial.hardDeadline,
        { value: ton("0.15") },
    );
    val boostTrace = boosted.waitForTrace();
    assert (boostTrace != null) throw CanaryErrors.WrongContract;
    expect(boostTrace!).toHaveAllSuccessfulTxs();
    assert (transactionAt(boostTrace!, duelAddress) != null) throw CanaryErrors.WrongContract;
    val boost = duel.duelBoostData(secondOfferId);
    assert (
        boost.stakeA == ton("0.6") && boost.stakeB == ton("0.5") && boost.chanceABps == 5_454 &&
        boost.chanceBBps == 4_546 &&
        boost.boostRevision == 1
    ) throw CanaryErrors.WrongBinding;
    println(
        "DUEL_CANARY_BOOST duel_id={} boost_deadline={} revision={} chance_a={}",
        secondOfferId,
        boost.boostDeadline,
        boost.boostRevision,
        boost.chanceABps,
    );
}

fun runCanarySettle(
    duelAddress: address,
    networkId: int32,
    firstOfferId: uint64,
    secondOfferId: uint64,
    firstWallet: address,
    secondWallet: address,
) {
    assert (firstWallet != secondWallet) throw CanaryErrors.SameWallet;
    val duel = DuelEscrow.fromAddress(duelAddress);
    requireCanaryContract(duelAddress, networkId);
    val boost = duel.duelBoostData(secondOfferId);
    assert (
        boost.boostRevision == 1 && boost.chanceABps == 5_454 && boost.chanceBBps == 4_546
    ) throw CanaryErrors.WrongBinding;
    val lockedBeforeSettlement = duel.contractConfig().locked;

    val firstReveal = duel.sendReveal(
        firstWallet,
        firstOfferId,
        secondOfferId,
        firstOfferId,
        CANARY_SECRET_A,
        { value: ton("0.03") },
    );
    val firstRevealTrace = firstReveal.waitForTrace();
    assert (firstRevealTrace != null) throw CanaryErrors.MissingSettlement;
    expect(firstRevealTrace!).toHaveAllSuccessfulTxs();
    assert (
        transactionAt(firstRevealTrace!, duelAddress) != null
    ) throw CanaryErrors.MissingSettlement;

    val secondReveal = duel.sendReveal(
        secondWallet,
        secondOfferId,
        secondOfferId,
        secondOfferId,
        CANARY_SECRET_B,
        { value: ton("0.03") },
    );
    val settlementTrace = secondReveal.waitForTrace();
    assert (settlementTrace != null) throw CanaryErrors.MissingSettlement;
    expect(settlementTrace!).toHaveAllSuccessfulTxs();
    val settlement = transactionAt(settlementTrace!, duelAddress);
    assert (settlement != null) throw CanaryErrors.MissingSettlement;
    assert (
        duel.contractConfig().locked == lockedBeforeSettlement - ton("1.1")
    ) throw CanaryErrors.UnexpectedLockedValue;

    println(
        "DUEL_CANARY_PROOF duel_id={} settlement_hash={:x}",
        secondOfferId,
        settlement!.toCell().hash(),
    );
}

fun runCanary(
    duelAddress: address,
    networkId: int32,
    firstOfferId: uint64,
    secondOfferId: uint64,
    expiresAt: uint32,
    firstWallet: address,
    secondWallet: address,
) {
    val lockedBefore = DuelEscrow.fromAddress(duelAddress).contractConfig().locked;
    runCanaryOpenAndBoost(
        duelAddress,
        networkId,
        firstOfferId,
        secondOfferId,
        expiresAt,
        firstWallet,
        secondWallet,
    );
    val duel = DuelEscrow.fromAddress(duelAddress);
    testing.setNow(duel.duelBoostData(secondOfferId).boostDeadline + 1);
    runCanarySettle(
        duelAddress,
        networkId,
        firstOfferId,
        secondOfferId,
        firstWallet,
        secondWallet,
    );
    assert (duel.contractConfig().locked == lockedBefore) throw CanaryErrors.UnexpectedLockedValue;
}
