# Deployment and operations

LOOP ships immutable, testnet-only releases. Mainnet is disabled in application validation and is not deployed by CI.

## Production topology

On the current shared VPS, Apache owns ports 80/443 and forwards only the LOOP SNI host to nginx on `127.0.0.1:18791`. nginx serves the compiled Mini App and proxies the API on `127.0.0.1:8000`. PostgreSQL, Redis, API, migrations, and the chain worker share a private Docker network; databases are not exposed publicly.

Application containers run without root, with read-only filesystems, dropped capabilities, `no-new-privileges`, health checks, bounded logs, and explicit resource limits. nginx applies exact CORS, CSP, request limits, safe framing for Telegram, HSTS after staged validation, `nosniff`, and a restrictive referrer policy.

## Configuration

Create `/opt/loop/shared/.env.production` as a root-owned `0600` file outside every release directory. Use deployment secrets or an interactive secret manager; never paste credentials into a command, CI log, repository, or support ticket.

Required production values include:

- Telegram bot token, username, webhook secret, and session secret;
- exact public origin and CORS origin;
- PostgreSQL and Redis credentials;
- TON testnet endpoint, contract address, and audited code hash;
- metrics authentication token.

Production startup fails when required values are missing, secrets are too short, HTTPS is absent, mainnet is selected, or the configured contract hash cannot be attested.

## Release flow

The `main` workflow runs web, API, and contract gates. A successful release is uploaded into `/opt/loop/releases/<git-sha>` and activated by `deploy/activate-release.sh`.

Activation performs this sequence:

1. build the API image under the immutable Git SHA;
2. wait for PostgreSQL and Redis;
3. run Alembic migrations as a one-shot container;
4. start API and finalized chain worker;
5. verify local readiness;
6. atomically switch `/opt/loop/current`;
7. validate and reload nginx;
8. verify public HTTPS readiness.

The activation script restores the previous symlink when nginx validation fails.

Manual topology checks use the same Compose file:

```bash
docker compose --env-file .env.production config
docker compose --env-file .env.production up -d --wait db redis
docker compose --env-file .env.production run --rm migrate
docker compose --env-file .env.production up -d api worker
curl --fail --silent --show-error https://144-31-30-62.sslip.io/ready
```

## Telegram activation

Configure the webhook and menu only after HTTPS is ready. Inline mode is the one BotFather-only setting: run `/setinline` for the bot and verify that Bot API `getMe` reports `supports_inline_queries=true`.

## Monitoring

Alert outside the production bot for service health, 5xx rate, database locks, disk and inodes, Redis eviction, certificate age, chain checkpoint lag, missing masterchain finality, RPC divergence, overdue duels, bounced payouts, escrow reconciliation mismatch, and backup age.

The chain worker must fail closed. An RPC payload without successful execution, expected account, transaction identity, or masterchain inclusion is retried and cannot advance the checkpoint.

## Backups

Archive PostgreSQL WAL continuously and take encrypted off-site base backups. The operating target is RPO 5 minutes and RTO 60 minutes. Verify every backup and perform an isolated restore monthly. Redis is disposable.

## Rollback and incident mode

Disable only new offers and matchmaking. Never disable reveal, cancellation, settlement, expiry, or refund paths. Drain and reconcile active duels, then roll application images back by digest while preserving chain events, BANK proofs, and database audit history.

Rotating an exposed bot token, wallet seed, password, API key, or TLS key is an incident-response action and must happen before redeployment. Do not attempt to sanitize a leaked credential by merely deleting it from the latest commit.
