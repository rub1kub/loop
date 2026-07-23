import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
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
    println("sender={} bank_owner={} duel_owner={}", deployer.address, bank.contractConfig().owner, duel.contractConfig().owner);

    val bankResult = bank.sendSetBankPaused(
        deployer.address,
        queryId,
        true,
        { value: ton("0.03") },
    );
    println(bankResult.waitForTrace());
    assert (bank.contractConfig().paused) throw PauseErrors.BankPauseFailed;

    val duelResult = duel.sendSetPaused(
        deployer.address,
        queryId + 1,
        true,
        { value: ton("0.03") },
    );
    println(duelResult.waitForTrace());
    assert (duel.contractConfig().paused) throw PauseErrors.DuelPauseFailed;
    println("Previous LOOP contracts paused");
}
