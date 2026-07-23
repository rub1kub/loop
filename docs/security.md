# Security model

## Trust boundaries

- Telegram identity is trusted only after server-side `initData` HMAC, age, future-skew and replay checks.
- Wallet ownership is trusted only after a scoped TON proof bound to origin, payload, public key, network and expiration.
- A TON Connect callback is never financial proof.
- Contract state and successful masterchain-finalized transactions are authoritative.
- PostgreSQL is an idempotent projection, not a ledger of custody.

## Contract invariants

BankQueue rejects unsupported multipliers, amounts outside limits, duplicate identifiers, concurrent owner positions, malformed messages and underfunded gas. Older FIFO positions always receive priority; only the remainder seeds the newly appended position. Fees, initial funding and payouts are deterministic integer calculations.

DuelEscrow rejects noncanonical pools, incompatible matches, repeated owners, commitment mismatch, early timeout, duplicate reveal/acceptance and dust messages. Commitments and outcomes are domain-separated by network and contract address. Direct acceptance requires a short-lived server signature bound to the invited wallet and is matched atomically. Pausing does not disable cancel, expiry, reveal or settlement. Outcomes do not depend on backend randomness.

Both current contracts expose explicit owner commands for pause, reserve funding, bounded surplus
withdrawal, fee/treasury changes and ownership transfer. Configuration changes require a paused
contract. DUEL additionally requires zero locked stakes before changing its fee. A withdrawal can
only target the configured treasury and cannot cross `locked + 0.2 GRAM` retained on the contract.

## Chain worker

Each projection checks contract address, message direction, sender, value, opcode, query and entity identifiers, canonical terms, compute/action success and masterchain sequence. Unknown, failed or incomplete transactions remain unprojected. Checkpoints and event identities make replay idempotent.

## Application controls

- restrictive CORS and production HTTPS;
- signed sessions with short expiry;
- a separate one-hour owner session in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie scoped to `/api/v1/control`;
- one-time TON proof challenges bound to the production origin, configured owner wallet and network;
- durable application intake switches and an append-only administrative action log;
- rate limiting and bounded request schemas;
- SQL row locks and partial unique constraints for races;
- redacted structured logs and no secret material in API responses;
- read-only containers, dropped Linux capabilities and no-new-privileges;
- startup attestation of both configured contract code hashes.

## Known limits

- The project is testnet-only and has not received an external professional audit.
- The immutable direct-invite signer cannot be rotated in place; suspected key compromise requires pausing new activity and deploying a new contract after all recovery paths clear.
- Referral anti-abuse prevents direct self-referral and duplicate qualification but cannot prove two Telegram accounts are unrelated people.
- PLUSH BRICK is a mainnet Jetton while contracts are testnet. V1 holder fee discounts are disabled rather than trusted to the backend.
- BANK depends entirely on later deposits; a stalled queue is expected behavior, not a solvency guarantee.
- Ownership transfer is intentionally powerful and immediate; the browser requires an explicit confirmation, but the final authority is the owner-signed contract message.

For private vulnerability reporting, see the repository [security policy](../SECURITY.md).
