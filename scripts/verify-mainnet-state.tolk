import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"
import "@wrappers/DuelEscrow.gen"

// Reads the live configuration of both mainnet contracts. Run with
// `--net mainnet` after deployment to confirm what was actually written on
// chain, rather than trusting what the deploy script intended to write.
fun main(bankAddress: address, duelAddress: address) {
    val bank = BankQueue.fromAddress(bankAddress).contractConfig();
    println("BANK owner       {}", bank.owner);
    println("BANK treasury    {}", bank.treasury);
    println("BANK feeBps      {}", bank.feeBps);
    println("BANK paused      {}", bank.paused);
    println("BANK locked      {}", bank.lockedFunding);
    println("BANK completed   {}", bank.completedPositions);

    val duel = DuelEscrow.fromAddress(duelAddress).adminState();
    println("DUEL owner       {}", duel.owner);
    println("DUEL treasury    {}", duel.treasury);
    println("DUEL feeBps      {}", duel.feeBps);
    println("DUEL paused      {}", duel.paused);
    println("DUEL locked      {}", duel.locked);
}
