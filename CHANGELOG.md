# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [Unreleased]

### Changed

- Replaced the activity-cycle BANK with an independent FIFO position queue.
- Split BANK and DUEL into separate contracts, backend modules, tables, events and screens.
- Rebuilt DUEL around canonical 25/50/75 terms and commit–reveal settlement.
- Reworked Telegram authentication, safe areas, inline invites and monochrome interface.

### Added

- Reproducible testnet deployment manifests and fail-closed verification.
- Finalized chain worker projections, AFK matchmaking reservations and referral attribution.
- Production screenshots, operations runbooks and unified Make targets.
