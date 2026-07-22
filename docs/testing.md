# Testing

## Suites

| Suite      | Scope                                                                                                                                                                                                                      |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Acton      | BANK initial funding, FIFO allocation, partial/exact/cascading settlement, value conservation, fees, replay and races; DUEL matching, address binding, domain separation, commit–reveal, timeouts, refunds and permissions |
| pytest     | Telegram auth, API validation, independent models, invites, matchmaking races, chain indexing, idempotency, referral controls and TON provider proofs                                                                      |
| Vitest     | parsing, API schemas, TON message building, haptics, loader and DUEL controls                                                                                                                                              |
| Playwright | real production UI at phone viewport, BANK wizard, DUEL state, profile and tab-bar safe area                                                                                                                               |
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

DUEL release candidates additionally run line/branch coverage and critical/major mutation testing:

```bash
acton test tests/duel_contract.test.tolk --coverage --coverage-format text
acton test tests/duel_contract.test.tolk --mutate --mutate-contract DuelEscrow \
  --mutation-diff branch --mutation-levels critical,major
```

## E2E boundary

The browser suite verifies interface and message construction without a seed phrase. Contract tests exercise full messages in an emulated TVM. Read-only verification proves deployed artifacts and recorded smoke transactions. The scheduled two-wallet DUEL canary is intentionally outside CI: it requires two pre-existing dedicated testnet signing wallets, never creates them automatically and only requests faucet funds below its configured safety floor.
