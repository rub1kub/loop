# TON integration

## Network and units

The default network is testnet. GRAM is the native currency described by current TON documentation, represented as integer nano units. Asset labels or token metadata are never used as identity. Plush Brick eligibility uses the configured Jetton master address and a derived holder wallet on the matching network.

## TON Connect

The frontend requests a `ton_proof` challenge before connection. The API verifies the proof's domain, timestamp, network, payload, signature and wallet binding before persisting an address. Transaction requests have a short `validUntil`; frontend callbacks mean submitted, not settled. The chain indexer alone advances financial projections after finalized successful execution.

## Contract

`DuelEscrow` is a native-currency offer escrow with typed Tolk messages and storage. It supports open, compatible match, reveal, cancel, expiry, pause-safe recovery and getters. Payout destinations always come from stored authenticated senders, never message body input.

Commit-reveal follows TON's recommendation for monetary games. Commitments are created with the same canonical cell layout in TypeScript and Tolk. If only one player reveals, withholding loses after deadline; if neither reveals, both principals are recoverable.

Primary references:

- <https://docs.ton.org/start-here>
- <https://docs.ton.org/contracts/techniques/security>
- <https://docs.ton.org/contracts/techniques/random>
- <https://docs.ton.org/applications/ton-connect/overview>
- <https://ton-blockchain.github.io/acton/docs/welcome>

