import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"

/// Moves plain TON between two of the project's own wallets.
///
/// The mainnet smoke has to be paid for from the wallet that runs it, and the
/// balance sits wherever the last operation left it. Named rather than
/// hardcoded, because every one of these wallets resolves to a different
/// address depending on the network the script is run against.
fun main(fromWallet: string, toWallet: string, amount: coins) {
    val sender = scripts.wallet(fromWallet);
    val recipient = scripts.wallet(toWallet);
    println("{} -> {} : {}", sender.address, recipient.address, amount);

    val result = net.send(
        sender.address,
        createMessage({ bounce: false, dest: recipient.address, value: amount }),
    );
    println(result.waitForTrace());
    println("balance now {}", scripts.fetchAccountBalance(recipient.address));
}
