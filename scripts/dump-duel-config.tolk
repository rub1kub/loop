import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/DuelEscrow.gen"

fun main(duelAddress: address) {
    val s = DuelEscrow.fromAddress(duelAddress).adminState();
    println("owner   {}", s.owner);
    println("feeBps  {}", s.feeBps);
    println("paused  {}", s.paused);
    println("locked  {}", s.locked);
}
