import "@acton/io"
import "@acton/emulation/network"
import "@acton/testing/expect"
import "@acton/types/big_array"
import "@acton/types/transaction"
import "@wrappers/BankQueue.gen"
import "@contracts/bank/storage"

enum BankCanaryErrors {
    QueueNotEmpty = 960
    SameWallet = 961
    WrongContract = 962
    MissingTransaction = 963
    FirstPositionMismatch = 964
    PayoutMismatch = 965
    RemainderMismatch = 966
}

fun bankTransactionAt(trace: SendResultList, account: address): TlbTransaction? {
    var index = 0;
    repeat (trace.size()) {
        val transaction = trace.at(index).tx.load();
        if (transaction.getAccountAddress() == account) {
            return transaction;
        }
        index += 1;
    }
    return null;
}

fun runBankCycle(
    bankAddress: address,
    firstPositionId: uint64,
    secondPositionId: uint64,
    firstWallet: address,
    secondWallet: address,
) {
    assert (firstWallet != secondWallet) throw BankCanaryErrors.SameWallet;
    assert (
        firstPositionId != 0 && secondPositionId != 0 && firstPositionId != secondPositionId
    ) throw BankCanaryErrors.WrongContract;

    val bank = BankQueue.fromAddress(bankAddress);
    val before = bank.queueData();
    val config = bank.contractConfig();
    assert (
        before.openPositions == 0 && config.lockedFunding == 0 && !config.paused
    ) throw BankCanaryErrors.QueueNotEmpty;

    val principal = ton("1");
    val multiplierBps: uint16 = 12_500;
    val fee = mulDivFloor(principal, config.feeBps, 10_000);
    val distributable = principal - fee;
    val target = mulDivFloor(principal, multiplierBps, 10_000);
    val neededAfterFirst = target - distributable;
    val secondRemainder = distributable - neededAfterFirst;

    val opened = bank.sendCreatePosition(
        firstWallet,
        firstPositionId,
        firstPositionId,
        principal,
        multiplierBps,
        { value: principal + ton("0.08") },
    );
    val openTrace = opened.waitForTrace();
    assert (openTrace != null) throw BankCanaryErrors.MissingTransaction;
    expect(openTrace!).toHaveAllSuccessfulTxs();
    val openTransaction = bankTransactionAt(openTrace!, bankAddress);
    assert (openTransaction != null) throw BankCanaryErrors.MissingTransaction;
    val first = bank.positionData(firstPositionId);
    assert (
        first.owner == firstWallet && first.principal == principal &&
        first.targetPayout == target &&
        first.fundedAmount == distributable &&
        first.status == BANK_POSITION_PARTIALLY_FUNDED
    ) throw BankCanaryErrors.FirstPositionMismatch;

    val funded = bank.sendCreatePosition(
        secondWallet,
        secondPositionId,
        secondPositionId,
        principal,
        multiplierBps,
        { value: principal + ton("0.08") },
    );
    val fundingTrace = funded.waitForTrace();
    assert (fundingTrace != null) throw BankCanaryErrors.MissingTransaction;
    expect(fundingTrace!).toHaveAllSuccessfulTxs();
    val fundingTransaction = bankTransactionAt(fundingTrace!, bankAddress);
    assert (fundingTransaction != null) throw BankCanaryErrors.MissingTransaction;

    // The live RPC trace does not always decode generated outbound message types.
    // Exact payout opcode, body, destination, value and finality are independently
    // checked by scripts/verify-contracts.py against the finalized chain record.
    val completed = bank.positionData(firstPositionId);
    val remainder = bank.positionData(secondPositionId);
    val after = bank.queueData();
    val afterConfig = bank.contractConfig();
    assert (
        completed.status == BANK_POSITION_PAYOUT_SENT &&
        completed.fundedAmount == completed.targetPayout &&
        after.completedPositions == before.completedPositions + 1
    ) throw BankCanaryErrors.PayoutMismatch;
    assert (
        remainder.owner == secondWallet && remainder.fundedAmount == secondRemainder &&
        remainder.status == BANK_POSITION_PARTIALLY_FUNDED &&
        after.openPositions == 1 &&
        afterConfig.lockedFunding == secondRemainder
    ) throw BankCanaryErrors.RemainderMismatch;

    println(
        "BANK_CANARY_PROOF first_position={} second_position={} first_hash={:x} funding_hash={:x}",
        firstPositionId,
        secondPositionId,
        openTransaction!.toCell().hash(),
        fundingTransaction!.toCell().hash(),
    );
}
