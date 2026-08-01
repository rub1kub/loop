import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"

enum RecoveryErrors {
    LockedValueRemains = 980
}

// Only the offer's own owner may cancel it, and on mainnet that is never the
// testnet "deployer" alias this script used to hardcode, so the signer is named
// explicitly.
fun main(duelAddress: address, offerId: uint64, ownerWalletName: string) {
    val owner = scripts.wallet(ownerWalletName);
    val duel = DuelEscrow.fromAddress(duelAddress);
    val cancelled = duel.sendCancelOffer(
        owner.address,
        offerId,
        offerId,
        { value: ton("0.03") },
    );
    println(cancelled.waitForTrace());
    assert (duel.contractConfig().locked == 0) throw RecoveryErrors.LockedValueRemains;
    println("DUEL recovery passed: offer={} refunded and locked=0", offerId);
}
