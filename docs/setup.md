# Setup

## Prerequisites

- Node.js 22+
- Python 3.12+ (3.13 is used in CI examples)
- PostgreSQL 17+
- Redis 8+
- Acton 1.0.0
- Docker with Compose for the production topology

Copy the example configuration into an ignored local file. Never reuse testnet or production credentials in development.

```bash
cp .env.example .env
npm ci
python3.13 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
```

## Local application

Start the Mini App:

```bash
npm run dev:web
```

Start the API in a second terminal:

```bash
.venv/bin/uvicorn app.main:app --app-dir apps/api --reload
```

PostgreSQL and Redis must match `LOOP_DATABASE_URL` and `LOOP_REDIS_URL`. Schema creation is migration-driven; do not enable automatic production schema creation.

## Browser preview

Telegram authentication cannot be reproduced by arbitrary browser query parameters. For visual development only, enable the explicit mock adapter:

```bash
VITE_MOCK_TELEGRAM=true npm run dev:web -- --host 127.0.0.1
```

The mock contains realistic BANK, DUEL, PROFILE, loader, and inline-message states. Production builds must keep `VITE_MOCK_TELEGRAM=false`; the API still rejects unsigned identity even if a client is modified.

## Telegram development

1. Serve the Mini App and API through HTTPS.
2. Set `LOOP_PUBLIC_ORIGIN`, `LOOP_CORS_ORIGINS`, bot username, bot token, webhook secret, and session secret.
3. Configure the bot menu Web App URL and the webhook only after `/ready` succeeds.
4. Enable inline mode once through BotFather `/setinline`.

See [Telegram integration](telegram.md) for validation and invitation semantics.

## Smart contract

Build and test the existing verified Tolk contract without creating a new wallet:

```bash
acton build
acton check
acton test --coverage --coverage-format text --coverage-minimum-percent 75
```

Acton wallet files and compiled artifacts are ignored. Never place a mnemonic in `.env`, a command argument, shell history, CI variables visible to pull requests, or repository files.

## Quality gates

```bash
npm run check
.venv/bin/ruff check apps/api
.venv/bin/mypy apps/api/app
.venv/bin/pytest apps/api/tests --cov=app --cov-fail-under=60
acton fmt --check
acton check
acton test --coverage --coverage-format text --coverage-minimum-percent 75
```

Browser end-to-end tests run separately:

```bash
npm --workspace @loop/web run e2e
```
