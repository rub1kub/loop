import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"

// Resolves two wallet aliases to their addresses on the network this script is
// run against. `acton wallet list` always answers in a testnet context, so
// anything that needs a mainnet address has to ask under `--net mainnet`
// instead — the two differ, because a v5r1 address depends on the network.
fun main(firstWallet: string, secondWallet: string) {
    println("WALLET {} {}", firstWallet, scripts.wallet(firstWallet).address);
    println("WALLET {} {}", secondWallet, scripts.wallet(secondWallet).address);
}
