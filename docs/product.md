# Product

LOOP is a Telegram Mini App with two deliberately independent testnet modes.

## BANK

BANK is a transparent simulation of a FIFO financial pyramid. A user contributes test GRAM and selects a 1.25×, 1.5× or 2× target. Each later contribution first pays the oldest unfinished position, then continues through the queue. There is no yield source, guarantee or DUEL subsidy. If contributions stop, payouts stop.

## DUEL

DUEL is an equal 50/50 two-player challenge. A player chooses a test-GRAM stake and the
counterparty contributes the same amount. Commit–reveal prevents either player or the backend
from selecting the result after matching. Timeouts preserve permissionless recovery. The
deployed escrow retains legacy 25/75 decoding only so older funded invitations can finish safely.

## RATING

RATING is a monthly social-reputation layer. LOOP Score rewards finalized BANK payouts,
finalized DUEL settlements, timely reveals and friends who qualify through a verified on-chain
action. Missed DUEL reveals reduce the score. Stake size, payout size, profit, wallet balance,
wins and losses are deliberately absent.

The global list and the qualified-referral circle use the same public formula. SIGNAL, PULSE,
ORBIT and LOOP levels make progress legible without turning financial volume into status.
RATING is an off-chain projection of verified events and never changes contract state.

## Shared product layer

Telegram identity, an external TON Connect wallet, RATING, referrals and profile navigation are
shared. Financial state is not. BANK and DUEL have separate contracts, projections, history,
fees and screens. Neither mode writes into the other.

LOOP has no wallet creation, portfolio, internal balance or custody. A wallet connection proves an address and signs a transaction; only a finalized on-chain transaction changes a financial projection.

## Network boundary

Financial actions are hard-disabled outside TON testnet (`-3`). The UI labels every transaction as testnet. The browser demo never broadcasts transactions.
