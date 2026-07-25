import "@acton/env"
import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

enum DeployErrors {
    InvalidNetwork = 970
    MissingMainnetOwner = 971
    MainnetMustStartPaused = 972
}

fun main(networkId: int32, startPaused: bool) {
    assert (networkId == -3 || networkId == -239) throw DeployErrors.InvalidNetwork;
    val deployer = scripts.wallet("deployer");
    val configuredOwner = env<address>("LOOP_CONTRACT_OWNER_ADDRESS");
    val configuredTreasury = env<address>("LOOP_CONTRACT_TREASURY_ADDRESS");
    if (networkId == -239) {
        assert (
            configuredOwner != null && configuredTreasury != null
        ) throw DeployErrors.MissingMainnetOwner;
        assert (startPaused) throw DeployErrors.MainnetMustStartPaused;
    }
    val owner = configuredOwner ?? deployer.address;
    val treasury = configuredTreasury ?? deployer.address;
    val bank = BankQueue.fromStorage({
        owner,
        treasury,
        feeBps: 100,
        paused: startPaused,
        headQueueIndex: 0,
        nextQueueIndex: 0,
        lockedFunding: 0,
        positions: [],
        queue: [],
        activePositions: [],
        usedPositionIds: [],
    });
    val result = bank.deploy(deployer.address, { value: ton("0.5") });
    println(result.waitForTrace());
    println("LOOP BankQueue deployed to {}", bank.address);
}
