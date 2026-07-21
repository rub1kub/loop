# Setup

## Prerequisites

Use Node.js 22+, Python 3.12+, PostgreSQL 16+, Redis 7+ and Acton 1.0.0. Copy `.env.example` to an ignored `.env`; never reuse test or production credentials.

## Application

```bash
npm ci
npm run dev:web

python3.13 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
.venv/bin/uvicorn app.main:app --app-dir apps/api --reload
```

Set `VITE_MOCK_TELEGRAM=true` only for browser UI development. Real authentication must run in a Telegram WebView with signed `initData`.

## Contract

```bash
acton build
acton check
acton test --coverage --coverage-format text --coverage-minimum-percent 75
```

Acton wallet files and compiled artifacts are ignored. Import or generate a testnet wallet through Acton's secure wallet store; never put a mnemonic in `.env`, shell history or repository files.

## Verification

```bash
npm run check
.venv/bin/pytest apps/api/tests --cov=app --cov-fail-under=60
npm --workspace @loop/web run e2e
```
