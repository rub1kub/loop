import "@acton/emulation/scripts"
import "@canary/logic"

const CANARY_ENTRY_NETWORK_ID: int32 = -3

/// Live evidence for the PLUSH BRICK zero-fee settlement. Both canary offers
/// carry a holder permit, so the settlement pays the full pool no matter which
/// secret wins and the outcome does not depend on chance.
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
            true,
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
