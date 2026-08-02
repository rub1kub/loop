import "@acton/emulation/scripts"
import "@bank_canary/logic"

/// Runs the full BANK payout cycle against a throwaway shadow on mainnet.
///
/// Uses the canary and deployer wallets rather than the canary pair: those two
/// are the ones the treasury keeps funded, and the cycle needs a little over
/// one GRAM in each. The production queue can never run this — a completed
/// cycle leaves it non-pristine forever.
fun main(shadowAddress: address, firstPositionId: uint64, secondPositionId: uint64) {
    runBankCycle(
        shadowAddress,
        firstPositionId,
        secondPositionId,
        scripts.wallet("loop-mainnet-canary").address,
        scripts.wallet("loop-mainnet-deployer").address,
    );
}
