// The allocation cascade must survive its own worst case inside the basechain
// gas limit.
//
// BANK_MAX_ALLOCATION_STEPS = 81 is provably sufficient: a step past the head
// costs at least a 1.25 GRAM target, and a deposit is capped at 100 GRAM, so
// the extremal walk is 1 head residual + 79 full closes + 1 partial.
//
// Sufficiency alone was not enough. While settled positions were retained in
// storage, that same walk exhausted the 1M gas limit at roughly 69 steps, so a
// large deposit against a long queue aborted with exit -14 instead of ever
// reaching the guard, and kept aborting. Dropping settled positions removed the
// per-close write that caused it. These tests pin the result so the regression
// cannot come back quietly.

import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/testing"
import "@acton/testing/expect"

import "@acton/types/big_array"
import "@acton/types/transaction"
import "@wrappers/BankQueue.gen"
import "@contracts/bank/errors"
import "@contracts/bank/messages"
import "@contracts/bank/storage"

// Leaves ~14% of the basechain limit as headroom for compiler drift.
const GAS_REGRESSION_CEILING = 950_000

fun depositor(i: int): address {
    return address.fromWorkchainAndHash(0, 0xA77AC000 + i);
}

fun matureBank(): BankQueue {
    val owner = testing.treasury("gas-owner");
    val treasury = testing.treasury("gas-treasury");
    val contract = BankQueue.fromStorage({
        owner: owner.address,
        treasury: treasury.address,
        feeBps: 0,
        paused: false,
        headQueueIndex: 0,
        nextQueueIndex: 0,
        // Past third-stage maturity, so principalLimit sits at its 100 GRAM cap
        // and the largest possible deposit is available.
        completedPositions: 10_000,
        lockedFunding: 0,
        positions: ([] as PositionMap),
        queue: ([] as QueueMap),
        activePositions: ([] as ActivePositionMap),
        usedPositionIds: ([] as UsedPositionMap),
    });
    expect(
        contract.deploy(owner.address, { value: ton("1") }),
    ).toHaveSuccessfulDeploy({ to: contract.address });
    return contract;
}

fun deposit(
    contract: BankQueue,
    i: int,
    principal: coins,
    multiplierBps: uint16,
): SendResultList {
    val from = depositor(i);
    testing.topUp(from, principal + ton("1"));
    return contract.sendCreatePosition(
        from,
        (7_000 + i) as uint64,
        (7_000 + i) as uint64,
        principal,
        multiplierBps,
        { value: principal + ton("0.08") },
    );
}

/// Asserts the cascade stayed inside the gas budget. `toBeLessThan` does not
/// exist for integers in this framework, so the comparison is folded into a
/// boolean the matcher can check.
fun expectWithinGasBudget(used: int): void {
    expect(used > 0 && used < GAS_REGRESSION_CEILING).toEqual(true);
}

fun contractGas(result: SendResultList, contract: BankQueue): int {
    var index = 0;
    while (index < result.size()) {
        val tx = result.at(index).tx.load();
        if (tx.getAccountAddress() == contract.address) {
            return tx.getUsedGas();
        }
        index += 1;
    }
    return -1;
}

/// Builds the extremal queue: a head left with exactly one nanogram of
/// residual, behind it 80 minimum-size positions. Every message is a plain,
/// legal CreatePosition from a distinct sender.
fun extremalQueue(): BankQueue {
    val contract = matureBank();
    expect(deposit(contract, 0, ton("80") + 1, 20_000)).toHaveSuccessfulTx<CreatePosition>();
    var i = 1;
    while (i <= 80) {
        expect(deposit(contract, i, ton("1"), 12_500)).toHaveSuccessfulTx<CreatePosition>();
        i += 1;
    }
    expect(
        contract.positionData(7_000).targetPayout - contract.positionData(7_000).fundedAmount,
    ).toEqual(1);
    testing.topUp(contract.address, ton("500"));
    return contract;
}

get fun `test the worst reachable cascade fits in basechain gas`() {
    val contract = extremalQueue();
    // 1 nanogram closes the head, then 79 full closes, then one partial: the
    // 81 steps the guard was sized for.
    val worst = deposit(contract, 900, ton("100"), 12_500);
    expect(worst).toHaveSuccessfulTx<CreatePosition>();
    expect(contract.queueData().headQueueIndex).toEqual(80);
    expectWithinGasBudget(contractGas(worst, contract));
}

get fun `test settled positions are dropped so cascade cost stays bounded`() {
    val contract = extremalQueue();
    val worst = deposit(contract, 900, ton("100"), 12_500);
    expect(worst).toHaveSuccessfulTx<CreatePosition>();
    // Retaining settled records was what made this walk unaffordable; the
    // dictionary now shrinks as the cascade advances.
    expect(contract.queueData().openPositions).toEqual(2);
}

get fun `test a long queue still accepts the largest deposit`() {
    val contract = matureBank();
    expect(deposit(contract, 0, ton("100"), 20_000)).toHaveSuccessfulTx<CreatePosition>();
    var i = 1;
    while (i <= 89) {
        expect(deposit(contract, i, ton("1"), 12_500)).toHaveSuccessfulTx<CreatePosition>();
        i += 1;
    }
    testing.topUp(contract.address, ton("500"));
    // This is the sequence that used to brick every large deposit permanently.
    val large = deposit(contract, 900, ton("100"), 12_500);
    expect(large).toHaveSuccessfulTx<CreatePosition>();
    expect(contract.queueData().headQueueIndex > 0).toEqual(true);
    expectWithinGasBudget(contractGas(large, contract));
}
