# Deployment and operations

The published environment uses Docker Compose behind Apache and nginx at `app.tonsuite.org`.
The active release is testnet-only. Mainnet support exists behind an evidence gate and is not
active.

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
the API, chain worker or notifier and without touching PostgreSQL. It refuses the release when API code, migrations, Compose,
contracts or deployment manifests differ from the active runtime release. Use the full command
for any such change or for a staged production environment.

`--fast` still builds production web assets but skips local tests. `--full-checks` additionally
runs browser, security and contract verification. `--allow-unpushed` is an emergency escape hatch
and should not be used for routine releases. Override the SSH alias with
`LOOP_DEPLOY_HOST=<host>`.

The server activation then performs these guarded steps:

1. The immutable Git commit and built web entrypoint are present under the release SHA.
2. Writers stop and a staged `.env.production.next` is activated atomically with rollback protection.
3. A contract-network change requires both source contracts to be paused with `locked=0` and no
   active BANK/DUEL projection; a same-network DUEL address change applies the narrower DUEL drain
   check.
4. PostgreSQL backup completes before migration.
5. The API image builds; database and Redis become healthy.
6. Alembic upgrades to head and repeats the idle-projection guard.
7. API startup attests both code hashes, retained reserves and the DUEL network/address/signer
   domain.
8. API, chain-worker and notification-worker health pass before nginx reload and public smoke.
9. The CLI verifies the runtime SHA, web SHA, all five containers, Telegram webhook and exact frontend asset.
10. `/control` loads as a regular browser route, rejects an unauthenticated overview request and
    requests a one-time owner TON proof without Telegram initialization.

The BANK/DUEL split migration archives old cycle-era tables under `legacy_*`; it does not reinterpret their records as financial state. The activation script stops writers before preflight and backup, then automatically restores the protected environment, pre-migration database and previous immutable release if migration, health, nginx or public smoke validation fails.

To stage a contract switch, create `/opt/loop/shared/.env.production.next` from the current protected environment, update only the intended values and set mode `600`. The activation script consumes it only after writers stop.

## Health checks

```bash
curl --fail https://app.tonsuite.org/live
curl --fail https://app.tonsuite.org/ready
```

Readiness checks PostgreSQL, Redis and configured contract attestation. Operations additionally
inspect both worker heartbeats, current Alembic revision, webhook URL/status, container health and
hashed frontend asset delivery.

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

After any deployment, update the relevant manifest and environment hash, run
`make contracts-verify`, then release the application.

### Mainnet release gate

Mainnet remains blocked until a specific clean `main` commit has an independent audit report.
Create `deployments/mainnet/release.json` from the example and run:

```bash
make contracts-mainnet-technical
make contracts-mainnet-preflight
```

The technical gate requires 98% line coverage, 75% branch coverage, a stable gas snapshot,
separate BANK/DUEL critical and major mutation thresholds, API security tests and TON message
tests. The preflight additionally binds the release to the audited commit/report, mainnet owner,
treasury, invite signer and conservative limits.

Contracts deploy paused and only through the explicit real-funds consent gate:

```bash
ALLOW_MAINNET_DEPLOY=I_UNDERSTAND_REAL_FUNDS \
LOOP_CONTRACT_OWNER_ADDRESS=<owner> \
LOOP_CONTRACT_TREASURY_ADDRESS=<treasury> \
LOOP_DUEL_INVITE_PUBLIC_KEY=<64-hex-public-key> \
  make contracts-deploy-mainnet
```

Publish source verification, complete the BANK shadow payout cycle and run the direct two-wallet
DUEL mainnet canary in `--evidence-only` mode before switching the application. Put the finalized
evidence in the contract manifests, then run:

```bash
make contracts-mainnet-verify
```

The application environment must repeat the exact audited commit, report SHA-256 and launch caps,
point at a non-testnet provider and explicitly enable both mainnet and the canary monitor. Release
activation refuses the switch while the source network has live obligations or either production
contract is not paused and empty.

Do not run a payout cycle on the production BANK address: a real FIFO cycle necessarily leaves the
last contributor in the queue. Deploy the same audited code to a separate shadow address, rehearse
the exact two-wallet cycle on a fork and only then broadcast it to the shadow contract. The verifier
checks both inbound messages, distinct wallets, both fees, the payout body/value and finality, and
also proves that the shadow code hash equals the production manifest.

```bash
LOOP_ALLOW_MAINNET_CANARY=1 \
  .venv/bin/python scripts/run-bank-canary.py \
  --network mainnet \
  --contract <shadow-address> \
  --production-contract <production-address> \
  --treasury <shadow-treasury> \
  --first-wallet loop-mainnet-canary-a \
  --second-wallet loop-mainnet-canary-b \
  --broadcast
```

Record the two finalized transaction hashes, logical times and masterchain blocks in
`deployments/mainnet/bank.json`. Deploy the final BANK separately, paused and empty. The post-deploy
gate rejects evidence that points at that production address.

The DUEL canary service refuses to start unless both configured Acton aliases already exist and
resolve to distinct addresses. They are dedicated low-value operator wallets, never user wallets.
It rehearses against a network fork, confirms the contract network/address/signer domain, clears
only a recoverable interrupted canary state and then broadcasts. Testnet may request an Acton
airdrop below the safety floor; mainnet never invokes a faucet and additionally requires
`LOOP_ALLOW_MAINNET_CANARY=1`. Hosts pin the project-compatible Acton binary at
`/opt/loop/tools/acton`.

Create the aliases once in the host's protected Acton store, then verify addresses and balances without exporting either mnemonic:

```bash
acton wallet new --name loop-canary-a --version v5r1 --global --secure true --airdrop
acton wallet new --name loop-canary-b --version v5r1 --global --secure true --airdrop
acton wallet list --balance
```

The faucet is testnet-only and rate-limited. The hourly job never creates wallets or handles user
keys. Mainnet uses the separate `loop-mainnet-canary-a/b` aliases and stays disabled until the
mainnet release gate is complete.

## Backup and recovery

`deploy/backup-postgres.sh` creates timestamped compressed database dumps with restricted permissions and returns the validated archive path to the activation script. Failed activation restores that archive before restarting the prior release. A disaster-recovery restore is still an operator action into a clean database, followed by migration validation and deterministic chain replay. Contract funds remain recoverable through permissionless contract timeouts even if LOOP is unavailable.
