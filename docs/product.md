# Product

LOOP is a Telegram Mini App with two deliberately independent testnet modes.

## BANK

BANK is a transparent simulation of a FIFO financial pyramid. A user contributes test GRAM and selects a 1.25×, 1.5× or 2× target. Each later contribution first pays the oldest unfinished position, then continues through the queue. There is no yield source, guarantee or DUEL subsidy. If contributions stop, payouts stop.

## DUEL

DUEL is a two-player game. A player chooses a test-GRAM stake and a 25%, 50% or 75% chance. The counterparty contribution is computed so both positions share one canonical pool. Commit–reveal prevents either player or the backend from selecting the result after matching. Timeouts preserve permissionless recovery.

## Shared product layer

Telegram identity, an external TON Connect wallet, referrals and profile navigation are shared. Financial state is not. BANK and DUEL have separate contracts, projections, history, fees and screens. Neither mode writes into the other.

LOOP has no wallet creation, portfolio, internal balance or custody. A wallet connection proves an address and signs a transaction; only a finalized on-chain transaction changes a financial projection.

## Network boundary

Financial actions are hard-disabled outside TON testnet (`-3`). The UI labels every transaction as testnet. The browser demo never broadcasts transactions.
