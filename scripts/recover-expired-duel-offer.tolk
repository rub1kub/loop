import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@acton/testing/expect"
import "@wrappers/DuelEscrow.gen"
import "@contracts/duel/storage"

enum RecoveryErrors {
    OfferNotOpen = 980
    OfferNotExpired = 981
    LockedValueMismatch = 982
    MissingTrace = 983
}

fun main(duelAddress: address, offerId: uint64) {
    val keeper = scripts.wallet("deployer");
    val duel = DuelEscrow.fromAddress(duelAddress);
    val before = duel.contractConfig();
    val offer = duel.offerData(offerId);
    assert (offer.state == OFFER_OPEN) throw RecoveryErrors.OfferNotOpen;
    assert (blockchain.now() > offer.expiresAt) throw RecoveryErrors.OfferNotExpired;

    val expired = duel.sendExpireOffer(
        keeper.address,
        offerId,
        offerId,
        { value: ton("0.03") },
    );
    val trace = expired.waitForTrace();
    assert (trace != null) throw RecoveryErrors.MissingTrace;
    expect(trace!).toHaveAllSuccessfulTxs();
    assert (
        duel.contractConfig().locked == before.locked - offer.stake
    ) throw RecoveryErrors.LockedValueMismatch;
    println("DUEL recovery passed: offer={} expired and refunded", offerId);
}
