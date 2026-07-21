# TON integration

LOOP uses TON testnet for BANK and DUEL settlement. It creates no wallet and keeps no internal user balance.

## TON Connect boundary

The API issues a one-use TON proof challenge. It verifies origin, timestamp, network, payload, signature, public key and canonical address before binding a wallet. Transaction requests expire quickly. A wallet callback means only “submitted”; the chain worker waits for successful execution and masterchain inclusion.

## Contracts

BankQueue and DuelEscrow are independent Tolk contracts with independent storage, fees, messages and deployment manifests. Their current addresses and reproducible evidence are documented in [contracts.md](contracts.md).

## Read-only audit CLI

```bash
.venv/bin/loop-onchain-audit contract --mode bank
.venv/bin/loop-onchain-audit contract --mode duel
.venv/bin/loop-onchain-audit wallet --address <wallet-address>
.venv/bin/loop-onchain-audit transaction --hash <transaction-hash> --account <account-address>
.venv/bin/loop-onchain-audit jetton --owner <wallet-address> --master <jetton-master>
```

Jetton checks verify owner, master and derived wallet balance. User labels and user-supplied Jetton wallet addresses are not accepted as ownership evidence.

## Finality and projections

The worker verifies account, sender/destination, opcode, value, query/entity identifiers, canonical terms, compute/action success and positive masterchain sequence. BANK and DUEL use separate event identities and checkpoints; a failure rolls back only the event projection and is safe to retry.

Primary references: [TON Connect](https://docs.ton.org/applications/ton-connect/overview), [transactions](https://docs.ton.org/develop/dapps/transactions), [smart-contract security](https://docs.ton.org/develop/smart-contracts/security), [Tolk](https://docs.ton.org/v3/documentation/smart-contracts/tolk/overview) and [Acton](https://ton-blockchain.github.io/acton/docs/welcome).
