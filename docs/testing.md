# Testing

## Suites

| Suite      | Scope                                                                                                                                                                                                                      |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Acton      | BANK initial funding, FIFO allocation, partial/exact/cascading settlement, value conservation, fees, replay and races; DUEL matching, address binding, domain separation, commit–reveal, timeouts, refunds and permissions |
| pytest     | Telegram auth, API validation, independent models, invites, matchmaking races, chain indexing, idempotency, referral controls and TON provider proofs                                                                      |
| Vitest     | parsing, API schemas, TON message building, haptics, loader, fixed 50/50 DUEL and BANK queue copy                                                                                                                          |
| Playwright | production UI in Android Chromium and iOS WebKit across 320/390/430 px phone and desktop viewports, BANK wizard, 50/50 DUEL, RATING, profile, repeated keyboard/navigation transitions and tab-bar safe area               |
| Alembic    | clean install and migration graph consistency                                                                                                                                                                              |

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

## E2E boundary

The browser suite verifies interface and message construction without a seed phrase. Contract
tests exercise full messages in an emulated TVM. Read-only verification proves deployed artifacts,
recorded smoke transactions, reserve coverage and—on mainnet—a finalized two-wallet settlement.
The scheduled canary is intentionally outside CI and uses only pre-existing dedicated aliases.
