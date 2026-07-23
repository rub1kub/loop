# Architecture

## Bounded contexts

```text
                     Telegram identity
                            │
          ┌─────────────────┴─────────────────┐
          ▼                                   ▼
   BANK API module                      DUEL API module
   BankPosition                         DuelOffer / Duel
   BankPayout                           DuelInvitation
   BankChainEvent                       DuelChainEvent
   BankCheckpoint                       DuelCheckpoint
          │                                   │
          ▼                                   ▼
     BankQueue.tolk                     DuelEscrow.tolk
```

There is no universal cycle entity. Shared packages contain only identity, verified wallet ownership, referral attribution, provider access and delivery infrastructure.

RATING is a read-only social projection over finalized `BankPayout`, `DuelSettlement` and
`DuelReveal` rows plus qualified referral edges. It introduces no contract storage, financial
state or mutable score table: every response recomputes the public monthly formula from
idempotent proof-backed records.

The browser control site is a separate React entry point at `/control`. It does not initialize
Telegram, request Mini App expansion or reuse Telegram bearer sessions. The owner authenticates
with a one-time TON proof and receives an `HttpOnly`, `Secure`, `SameSite=Strict` cookie scoped to
the control API. Application intake state, synchronized contract configuration and the audit trail
are durable PostgreSQL records.

## Request path

1. Telegram sends signed `initData`; the API verifies HMAC, age and replay nonce.
2. The user proves control of an external testnet wallet through TON proof.
3. The API validates terms and returns a deterministic contract message. It does not mark funding complete.
   For direct DUEL, it signs a short-lived address-bound acceptance permit; it never signs an AFK match.
4. TON Connect asks the external wallet to sign and broadcast.
5. The worker reads the contract account, verifies message identity, values, opcode, exit status and masterchain inclusion.
6. A database transaction applies the idempotent BANK or DUEL projection.

Administrative contract messages follow the same rule: the API only prepares a bounded payload,
the owner wallet signs it, the contract enforces permissions and reserve invariants, and the worker
records the finalized change. The browser is never an authority for contract state.

## Data and concurrency

PostgreSQL is the durable projection store. Partial unique indexes prevent concurrent active positions/offers per wallet. Matchmaking locks compatible rows with `FOR UPDATE SKIP LOCKED`, records an expiring reservation and revalidates it on funding. Chain event identities are unique by network, account, logical time, transaction hash and event index.

Redis provides rate limits and short-lived distributed locks. It is never authoritative for offers, positions or payouts.

## Failure model

- Provider outage: keep the record pending and retry; do not infer success.
- Malformed or failed transaction: record no financial transition.
- Projection exception: roll back to a savepoint and retry safely.
- Worker restart: resume from per-contract checkpoints; duplicate events are ignored.
- Wallet callback without a block: remain pending.
- Contract migration with locked funds or active DUEL projection: fail before Alembic runs.
- Abandoned direct funding: release the expired reservation and let the same bound wallet retry.
