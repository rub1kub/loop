# Deployment and operations

The published environment uses Docker Compose behind Apache and nginx at `app.tonsuite.org`. It is testnet-only.

## Required configuration

Copy `.env.example` to the protected production environment and replace secrets. Production validation requires HTTPS, strong session/webhook/metrics secrets, bot identity, both contract addresses and both 32-byte code hashes. Secret files are never committed.

## Release

1. All static, unit, browser and contract checks pass.
2. `scripts/verify-contracts.py` matches local builds, manifests and finalized testnet state.
3. The immutable Git commit is uploaded to `/opt/loop/releases/<sha>`.
4. PostgreSQL backup completes before migration.
5. API image and web assets build; database and Redis become healthy.
6. Alembic upgrades to head.
7. API startup attests BankQueue and DuelEscrow code hashes.
8. API and worker health pass before nginx reload and public smoke.

```bash
make deploy RELEASE=<40-character-git-sha>
make smoke-test
```

The BANK/DUEL split migration archives old cycle-era tables under `legacy_*`; it does not reinterpret their records as financial state. The activation script stops writers before backup and automatically restores both the pre-migration database and previous immutable release if migration, health, nginx or public smoke validation fails.

## Health checks

```bash
curl --fail https://app.tonsuite.org/health
curl --fail https://app.tonsuite.org/ready
```

Readiness checks PostgreSQL, Redis and configured contract attestation. Operations additionally inspect worker heartbeat, current Alembic revision, webhook URL/status, container health and hashed frontend asset delivery.

## Contract deployment

Normal application releases never deploy contracts. Explicit testnet broadcasting requires:

```bash
ALLOW_TESTNET_DEPLOY=1 make contracts-deploy-testnet
```

After any deployment, update the relevant manifest and environment hash, run `make contracts-verify`, then release the application. Mainnet deployment is blocked in settings until external audit, governance, legal and recovery gates are documented.

## Backup and recovery

`deploy/backup-postgres.sh` creates timestamped compressed database dumps with restricted permissions and returns the validated archive path to the activation script. Failed activation restores that archive before restarting the prior release. A disaster-recovery restore is still an operator action into a clean database, followed by migration validation and deterministic chain replay. Contract funds remain recoverable through permissionless contract timeouts even if LOOP is unavailable.
