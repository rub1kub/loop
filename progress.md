Original prompt: Build a production-ready LOOP Telegram Mini App for TON/GRAM with an Apple-like monochrome UI, BANK/DUEL/PROFILE, TON Connect, Tolk/Acton contracts, FastAPI/aiogram/PostgreSQL/Redis, security, tests, deployment, and a public GitHub repository. Credentials supplied separately are deliberately excluded from this file.

## Decisions

- GRAM is treated as the native TON network currency described by current TON Docs; all amounts use integer nano units.
- DUEL uses funded offers plus two-party commit-reveal. A player who reveals while the opponent does not wins after the deadline; if neither reveals, both principals are refunded.
- The contract is the source of truth for escrow and outcomes. PostgreSQL stores projections, Redis stores disposable coordination data only.
- BANK is a non-custodial wallet savings goal until a separate bank economic model is specified; it never creates a database balance.
- Mainnet activation remains disabled until legal review and an independent smart-contract audit. Testnet is the release target.

## Work log

- Architecture and threat model drafted from the product brief and current TON/Telegram guidance.
- FastAPI/aiogram backend implemented with strict Telegram authentication, signed sessions, TON proof verification, wallet binding, non-custodial BANK goals, deterministic duel quotes, referrals, inline invites, durable models, migrations and chain projection worker.
- Backend lint and focused unit/API/property tests pass.

## Remaining

- Implement and validate frontend, contract, deployment, and live testnet flow.
