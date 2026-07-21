# Architecture

## System boundaries

LOOP is a modular monolith deployed as independently restartable processes:

```text
Telegram WebView / inline message
             │ HTTPS
             ▼
Apache SNI edge → nginx ─┬─ static React Mini App
                        ├─ FastAPI + aiogram webhook
                        └─ health and metrics
                                  │
                   PostgreSQL ── durable identity, BANK, offers,
                                  projections, outbox, checkpoints
                   Redis      ── rate limits, short locks, cache
                                  │
                   matcher / notifier / finalized chain worker
                                  │
                         TON testnet + DuelEscrow
                                  │
                         external user wallets
```

TON is authoritative for locked value, duel state, settlement, and refunds. PostgreSQL is authoritative for Telegram identity, matchmaking intent, invitation binding, notification delivery, idempotency, and indexed social projections. Redis can be removed without losing correctness.

## BANK projection

A BANK cycle is a seven-day social aggregate, not an account balance. `bank_cycles` stores status, goal, event count, and dates. `cycle_events` stores chronological social or blockchain evidence with a per-cycle deduplication key.

The chain worker creates events only after all of the following are true:

1. the transaction belongs to the configured contract account;
2. compute and action phases succeeded;
3. the transaction is not emulated;
4. a positive masterchain block sequence proves inclusion;
5. the `(network, account, lt, hash)` identity has not been projected before.

The worker checkpoint never advances past an unfinalized transaction. Funding, matching, settlement, and refund projections include an explorer URL derived from the verified transaction hash.

## DUEL protocol

The product API accepts only `chance_bps=5000`. Both users contribute half of the same `total_pool_nano`, and a compatible pair must have the same network, contract, pool, fee, and product conditions while using different users and wallets.

1. The client creates a 256-bit secret and a commitment bound to domain, offer id, wallet, and secret.
2. `OpenOffer` locks the contribution plus an explicit gas budget.
3. AFK offers are matched deterministically under PostgreSQL row locks. Direct challenges name a specific counter-offer and are excluded from the AFK pool.
4. Each owner sends `Reveal`. Two valid reveals settle from a deterministic commitment transcript.
5. One reveal followed by timeout awards the pool to the revealer. No reveals followed by timeout refunds both contributions.
6. An unmatched offer can be cancelled by its owner or expired permissionlessly.
7. Pausing blocks only new offers and matches; it cannot block reveal, cancellation, settlement, expiry, or refunds.

The deployed contract retains legacy 25/75 message compatibility, but the LOOP product, API, bot, and matcher reject it. This preserves the verified deployment while enforcing one understandable social rule at every application boundary.

## Telegram invitation flow

```text
creator funds offer
       │ finalized on TON
       ▼
bot resolves exact offer ──► inline LOOP DUEL message
                                      │ ПРИНЯТЬ
                                      ▼
                            signed Telegram Mini App
                                      │ opaque invite code
                                      ▼
                         API verifies accepter + offer terms
                                      │
                                      ▼
                         external wallet confirms counter-offer
```

An inline message is a transport for a verified challenge, not the authority for its terms. Stake, pool, owner, state, and expiry are loaded from the server-side offer after Telegram authentication.

## Backend modules

- `auth`: strict Telegram `initData` verification and short-lived signed sessions.
- `wallets`: one-use TON proof challenges and canonical external-wallet binding.
- `cycles`: BANK lifecycle, progress, event deduplication, and history.
- `matchmaking`: 50/50 compatibility, direct-offer isolation, and SQL locking.
- `duels`: transaction intent construction; wallet callbacks never finalize state.
- `chain`: masterchain-confirmed ingestion, overlap backfill, proofs, and idempotent projections.
- `referrals`: immutable first attribution and chain-qualified rewards.
- `bot`: menu button, start parameters, exact inline invitations, and outbox notifications.

## Data invariants

- One Telegram id maps to one user; one canonical `(network, address)` has one active owner.
- One active offer exists per wallet and matchmaking scope.
- One direct challenge resolves to one creator offer and cannot be taken by AFK matching.
- One chain event identity causes at most one state transition and one BANK event.
- One duel has exactly one terminal result.
- No database column represents spendable user funds.
