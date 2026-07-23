# BANK

BANK is an explicit testnet pyramid simulation implemented as a FIFO queue of positions.

## Position math

For principal `P`, multiplier `M` in basis points and fee `F`:

```text
target payout = floor(P × M / 10,000)
BANK fee      = floor(P × F / 10,000)
```

Supported multipliers are 12,500, 15,000 and 20,000. Published limits are 1–100 GRAM principal and a 1% fee. The attached gas value is not part of the principal.

## Allocation

On every valid deposit the contract:

1. deducts the deterministic BANK fee;
2. applies available principal to the oldest unfinished earlier position;
3. sends an automatic payout when that target is fully funded;
4. continues through older positions while value remains;
5. creates the new position at the queue tail and uses any remainder as its initial funding.

Older positions always have priority. No distributable value leaves the user cycle as an unspendable protocol reserve: after the older queue is funded, the remainder visibly starts the new jar. Later deposits close its outstanding target in FIFO order. DUEL value and events never enter this algorithm.

## States

`pending_confirmation → queued → partially_funded → completed → payout_sent`

`failed` is a projection state for a rejected or expired funding intent. The contract prevents duplicate position identifiers and concurrent active positions for one owner; the database mirrors those invariants for early feedback.

## UI

The jar is the primary object. An empty jar explains the FIFO cycle before starting a three-step
position wizard. An active jar shows BANK progress, the current rank among unfinished
positions, live active-position count, remaining funding, status and a testnet explorer proof.
The absolute on-chain queue index is retained for audit, while the API calculates the
reader-facing rank from unfinished earlier positions. DUEL financial events remain absent.

## Risk

There is no underlying return. A target can remain partially funded forever when later deposits stop. An on-chain BANK position has no cancellation or early-refund message; once confirmed, it remains in FIFO order until its target is funded. This is why the public build is testnet-only and presents the mechanism plainly before TON Connect confirmation.
