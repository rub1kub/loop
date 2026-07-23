import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"

enum DeployErrors {
    InvalidNetwork = 970
    InvalidInviteSigner = 971
}

fun main(networkId: int32, inviteSignerPublicKey: uint256) {
    assert (networkId == -3 || networkId == -239) throw DeployErrors.InvalidNetwork;
    assert (inviteSignerPublicKey != 0) throw DeployErrors.InvalidInviteSigner;
    val deployer = scripts.wallet("deployer");
    val escrow = DuelEscrow.fromStorage({
        owner: deployer.address,
        treasury: deployer.address,
        feeBps: 250,
        networkId,
        inviteSignerPublicKey,
        paused: false,
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
