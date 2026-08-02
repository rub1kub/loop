import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

enum WithdrawErrors {
    NotPaused = 990
    BalanceUnchanged = 991
}

/// Takes free balance out of a BankQueue, down to the storage floor.
///
/// Free means what no open position is counting on: the contract refuses any
/// amount that would dip into locked funding or below the reserve it needs to
/// keep paying its own storage.
fun main(bankAddress: address, amount: coins, queryId: uint64, ownerWalletName: string) {
    val owner = scripts.wallet(ownerWalletName);
    val bank = BankQueue.fromAddress(bankAddress);
    val config = bank.contractConfig();
    assert (config.paused) throw WithdrawErrors.NotPaused;
    val before = scripts.fetchAccountBalance(bankAddress);
    println("до:  баланс {} заперто {}", before, config.lockedFunding);

    val result = bank.sendBankWithdrawSurplus(
        owner.address,
        queryId,
        amount,
        { value: ton("0.06") },
    );
    println(result.waitForTrace());
    println("после: баланс {}", scripts.fetchAccountBalance(bankAddress));
}
