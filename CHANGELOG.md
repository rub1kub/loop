# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [Unreleased]

### Fixed

- Reconciled ambiguous DUEL wallet callbacks against the TON projection instead of discarding a
  potentially funded quote; stale cleanup now atomically releases AFK and direct reservations.
- Limited the DUEL result needle to one finite, settled-only reveal and removed it from all
  waiting/revealing states and already-known cross-device results.
- Kept invite sharing available after returning from Telegram and stopped showing the previous
  opponent while a new search has no match.
- Made team avatar upload versioned and retryable, restored member photos and switched nested
  team navigation to Telegram's native BackButton.
- Restored the `nosniff` value of the public `X-Content-Type-Options` header and pinned every
  published security-header value in an automated test.
- Made a no-reveal `ExpireDuel` terminal in the projection so monitoring no longer reports a
  permanently overdue duel.
- Qualified referred friends after a confirmed BANK payout, not only after a DUEL settlement.

### Changed

- Result sheet, cards and public feed now show the full verified payout (`Выплата +X GRAM`), not
  the internal delta to the entry; immutable card template version is 5.
- Raised the default referral share to 5% while preserving configured 10% personal overrides;
  the profile action is again the literal `Пригласить в LOOP`.
- Team owners can upload colour avatars; hidden tag/mark fields remain compatibility-only.
- Reported confirmed friends in the profile instead of referral reward points, which read as the
  monthly LOOP score.
- Recorded the owner decision that PLUSH BRICK zero fee for holders is the committed mainnet
  model, executed by DuelEscrow v1.5 holder permits; buyback remains a stated manual
  intent.

- Replaced the activity-cycle BANK with an independent FIFO position queue.
- Split BANK and DUEL into separate contracts, backend modules, tables, events and screens.
- Restricted new DUEL creation to equal 50/50 terms while retaining legacy-contract recovery.
- Reworked Telegram authentication, safe areas, inline invites and monochrome interface.
- Domain-separated DUEL commitments by network and contract address.
- Made direct DUEL acceptance atomic and cryptographically bound to the invited wallet address.

### Added

- Weekly BANK Wave, proof-backed operator contribution workflow and rate-limited momentum
  notifications for a near Wave, teammate entry and an imminent payout.
- DuelEscrow v1.5: PLUSH BRICK holders win the full pool with no protocol fee, proven by a
  domain-separated Ed25519 holder permit bound to the network, contract, offer and wallet.
  Quotes verify mainnet ownership before issuing a permit, the worker re-verifies it before
  projecting an exemption, and enabling the mode requires the live contract to report holder
  support at startup.

- Reproducible testnet deployment manifests and fail-closed verification.
- Finalized chain worker projections, AFK matchmaking reservations and referral attribution.
- Production screenshots, operations runbooks and unified Make targets.
- DUEL v1.1 migration preflight, two-wallet live canary and Prometheus alert rules.
- Monthly LOOP Score, seasonal levels, global/friend rankings and live participation pulse.
- Reader-facing BANK queue rank derived from unfinished proof-backed positions.
- Separate browser owner site with TON proof login, live contract state, application intake controls and an administrative audit trail.
- Owner-only contract reserve funding, protected surplus withdrawal, fee/treasury changes and ownership transfer with locked-value invariants.
- Canonical agent knowledge base covering product rules, architecture, data, contracts, operations,
  task playbooks and the dated production snapshot.
- Proof-bound BANK and DUEL result cards with personal Telegram delivery, native sharing,
  referral links and user-controlled notifications.
