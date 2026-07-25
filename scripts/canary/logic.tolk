import "@acton/crypto"
import "@acton/env"
import "@acton/io"
import "@acton/emulation/network"
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

fun cancelCanaryOffer(
    duelAddress: address,
    walletAddress: address,
    offerId: uint64,
    queryId: uint64,
) {
    val duel = DuelEscrow.fromAddress(duelAddress);
    val result = duel.sendCancelOffer(
        walletAddress,
        queryId,
        offerId,
        { value: ton("0.03") },
    );
    val trace = result.waitForTrace();
    assert (trace != null) throw CanaryErrors.CanaryStateBusy;
    expect(trace!).toHaveAllSuccessfulTxs();
}

fun cleanInterruptedCanary(
    duelAddress: address,
    firstWallet: address,
    secondWallet: address,
    queryId: uint64,
) {
    val duel = DuelEscrow.fromAddress(duelAddress);
    val firstActive = duel.activeOffer(firstWallet);
    val secondActive = duel.activeOffer(secondWallet);
    if (firstActive != 0 || secondActive != 0) {
        if (firstActive != 0 && secondActive == 0) {
            assert (
                duel.offerData(firstActive).state == OFFER_OPEN
            ) throw CanaryErrors.CanaryStateBusy;
            cancelCanaryOffer(duelAddress, firstWallet, firstActive, queryId);
        } else if (firstActive == 0 && secondActive != 0) {
            assert (
                duel.offerData(secondActive).state == OFFER_OPEN
            ) throw CanaryErrors.CanaryStateBusy;
            cancelCanaryOffer(duelAddress, secondWallet, secondActive, queryId);
        } else {
            val firstOffer = duel.offerData(firstActive);
            val secondOffer = duel.offerData(secondActive);
            if (firstOffer.state == OFFER_OPEN && secondOffer.state == OFFER_OPEN) {
                cancelCanaryOffer(duelAddress, firstWallet, firstActive, queryId);
                cancelCanaryOffer(duelAddress, secondWallet, secondActive, queryId + 1);
            } else {
                assert (
                    firstOffer.state == OFFER_MATCHED && secondOffer.state == OFFER_MATCHED
                ) throw CanaryErrors.CanaryStateBusy;
                val duelId = firstActive > secondActive ? firstActive : secondActive;
                val staleDuel = duel.duelData(duelId);
                assert (
                    blockchain.now() > staleDuel.revealDeadline
                ) throw CanaryErrors.CanaryStateBusy;
                val expired = duel.sendExpireDuel(
                    firstWallet,
                    queryId,
                    duelId,
                    { value: ton("0.03") },
                );
                val trace = expired.waitForTrace();
                assert (trace != null) throw CanaryErrors.CanaryStateBusy;
                expect(trace!).toHaveAllSuccessfulTxs();
            }
        }
        assert (
            duel.activeOffer(firstWallet) == 0 && duel.activeOffer(secondWallet) == 0
        ) throw CanaryErrors.CanaryStateBusy;
    }
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
    println(
        "DUEL_CANARY_ENTRY network={} first_offer={} second_offer={}",
        networkId,
        firstOfferId,
        secondOfferId,
    );
    val signerSeed = env<int>("LOOP_DUEL_CANARY_SIGNING_SEED");
    println("DUEL_CANARY_SIGNER_READY present={}", signerSeed != null);
    assert (signerSeed != null) throw CanaryErrors.MissingSigner;
    assert (
        networkId == TESTNET_NETWORK_ID || networkId == MAINNET_NETWORK_ID
    ) throw CanaryErrors.UnsupportedNetwork;
    assert (firstWallet != secondWallet) throw CanaryErrors.SameWallet;
    assert (firstOfferId < secondOfferId) throw CanaryErrors.WrongContract;

    val duel = DuelEscrow.fromAddress(duelAddress);
    val before = duel.contractConfig();
    val signer = crypto.seedToKeyPair(signerSeed!);
    println(
        "DUEL_CANARY_BINDING network={} address={} signer={} active={}",
        before.networkId == networkId,
        before.contractAddress == duelAddress,
        before.inviteSignerPublicKey == signer.publicKey,
        !before.paused,
    );
    assert (
        before.networkId == networkId && before.contractAddress == duelAddress &&
        before.inviteSignerPublicKey == signer.publicKey &&
        !before.paused
    ) throw CanaryErrors.WrongContract;
    println("DUEL_CANARY_CLEANUP start");
    cleanInterruptedCanary(duelAddress, firstWallet, secondWallet, firstOfferId - 2);
    println("DUEL_CANARY_CLEANUP complete");
    println(
        "DUEL_CANARY_STATE_READY first_active={} second_active={}",
        duel.activeOffer(firstWallet),
        duel.activeOffer(secondWallet),
    );
    val lockedBefore = duel.contractConfig().locked;
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
                signerSeed!,
                networkId,
                duelAddress,
                inviteId,
                firstOfferId,
                secondWallet,
                expiresAt,
            ),
        },
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
    assert (duel.contractConfig().locked == lockedBefore) throw CanaryErrors.UnexpectedLockedValue;

    println(
        "DUEL_CANARY_PROOF duel_id={} settlement_hash={:x}",
        secondOfferId,
        settlement!.toCell().hash(),
    );
}
