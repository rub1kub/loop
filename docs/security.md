# Security model

## Trust boundaries

The Telegram WebView, client JavaScript, wallet bridge, RPC responses and all API input are untrusted. Contract state is the financial source of truth. Chain ingestion is reconciled from overlapping finalized history; a stream is only a low-latency hint.

## Controls

- Telegram authorization validates the raw query with the Bot API HMAC construction, rejects duplicate keys, enforces a short age/future-skew window and consumes an exchange digest once.
- Sessions are short-lived, audience-bound HMAC tokens. Secrets, raw `initData`, wallet proofs and full Telegram identifiers are never logged.
- Wallet binding requires a fresh, one-use, session-bound TON proof for the exact domain and network. Wallet address formatting is canonicalized before uniqueness checks.
- Mutations require bearer authorization, exact production CORS/origin policy, size limits and layered Redis/API/nginx rate limits.
- SQL is parameterized through SQLAlchemy. Outbound HTTP targets come only from operator configuration; user-controlled URLs are never fetched.
- Matchmaking correctness uses PostgreSQL transactions and uniqueness constraints; Redis locks only reduce contention.
- The escrow authenticates `in.senderAddress`, uses fixed-width payloads, checks principal and deadlines, rejects replays, preserves timeout recovery while paused and has no admin seizure path.
- On-chain randomness alone is not used. Commitments bind secrets before participants are paired, and non-reveal cannot improve a player's payout.

## Mainnet release gate

Mainnet is intentionally disabled until an independent Tolk/TVM audit, jurisdiction-specific legal review, multisig governance, incident/refund rehearsal and restoration of an encrypted off-site PostgreSQL backup have all completed. Single-block TON PRNG is not an acceptable substitute for the commit-reveal protocol.

## Secret handling

`.env`, Acton wallet files, mnemonics, bot tokens, RPC keys, database passwords and TLS private keys are ignored by Git. Production consumes root-owned `0400` secret files. Deployment/admin keys stay offline or in multisig custody; a low-value keeper, if used, has no privileged contract role.

## Reporting

Please disclose vulnerabilities privately to the repository owner. Do not create a public issue containing an exploit, credentials or personally identifiable data.

