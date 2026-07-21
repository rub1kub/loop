# LOOP

LOOP is a Telegram Mini App that turns native TON/GRAM interactions into a small, monochrome, wallet-first experience. The application never keeps an off-chain user balance: funds remain in the user's wallet or in the verifiable escrow state of a smart contract.

## Product

- **BANK** — a non-custodial savings goal driven by the connected wallet balance.
- **DUEL** — funded 25/50/75 probability offers with complementary stakes, commit-reveal entropy, timeout recovery, and contract payouts.
- **PROFILE** — Telegram identity, verified wallet, duel history, referrals, holder benefits, and settings.
- **Telegram** — validated Mini App `initData`, native buttons, safe areas, haptics, bot menu, notifications, and inline duel invitations.
- **TON** — TON Connect, Tolk contracts built by Acton, chain-confirmed state, and permissionless recovery paths.

## Repository

```text
apps/web/       React + TypeScript Mini App
apps/api/       FastAPI + aiogram API, bot and workers
contracts/      Tolk sources, Acton wrappers and tests
deploy/         Docker, nginx, TLS and operational scripts
docs/           Architecture, security and operations
```

## Local development

Requirements: Node.js 22+, Python 3.12+, PostgreSQL 16+, Redis 7+, and Acton 1.0.0.

```bash
cp .env.example .env
npm ci
npm run dev:web

python3.13 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
.venv/bin/uvicorn app.main:app --app-dir apps/api --reload

acton build
acton test
```

The browser-only demo uses `VITE_MOCK_TELEGRAM=true`; production rejects unsigned Telegram identity. See [deployment](docs/deployment.md) and [security](docs/security.md) before enabling any funded environment.

## Quality gates

```bash
npm run check
.venv/bin/pytest apps/api/tests
acton fmt --check
acton check
acton test --coverage --coverage-format text
```

## Release policy

Testnet is the only enabled chain in the default configuration. Mainnet requires all of the following: an independent contract audit, legal/compliance approval for each served jurisdiction, verified contract source/hash, multisig ownership, rehearsed refunds and restored off-site backups.

## Documentation

- [Architecture](docs/architecture.md)
- [TON integration](docs/ton.md)
- [Telegram integration](docs/telegram.md)
- [Security model](docs/security.md)
- [Deployment and operations](docs/deployment.md)

## License

MIT
