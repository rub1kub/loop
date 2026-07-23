Original prompt: Transform LOOP from an incorrect wallet-first implementation into a production-ready social Telegram Mini App built around BANK, DUEL, and a Telegram-native social layer. Credentials supplied separately are deliberately excluded from this file.

## Product decisions

- LOOP is not a wallet and has no internal spendable balance. TON Connect is limited to external wallet ownership proofs, transaction confirmation, payouts, and asset checks.
- BANK is a seven-day living social cycle represented by a jar. Verified system, Telegram, and on-chain events advance its progress and history.
- DUEL is an equal 50/50 person-to-person challenge. The product rejects probability controls and casino language.
- RATING is a monthly proof-backed reputation layer. Score never uses stake size, profit,
  balance, wins or losses.
- AFK matchmaking and direct Telegram invitations are separate paths. A direct challenge binds to one funded offer and cannot enter the generic pool.
- The contract is authoritative for escrow and outcomes. PostgreSQL stores idempotent social projections; Redis is disposable coordination state.
- Mainnet remains disabled pending an independent audit, legal review, multisig governance, recovery rehearsal, and verified backups.

## Completed

- Replaced wallet-goal domain behavior with BANK cycles, event progress, history, and proof references.
- Restricted the application, API, matcher, and bot to equal 50/50 DUEL terms while preserving the verifiable deployed contract.
- Added AFK matchmaking, exact-offer direct challenges, Telegram inline messages, and invitation acceptance flows.
- Rebuilt the Mini App around the selected monochrome Living Jar direction with functional onboarding, loader, BANK, DUEL, RATING, PROFILE, history, settings, and inline preview states.
- Added reader-facing BANK queue rank, active participants, a transparent monthly LOOP Score,
  SIGNAL/PULSE/ORBIT/LOOP levels, global ranking and a qualified-friend circle.
- Added masterchain-confirmed transaction validation, fail-closed checkpoints, contract/wallet/transaction/Jetton audit tools, and explorer proofs in application responses.
- Audited the existing testnet deployment: active state, bytecode hash match, deployment transaction, owner/treasury, immutable fee, pause authority, recovery permissions, and locked state.
- Passed frontend lint, unit tests, responsive Playwright flows and production build; strict API
  lint/type checks and proof-derived RATING integration tests; Acton contract coverage remains
  above the configured gate.
- Published commercial open-source documentation, screenshots, design comparison evidence, contribution guidance, security policy, deployment operations, and TON audit details.
- Published the active product line on `main` using Conventional Commits and immutable releases.

## Remaining operational gates

- Resolve the GitHub account billing lock if hosted Actions remain unable to start.
- Keep mainnet disabled until all documented release gates are complete.
