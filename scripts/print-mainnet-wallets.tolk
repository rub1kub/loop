import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"

// Prints each mainnet wallet's address as resolved for the network this script
// is run against. Run it with `--net mainnet`: `acton wallet list` reports the
// testnet address instead, and the two differ because a v5r1 wallet's address
// depends on the network global id.
fun main() {
    println("deployer  {}", scripts.wallet("loop-mainnet-deployer").address);
    println("owner     {}", scripts.wallet("loop-mainnet-owner").address);
    println("treasury  {}", scripts.wallet("loop-mainnet-treasury").address);
    println("canary    {}", scripts.wallet("loop-mainnet-canary").address);
}
