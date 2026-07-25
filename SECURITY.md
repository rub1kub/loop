# Security policy

LOOP is currently a testnet-only project. It has not completed an independent mainnet security audit. Do not send mainnet assets to the published contract or treat testnet balances as production funds.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/rub1kub/loop/security/advisories/new). Include the affected component, impact, minimal sanitized reproduction, and any suggested mitigation.

Do not open a public issue for an active exploit. Never include mnemonics, private keys, bot tokens, Telegram `initData`, wallet proofs, production URLs containing credentials, or personal data in a report.

The maintainer will acknowledge actionable reports, validate impact, prepare a fix, and coordinate disclosure. Public reports that expose credentials or exploit details may be removed to protect users.

## Supported versions

Only the latest commit on `main` and the currently published testnet release receive security
fixes. Mainnet code is not a supported deployment until every release gate in
[docs/security.md](docs/security.md) is complete.
