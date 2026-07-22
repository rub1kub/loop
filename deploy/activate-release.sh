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
pending_env="$loop_root/shared/.env.production.next"
previous_release=""
backup_path=""
env_backup=""
env_changed=false
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
  if [[ $env_changed == true && -n $env_backup && -s $env_backup ]]; then
    install -m 600 "$env_backup" "$shared_env"
  fi
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
if [[ -e $pending_env && $(stat -c '%a' "$pending_env") != 600 ]]; then
  echo "pending production environment must have mode 600" >&2
  exit 3
fi
if [[ ! -s "$release_dir/apps/web/dist/index.html" ]]; then
  echo "release is missing the built web entrypoint: apps/web/dist/index.html" >&2
  exit 3
fi
chmod 755 "$release_dir"
ln -sfn "$shared_env" "$release_dir/.env.production"

cd "$release_dir"
export LOOP_IMAGE_TAG="$release_id"
docker compose --project-name loop --env-file .env.production build --pull api
docker compose --project-name loop --env-file .env.production up -d --wait db redis
if [[ -n $previous_release ]]; then
  rollback_armed=true
  docker compose --project-name loop --env-file .env.production stop api worker
  if [[ -s $pending_env ]]; then
    env_backup="$loop_root/shared/.env.production.rollback-$release_id"
    install -m 600 "$shared_env" "$env_backup"
    install -m 600 "$pending_env" "$shared_env.new"
    mv -Tf "$shared_env.new" "$shared_env"
    rm -f "$pending_env"
    env_changed=true
  fi

  previous_duel_manifest="$previous_release/deployments/testnet/duel.json"
  target_duel_manifest="$release_dir/deployments/testnet/duel.json"
  test -s "$previous_duel_manifest"
  test -s "$target_duel_manifest"
  previous_duel_address=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["address"])' "$previous_duel_manifest")
  target_duel_address=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["address"])' "$target_duel_manifest")
  if [[ $previous_duel_address != "$target_duel_address" ]]; then
    docker compose --project-name loop --env-file .env.production run --rm --no-deps api \
      python -m app.duel_v11_preflight \
      --previous-contract "$previous_duel_address" \
      --target-contract "$target_duel_address"
  fi

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
curl --fail --silent --show-error https://app.tonsuite.org/ >/dev/null
curl --fail --silent --show-error https://app.tonsuite.org/ready >/dev/null
rollback_armed=false
trap - ERR
if [[ -n $env_backup ]]; then
  rm -f "$env_backup"
fi
