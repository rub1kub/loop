# Security policy

LOOP is active on TON mainnet and has not completed an independent external audit. Treat every
transaction as involving real funds. Automated tests, source verification and canaries reduce
known risk; they do not prove that the contracts or application are free of vulnerabilities.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/rub1kub/loop/security/advisories/new). Include the affected component, impact, minimal sanitized reproduction, and any suggested mitigation.

Do not open a public issue for an active exploit. Never include mnemonics, private keys, bot tokens, Telegram `initData`, wallet proofs, production URLs containing credentials, or personal data in a report.

The maintainer will acknowledge actionable reports, validate impact, prepare a fix, and coordinate disclosure. Public reports that expose credentials or exploit details may be removed to protect users.

## Supported versions

Only the latest commit on `main` and the currently deployed production release receive security
fixes. Historical testnet deployments and retired mainnet contracts are unsupported except for
documented recovery paths. Current trust boundaries and owner powers are described in
[docs/security.md](docs/security.md).
