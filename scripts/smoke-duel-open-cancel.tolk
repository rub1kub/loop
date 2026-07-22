import "@acton/io"
import "@acton/emulation/network"
import "@acton/emulation/scripts"
import "@acton/types/big_array"
import "@acton/types/transaction"
import "@wrappers/DuelEscrow.gen"

const SMOKE_COMMITMENT_DOMAIN = 0x4C4F4F60
const SMOKE_SECRET: uint256 = 0x6C6F6F702D6475656C2D746573746E65742D736D6F6B652D76312D3030303031

enum SmokeErrors {
    ContractNotIdle = 901
    OfferMismatch = 902
    LockedValueMismatch = 903
    MissingTransaction = 904
}

fun transactionAt(trace: SendResultList, account: address): TlbTransaction? {
    var index = 0;
    repeat (trace.size()) {
        val transaction = trace.at(index).tx.load();
        if (transaction.getAccountAddress() == account) {
            return transaction;
        }
        index += 1;
    }
    return null;
}

fun smokeCommitment(
    networkId: int32,
    contractAddress: address,
    offerId: uint64,
    owner: address,
): uint256 {
    return beginCell()
        .storeUint(SMOKE_COMMITMENT_DOMAIN, 32)
        .storeInt(networkId, 32)
        .storeAddress(contractAddress)
        .storeUint(offerId, 64)
        .storeAddress(owner)
        .storeUint(SMOKE_SECRET, 256)
        .hash();
}

fun main(duelAddress: address, offerId: uint64, expiresAt: uint32) {
    val deployer = scripts.wallet("deployer");
    val duel = DuelEscrow.fromAddress(duelAddress);
    val before = duel.contractConfig();
    assert (before.locked == 0) throw SmokeErrors.ContractNotIdle;

    val opened = duel.sendOpenOffer(
        deployer.address,
        offerId,
        offerId,
        smokeCommitment(before.networkId, before.contractAddress, offerId, deployer.address),
        5_000,
        ton("2"),
        expiresAt,
        0,
        { value: ton("1.05") },
    );
    val openTrace = opened.waitForTrace();
    assert (openTrace != null) throw SmokeErrors.MissingTransaction;
    val openTransaction = transactionAt(openTrace!, duelAddress);
    assert (openTransaction != null) throw SmokeErrors.MissingTransaction;
    println(openTrace);

    val offer = duel.offerData(offerId);
    assert (
        offer.owner == deployer.address && offer.totalPool == ton("2") && offer.stake == ton("1") &&
        offer.chanceBps == 5_000
    ) throw SmokeErrors.OfferMismatch;
    assert (duel.contractConfig().locked == ton("1")) throw SmokeErrors.LockedValueMismatch;

    val cancelled = duel.sendCancelOffer(
        deployer.address,
        offerId,
        offerId,
        { value: ton("0.03") },
    );
    val cancelTrace = cancelled.waitForTrace();
    assert (cancelTrace != null) throw SmokeErrors.MissingTransaction;
    val cancelTransaction = transactionAt(cancelTrace!, duelAddress);
    assert (cancelTransaction != null) throw SmokeErrors.MissingTransaction;
    println(cancelTrace);
    assert (duel.contractConfig().locked == 0) throw SmokeErrors.LockedValueMismatch;

    println("DUEL_SMOKE_OPEN_HASH {:x}", openTransaction!.toCell().hash());
    println("DUEL_SMOKE_CANCEL_HASH {:x}", cancelTransaction!.toCell().hash());
    println("DUEL smoke passed: offer={} opened, escrowed and refunded", offerId);
}
