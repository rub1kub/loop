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
    expect(contract.activePosition(first.address)).toEqual(POSITION_A);
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
    // A settled position is pruned from storage, so `positionData` no longer
    // answers for it: the payout message above is its public proof, and the
    // dictionary stays proportional to the live queue rather than to lifetime
    // history.
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
    // Both settled positions are pruned; the two payout messages above are the
    // evidence that they closed.
    expect(contract.queueData().headQueueIndex).toEqual(3);
    expect(contract.queueData().openPositions).toEqual(1);
}

get fun `test allocation step cap rejects corrupted oversized queue work`() {
    val owner = testing.treasury("bank-cap-owner");
    val treasury = testing.treasury("bank-cap-treasury");
    val legacyOwner = testing.treasury("bank-cap-legacy");
    val depositor = testing.treasury("bank-cap-depositor");
    var positions = [] as PositionMap;
    var queue = [] as QueueMap;
    var used = [] as UsedPositionMap;
    var index: uint64 = 0;
    repeat (82) {
        val positionId: uint64 = 5_000 + index;
        positions.set(
            positionId,
            BankPositionData {
                owner: legacyOwner.address,
                principal: 1,
                multiplierBps: 12_500,
                targetPayout: 1,
                fundedAmount: 0,
                queueIndex: index,
                createdAt: 1,
                completedAt: 0,
                status: BANK_POSITION_QUEUED,
            }.toCell(),
        );
        queue.set(index, positionId);
        used.set(positionId, true);
        index += 1;
    }
    val contract = BankQueue.fromStorage({
        owner: owner.address,
        treasury: treasury.address,
        feeBps: 0,
        paused: false,
        headQueueIndex: 0,
        nextQueueIndex: 82,
        completedPositions: 10_000,
        lockedFunding: 0,
        positions,
        queue,
        activePositions: ([] as ActivePositionMap),
        usedPositionIds: used,
    });
    expect(
        contract.deploy(owner.address, { value: ton("1") }),
    ).toHaveSuccessfulDeploy({ to: contract.address });
    expect(
        openPosition(contract, depositor, POSITION_A, ton("100"), 12_500),
    ).toHaveFailedTx({ exitCode: BankErrors.AllocationLimit });
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

get fun `test create-position guards fail before queue mutation`() {
    val (contract, owner, _, first, _) = setupBank(0);
    expect(
        contract.sendSetBankPaused(
            owner.address,
            1_101,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
    expect(
        openPosition(contract, first, POSITION_A, ton("1"), 12_500),
    ).toHaveFailedTx({ exitCode: BankErrors.Paused });
    expect(
        contract.sendSetBankPaused(
            owner.address,
            1_102,
            false,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
    expect(
        openPosition(contract, first, 0, ton("1"), 12_500),
    ).toHaveFailedTx({ exitCode: BankErrors.PositionAlreadyUsed });
    expect(contract.queueData().openPositions).toEqual(0);
}

get fun `test zero fee emits no protocol transfer`() {
    val (contract, _, treasury, first, _) = setupBank(0);
    val opened = openPosition(contract, first, POSITION_A, ton("1"), 12_500);
    expect(opened).toHaveSuccessfulTx<CreatePosition>();
    expect(opened).toNotHaveTx<BankProtocolFee>({
        from: contract.address,
        to: treasury.address,
    });
}

get fun `test BANK opens at one GRAM and each rung needs five payouts per GRAM`() {
    // A fresh queue has proved nothing, so it carries the smallest position
    // the contract accepts and refuses a hair more.
    val (fresh, _, _, first, second) = setupBankAtCompleted(0, 0);
    expect(fresh.queueData().principalLimit).toEqual(ton("1"));
    expect(
        openPosition(fresh, first, POSITION_A, ton("1"), 12_500),
    ).toHaveSuccessfulTx<CreatePosition>();
    expect(
        openPosition(fresh, second, POSITION_B, ton("1.000000001"), 12_500),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidPrincipal });

    // One payout short of a rung the old cap still stands.
    val (justShort, _, _, _, _) = setupBankAtCompleted(0, 9);
    expect(justShort.queueData().principalLimit).toEqual(ton("1"));

    val (twoGram, _, _, third, _) = setupBankAtCompleted(0, 10);
    expect(twoGram.queueData().principalLimit).toEqual(ton("2"));
    expect(
        openPosition(twoGram, third, POSITION_C, ton("2"), 12_500),
    ).toHaveSuccessfulTx<CreatePosition>();

    val (fiveGram, _, _, fourth, _) = setupBankAtCompleted(0, 25);
    expect(fiveGram.queueData().principalLimit).toEqual(ton("5"));
    expect(
        openPosition(fiveGram, fourth, POSITION_D, ton("5.000000001"), 12_500),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidPrincipal });
}

get fun `test BANK ladder climbs to one hundred GRAM and stops there`() {
    val (ten, _, _, _, _) = setupBankAtCompleted(0, 50);
    expect(ten.queueData().principalLimit).toEqual(ton("10"));

    val (thirty, _, _, first, _) = setupBankAtCompleted(0, 150);
    expect(thirty.queueData().principalLimit).toEqual(ton("30"));
    expect(
        openPosition(thirty, first, POSITION_A, ton("30"), 12_500),
    ).toHaveSuccessfulTx<CreatePosition>();

    // The top rung is not a round-number choice: the allocation loop is
    // bounded at 81 steps, and a deposit past ~112 GRAM cannot be spread over
    // a queue of minimum positions without reverting.
    val (capped, _, _, _, _) = setupBankAtCompleted(0, 10_000);
    expect(capped.queueData().principalLimit).toEqual(ton("100"));

    val (stillCapped, _, _, second, _) = setupBankAtCompleted(0, 1_000_000);
    expect(stillCapped.queueData().principalLimit).toEqual(ton("100"));
    expect(
        openPosition(stillCapped, second, POSITION_B, ton("100.000000001"), 12_500),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidPrincipal });
}

get fun `test a rung holds until its last missing payout arrives`() {
    val (contract, _, _, player, _) = setupBankAtCompleted(0, 99);
    expect(contract.contractConfig().principalLimit).toEqual(ton("15"));
    expect(
        openPosition(contract, player, POSITION_A, ton("20"), 12_500),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidPrincipal });
    expect(contract.queueData().openPositions).toEqual(0);

    val (unlocked, _, _, next, _) = setupBankAtCompleted(0, 100);
    expect(unlocked.contractConfig().principalLimit).toEqual(ton("20"));
    expect(
        openPosition(unlocked, next, POSITION_B, ton("20"), 12_500),
    ).toHaveSuccessfulTx<CreatePosition>();
}

get fun `test owner can fund reserve and withdraw only free balance while paused`() {
    val (contract, owner, treasury, _, _) = setupBank(100);
    expect(
        contract.sendBankFundReserve(
            owner.address,
            2_001,
            ton("1"),
            { value: ton("1.02") },
        ),
    ).toHaveSuccessfulTx<BankFundReserve>();

    val whileRunning = contract.sendBankWithdrawSurplus(
        owner.address,
        2_002,
        ton("0.5"),
        { value: ton("0.05") },
    );
    expect(whileRunning).toHaveFailedTx({ exitCode: BankErrors.MustBePaused });

    expect(
        contract.sendSetBankPaused(
            owner.address,
            2_003,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
    expect(
        contract.sendBankWithdrawSurplus(
            owner.address,
            2_003,
            ton("0.1"),
            { value: ton("0.049999999") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InsufficientValue });
    val withdrawal = contract.sendBankWithdrawSurplus(
        owner.address,
        2_004,
        ton("0.5"),
        { value: ton("0.05") },
    );
    expect(withdrawal).toHaveSuccessfulTx<BankAdminWithdrawal>({
        from: contract.address,
        to: treasury.address,
        value: ton("0.5"),
    });
}

get fun `test BANK surplus withdrawal cannot touch position funding`() {
    val (contract, owner, _, first, _) = setupBank(0);
    openPosition(contract, first, POSITION_A, ton("1"), 20_000);
    expect(
        contract.sendSetBankPaused(
            owner.address,
            2_101,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
    expect(contract.adminState().lockedFunding).toEqual(ton("1"));
    val excessive = contract.sendBankWithdrawSurplus(
        owner.address,
        2_102,
        ton("10"),
        { value: ton("0.05") },
    );
    expect(excessive).toHaveFailedTx({ exitCode: BankErrors.InsufficientSurplus });
    expect(contract.contractConfig().lockedFunding).toEqual(ton("1"));
}

get fun `test BANK withdrawal boundary excludes locked value and inbound gas`() {
    val (lockedContract, owner, _, first, _) = setupBank(0);
    openPosition(lockedContract, first, POSITION_A, ton("1"), 20_000);
    expect(
        lockedContract.sendSetBankPaused(
            owner.address,
            2_111,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
    val lockedBalance = testing.getAccountBalance(lockedContract.address);
    val lockedFree = lockedBalance - ton("1") - ton("0.2");
    expect(
        lockedContract.sendBankWithdrawSurplus(
            owner.address,
            2_112,
            lockedFree + 1,
            { value: ton("0.05") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InsufficientSurplus });

    val (exactContract, exactOwner, exactTreasury, _, _) = setupBankAtCompleted(100, 101);
    expect(
        exactContract.sendSetBankPaused(
            exactOwner.address,
            2_113,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
    val exactFree = testing.getAccountBalance(exactContract.address) - ton("0.2");
    expect(
        exactContract.sendBankWithdrawSurplus(
            exactOwner.address,
            2_114,
            exactFree,
            { value: ton("0.05") },
        ),
    ).toHaveSuccessfulTx<BankAdminWithdrawal>({
        from: exactContract.address,
        to: exactTreasury.address,
        value: exactFree,
    });
}

get fun `test BANK configuration changes require the paused owner`() {
    val (contract, owner, _, first, second) = setupBank(100);
    expect(
        contract.sendBankSetFee(
            owner.address,
            2_201,
            200,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.MustBePaused });
    expect(
        contract.sendSetBankPaused(
            owner.address,
            2_202,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
    expect(
        contract.sendBankSetFee(
            first.address,
            2_203,
            200,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.NotOwner });
    expect(
        contract.sendBankSetFee(
            owner.address,
            2_204,
            1_001,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidFee });
    expect(
        contract.sendBankSetTreasury(
            owner.address,
            2_205,
            contract.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidTreasury });
    expect(
        contract.sendBankSetTreasury(
            owner.address,
            2_206,
            second.address,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<BankSetTreasury>();
    expect(
        contract.sendBankSetFee(
            owner.address,
            2_207,
            200,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<BankSetFee>();
    expect(
        contract.sendBankSetOwner(
            owner.address,
            2_208,
            first.address,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<BankSetOwner>();
    val admin = contract.adminState();
    expect(admin.owner).toEqual(first.address);
    expect(admin.treasury).toEqual(second.address);
    expect(admin.feeBps).toEqual(200);
    expect(
        contract.sendSetBankPaused(
            owner.address,
            2_209,
            false,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.NotOwner });
    expect(
        contract.sendSetBankPaused(
            first.address,
            2_210,
            false,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
}

get fun `test every BANK admin boundary fails closed`() {
    val (contract, owner, _, first, second) = setupBank(100);
    expect(
        contract.sendSetBankPaused(
            owner.address,
            2_301,
            true,
            { value: ton("0.019999999") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InsufficientValue });
    expect(
        contract.sendBankFundReserve(
            owner.address,
            2_302,
            0,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidAdminAmount });
    expect(
        contract.sendBankFundReserve(
            owner.address,
            2_303,
            ton("1"),
            { value: ton("1.019999999") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InsufficientValue });
    expect(
        contract.sendBankSetTreasury(
            owner.address,
            2_304,
            second.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.MustBePaused });
    expect(
        contract.sendBankSetOwner(
            owner.address,
            2_305,
            first.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.MustBePaused });
    expect(
        contract.sendSetBankPaused(
            owner.address,
            2_306,
            true,
            { value: ton("0.02") },
        ),
    ).toHaveSuccessfulTx<SetBankPaused>();
    expect(
        contract.sendBankWithdrawSurplus(
            owner.address,
            2_307,
            0,
            { value: ton("0.05") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidAdminAmount });
    expect(
        contract.sendBankSetFee(
            owner.address,
            2_308,
            200,
            { value: ton("0.019999999") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InsufficientValue });
    expect(
        contract.sendBankSetTreasury(
            owner.address,
            2_309,
            second.address,
            { value: ton("0.019999999") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InsufficientValue });
    expect(
        contract.sendBankSetOwner(
            owner.address,
            2_310,
            first.address,
            { value: ton("0.019999999") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InsufficientValue });
    expect(
        contract.sendBankSetOwner(
            owner.address,
            2_311,
            owner.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidOwner });
    expect(
        contract.sendBankSetOwner(
            owner.address,
            2_312,
            contract.address,
            { value: ton("0.02") },
        ),
    ).toHaveFailedTx({ exitCode: BankErrors.InvalidOwner });
    val malformed = contract.sendAny(
        first.address,
        beginCell().storeUint(0xDEADBEEF, 32).endCell(),
        { value: ton("0.02") },
    );
    expect(malformed).toHaveFailedTx({ exitCode: BankErrors.InvalidMessage });
}

fun setupBank(feeBps: uint16): (BankQueue, Treasury, Treasury, Treasury, Treasury) {
    return setupBankAtCompleted(feeBps, 100);
}

fun setupBankAtCompleted(
    feeBps: uint16,
    completedPositions: uint64,
): (BankQueue, Treasury, Treasury, Treasury, Treasury) {
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
        completedPositions,
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
