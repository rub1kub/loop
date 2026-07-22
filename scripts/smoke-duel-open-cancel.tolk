import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"

const SMOKE_COMMITMENT_DOMAIN = 0x4C4F4F50
const SMOKE_SECRET: uint256 = 0x6C6F6F702D6475656C2D746573746E65742D736D6F6B652D76312D3030303031

enum SmokeErrors {
    ContractNotIdle = 901
    OfferMismatch = 902
    LockedValueMismatch = 903
}

fun smokeCommitment(offerId: uint64, owner: address): uint256 {
    return beginCell()
        .storeUint(SMOKE_COMMITMENT_DOMAIN, 32)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(SMOKE_SECRET, 256)
        .hash();
}

fun main(duelAddress: address, offerId: uint64, expiresAt: uint32) {
    val deployer = scripts.wallet("deployer");
    val duel = DuelEscrow.fromAddress(duelAddress);
    val before = duel.contractConfig();
    assert (before.locked == 0) throw SmokeErrors.ContractNotIdle;

    val opened = duel.sendOpenOffer(
        deployer.address,
        offerId,
        offerId,
        smokeCommitment(offerId, deployer.address),
        5_000,
        ton("2"),
        expiresAt,
        0,
        { value: ton("1.05") },
    );
    println(opened.waitForTrace());

    val offer = duel.offerData(offerId);
    assert (
        offer.owner == deployer.address && offer.totalPool == ton("2") && offer.stake == ton("1") &&
        offer.chanceBps == 5_000
    ) throw SmokeErrors.OfferMismatch;
    assert (duel.contractConfig().locked == ton("1")) throw SmokeErrors.LockedValueMismatch;

    val cancelled = duel.sendCancelOffer(
        deployer.address,
        offerId,
        offerId,
        { value: ton("0.03") },
    );
    println(cancelled.waitForTrace());
    assert (duel.contractConfig().locked == 0) throw SmokeErrors.LockedValueMismatch;

    println("DUEL smoke passed: offer={} opened, escrowed and refunded", offerId);
}
