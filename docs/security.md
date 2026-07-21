# Security model

## Trust boundaries

The Telegram WebView, client JavaScript, wallet bridge, RPC responses, inline-message payloads, and all API input are untrusted. The contract is authoritative for locked value and terminal outcomes. PostgreSQL stores replay-safe social projections; Redis is never a correctness dependency.

## Identity and session controls

- Telegram authorization validates raw `initData`, rejects duplicate keys, and enforces age and future-skew windows.
- Reusing a valid Telegram payload cannot extend its original session lifetime; exchange digests are idempotent.
- Sessions are short-lived and audience-bound. Raw `initData`, wallet proofs, secrets, and full Telegram identifiers are not logged.
- Wallet binding uses a fresh, one-use, session-bound TON proof for the exact domain and network.
- The API compares the signed public key with the wallet's on-chain key and canonicalizes addresses before uniqueness checks.

## Application controls

- Mutations require bearer authorization, exact production origin/CORS checks, size limits, and layered Redis, API, and nginx rate limits.
- SQL is parameterized through SQLAlchemy. User-controlled URLs are never fetched.
- AFK matchmaking uses PostgreSQL transactions and uniqueness constraints; Redis locks only reduce contention.
- Direct challenge codes are opaque, expire, bind to one existing creator offer, and cannot silently enter the AFK pool.
- The product and API accept only equal 50/50 duels even though the verified historical contract ABI has wider weighted compatibility.
- No database field is a spendable balance and no backend action can redirect a contract payout.

## On-chain controls

- Funding, matching, settlement, and refund projections require successful non-emulated execution for the configured contract plus masterchain inclusion.
- Unfinalized or malformed transactions do not advance the chain checkpoint.
- Chain events are idempotent by network, account, logical time, and hash.
- Commitments bind domain, offer id, owner, and secret before matching.
- A missing reveal cannot improve the non-revealer's payout: one revealer wins after timeout, while zero reveals refund both principals.
- Stored owners determine refunds and payouts. Message bodies cannot supply an arbitrary payout destination.
- Owner pause authority cannot seize funds or block reveal, cancel, settle, expiry, or refund paths.

## Secret handling

`.env`, Acton wallet files, mnemonics, bot tokens, RPC keys, database passwords, and TLS private keys are ignored by Git. Production consumes a deployment-only `0600` secret file outside immutable release directories.

Never pass a seed phrase or password as a command argument, commit it to history, paste it into CI output, or send it in a vulnerability report. Any credential disclosed in chat or logs must be rotated; deleting the text later does not restore secrecy.

## Mainnet release gate

Mainnet remains disabled until all of the following are complete:

- independent Tolk/TVM and application security audits;
- jurisdiction-specific legal and compliance review;
- multisig governance and documented pause ownership;
- verified public source and bytecode provenance;
- funded-path incident and refund rehearsal;
- encrypted off-site backup restoration test;
- monitored, low-cap canary release and reconciliation.

## Reporting

Follow the private process in [../SECURITY.md](../SECURITY.md). Do not create a public issue containing an exploit, credentials, Telegram identity data, or wallet secrets.
