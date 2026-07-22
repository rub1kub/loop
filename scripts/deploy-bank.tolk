import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

fun main() {
    val deployer = scripts.wallet("deployer");
    val bank = BankQueue.fromStorage({
        owner: deployer.address,
        treasury: deployer.address,
        feeBps: 100,
        paused: false,
        headQueueIndex: 0,
        nextQueueIndex: 0,
        lockedFunding: 0,
        positions: [],
        queue: [],
        activePositions: [],
        usedPositionIds: [],
    });
    val result = bank.deploy(deployer.address, { value: ton("0.2") });
    println(result.waitForTrace());
    println("LOOP BankQueue deployed to {}", bank.address);
}
