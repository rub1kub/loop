import "@acton/emulation/scripts"
import "@bank_canary/logic"

fun main(
    bankAddress: address,
    firstPositionId: uint64,
    secondPositionId: uint64,
) {
    val firstWallet = scripts.wallet("deployer");
    val secondWallet = scripts.wallet("loop-canary-a");
    runBankCycle(
        bankAddress,
        firstPositionId,
        secondPositionId,
        firstWallet.address,
        secondWallet.address,
    );
}
