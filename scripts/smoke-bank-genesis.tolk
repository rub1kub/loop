import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"
import "@contracts/bank/storage"

enum Errors {
    QueueNotEmpty = 901
    PositionMismatch = 902
    FundingMismatch = 903
    QueueMismatch = 904
}

fun main(bankAddress: address, positionId: uint64, principal: coins, multiplierBps: uint16) {
    val deployer = scripts.wallet("deployer");
    val bank = BankQueue.fromAddress(bankAddress);
    val before = bank.queueData();
    assert (before.openPositions == 0) throw Errors.QueueNotEmpty;

    val result = bank.sendCreatePosition(
        deployer.address,
        positionId,
        positionId,
        principal,
        multiplierBps,
        { value: principal + ton("0.08") },
    );
    println(result.waitForTrace());

    val config = bank.contractConfig();
    val position = bank.positionData(positionId);
    val queue = bank.queueData();
    val fee = mulDivFloor(principal, config.feeBps, 10_000);
    val expectedFunding = principal - fee;
    val expectedTarget = mulDivFloor(principal, multiplierBps, 10_000);

    assert (
        position.owner == deployer.address && position.principal == principal &&
        position.targetPayout == expectedTarget
    ) throw Errors.PositionMismatch;
    assert (
        position.fundedAmount == expectedFunding &&
        position.status == BANK_POSITION_PARTIALLY_FUNDED &&
        config.lockedFunding == expectedFunding
    ) throw Errors.FundingMismatch;
    assert (
        queue.headQueueIndex == 0 && queue.nextQueueIndex == 1 && queue.openPositions == 1
    ) throw Errors.QueueMismatch;

    println(
        "BANK smoke passed: position={}, funded={}, target={}, open={}",
        positionId,
        position.fundedAmount,
        position.targetPayout,
        queue.openPositions,
    );
}
