import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

// Deploys a throwaway BankQueue for the mainnet payout smoke.
//
// The production queue can never run this test: BANK only pays a position out
// of later contributions, so a completed cycle leaves the queue non-pristine
// forever, and the readiness gate rejects a production manifest whose queue has
// already moved. The shadow therefore carries the same code and fee but a
// different treasury, which changes its state init and so its address.
//
// Deployed unpaused, unlike production: the whole point is to transact against
// it immediately.
fun main(ownerAddress: address, treasuryAddress: address) {
    val deployer = scripts.wallet("loop-mainnet-deployer");
    val bank = BankQueue.fromStorage({
        owner: ownerAddress,
        treasury: treasuryAddress,
        feeBps: 1000,
        paused: false,
        headQueueIndex: 0,
        nextQueueIndex: 0,
        completedPositions: 0,
        lockedFunding: 0,
        positions: [],
        queue: [],
        activePositions: [],
        usedPositionIds: [],
    });
    val result = bank.deploy(deployer.address, { value: ton("0.3") });
    println(result.waitForTrace());
    println("SHADOW BankQueue deployed to {}", bank.address);
}
