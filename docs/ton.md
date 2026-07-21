# TON integration and on-chain audit

LOOP uses TON as a verification and settlement layer. It does not create wallets or maintain an application balance. The default and only enabled production network is TON testnet (`-3`). Amounts are integers in nano units; labels and Jetton metadata are never treated as asset identity.

## TON Connect boundary

The frontend requests a one-use `ton_proof` challenge before binding an external wallet. The API verifies domain, timestamp, network, payload, signature, on-chain public key, and canonical address before storing ownership evidence.

Transaction requests have a short `validUntil`. A TON Connect callback means only **submitted**. Funding, matching, settlement, refund, and BANK proof state change only after the chain worker verifies successful execution and masterchain inclusion.

## Contract audit summary

`DuelEscrow` is a native-currency two-party escrow written in Tolk and built with Acton. The audited local bytecode matches the deployed code hash.

| Area             | Verified result                                                                                                                      |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Address          | [`kQBXddZVMOteEYD87uSOfIAPL3P4UuI0Vf_fUAyGLS5l212a`](https://testnet.tonviewer.com/kQBXddZVMOteEYD87uSOfIAPL3P4UuI0Vf_fUAyGLS5l212a) |
| Raw address      | `0:5775D65530EB5E1180FCEEE48E7C800F2F73F852E23455FFDF500C862D2E65DB`                                                                 |
| State            | Active; balance `199925866` nanoTON at audit time                                                                                    |
| Code hash        | `1D8330B799875E54680D3180703A2CC0A3C3FFE4C763B6A9D2980E910252B63D`                                                                   |
| Deployment       | Successful, non-emulated transaction; masterchain inclusion at seqno `72977954`                                                      |
| Owner            | Existing testnet deployment wallet; no replacement wallet was created                                                                |
| Treasury         | Same existing testnet deployment wallet                                                                                              |
| Fee              | Immutable `250` basis points in deployed storage                                                                                     |
| Pause            | `false`; only owner may toggle pause                                                                                                 |
| Locked principal | `0` at audit time                                                                                                                    |
| Upgrade path     | None; no code-upgrade handler exists                                                                                                 |

The live `contractConfig` getter was re-read at masterchain seqno `73000745`: owner and treasury matched the existing deployment wallet, `feeBps=250`, `paused=false`, and `locked=0`.

## Permissions and recovery

- The owner can only toggle `paused`.
- The owner cannot change code, fee, treasury, offer owner, commitment, payout destination, or result.
- Pausing blocks new offers and new matches; it does not block reveal, owner cancellation, permissionless expiry, settlement, or refunds.
- Cancellation authenticates the original sender and refunds the stored owner.
- Expiry is permissionless after the stored deadline.
- Payout destinations are derived from stored authenticated senders, never from a message-provided destination.
- Offer ids are replay-protected and one wallet cannot open concurrent offers.
- One valid reveal wins after timeout; zero reveals refund both principals.

The deployed contract accepts historical 25/50/75 weighted messages. The current LOOP API, web client, bot, and matcher accept only equal 50/50 social duels. A new contract was not deployed because source, generated wrappers, local bytecode, live code hash, state, and deployment transaction were verifiable.

## Messages and evidence

Typed inbound operations are `OpenOffer`, `CancelOffer`, `MatchOffers`, `Reveal`, `ExpireOffer`, `ExpireDuel`, and owner-only `SetPaused`. Terminal transfers carry typed `DuelPayout`, `OfferRefund`, or `ProtocolFee` bodies for deterministic indexing.

The chain worker verifies:

- configured account equality;
- normalized transaction hash;
- successful compute and action phases;
- non-emulated execution;
- positive `mc_block_seqno`;
- idempotent `(network, account, lt, hash)` storage.

## Read-only verification tools

Install the API package and run:

```bash
.venv/bin/loop-onchain-audit contract
.venv/bin/loop-onchain-audit wallet --address <wallet-address>
.venv/bin/loop-onchain-audit transaction --hash <transaction-hash> --account <account-address>
.venv/bin/loop-onchain-audit jetton --owner <wallet-address> --master <jetton-master>
```

The HTTP API exposes the same application-safe reads:

```text
GET /api/v1/onchain/contract
GET /api/v1/onchain/jettons/{jetton_master}
```

Jetton checks derive the owner wallet from the configured master, then verify owner, master, and balance. A label or user-supplied wallet address is never sufficient evidence.

## Build and test evidence

```bash
acton build
acton check
acton test --coverage --coverage-format text --coverage-minimum-percent 75
```

The contract suite covers successful settlement, cancellation, expiry, one-reveal timeout, zero-reveal refunds, pause-safe recovery, replay prevention, wrong senders, malformed messages, dust calls, and operational guards. Source publication was exercised only in dry-run mode; it must not be described as an on-chain source-verification transaction.

Primary references:

- <https://docs.ton.org/applications/ton-connect/overview>
- <https://docs.ton.org/develop/dapps/transactions>
- <https://docs.ton.org/develop/smart-contracts/security>
- <https://docs.ton.org/develop/jettons/asset-processing>
- <https://docs.ton.org/v3/documentation/smart-contracts/tolk/overview>
- <https://ton-blockchain.github.io/acton/docs/welcome>
