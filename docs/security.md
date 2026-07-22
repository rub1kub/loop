# Security model

## Trust boundaries

- Telegram identity is trusted only after server-side `initData` HMAC, age, future-skew and replay checks.
- Wallet ownership is trusted only after a scoped TON proof bound to origin, payload, public key, network and expiration.
- A TON Connect callback is never financial proof.
- Contract state and successful masterchain-finalized transactions are authoritative.
- PostgreSQL is an idempotent projection, not a ledger of custody.

## Contract invariants

BankQueue rejects unsupported multipliers, amounts outside limits, duplicate identifiers, concurrent owner positions, malformed messages and underfunded gas. Older FIFO positions always receive priority; only the remainder seeds the newly appended position. Fees, initial funding and payouts are deterministic integer calculations.

DuelEscrow rejects noncanonical pools, incompatible matches, repeated owners, commitment mismatch, early timeout, duplicate reveal/acceptance and dust messages. Pausing does not disable cancel, expiry, reveal or settlement. Outcomes do not depend on backend randomness.

## Chain worker

Each projection checks contract address, message direction, sender, value, opcode, query and entity identifiers, canonical terms, compute/action success and masterchain sequence. Unknown, failed or incomplete transactions remain unprojected. Checkpoints and event identities make replay idempotent.

## Application controls

- restrictive CORS and production HTTPS;
- signed sessions with short expiry;
- rate limiting and bounded request schemas;
- SQL row locks and partial unique constraints for races;
- redacted structured logs and no secret material in API responses;
- read-only containers, dropped Linux capabilities and no-new-privileges;
- startup attestation of both configured contract code hashes.

## Known limits

- The project is testnet-only and has not received an external professional audit.
- Referral anti-abuse prevents direct self-referral and duplicate qualification but cannot prove two Telegram accounts are unrelated people.
- PLUSH BRICK is a mainnet Jetton while contracts are testnet. V1 holder fee discounts are disabled rather than trusted to the backend.
- BANK depends entirely on later deposits; a stalled queue is expected behavior, not a solvency guarantee.

For private vulnerability reporting, see the repository [security policy](../SECURITY.md).
