import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

enum FundErrors {
    QueueNotShrinking = 970
}

/// Opens a BANK position straight at the contract, past the application's
/// launch cap.
///
/// The cap that stops at 1 GRAM lives in the application, not in the contract,
/// and winding a queue down needs a deposit sized to what the head position is
/// still missing rather than to what a participant may open. The contract's own
/// limit still applies, so this cannot exceed what the queue has earned.
///
/// The wallet is named because a hardcoded alias resolves to a different
/// account on mainnet, and because the contract allows one open position per
/// address — a second call has to come from a different wallet.
fun main(bankAddress: address, positionId: uint64, principal: coins, walletName: string) {
    val sender = scripts.wallet(walletName);
    val bank = BankQueue.fromAddress(bankAddress);
    val before = bank.contractConfig();
    println("до:  заперто {} потолок {}", before.lockedFunding, before.principalLimit);

    val opened = bank.sendCreatePosition(
        sender.address,
        positionId,
        positionId,
        principal,
        20_000,
        { value: principal + ton("0.08") },
    );
    println(opened.waitForTrace());

    val after = bank.contractConfig();
    println("после: заперто {} выплат {}", after.lockedFunding, after.completedPositions);
    assert (after.lockedFunding < before.lockedFunding) throw FundErrors.QueueNotShrinking;
    println("BANK queue advanced: locked {} -> {}", before.lockedFunding, after.lockedFunding);
}
