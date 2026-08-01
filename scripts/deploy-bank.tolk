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
    // Bind the signing wallet to the target network with literals: a runtime
    // string cannot be used here because emulation resolves the name through
    // `testing.treasury`, which parses it as a compile-time slice. Binding it
    // this way also makes it impossible to sign a mainnet deployment with the
    // testnet key, which holds no mainnet funds.
    val deployer = networkId == -239
        ? scripts.wallet("loop-mainnet-deployer")
        : scripts.wallet("deployer");
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
        feeBps: 1000,
        paused: startPaused,
        headQueueIndex: 0,
        nextQueueIndex: 0,
        completedPositions: 0,
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
