# Testing

## Suites

| Suite      | Scope                                                                                                                                                                                                                           |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Acton      | BANK maturity limits, FIFO allocation, partial/exact/cascading settlement, value conservation, fees, replay and races; DUEL matching, boosts, revision races, hard deadlines, 90/10 cap, commit–reveal, refunds and permissions |
| pytest     | Telegram auth, API validation, independent models, invites, matchmaking races, chain indexing, idempotency, referral controls and TON provider proofs                                                                           |
| Vitest     | parsing, API schemas, TON message construction and context binding, boost states, haptics, loader and BANK queue copy                                                                                                           |
| Playwright | production UI across 320/390/430 px phone and desktop viewports, BANK wizard, DUEL boost flow, RATING, profile, repeated keyboard/navigation transitions and tab-bar safe area                                                  |
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
critical/major DUEL mutation thresholds and focused API/web security checks:

```bash
make contracts-mainnet-technical
```

The evidence and live post-deployment gates are separate:

```bash
make contracts-mainnet-preflight
make contracts-mainnet-verify
```

## Current v1.3 evidence

- 13 BANK and 45 DUEL contract tests;
- 99.7% contract line coverage and 83.5% branch coverage;
- 88.2% BANK and 96.7% DUEL critical/major mutation scores;
- 64 consecutive DUEL settlements without an active-offer or locked-value leak;
- 82 API tests, 57 web tests, 13 focused security tests and four repeated viewport/keyboard
  stress modes;
- finalized two-wallet testnet pair → boost → deadline → reveal → payout canary.

## E2E boundary

The browser suite verifies interface and message construction without a seed phrase. Contract
tests exercise full messages in an emulated TVM. Read-only verification proves deployed artifacts,
recorded smoke transactions, reserve coverage and a finalized two-wallet boost/settlement.
The scheduled canary is intentionally outside CI and uses only pre-existing dedicated aliases.
