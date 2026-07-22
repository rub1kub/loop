import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"

enum RecoveryErrors {
    LockedValueRemains = 980
}

fun main(duelAddress: address, offerId: uint64) {
    val deployer = scripts.wallet("deployer");
    val duel = DuelEscrow.fromAddress(duelAddress);
    val cancelled = duel.sendCancelOffer(
        deployer.address,
        offerId,
        offerId,
        { value: ton("0.03") },
    );
    println(cancelled.waitForTrace());
    assert (duel.contractConfig().locked == 0) throw RecoveryErrors.LockedValueRemains;
    println("DUEL recovery passed: offer={} refunded and locked=0", offerId);
}
