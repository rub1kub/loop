import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"

fun main() {
    val deployer = scripts.wallet("deployer");
    val escrow = DuelEscrow.fromStorage({
        owner: deployer.address,
        treasury: deployer.address,
        feeBps: 250,
        paused: false,
        locked: 0,
        offers: [],
        duels: [],
        activeOffers: [],
        usedOfferIds: [],
    });
    val result = escrow.deploy(deployer.address, { value: ton("0.2") });
    println(result.waitForTrace());
    println("LOOP DuelEscrow deployed to {}", escrow.address);
}
