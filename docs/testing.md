# Testing

## Suites

| Suite      | Scope                                                                                                                                                                                                                           |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Acton      | BANK maturity limits, FIFO allocation, partial/exact/cascading settlement, value conservation, fees, replay and races; DUEL matching, boosts, revision races, hard deadlines, 90/10 cap, commit–reveal, refunds and permissions |
| pytest     | Telegram auth, API validation, independent models, invites, matchmaking races, chain indexing, idempotency, temporal team scoring and roles, referral controls, security headers and TON proofs                                  |
| Vitest     | parsing, API schemas, TON message construction and context binding, boost states, team navigation, haptics, loader and BANK queue copy                                                                                         |
| Playwright | production UI across phone, tablet and desktop viewports, BANK wizard, DUEL boost flow, RATING, TEAMS, profile, repeated keyboard/navigation transitions and tab-bar safe area                                                     |
| Alembic    | clean install and migration graph consistency                                                                                                                                                                                   |

## Commands

```bash
make test-unit
make test-integration
make contracts-test
make test-e2e
make test-security
```

Run static verification separately:

```bash
make lint
make typecheck
```

Run live read-only testnet verification:

```bash
make chain-smoke-test
```

The complete mainnet technical profile runs forked coverage, gas regression, separate
critical/major BANK and DUEL mutation thresholds and focused API/web security checks:

```bash
make contracts-mainnet-technical
```

The evidence and live post-deployment gates are separate:

```bash
make contracts-mainnet-preflight
make contracts-mainnet-verify
```

## Current evidence

- 22 BANK and 73 DUEL contract tests, including an adversarial suite and the allocation gas ceiling;
- 99.67% contract line coverage and 87.45% branch coverage;
- BANK mutation scores: 93.5% critical and 82.4% major;
- DUEL mutation scores: 99.1% critical and 90.0% major;
- 64 consecutive DUEL settlements without an active-offer or locked-value leak;
- finalized two-wallet BANK deposit → payout testnet cycle;
- finalized two-wallet DUEL pair → boost → deadline → reveal → payout testnet cycle.

## E2E boundary

The browser suite verifies interface and message construction without a seed phrase. Contract
tests exercise full messages in an emulated TVM. Read-only verification proves deployed artifacts,
recorded BANK fee/payout and DUEL settlement transactions, reserve coverage and masterchain
finality.
The scheduled canary is intentionally outside CI and uses only pre-existing dedicated aliases.
