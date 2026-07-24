# Contributing to LOOP

Thanks for helping build LOOP as a Telegram Mini App for TON testnet. Contributions must preserve the BANK/DUEL boundary: LOOP is not a wallet, does not hold an internal balance, and uses TON Connect only for external wallet proofs and transactions.

Start with the canonical [agent and maintainer knowledge base](docs/agents/README.md).

## Development workflow

1. Create a focused branch from `main`.
2. Keep changes small and avoid unrelated formatting or generated artifacts.
3. Add or update the smallest relevant tests.
4. Run the quality gates for the layers you changed.
5. Open a pull request that explains product impact, security impact, and verification evidence.

```bash
npm ci
python3.13 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
```

## Quality gates

Web changes:

```bash
npm run lint:web
npm run test:web
npm run build:web
npm run format:check
npm --workspace @loop/web run e2e
```

API changes:

```bash
.venv/bin/ruff check apps/api
.venv/bin/mypy apps/api/app
.venv/bin/pytest apps/api/tests --cov=app --cov-fail-under=60
```

Contract changes:

```bash
acton fmt --check
acton check
acton test --coverage --coverage-format text --coverage-minimum-percent 75
```

## Commit convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat(bank): add verified fifo payout
fix(duel): keep direct invitations out of AFK matching
docs(ton): record deployment verification
```

## Pull request checklist

- Product language describes the explicit testnet BANK simulation or DUEL challenge, not a wallet dashboard.
- No seed, private key, token, credential, Telegram payload, or PII is committed or logged.
- New funded paths have cancellation or timeout recovery and documented proof semantics.
- Contract address, network, amount units, and transaction finality are explicit.
- UI changes work at Telegram mobile widths and include loading, empty, error, and active states.
- Relevant checks pass and visible UI changes include screenshots.

Security reports must follow [SECURITY.md](SECURITY.md), not the public issue tracker.
