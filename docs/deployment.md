# Deployment and operations

## Production topology

Only nginx publishes ports 80/443. PostgreSQL, Redis, API and workers use an internal Docker network. Images run as non-root with read-only filesystems, dropped capabilities, `no-new-privileges`, health checks and explicit resource limits. PostgreSQL and Redis are never bound to a public host interface.

TLS uses Let's Encrypt with monitored renewal. nginx enforces request limits, exact CORS, CSP, HSTS after a staged rollout, `nosniff`, a restrictive referrer policy and per-route rate limiting. Telegram framing behavior must be verified before tightening `frame-ancestors`.

## Deployment order

1. Configure DNS and copy `.env.example` to a root-owned environment file without placing values in shell history.
2. Start PostgreSQL and Redis; run the one-shot migration container with a DDL-only database role.
3. Deploy immutable API/frontend images, then verify `/live`, `/ready` and the public TON Connect manifest.
4. Configure the bot webhook and menu only after HTTPS is healthy.
5. Run the indexer in shadow mode and reconcile from finalized history before enabling matchmaking.
6. Enable testnet/invite-only low-cap duels; exercise settle, cancel, expiry and restart recovery.

Mainnet deployment is a separate manual multisig change and is not performed by CI.

## Backups and monitoring

Archive PostgreSQL WAL continuously and take encrypted off-site base backups. Target RPO is 5 minutes and RTO is 60 minutes; verify every backup and perform an isolated restore monthly. Redis is disposable.

Alert independently of the production bot for service health, 5xx rate, database locks, disk/inodes, Redis eviction, certificate age, chain checkpoint lag, RPC divergence, overdue duels, bounced payouts, escrow reconciliation mismatch, keeper gas and backup/restore age.

## Rollback

Disable only new offers and referrals. Never disable reveal, settlement, cancellation or timeout refunds. Drain and reconcile active rounds, then roll application images back by digest while retaining chain events and database audit history.

