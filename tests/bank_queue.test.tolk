import "@acton/emulation/network"
import "@acton/emulation/testing"
import "@acton/testing/expect"

import "@wrappers/BankQueue.gen"
import "@contracts/bank/errors"
import "@contracts/bank/messages"
import "@contracts/bank/storage"

const POSITION_A: uint64 = 1_001
const POSITION_B: uint64 = 1_002
const POSITION_C: uint64 = 1_003
const POSITION_D: uint64 = 1_004

fun openPosition(
    contract: BankQueue,
    player: Treasury,
    positionId: uint64,
    principal: coins,
    multiplierBps: uint16,
): SendResultList {
    return contract.sendCreatePosition(
        player.address,
        positionId,
        positionId,
        principal,
        multiplierBps,
        { value: principal + ton("0.08") },
    );
}

get fun `test first position keeps all distributable value in the user cycle`() {
    val (contract, _, _, first, _) = setupBank(0);
    val result = openPosition(contract, first, POSITION_A, ton("10"), 12_500);

    expect(result).toHaveSuccessfulTx<CreatePosition>({
        from: first.address,
        to: contract.address,
    });
    val position = contract.positionData(POSITION_A);
    expect(position.owner).toEqual(first.address);
    expect(position.targetPayout).toEqual(ton("12.5"));
    expect(position.fundedAmount).toEqual(ton("10"));
    expect(position.status).toEqual(BANK_POSITION_PARTIALLY_FUNDED);
    expect(contract.queueData().openPositions).toEqual(1);
    expect(contract.contractConfig().lockedFunding).toEqual(ton("10"));
}

get fun `test later deposit partially funds the FIFO head`() {
    val (contract, _, _, first, second) = setupBank(0);
    openPosition(contract, first, POSITION_A, ton("10"), 20_000);
    openPosition(contract, second, POSITION_B, ton("5"), 15_000);

    val firstPosition = contract.positionData(POSITION_A);
    val secondPosition = contract.positionData(POSITION_B);
    expect(firstPosition.fundedAmount).toEqual(ton("15"));
    expect(firstPosition.status).toEqual(BANK_POSITION_PARTIALLY_FUNDED);
    expect(secondPosition.fundedAmount).toEqual(0);
    expect(secondPosition.status).toEqual(BANK_POSITION_QUEUED);
    expect(secondPosition.targetPayout).toEqual(ton("7.5"));
    expect(contract.contractConfig().lockedFunding).toEqual(ton("15"));
}

get fun `test exact funding sends payout and advances the head`() {
    val (contract, _, _, first, second) = setupBank(0);
    openPosition(contract, first, POSITION_A, ton("1"), 12_500);
    val result = openPosition(contract, second, POSITION_B, ton("1"), 15_000);

    expect(result).toHaveSuccessfulTx<BankPayout>({
        from: contract.address,
        to: first.address,
        value: ton("1.25"),
    });
    val completed = contract.positionData(POSITION_A);
    expect(completed.status).toEqual(BANK_POSITION_PAYOUT_SENT);
    expect(completed.fundedAmount).toEqual(completed.targetPayout);
    expect(contract.positionData(POSITION_B).fundedAmount).toEqual(ton("0.75"));
    expect(contract.queueData().headQueueIndex).toEqual(1);
    expect(contract.queueData().openPositions).toEqual(1);
}

get fun `test one deposit cascades across multiple older positions`() {
    val (contract, _, _, first, second) = setupBank(0);
    val third = testing.treasury("bank-third");
    val fourth = testing.treasury("bank-fourth");
    openPosition(contract, first, POSITION_A, ton("1"), 20_000);
    openPosition(contract, second, POSITION_B, ton("1"), 20_000);
    openPosition(contract, third, POSITION_C, ton("1"), 20_000);

    val cascade = openPosition(contract, fourth, POSITION_D, ton("3"), 20_000);
    expect(cascade).toHaveSuccessfulTx<BankPayout>({
        from: contract.address,
        to: second.address,
        value: ton("2"),
    });
    expect(cascade).toHaveSuccessfulTx<BankPayout>({
        from: contract.address,
        to: third.address,
        value: ton("2"),
    });
    expect(contract.positionData(POSITION_B).status).toEqual(BANK_POSITION_PAYOUT_SENT);
    expect(contract.positionData(POSITION_C).status).toEqual(BANK_POSITION_PAYOUT_SENT);
    expect(contract.queueData().headQueueIndex).toEqual(3);
}

get fun `test BANK fee is separate and deterministic`() {
    val (contract, _, feeCollector, first, _) = setupBank(100);
    val result = openPosition(contract, first, POSITION_A, ton("10"), 20_000);

    expect(result).toHaveSuccessfulTx<BankProtocolFee>({
        from: contract.address,
        to: feeCollector.address,
        value: ton("0.1"),
    });
    expect(contract.contractConfig().lockedFunding).toEqual(ton("9.9"));
    expect(contract.positionData(POSITION_A).fundedAmount).toEqual(ton("9.9"));
    expect(contract.positionData(POSITION_A).targetPayout).toEqual(ton("20"));
}

get fun `test serialized deposits preserve every distributable nano`() {
    val (contract, _, feeCollector, first, second) = setupBank(100);
    val third = testing.treasury("bank-third-invariant");
    openPosition(contract, first, POSITION_A, ton("10"), 20_000);
    openPosition(contract, second, POSITION_B, ton("10"), 20_000);
    val result = openPosition(contract, third, POSITION_C, ton("10"), 20_000);

    expect(result).toHaveSuccessfulTx<BankPayout>({
        from: contract.address,
        to: first.address,
        value: ton("20"),
    });
    expect(result).toHaveSuccessfulTx<BankProtocolFee>({
        from: contract.address,
        to: feeCollector.address,
        value: ton("0.1"),
    });
    expect(contract.positionData(POSITION_B).fundedAmount).toEqual(ton("9.7"));
    expect(contract.positionData(POSITION_C).fundedAmount).toEqual(0);
    expect(contract.contractConfig().lockedFunding).toEqual(ton("9.7"));
}

get fun `test duplicate position id and concurrent owner position are rejected`() {
    val (contract, _, _, first, second) = setupBank(0);
    openPosition(contract, first, POSITION_A, ton("1"), 12_500);

    val duplicateId = openPosition(contract, second, POSITION_A, ton("1"), 12_500);
    expect(duplicateId).toHaveFailedTx({
        from: second.address,
        to: contract.address,
        exitCode: BankErrors.PositionAlreadyUsed,
    });

    val duplicateOwner = openPosition(contract, first, POSITION_B, ton("1"), 12_500);
    expect(duplicateOwner).toHaveFailedTx({
        from: first.address,
        to: contract.address,
        exitCode: BankErrors.OwnerAlreadyActive,
    });
}

get fun `test invalid multiplier and underfunded messages cannot mutate queue`() {
    val (contract, _, _, first, _) = setupBank(0);
    val invalidMultiplier = openPosition(contract, first, POSITION_A, ton("1"), 13_000);
    expect(invalidMultiplier).toHaveFailedTx({
        from: first.address,
        to: contract.address,
        exitCode: BankErrors.InvalidMultiplier,
    });

    val underfunded = contract.sendCreatePosition(
        first.address,
        POSITION_B,
        POSITION_B,
        ton("10"),
        12_500,
        { value: ton("1") },
    );
    expect(underfunded).toHaveFailedTx({
        from: first.address,
        to: contract.address,
        exitCode: BankErrors.InsufficientValue,
    });
    expect(contract.queueData().openPositions).toEqual(0);
}

fun setupBank(feeBps: uint16): (BankQueue, Treasury, Treasury, Treasury, Treasury) {
    val owner = testing.treasury("bank-owner");
    val feeCollector = testing.treasury("bank-fee");
    val first = testing.treasury("bank-first");
    val second = testing.treasury("bank-second");
    val contract = BankQueue.fromStorage({
        owner: owner.address,
        treasury: feeCollector.address,
        feeBps,
        paused: false,
        headQueueIndex: 0,
        nextQueueIndex: 0,
        lockedFunding: 0,
        positions: ([] as PositionMap),
        queue: ([] as QueueMap),
        activePositions: ([] as ActivePositionMap),
        usedPositionIds: ([] as UsedPositionMap),
    });
    val deployed = contract.deploy(owner.address, { value: ton("1") });
    expect(deployed).toHaveSuccessfulDeploy({ to: contract.address });
    return (contract, owner, feeCollector, first, second);
}
