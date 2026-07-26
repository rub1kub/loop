import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@acton/testing/expect"
import "@wrappers/BankQueue.gen"
import "@wrappers/DuelEscrow.gen"

enum PauseErrors {
    BankPauseFailed = 990
    DuelPauseFailed = 991
}

fun main(bankAddress: address, duelAddress: address, queryId: uint64) {
    val deployer = scripts.wallet("deployer");
    val bank = BankQueue.fromAddress(bankAddress);
    val duel = DuelEscrow.fromAddress(duelAddress);

    val bankResult = bank.sendSetBankPaused(
        deployer.address,
        queryId,
        true,
        { value: ton("0.03") },
    );
    val bankTrace = bankResult.waitForTrace();
    assert (bankTrace != null) throw PauseErrors.BankPauseFailed;
    expect(bankTrace!).toHaveAllSuccessfulTxs();

    val duelResult = duel.sendSetPaused(
        deployer.address,
        queryId + 1,
        true,
        { value: ton("0.03") },
    );
    val duelTrace = duelResult.waitForTrace();
    assert (duelTrace != null) throw PauseErrors.DuelPauseFailed;
    expect(duelTrace!).toHaveAllSuccessfulTxs();
    println("Previous LOOP contracts paused");
}
