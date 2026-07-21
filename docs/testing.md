# Testing

## Suites

| Suite      | Scope                                                                                                                                                               |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Acton      | BANK FIFO allocation, partial/exact/cascading funding, fees, payout, replay and malicious messages; DUEL matching, commit–reveal, timeouts, refunds and permissions |
| pytest     | Telegram auth, API validation, independent models, invites, matchmaking races, chain indexing, idempotency, referral controls and TON provider proofs               |
| Vitest     | parsing, API schemas, TON message building, haptics, loader and DUEL controls                                                                                       |
| Playwright | real production UI at phone viewport, BANK wizard, DUEL state, profile and tab-bar safe area                                                                        |
| Alembic    | clean install and migration graph consistency                                                                                                                       |

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

## E2E boundary

The browser suite verifies interface and message construction without a seed phrase. Contract tests exercise full messages in an emulated TVM. The read-only chain smoke verifies deployed artifacts. A broadcast two-wallet end-to-end test is deliberately not run in CI because it would require funded signing keys; release validation uses manually signed testnet transactions and explorer proofs instead.
