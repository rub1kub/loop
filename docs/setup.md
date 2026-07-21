# Setup

## Requirements

- Node.js 22 and npm
- Python 3.12+
- Docker with Compose
- Acton 1.0 with Tolk 1.4

## Install

```bash
cp .env.example .env
make setup
```

For a browser-only UI preview:

```bash
VITE_MOCK_TELEGRAM=true make dev
```

For the API, set a development database/Redis URL and run:

```bash
.venv/bin/uvicorn app.main:app --app-dir apps/api --reload
```

## Telegram configuration

Set the bot token, username, webhook secret, HTTPS public origin and session secret. The API configures the menu button, commands, webhook and inline mode during startup. Unsigned browser identity is rejected unless the compile-time mock flag was intentionally enabled for a local build.

## TON configuration

Use network id `-3`, the testnet provider, and the addresses/hashes in `deployments/testnet`. Never put a wallet seed or private key in application environment variables: users sign through TON Connect, while contract deployment is an explicit operator workflow in Acton.
