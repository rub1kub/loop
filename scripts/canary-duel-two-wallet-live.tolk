import "@acton/emulation/scripts"
import "@canary/logic"

const CANARY_ENTRY_NETWORK_ID: int32 = -3

fun main(
    duelAddress: address,
    firstOfferId: uint64,
    secondOfferId: uint64,
    expiresAt: uint32,
    phase: uint8,
) {
    val firstWallet = scripts.wallet("loop-canary-a");
    val secondWallet = scripts.wallet("loop-canary-b");
    if (phase == 1) {
        runCanaryOpenAndBoost(
            duelAddress,
            CANARY_ENTRY_NETWORK_ID,
            firstOfferId,
            secondOfferId,
            expiresAt,
            firstWallet.address,
            secondWallet.address,
        );
    } else {
        assert (phase == 2) throw CanaryErrors.InvalidPhase;
        runCanarySettle(
            duelAddress,
            CANARY_ENTRY_NETWORK_ID,
            firstOfferId,
            secondOfferId,
            firstWallet.address,
            secondWallet.address,
        );
    }
}
