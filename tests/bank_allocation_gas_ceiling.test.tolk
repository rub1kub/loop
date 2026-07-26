// Characterisation tests for a KNOWN, UNFIXED limitation of BankQueue 1.3.0.
//
// `BANK_MAX_ALLOCATION_STEPS = 81` is unreachable: a walk long enough to trip
// it exhausts the 1M basechain gas limit at roughly 69 steps first, so a large
// deposit against a long queue aborts with exit -14 instead of the intended
// AllocationLimit throw. The principal bounces back to a normal wallet, but
// large deposits stay unusable until the queue drains through smaller ones.
//
// Reachable only once principalLimit has matured past ~90 GRAM, i.e. after
// roughly 3850 completed positions. These tests preload that maturity counter
// and nothing else: every deposit below goes through the real CreatePosition
// handler. They also UNDERSTATE the problem, because they start with empty
// positions/usedPositionIds dictionaries, while a contract with that many
// completions would carry thousands of entries and pay more gas per step.
//
// When a future BankQueue makes long cascades survivable, these expectations
// are meant to change.

import "@acton/emulation/network"
import "@acton/emulation/testing"
import "@acton/testing/expect"

import "@wrappers/BankQueue.gen"
import "@contracts/bank/errors"
import "@contracts/bank/messages"
import "@contracts/bank/storage"

const OUT_OF_GAS = -14

fun depositor(i: int): address {
    return address.fromWorkchainAndHash(0, 0xA77AC000 + i);
}

fun matureBank(): BankQueue {
    val owner = testing.treasury("scratch-owner");
    val treasury = testing.treasury("scratch-treasury");
    val contract = BankQueue.fromStorage({
        owner: owner.address,
        treasury: treasury.address,
        feeBps: 0,
        paused: false,
        headQueueIndex: 0,
        nextQueueIndex: 0,
        // >= 4350 completions, so principalLimit has matured to its 100 GRAM cap
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

/// Every message below is a plain, legal `CreatePosition`:
/// distinct senders, principals inside [1 GRAM, principalLimit], allowed multipliers.
///
///  1. one whale takes the maximum position: 100 GRAM x 2.0 -> targetPayout 200 GRAM.
///     The queue was empty, so it is self-funded with its own 100 GRAM distributable
///     and sits at the head needing 100 GRAM more.
///  2. 89 ordinary users take the *minimum* position: 1 GRAM x 1.25 -> targetPayout
///     1.25 GRAM. Each one's 1 GRAM is swallowed by the whale head, so all 89 stay
///     at fundedAmount == 0. Head residual is now 200 - 189 = 11 GRAM.
///
/// The queue is now 90 deep and the next maximum deposit has to walk 73 of them.
fun buildQueue(smallPositions: int): BankQueue {
    val contract = matureBank();
    expect(contract.queueData().principalLimit).toEqual(ton("100"));

    expect(deposit(contract, 0, ton("100"), 20_000)).toHaveSuccessfulTx<CreatePosition>();
    expect(contract.positionData(7_000).targetPayout).toEqual(ton("200"));
    expect(contract.positionData(7_000).fundedAmount).toEqual(ton("100"));

    var i = 1;
    while (i <= smallPositions) {
        expect(deposit(contract, i, ton("1"), 12_500)).toHaveSuccessfulTx<CreatePosition>();
        expect(contract.positionData((7_000 + i) as uint64).fundedAmount).toEqual(0);
        i += 1;
    }
    expect(
        contract.positionData(7_000).fundedAmount,
    ).toEqual(ton("100") + smallPositions * ton("1"));
    expect(contract.queueData().openPositions).toEqual(smallPositions + 1);

    // plenty of reserve, so nothing can fail for balance reasons
    testing.topUp(contract.address, ton("400"));
    return contract;
}

get fun `test legitimate maximum deposit reverts out of gas`() {
    val contract = buildQueue(89);

    // 100 GRAM x 1.25 -- the largest position the maturity limit allows.
    //   step  1     : 11 GRAM closes the whale head (payout 200 GRAM)
    //   steps 2..72 : 71 x 1.25 GRAM closes 71 minimum positions
    //   step  73    : 0.25 GRAM partially funds the 72nd
    // 73 <= BANK_MAX_ALLOCATION_STEPS, so the AllocationLimit guard never fires --
    // the transaction dies in the compute phase first.
    val attack = deposit(contract, 200, ton("100"), 12_500);
    expect(attack).toHaveFailedTx({ to: contract.address, exitCode: OUT_OF_GAS });

    // state is untouched: nobody in the queue got paid, the depositor got nothing
    expect(contract.queueData().headQueueIndex).toEqual(0);
    expect(contract.queueData().openPositions).toEqual(90);
}

get fun `test 68 allocation steps still fit in the 1M gas limit`() {
    // 94 GRAM => 1 + 66 full closes + 1 partial = 68 steps
    expect(
        deposit(buildQueue(89), 200, ton("94"), 12_500),
    ).toHaveSuccessfulTx<CreatePosition>();
}

get fun `test 69 allocation steps blow the gas limit long before step 81`() {
    // 96 GRAM => 1 + 68 full closes = 69 steps: compute phase runs out of gas.
    // BANK_MAX_ALLOCATION_STEPS = 81 is therefore dead code on basechain:
    // the loop can never survive long enough to trip it.
    expect(
        deposit(buildQueue(89), 200, ton("96"), 12_500),
    ).toHaveFailedTx({ exitCode: OUT_OF_GAS });
}

get fun `test the broken state persists and blocks every large deposit`() {
    val contract = buildQueue(89);
    expect(deposit(contract, 200, ton("100"), 12_500)).toHaveFailedTx({ exitCode: OUT_OF_GAS });
    // a different user, same legal deposit, same revert -- it is a property of the
    // queue, not of one message
    expect(deposit(contract, 201, ton("100"), 12_500)).toHaveFailedTx({ exitCode: OUT_OF_GAS });
    expect(deposit(contract, 202, ton("99"), 12_500)).toHaveFailedTx({ exitCode: OUT_OF_GAS });

    // only small deposits still get through, so the queue can only be drained
    // in crawling increments while the whale-sized deposits keep bouncing
    expect(deposit(contract, 203, ton("5"), 12_500)).toHaveSuccessfulTx<CreatePosition>();
    expect(deposit(contract, 204, ton("100"), 12_500)).toHaveFailedTx({ exitCode: OUT_OF_GAS });
}

// ---------------------------------------------------------------------------
// How mature does BANK have to be before this is reachable?
// ---------------------------------------------------------------------------

fun bankAtCompleted(completed: uint64, tag: string): BankQueue {
    val owner = testing.treasury(tag);
    val treasury = testing.treasury("scratch-treasury");
    val contract = BankQueue.fromStorage({
        owner: owner.address,
        treasury: treasury.address,
        feeBps: 0,
        paused: false,
        headQueueIndex: 0,
        nextQueueIndex: 0,
        completedPositions: completed,
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

get fun `test reachable at 3850 completions where principalLimit is only 90 GRAM`() {
    val contract = bankAtCompleted(3_850, "scratch-owner-3850");
    expect(contract.queueData().principalLimit).toEqual(ton("90"));

    expect(deposit(contract, 0, ton("90"), 20_000)).toHaveSuccessfulTx<CreatePosition>();
    var i = 1;
    while (i <= 89) {
        expect(deposit(contract, i, ton("1"), 12_500)).toHaveSuccessfulTx<CreatePosition>();
        i += 1;
    }
    // head: target 180, funded 179, residual 1 GRAM
    expect(contract.positionData(7_000).fundedAmount).toEqual(ton("179"));
    testing.topUp(contract.address, ton("400"));

    // 90 GRAM => 1 + 71 full closes + 1 partial = 73 steps
    expect(deposit(contract, 200, ton("90"), 12_500)).toHaveFailedTx({ exitCode: OUT_OF_GAS });
    expect(contract.queueData().headQueueIndex).toEqual(0);
}

get fun `test a bouncing wallet gets its principal back but stays unable to deposit`() {
    val contract = buildQueue(89);
    val from = depositor(300);
    testing.topUp(from, ton("200"));
    val before = testing.getAccountBalance(from);
    val attack = contract.sendCreatePosition(
        from,
        9_300,
        9_300,
        ton("100"),
        12_500,
        { value: ton("100.08"), bounce: true },
    );
    expect(attack).toHaveFailedTx({ to: contract.address, exitCode: OUT_OF_GAS });
    // principal comes back on the bounce, so this is a liveness break, not theft
    expect(testing.getAccountBalance(from) > before - ton("1")).toEqual(true);
    expect(contract.queueData().openPositions).toEqual(90);
}
