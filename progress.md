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
- Responsive Telegram Mini App implemented with native theme/safe-area integration, loader, five-step onboarding, BANK/DUEL/PROFILE screens, TON Connect proof binding, encrypted local duel secrets, deterministic canvas visualization and native haptics/navigation.
- Frontend lint, unit tests, production build, Playwright end-to-end flow and the deterministic game-style browser harness pass; mobile screenshots were reviewed visually.
- Native TON escrow implemented in Tolk with typed operations, replay protection, canonical matching, weighted two-party commit-reveal, permissionless timeouts, explicit payout/refund events and pause-safe recovery.
- Nineteen contract scenarios pass with 99.0% line coverage and an 89.2% critical mutation score; API attack/error tests, strict typing and frontend checks also pass.
- The bytecode was deployed to TON testnet and independently read back from TON Center; the live code hash matches the local Acton artifact exactly.
- Docker Compose, immutable release activation, least-privilege deployment user, nginx/Apache shared-host routing, TLS and health checks are deployed; backup procedures and GitHub Actions delivery are configured.
- The Mini App is live over Let's Encrypt HTTPS; API/worker/PostgreSQL/Redis are isolated and healthy, the Telegram webhook has no delivery errors, the bot menu opens the production URL, and inline queries are enabled with the `1 50` duel hint.

## Remaining

- Resolve the GitHub account billing lock so hosted Actions can execute the already configured CI/deployment workflow.
- Keep mainnet disabled until the independent audit, legal, multisig and backup-restore gates are complete.
