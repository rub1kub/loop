#!/usr/bin/env bash
set -Eeuo pipefail

backup_root=/opt/loop/backups
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
archive_path="$backup_root/loop-$timestamp.dump"
umask 077
set -a
source /opt/loop/shared/.env.production
set +a
mkdir -p "$backup_root"
chmod 700 "$backup_root"
cd /opt/loop/current
docker compose --project-name loop --env-file .env.production exec -T db \
  pg_dump --format=custom --no-owner --no-acl \
  --username="${POSTGRES_USER:?POSTGRES_USER must be exported}" \
  "${POSTGRES_DB:?POSTGRES_DB must be exported}" >"$archive_path"
test -s "$archive_path"
sha256sum "$archive_path" >"$archive_path.sha256"
printf '%s\n' "$archive_path"
