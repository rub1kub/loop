# Architecture

## System boundaries

LOOP is a modular monolith deployed as independently scalable processes:

```text
Telegram / browser
       │ HTTPS
       ▼
nginx ─┬─ static Mini App
       ├─ FastAPI + aiogram webhook
       └─ health and metrics
              │
        PostgreSQL ── durable users, offers, projections, outbox, checkpoints
        Redis      ── rate limits, short-lived locks and cache only
              │
        TON indexer / matcher / notifier
              │
        TON testnet + DuelEscrow contract
```

The chain is authoritative for locked value, duel state and payouts. PostgreSQL is authoritative for off-chain identity, matchmaking intent, notification delivery, idempotency and indexed projections. Redis can be deleted without losing correctness.

## Duel protocol

Amounts are unsigned integer nano units. `chance_bps` is one of `2500`, `5000`, or `7500`; `stake = total_pool * chance_bps / 10_000`. A pair is compatible only when network, contract, pool and fee match, chances sum to 10,000, and user and wallet differ.

1. The client generates a 256-bit secret and commitment bound to the offer id and wallet.
2. `OpenOffer` locks the exact principal plus an explicit gas budget in the contract.
3. A complementary offer can name the first offer, or anyone can call `MatchOffers`; the contract validates all terms.
4. Each wallet sends `Reveal`. After both valid reveals, the contract hashes a deterministic transcript and selects a winner weighted by principal.
5. One reveal followed by timeout awards the pool to the revealer. No reveals followed by timeout refunds both principals.
6. Unmatched offers can be cancelled by their owner or expired permissionlessly. Pausing blocks new offers and matches but never reveal, settle, cancel or refund.

Every transition is replay-safe and terminal outcomes are mutually exclusive. No backend decision can alter a valid outcome or redirect a payout.

## Backend modules

- `auth`: strict Telegram `initData` verification and short-lived signed sessions.
- `wallets`: one-use TON proof challenges and canonical wallet binding.
- `matchmaking`: SQL row locking and deterministic compatibility rules.
- `duels`: transaction payload construction; a signed/submitted transaction is never considered final.
- `chain`: finalized event ingestion, overlap backfill and idempotent projections.
- `referrals`: immutable first attribution, self/cycle prevention and chain-qualified rewards.
- `bot`: menu button, start parameters, inline invitations and outbox notifications.

## Data invariants

- one Telegram id maps to one user; one canonical `(network, address)` has one active owner;
- one active offer per wallet and matchmaking scope;
- one chain event identity can cause one state transition;
- one duel has exactly one terminal result;
- one referred user has at most one immutable inviter;
- no database column represents spendable user funds.

