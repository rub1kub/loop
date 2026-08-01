import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@wrappers/BankQueue.gen"

// Reads every BankQueue value the mainnet manifest has to carry, straight from
// the chain, so no number in `deployments/mainnet/bank.json` is ever typed from
// memory.
fun main(productionAddress: address, shadowAddress: address, smokePositionId: uint64, fundingPositionId: uint64) {
    val production = BankQueue.fromAddress(productionAddress).contractConfig();
    println("PROD owner              {}", production.owner);
    println("PROD treasury           {}", production.treasury);
    println("PROD feeBps             {}", production.feeBps);
    println("PROD paused             {}", production.paused);
    println("PROD headQueueIndex     {}", production.headQueueIndex);
    println("PROD nextQueueIndex     {}", production.nextQueueIndex);
    println("PROD completedPositions {}", production.completedPositions);
    println("PROD principalLimit     {}", production.principalLimit);
    println("PROD lockedFunding      {}", production.lockedFunding);

    val shadow = BankQueue.fromAddress(shadowAddress);
    val shadowConfig = shadow.contractConfig();
    println("SHADOW treasury           {}", shadowConfig.treasury);
    println("SHADOW completedPositions {}", shadowConfig.completedPositions);
    println("SHADOW lockedFunding      {}", shadowConfig.lockedFunding);

    val paid = shadow.positionData(smokePositionId);
    println("SMOKE owner        {}", paid.owner);
    println("SMOKE principal    {}", paid.principal);
    println("SMOKE targetPayout {}", paid.targetPayout);
    println("SMOKE fundedAmount {}", paid.fundedAmount);
    println("SMOKE status       {}", paid.status);

    val funder = shadow.positionData(fundingPositionId);
    println("FUNDER owner     {}", funder.owner);
    println("FUNDER principal {}", funder.principal);
    println("FUNDER status    {}", funder.status);
}
