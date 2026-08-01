import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

enum SetBankPausedErrors {
    StateMismatch = 901
}

fun main(bankAddress: address, paused: bool, queryId: uint64, ownerWalletName: string) {
    val owner = scripts.wallet(ownerWalletName);
    val bank = BankQueue.fromAddress(bankAddress);
    val result = bank.sendSetBankPaused(
        owner.address,
        queryId,
        paused,
        { value: ton("0.03") },
    );
    println(result.waitForTrace());
    assert (bank.contractConfig().paused == paused) throw SetBankPausedErrors.StateMismatch;
    println("LOOP BankQueue paused={}", paused);
}
