# DUEL

DUEL is an escrow-based PvP mode independent of BANK.

## Canonical terms

The creator chooses a stake and chance: 25%, 50% or 75%. Amounts are rounded to a shared quarter-unit so the two contributions form exactly one pool. Examples:

| Chance | Player share | Opponent share |
| ------ | -----------: | -------------: |
| 25%    |       1 unit |        3 units |
| 50%    |      2 units |        2 units |
| 75%    |      3 units |         1 unit |

Winner payout is `pool - floor(pool × fee / 10,000)`. DuelEscrow v1.1 enforces one global 2.5% fee.

## Matchmaking

AFK offers remain open after the Mini App closes. The API reserves the oldest compatible complementary offer under a database lock. A reservation has a deadline and returns to the queue if the second funding transaction never finalizes.

Direct invitations have a Telegram-safe code and an independent 256-bit on-chain invite ID. Acceptance requires a short-lived Ed25519 permit signed by LOOP and bound to the testnet global ID, DuelEscrow address, creator offer, invite ID and verified invited wallet. The contract atomically verifies the permit, binds both opponents and matches the offers; another wallet cannot steal or replay it.

## Commit–reveal

Each player generates a 256-bit secret locally and funds an offer with its commitment. Every commitment includes a versioned domain, network global ID and contract address, so it cannot be replayed across deployments or networks. The secret is kept in secure Telegram/device storage, never in the backend database. Once matched, players reveal within the deadline. The contract combines valid reveals to select a weighted winner.

- Two reveals: weighted settlement.
- One reveal by deadline: sole revealer wins.
- No reveals: both principals are refunded.
- Unmatched expiry or creator cancellation: principal is refunded.

Recovery is permissionless after deadlines. Offer and duel identifiers are replay protected.

## Operational proof

The migration gate refuses a contract switch unless the previous escrow reports `locked=0` and PostgreSQL has no active offer, duel or accepted invitation. A two-wallet canary performs direct open, address-bound accept, both reveals and settlement on testnet, then reports only a masterchain-finalized Reveal containing exactly one payout for the expected duel.

## PLUSH BRICK

Ownership is checked independently against the configured mainnet Jetton master. No V1 discount is advertised or applied: a testnet escrow cannot securely enforce a mainnet ownership-dependent fee without an additional proof/oracle design.
