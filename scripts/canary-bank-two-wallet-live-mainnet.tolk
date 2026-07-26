import "@acton/emulation/scripts"
import "@bank_canary/logic"

fun main(
    bankAddress: address,
    firstPositionId: uint64,
    secondPositionId: uint64,
) {
    val firstWallet = scripts.wallet("loop-mainnet-canary-a");
    val secondWallet = scripts.wallet("loop-mainnet-canary-b");
    runBankCycle(
        bankAddress,
        firstPositionId,
        secondPositionId,
        firstWallet.address,
        secondWallet.address,
    );
}
