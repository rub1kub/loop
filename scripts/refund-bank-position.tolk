import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

enum RefundErrors {
    NotPaused = 980
    FundingUnchanged = 981
}

/// Returns one open position's collected funding to whoever opened it.
///
/// The contract only accepts this while paused, so nobody's position can be
/// pulled out from under a payout that is already in flight. Named wallet
/// rather than a hardcoded one: the owner address differs per network.
fun main(bankAddress: address, positionId: uint64, queryId: uint64, ownerWalletName: string) {
    val owner = scripts.wallet(ownerWalletName);
    val bank = BankQueue.fromAddress(bankAddress);
    val before = bank.contractConfig();
    assert (before.paused) throw RefundErrors.NotPaused;
    println("до:  заперто {}", before.lockedFunding);

    val result = bank.sendBankRefundPosition(
        owner.address,
        queryId,
        positionId,
        { value: ton("0.06") },
    );
    println(result.waitForTrace());

    val after = bank.contractConfig();
    assert (after.lockedFunding < before.lockedFunding) throw RefundErrors.FundingUnchanged;
    println("BANK refund sent: locked {} -> {}", before.lockedFunding, after.lockedFunding);
}
