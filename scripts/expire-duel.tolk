import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"

enum RecoveryErrors {
    LockedValueRemains = 981
}

// Settles a duel that nobody revealed before the reveal deadline: both stakes
// go back to their owners. Anyone may send it — the contract gates only on the
// deadline — but the signer is still named, because the testnet "deployer"
// alias does not exist on mainnet.
fun main(duelAddress: address, duelId: uint64, senderWalletName: string) {
    val sender = scripts.wallet(senderWalletName);
    val duel = DuelEscrow.fromAddress(duelAddress);
    val expired = duel.sendExpireDuel(
        sender.address,
        duelId,
        duelId,
        { value: ton("0.05") },
    );
    println(expired.waitForTrace());
    assert (duel.contractConfig().locked == 0) throw RecoveryErrors.LockedValueRemains;
    println("DUEL recovery passed: duel={} refunded and locked=0", duelId);
}
