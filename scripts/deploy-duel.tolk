import "@acton/env"
import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"

enum DeployErrors {
    InvalidNetwork = 970
    InvalidInviteSigner = 971
    MissingMainnetOwner = 972
    MainnetMustStartPaused = 973
}

fun main(networkId: int32, inviteSignerPublicKey: uint256, startPaused: bool) {
    assert (networkId == -3 || networkId == -239) throw DeployErrors.InvalidNetwork;
    assert (inviteSignerPublicKey != 0) throw DeployErrors.InvalidInviteSigner;
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
    val escrow = DuelEscrow.fromStorage({
        owner,
        treasury,
        feeBps: 250,
        networkId,
        inviteSignerPublicKey,
        paused: startPaused,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    val result = escrow.deploy(deployer.address, { value: ton("0.5") });
    println(result.waitForTrace());
    println("LOOP DuelEscrow deployed to {}", escrow.address);
}
