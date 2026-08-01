import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@acton/testing/expect"
import "@wrappers/DuelEscrow.gen"

enum DuelPauseErrors {
    UnexpectedPauseState = 992
    UnexpectedOwner = 993
}

fun main(duelAddress: address, ownerAddress: address, paused: bool, queryId: uint64, signerWalletName: string) {
    val signer = scripts.wallet(signerWalletName);
    val duel = DuelEscrow.fromAddress(duelAddress);
    // `adminState` has the same shape in every deployed DuelEscrow, while
    // `contractConfig` grew a field in v1.4. Pausing a retired deployment must
    // keep working after the local ABI moves on, otherwise the owner loses the
    // ability to close the contract exactly when a cutover requires it.
    val before = duel.adminState();
    assert (before.owner == ownerAddress) throw DuelPauseErrors.UnexpectedOwner;
    println(
        "signer={} sender={} contract={}",
        signer.address,
        ownerAddress,
        duelAddress,
    );
    println(
        "current_paused={} target_paused={} locked={}",
        before.paused,
        paused,
        before.locked,
    );

    val result = duel.sendSetPaused(
        ownerAddress,
        queryId,
        paused,
        { value: ton("0.03") },
    );
    val trace = result.waitForTrace();
    expect(trace!).toHaveAllSuccessfulTxs();
    assert (duel.adminState().paused == paused) throw DuelPauseErrors.UnexpectedPauseState;
    println("DUEL pause state updated: paused={}", paused);
}
