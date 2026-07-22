import "@acton/crypto"
import "@acton/env"
import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"
import "@contracts/duel/messages"

const CANARY_NETWORK_ID: int32 = -3
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
}

fun canaryCommitment(
    duelAddress: address,
    offerId: uint64,
    owner: address,
    secret: uint256,
): uint256 {
    return beginCell()
        .storeUint(CANARY_COMMITMENT_DOMAIN, 32)
        .storeInt(CANARY_NETWORK_ID, 32)
        .storeAddress(duelAddress)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(secret, 256)
        .hash();
}

fun canaryPermit(
    signerSeed: uint256,
    duelAddress: address,
    inviteId: uint256,
    counterOfferId: uint64,
    invitedAddress: address,
    validUntil: uint32,
): bits512 {
    val hash = beginCell()
        .storeUint(CANARY_DIRECT_ACCEPT_DOMAIN, 32)
        .storeInt(CANARY_NETWORK_ID, 32)
        .storeAddress(duelAddress)
        .storeUint(inviteId, 256)
        .storeUint(counterOfferId, 64)
        .storeAddress(invitedAddress)
        .storeUint(validUntil, 32)
        .hash();
    return crypto.rawSign(signerSeed, hash) as bits512;
}

fun main(
    duelAddress: address,
    firstWalletName: string,
    secondWalletName: string,
    firstOfferId: uint64,
    secondOfferId: uint64,
    expiresAt: uint32,
) {
    val signerSeed = env<int>("LOOP_DUEL_CANARY_SIGNING_SEED");
    assert (signerSeed != null) throw CanaryErrors.MissingSigner;
    val firstWallet = scripts.wallet(firstWalletName);
    val secondWallet = scripts.wallet(secondWalletName);
    assert (firstWallet.address != secondWallet.address) throw CanaryErrors.SameWallet;
    assert (firstOfferId < secondOfferId) throw CanaryErrors.WrongContract;

    val duel = DuelEscrow.fromAddress(duelAddress);
    val before = duel.contractConfig();
    val signer = crypto.seedToKeyPair(signerSeed!);
    assert (
        before.networkId == CANARY_NETWORK_ID && before.contractAddress == duelAddress &&
        before.inviteSignerPublicKey == signer.publicKey &&
        !before.paused
    ) throw CanaryErrors.WrongContract;
    val lockedBefore = before.locked;
    val inviteId = beginCell()
        .storeUint(0x43414E59, 32)
        .storeAddress(duelAddress)
        .storeUint(firstOfferId, 64)
        .storeUint(secondOfferId, 64)
        .hash();

    val opened = duel.sendOpenDirectOffer(
        firstWallet.address,
        firstOfferId,
        firstOfferId,
        canaryCommitment(duelAddress, firstOfferId, firstWallet.address, CANARY_SECRET_A),
        5_000,
        ton("1"),
        expiresAt,
        inviteId,
        { value: ton("0.55") },
    );
    val openTrace = opened.waitForTrace();
    assert (openTrace != null) throw CanaryErrors.WrongContract;
    assert (
        openTrace!.findTransaction<OpenDirectOffer>({ to: duelAddress, success: true }) != null
    ) throw CanaryErrors.WrongContract;

    val accepted = duel.sendAcceptDirectOffer(
        secondWallet.address,
        secondOfferId,
        secondOfferId,
        canaryCommitment(duelAddress, secondOfferId, secondWallet.address, CANARY_SECRET_B),
        5_000,
        ton("1"),
        expiresAt,
        DirectAcceptance {
            counterOfferId: firstOfferId,
            validUntil: expiresAt,
            signature: canaryPermit(
                signerSeed!,
                duelAddress,
                inviteId,
                firstOfferId,
                secondWallet.address,
                expiresAt,
            ),
        },
        { value: ton("0.55") },
    );
    val acceptTrace = accepted.waitForTrace();
    assert (acceptTrace != null) throw CanaryErrors.WrongContract;
    assert (
        acceptTrace!.findTransaction<AcceptDirectOffer>({ to: duelAddress, success: true }) != null
    ) throw CanaryErrors.WrongContract;
    assert (
        duel.directOfferData(firstOfferId).opponent! == secondWallet.address &&
        duel.directOfferData(secondOfferId).opponent! == firstWallet.address
    ) throw CanaryErrors.WrongBinding;

    val firstReveal = duel.sendReveal(
        firstWallet.address,
        firstOfferId,
        secondOfferId,
        firstOfferId,
        CANARY_SECRET_A,
        { value: ton("0.03") },
    );
    val firstRevealTrace = firstReveal.waitForTrace();
    assert (firstRevealTrace != null) throw CanaryErrors.MissingSettlement;
    assert (
        firstRevealTrace!.findTransaction<Reveal>({ to: duelAddress, success: true }) != null
    ) throw CanaryErrors.MissingSettlement;

    val secondReveal = duel.sendReveal(
        secondWallet.address,
        secondOfferId,
        secondOfferId,
        secondOfferId,
        CANARY_SECRET_B,
        { value: ton("0.03") },
    );
    val settlementTrace = secondReveal.waitForTrace();
    assert (settlementTrace != null) throw CanaryErrors.MissingSettlement;
    val settlement = settlementTrace!.findTransaction<Reveal>({
        to: duelAddress,
        success: true,
    });
    assert (settlement != null) throw CanaryErrors.MissingSettlement;
    assert (
        settlementTrace!.findTransaction<DuelPayout>({ from: duelAddress, success: true }) != null
    ) throw CanaryErrors.MissingSettlement;
    assert (duel.contractConfig().locked == lockedBefore) throw CanaryErrors.UnexpectedLockedValue;

    println(
        "DUEL_CANARY_PROOF duel_id={} settlement_hash={:064x}",
        secondOfferId,
        settlement!.toCell().hash(),
    );
}
