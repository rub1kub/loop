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
2. creates the new position at the queue tail;
3. applies available principal to the oldest unfinished earlier position;
4. sends an automatic payout when that target is fully funded;
5. continues through older positions while value remains.

The first position cannot finance itself. Any unallocated seed remainder is tracked as protocol reserve, not as a user position. DUEL value and events never enter this algorithm.

## States

`pending_confirmation → queued → partially_funded → completed → payout_sent`

`failed` is a projection state for a rejected or expired funding intent. The contract prevents duplicate position identifiers and concurrent active positions for one owner; the database mirrors those invariants for early feedback.

## UI

The jar is the primary object. An empty jar starts a three-step position wizard. An active jar shows only BANK progress, remaining funding, queue position, status and a testnet explorer proof. DUEL statistics and events are absent.

## Risk

There is no underlying return. A target can remain partially funded forever when later deposits stop. This is why the public build is testnet-only and presents the mechanism plainly.
