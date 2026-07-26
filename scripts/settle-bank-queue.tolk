import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"
import "@contracts/bank/storage"

/// Settles the BANK queue down to `lockedFunding == 0` so the contract can be
/// retired without stranding anyone's funding.
///
/// The queue never empties on its own: whatever a deposit does not consume
/// seeds the next position, so locked value moves between participants instead
/// of disappearing. It can be driven to zero, but only deliberately — the
/// head's remaining need has to be prepared so that one later deposit covers it
/// exactly, leaving no remainder to seed anything.
///
/// This is an owner-operated migration tool, not a user path. It pays every
/// waiting position in full; the wallet that sends the final deposit knowingly
/// receives nothing, because its whole contribution closes the last obligation.
enum SettleErrors {
    WalletUnknown = 980
    NothingToSettle = 981
    UnexpectedLocked = 982
}

fun walletFor(index: int): ActonWallet {
    if (index == 0) {
        return scripts.wallet("deployer");
    }
    if (index == 1) {
        return scripts.wallet("loop-canary-a");
    }
    assert (index == 2) throw SettleErrors.WalletUnknown;
    return scripts.wallet("loop-canary-b");
}

fun main(
    bankAddress: address,
    walletIndex: int,
    positionId: uint64,
    principal: coins,
    multiplierBps: uint16,
    expectedLockedAfter: coins,
) {
    val sender = walletFor(walletIndex);
    val bank = BankQueue.fromAddress(bankAddress);
    val before = bank.contractConfig();
    assert (before.lockedFunding > 0) throw SettleErrors.NothingToSettle;
    println(
        "SETTLE_BEFORE locked={} head={} next={} fee_bps={}",
        before.lockedFunding,
        before.headQueueIndex,
        before.nextQueueIndex,
        before.feeBps,
    );

    val result = bank.sendCreatePosition(
        sender.address,
        positionId,
        positionId,
        principal,
        multiplierBps,
        { value: principal + ton("0.08") },
    );
    println(result.waitForTrace());

    val after = bank.contractConfig();
    println(
        "SETTLE_AFTER locked={} head={} next={}",
        after.lockedFunding,
        after.headQueueIndex,
        after.nextQueueIndex,
    );
    // Stated up front by the caller, so a miscalculated deposit is loud rather
    // than quietly leaving a fresh obligation behind.
    assert (after.lockedFunding == expectedLockedAfter) throw SettleErrors.UnexpectedLocked;
}
