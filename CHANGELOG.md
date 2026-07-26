# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [Unreleased]

### Fixed

- Restored the `nosniff` value of the public `X-Content-Type-Options` header and pinned every
  published security-header value in an automated test.
- Made a no-reveal `ExpireDuel` terminal in the projection so monitoring no longer reports a
  permanently overdue duel.
- Qualified referred friends after a confirmed BANK payout, not only after a DUEL settlement.

### Changed

- Reported confirmed friends in the profile instead of referral reward points, which read as the
  monthly LOOP score.
- Recorded the owner decision that PLUSH BRICK zero fee for holders is the committed mainnet
  model, to be executed by DuelEscrow v1.4 holder permits; buyback remains a stated manual
  intent.

- Replaced the activity-cycle BANK with an independent FIFO position queue.
- Split BANK and DUEL into separate contracts, backend modules, tables, events and screens.
- Restricted new DUEL creation to equal 50/50 terms while retaining legacy-contract recovery.
- Reworked Telegram authentication, safe areas, inline invites and monochrome interface.
- Domain-separated DUEL commitments by network and contract address.
- Made direct DUEL acceptance atomic and cryptographically bound to the invited wallet address.

### Added

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
