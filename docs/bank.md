# BANK

BANK is an explicit mainnet financial pyramid implemented as a FIFO queue of positions.

## Position math

For principal `P`, multiplier `M` in basis points and fee `F`:

```text
target payout = floor(P × M / 10,000)
BANK fee      = floor(P × F / 10,000)
```

Supported multipliers are 12,500, 15,000 and 20,000. The minimum principal is 1 GRAM and the
current fee is 10%. The contract limit matures with the queue:

| Completed positions | Maximum principal |
| ------------------: | ----------------: |
|                 0–9 |            1 GRAM |
|               10–14 |            2 GRAM |
|               15–24 |            3 GRAM |
|               25–34 |            5 GRAM |
|               35–49 |            7 GRAM |
|               50–74 |           10 GRAM |
|               75–99 |           15 GRAM |
|             100–149 |           20 GRAM |
|             150–249 |           30 GRAM |
|             250–374 |           50 GRAM |
|             375–499 |           75 GRAM |
|                500+ |          100 GRAM |

Only completed on-chain payouts move the counter. The application may impose a lower cap than the
live contract. The attached gas value is not part of the principal.

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
positions, live active-position count, remaining funding, status and a TON explorer proof.
The absolute on-chain queue index is retained for audit, while the API calculates the
reader-facing rank from unfinished earlier positions. DUEL financial events remain absent.

## Weekly Wave

The optional Wave is a recurring Sunday window from 20:00 to 20:30 Moscow time. Eight distinct
users with confirmed BANK positions unlock a 5 GRAM operator position. Repeated positions by one
user and the configured operator wallet do not increase the counter. The result is reported as
completed only after the operator position is independently observed in the BANK contract and its
transaction proof is available. The last distinct entrant receives a social status and a share
action, never a separate cash prize. Telegram announcements use the existing user notification
preference and durable deduplication. The first campaign is hard-capped at four verified operator
positions (20 GRAM principal); once that budget is exhausted, no following Wave is advertised.
Because LOOP never stores an operator seed, reaching the goal sends the configured operator an
actionable Telegram message. The operator signs the 5 GRAM position in the external wallet; until
the indexer sees that transaction, the public state remains `awaiting_boost` rather than claiming
that LOOP has paid.

## Risk

There is no underlying return. A target can remain partially funded forever when later deposits
stop. A user cannot cancel a confirmed position; while paused, the owner can refund a selected
position. The public mainnet build presents this mechanism plainly before TON Connect confirmation.
