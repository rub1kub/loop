# LOOP mainnet audit scope

This document defines the independent review boundary for the exact Git commit named in
`deployments/mainnet/release.json`. It is an audit request, not an audit report or a security
guarantee.

## In scope

- `BankQueue` v1.3 Tolk source, storage, messages and generated code hash.
- `DuelEscrow` v1.3 Tolk source, storage, messages and generated code hash.
- Deployment initialization, network/address domain separation and direct-invite permits.
- Every value-moving path: deposits, FIFO allocation, boosts, payouts, fees, refunds, reserve
  funding and surplus withdrawal.
- Owner permissions: pause, fee/treasury changes, ownership transfer and withdrawal boundaries.
- Replay protection, identifier uniqueness, timing boundaries, commit–reveal rules and message gas.
- Mainnet release evidence, source verification, shadow/canary proofs and application fail-closed
  activation.

The backend and Mini App are in scope where they construct, authorize, index or present a financial
action. Telegram authentication, TON proof validation, result-card referrals, administrative
sessions and chain-projection idempotency are included.

## Required invariants

### BANK

1. Every accepted principal is within the on-chain maturity limit.
2. The protocol fee is separate and deterministic.
3. Distributable value funds older FIFO positions before the new position.
4. A payout is sent exactly once and a position identifier cannot be replayed.
5. `lockedFunding + 0.2 GRAM` remains unavailable to owner withdrawal.
6. Pause blocks new positions but does not corrupt existing accounting.
7. The initial production application cap is at most 5 GRAM.

### DUEL

1. Both principals are locked once, and settlement/refund releases them once.
2. Commitments bind network, contract, duel, offer, wallet, secret and choice.
3. Direct acceptance requires a valid permit bound to the invited wallet.
4. Boosts are owner/revision/deadline bound and keep chance within 90/10.
5. Neither backend nor owner selects the outcome.
6. Recovery remains available while paused.
7. Locked stake and the 0.2 GRAM reserve are never withdrawable.
8. The initial production pool cap is at most 2 GRAM.

## Evidence expected from the release candidate

```bash
make contracts-mainnet-technical
make contracts-audit-pack
```

The technical gate must show:

- forked-mainnet execution of every contract test;
- at least 98% line and 75% branch coverage;
- critical mutation score at least 90% for BANK and 95% for DUEL;
- major mutation score at least 75% for both contracts;
- no gas-profile drift from the reviewed snapshot;
- focused backend and TON-message security tests passing.

The archive contains only allowlisted sources and documentation, a deterministic file-hash
manifest, toolchain versions and compiled contract hashes. It intentionally excludes `.env`,
wallet stores, credentials, build caches and deployment keys.

## Deployment evidence expected after approval

1. The report file and SHA-256 are committed under `docs/audits/`.
2. `release.json` names the exact audited commit, owner, treasury, invite key and initial caps.
3. BANK bytecode completes a finalized two-wallet deposit → payout cycle on a separate mainnet
   shadow address. The production BANK remains paused and empty.
4. DUEL completes a finalized two-wallet match, boost, reveal and payout.
5. Both production addresses publish source verification and match audited code hashes.
6. The application repeats the audited commit/report/caps and refuses mismatched configuration.
7. Mainnet activation occurs only after `make contracts-mainnet-verify` succeeds.

Any source, compiler, deployment parameter, key, fee, limit or contract-address change after the
review creates a new release candidate and requires renewed sign-off.

The current BANK mutation report has three surviving defensive mutations: the deployment/admin
paths already prevent an invalid fee from entering storage, the TVM original balance includes the
credited inbound message, and the 25–99 completion branch is behaviorally equivalent to the next
formula because integer division truncates `(completed - 100) / 250` to zero in that range. These
must be reviewed as explicit equivalences rather than silently excluded from the score.
