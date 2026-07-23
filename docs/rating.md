# RATING

RATING turns verified participation into visible reputation without rewarding financial volume.
It is a monthly off-chain projection; contracts remain the source of financial truth.

## LOOP Score

```text
+100  BANK payout with finalized on-chain proof
 +60  DUEL settlement with finalized on-chain proof
 +20  timely DUEL reveal
 +25  qualified friend with a verified on-chain action
 -40  missed DUEL reveal
```

The score has a zero floor. Stakes, payouts, profits, wallet balances, wins and losses are not
inputs. A settlement counts once per participant. A timely reveal is matched to that
participant's offer and deadline.

## Levels

| Level  | Monthly score |
| ------ | ------------: |
| SIGNAL |         0–199 |
| PULSE  |       200–499 |
| ORBIT  |       500–999 |
| LOOP   |        1,000+ |

Global ordering uses score first and proof count second. The friend circle contains the current
user and both sides of qualified referral edges. A referral qualifies only after the indexed
on-chain action already accepted by LOOP's chain worker.

## Live pulse

The screen also reports distinct users with an unfinished BANK position or active DUEL offer,
the split between both modes and the number of payout/settlement proofs indexed during the last
24 hours. These values are system status, not score.

## Trust boundary

The API derives RATING from masterchain-finalized, idempotent projection rows. It does not trust
wallet callbacks, Telegram message text or client-supplied points. RATING cannot move funds,
select a DUEL result or reorder the BANK contract queue.
