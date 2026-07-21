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

## Request path

1. Telegram sends signed `initData`; the API verifies HMAC, age and replay nonce.
2. The user proves control of an external testnet wallet through TON proof.
3. The API validates terms and returns a deterministic contract message. It does not mark funding complete.
4. TON Connect asks the external wallet to sign and broadcast.
5. The worker reads the contract account, verifies message identity, values, opcode, exit status and masterchain inclusion.
6. A database transaction applies the idempotent BANK or DUEL projection.

## Data and concurrency

PostgreSQL is the durable projection store. Partial unique indexes prevent concurrent active positions/offers per wallet. Matchmaking locks compatible rows with `FOR UPDATE SKIP LOCKED`, records an expiring reservation and revalidates it on funding. Chain event identities are unique by network, account, logical time, transaction hash and event index.

Redis provides rate limits and short-lived distributed locks. It is never authoritative for offers, positions or payouts.

## Failure model

- Provider outage: keep the record pending and retry; do not infer success.
- Malformed or failed transaction: record no financial transition.
- Projection exception: roll back to a savepoint and retry safely.
- Worker restart: resume from per-contract checkpoints; duplicate events are ignored.
- Wallet callback without a block: remain pending.
