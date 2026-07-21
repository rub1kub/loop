Original prompt: Transform LOOP from an incorrect wallet-first implementation into a production-ready social Telegram Mini App built around BANK, DUEL, and a Telegram-native social layer. Credentials supplied separately are deliberately excluded from this file.

## Product decisions

- LOOP is not a wallet and has no internal spendable balance. TON Connect is limited to external wallet ownership proofs, transaction confirmation, payouts, and asset checks.
- BANK is a seven-day living social cycle represented by a jar. Verified system, Telegram, and on-chain events advance its progress and history.
- DUEL is an equal 50/50 person-to-person challenge. The product rejects probability controls and casino language.
- AFK matchmaking and direct Telegram invitations are separate paths. A direct challenge binds to one funded offer and cannot enter the generic pool.
- The contract is authoritative for escrow and outcomes. PostgreSQL stores idempotent social projections; Redis is disposable coordination state.
- Mainnet remains disabled pending an independent audit, legal review, multisig governance, recovery rehearsal, and verified backups.

## Completed

- Replaced wallet-goal domain behavior with BANK cycles, event progress, history, and proof references.
- Restricted the application, API, matcher, and bot to equal 50/50 DUEL terms while preserving the verifiable deployed contract.
- Added AFK matchmaking, exact-offer direct challenges, Telegram inline messages, and invitation acceptance flows.
- Rebuilt the Mini App around the selected monochrome Living Jar direction with functional onboarding, loader, BANK, DUEL, PROFILE, history, settings, and inline preview states.
- Added masterchain-confirmed transaction validation, fail-closed checkpoints, contract/wallet/transaction/Jetton audit tools, and explorer proofs in application responses.
- Audited the existing testnet deployment: active state, bytecode hash match, deployment transaction, owner/treasury, immutable fee, pause authority, recovery permissions, and locked state.
- Passed frontend lint, unit tests and production build; strict API lint/type checks and 21 tests; 19 Acton contract tests with coverage above the configured gate.
- Published commercial open-source documentation, screenshots, design comparison evidence, contribution guidance, security policy, deployment operations, and TON audit details.
- Committed and pushed each product stage to `agent/loop-product-transformation` using Conventional Commits.

## Remaining operational gates

- Rotate every credential previously shared outside the production secret store before the next release.
- Merge the reviewed branch into `main` to trigger the immutable testnet deployment workflow.
- Resolve the GitHub account billing lock if hosted Actions remain unable to start.
- Keep mainnet disabled until all documented release gates are complete.
