import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

// Reads one BankQueue's configuration from the chain, so a manifest can be
// filled from the deployed contract rather than from what the source says it
// ought to be.
fun main(bankAddress: address) {
    val config = BankQueue.fromAddress(bankAddress).contractConfig();
    println("owner              {}", config.owner);
    println("treasury           {}", config.treasury);
    println("feeBps             {}", config.feeBps);
    println("paused             {}", config.paused);
    println("headQueueIndex     {}", config.headQueueIndex);
    println("nextQueueIndex     {}", config.nextQueueIndex);
    println("completedPositions {}", config.completedPositions);
    println("principalLimit     {}", config.principalLimit);
    println("lockedFunding      {}", config.lockedFunding);
}
