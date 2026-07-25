# Deployment and operations

The published environment uses Docker Compose behind Apache and nginx at `app.tonsuite.org`. It is testnet-only.

## Required configuration

Copy `.env.example` to the protected production environment and replace secrets. Production
validation requires HTTPS, strong session/webhook/metrics secrets, bot identity, both contract
addresses and both 32-byte code hashes. `LOOP_CONTROL_ADMIN_WALLET` must equal the on-chain owner
that may enter the browser site at `/control`. DUEL additionally requires a 32-byte Ed25519 signing
seed and its derived public key; this application key is not a TON wallet. Secret files are never
committed.

## Release

The production path is a direct SSH release from a maintainer machine. GitHub stores the source
history but GitHub Actions is not involved in delivery.

```bash
npm run deploy:vps
```

The deployer requires a clean `main` whose exact SHA is already on `origin/main`. It runs the
standard local checks, creates the source tree with `git archive`, overlays only the fresh web
build, strips macOS extended metadata, verifies SHA-256 on the server and installs the tree under
`/opt/loop/releases/<sha>`. Activation runs in a transient systemd unit, so an SSH interruption
does not terminate a release halfway through.

Before upload, the CLI reserves headroom for the release, two database-sized copies and 4 GiB of
Docker build space. Deploy and restart share the same server lock, so operational commands cannot
interrupt migration or rollback.

Use the explicit modes when needed:

```bash
npm run deploy:vps:web
npm run deploy:vps -- --dry-run
npm run deploy:vps -- --fast
npm run deploy:vps -- --full-checks
npm run deploy:vps:status
npm run deploy:vps:restart
```

`npm run deploy:vps:web` is the guarded static-web path. It switches
`/opt/loop/web-current` atomically, reloads nginx and runs public health checks without restarting
the API/worker or touching PostgreSQL. It refuses the release when API code, migrations, Compose,
contracts or deployment manifests differ from the active runtime release. Use the full command
for any such change or for a staged production environment.

`--fast` still builds production web assets but skips local tests. `--full-checks` additionally
runs browser, security and contract verification. `--allow-unpushed` is an emergency escape hatch
and should not be used for routine releases. Override the SSH alias with
`LOOP_DEPLOY_HOST=<host>`.

The server activation then performs these guarded steps:

1. The immutable Git commit and built web entrypoint are present under the release SHA.
2. Writers stop and a staged `.env.production.next` is activated atomically with rollback protection.
3. A DUEL address change requires `locked=0` on the previous contract and no active DUEL projection.
4. PostgreSQL backup completes before migration.
5. The API image builds; database and Redis become healthy.
6. Alembic upgrades to head and repeats the idle-projection guard.
7. API startup attests BankQueue and DuelEscrow code hashes.
8. API and worker health pass before nginx reload and public smoke.
9. The CLI verifies the runtime SHA, web SHA, all four containers, Telegram webhook and exact frontend asset.
10. `/control` loads as a regular browser route, rejects an unauthenticated overview request and
    requests a one-time owner TON proof without Telegram initialization.

The BANK/DUEL split migration archives old cycle-era tables under `legacy_*`; it does not reinterpret their records as financial state. The activation script stops writers before preflight and backup, then automatically restores the protected environment, pre-migration database and previous immutable release if migration, health, nginx or public smoke validation fails.

To stage a contract switch, create `/opt/loop/shared/.env.production.next` from the current protected environment, update only the intended values and set mode `600`. The activation script consumes it only after writers stop.

## Health checks

```bash
curl --fail https://app.tonsuite.org/live
curl --fail https://app.tonsuite.org/ready
```

Readiness checks PostgreSQL, Redis and configured contract attestation. Operations additionally inspect worker heartbeat, current Alembic revision, webhook URL/status, container health and hashed frontend asset delivery.

DUEL exposes authenticated Prometheus metrics for projection heartbeat, stale funding, overdue reveals, unbound direct matches, the last verified two-wallet canary and its lowest wallet balance. `deploy/monitoring/duel-alerts.yml` contains fail-closed rules. The public nginx virtual host always returns `404` for `/metrics`; scrapers use `127.0.0.1:8000` with the metrics bearer token.

Hosts without Prometheus run the same critical checks through `loop-duel-monitor.timer`. The oneshot service reads the protected metrics token, logs a compact JSON result to journald and fails if the worker heartbeat is stale, funding/reveals are overdue or a direct match lacks its bound opponent. Set `LOOP_REQUIRE_DUEL_CANARY=true` only after the two pre-existing canary wallet aliases are installed and the first live run succeeds.

```bash
sudo install -m 0644 deploy/systemd/loop-duel-monitor.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now loop-duel-monitor.timer
sudo systemctl start loop-duel-monitor.service
sudo systemctl status loop-duel-monitor.service --no-pager
```

## Contract deployment

Normal application releases never deploy contracts. Explicit testnet broadcasting requires:

```bash
ALLOW_TESTNET_DEPLOY=1 LOOP_DUEL_INVITE_PUBLIC_KEY=<64-hex-public-key> \
  make contracts-deploy-duel-testnet
```

After any deployment, update the relevant manifest and environment hash, run `make contracts-verify`, then release the application. Mainnet deployment is blocked in settings until external audit, governance, legal and recovery gates are documented.

For a newly deployed, empty BANK contract, emulate the one-time genesis funding smoke against a testnet fork before broadcasting the same arguments. The script fails if the queue is not empty or the resulting funding, fee, target and queue state differ from the contract formula.

```bash
acton script --fork-net testnet scripts/smoke-bank-genesis.tolk <address> <position-id> 1000000000 12500
acton script --net testnet scripts/smoke-bank-genesis.tolk <address> <position-id> 1000000000 12500
```

The DUEL canary service refuses to start unless both configured Acton aliases already exist and resolve to distinct addresses. These are dedicated low-value testnet operator wallets, never user wallets. It performs a fork rehearsal before every live run, checks that the application and contract are still testnet-scoped, and requests an Acton testnet airdrop only when either balance falls below `LOOP_DUEL_CANARY_MIN_BALANCE_NANO`. A failed faucet or insufficient post-airdrop balance stops the live transaction and becomes a stale-canary alert. Hosts pin the project-compatible Acton binary at `/opt/loop/tools/acton`; release activation materializes the matching embedded standard library and writable build cache before the canary namespace can start.

Create the aliases once in the host's protected Acton store, then verify addresses and balances without exporting either mnemonic:

```bash
acton wallet new --name loop-canary-a --version v5r1 --global --secure true --airdrop
acton wallet new --name loop-canary-b --version v5r1 --global --secure true --airdrop
acton wallet list --balance
```

The faucet is testnet-only and rate-limited. The hourly job never creates wallets, never handles user keys and never broadcasts to mainnet.

## Backup and recovery

`deploy/backup-postgres.sh` creates timestamped compressed database dumps with restricted permissions and returns the validated archive path to the activation script. Failed activation restores that archive before restarting the prior release. A disaster-recovery restore is still an operator action into a clean database, followed by migration validation and deterministic chain replay. Contract funds remain recoverable through permissionless contract timeouts even if LOOP is unavailable.
