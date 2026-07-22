#!/usr/bin/env bash
set -Eeuo pipefail

exec 9>/opt/loop/deploy.lock
if ! flock -n 9; then
  echo "another LOOP deployment is running" >&2
  exit 75
fi

release_id=${1:?release id is required}
if [[ ! $release_id =~ ^[0-9a-f]{40}$ ]]; then
  echo "invalid release id" >&2
  exit 2
fi

loop_root=/opt/loop
release_dir="$loop_root/releases/$release_id"
shared_env="$loop_root/shared/.env.production"
previous_release=""
backup_path=""
rollback_armed=false
database_changed=false

if [[ -L "$loop_root/current" ]]; then
  previous_release=$(readlink -f "$loop_root/current")
fi

rollback_release() {
  local exit_code=$?
  trap - ERR
  if [[ $rollback_armed != true ]]; then
    exit "$exit_code"
  fi

  set +e
  echo "release activation failed; restoring the previous application and database" >&2
  cd "$release_dir"
  export LOOP_IMAGE_TAG="$release_id"
  docker compose --project-name loop --env-file .env.production stop api worker >/dev/null

  local restore_ok=true
  if [[ $database_changed == true ]]; then
    restore_ok=false
  fi
  if [[ $database_changed == true && -n $backup_path && -s $backup_path ]]; then
    if docker compose --project-name loop --env-file .env.production exec -T db \
      sh -c 'pg_restore --clean --if-exists --exit-on-error --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
      <"$backup_path"; then
      restore_ok=true
    else
      echo "database restoration failed; previous application was not restarted" >&2
    fi
  fi

  if [[ $restore_ok == true && -n $previous_release && -d $previous_release ]]; then
    ln -sfn "$shared_env" "$previous_release/.env.production"
    cd "$previous_release"
    export LOOP_IMAGE_TAG
    LOOP_IMAGE_TAG=$(basename "$previous_release")
    docker compose --project-name loop --env-file .env.production up -d api worker
    docker compose --project-name loop --env-file .env.production up -d --wait --wait-timeout 120 api
    ln -sfn "$previous_release" "$loop_root/current.next"
    mv -Tf "$loop_root/current.next" "$loop_root/current"
    if sudo nginx -t; then
      sudo systemctl reload nginx
    fi
  fi
  exit "$exit_code"
}

trap rollback_release ERR

test -d "$release_dir"
test -f "$shared_env"
chmod 755 "$release_dir"
ln -sfn "$shared_env" "$release_dir/.env.production"

cd "$release_dir"
export LOOP_IMAGE_TAG="$release_id"
docker compose --project-name loop --env-file .env.production build --pull api
docker compose --project-name loop --env-file .env.production up -d --wait db redis
if [[ -n $previous_release ]]; then
  rollback_armed=true
  docker compose --project-name loop --env-file .env.production stop api worker
  backup_path=$("$release_dir/deploy/backup-postgres.sh")
  if [[ $backup_path != "$loop_root/backups/"*.dump || ! -s $backup_path ]]; then
    echo "database backup was not created at the expected path" >&2
    false
  fi
fi
database_changed=true
docker compose --project-name loop --env-file .env.production run --rm migrate
docker compose --project-name loop --env-file .env.production up -d api worker
docker compose --project-name loop --env-file .env.production up -d --wait --wait-timeout 120 api worker
curl --fail --silent --show-error http://127.0.0.1:8000/ready >/dev/null

ln -sfn "$release_dir" "$loop_root/current.next"
mv -Tf "$loop_root/current.next" "$loop_root/current"
sudo nginx -t
sudo systemctl reload nginx
curl --fail --silent --show-error https://app.tonsuite.org/ready >/dev/null
rollback_armed=false
trap - ERR
