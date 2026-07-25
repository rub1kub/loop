import "@acton/emulation/scripts"
import "@canary/logic"

const CANARY_ENTRY_NETWORK_ID: int32 = -239

fun main(
    duelAddress: address,
    firstOfferId: uint64,
    secondOfferId: uint64,
    expiresAt: uint32,
) {
    // This entrypoint is unreachable from the testnet timer and uses distinct
    // aliases that must be provisioned explicitly before a mainnet canary.
    val firstWallet = scripts.wallet("loop-mainnet-canary-a");
    val secondWallet = scripts.wallet("loop-mainnet-canary-b");
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
