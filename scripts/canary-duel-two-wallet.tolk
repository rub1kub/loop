import "@acton/emulation/scripts"
import "@canary/logic"

const CANARY_ENTRY_NETWORK_ID: int32 = -3

fun main(
    duelAddress: address,
    firstOfferId: uint64,
    secondOfferId: uint64,
    expiresAt: uint32,
) {
    // Acton 1.0.0 resolves wallet aliases while preparing a script. Keep
    // testnet and mainnet entrypoints separate so keys cannot cross networks.
    val firstWallet = scripts.wallet("loop-canary-a");
    val secondWallet = scripts.wallet("loop-canary-b");
    runCanary(
        duelAddress,
        CANARY_ENTRY_NETWORK_ID,
        firstOfferId,
        secondOfferId,
        expiresAt,
        firstWallet.address,
        secondWallet.address,
    );
}
