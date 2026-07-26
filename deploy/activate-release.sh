#!/usr/bin/env bash
set -Eeuo pipefail

exec 9>/opt/loop/deploy.lock
if ! flock -n 9; then
  echo "another LOOP deployment is running" >&2
  exit 75
fi

release_id=${1:?release id is required}
release_kind=${2:-full}
if [[ ! $release_id =~ ^[0-9a-f]{40}$ ]]; then
  echo "invalid release id" >&2
  exit 2
fi
if [[ $release_kind != full && $release_kind != web ]]; then
  echo "invalid release kind" >&2
  exit 2
fi

loop_root=/opt/loop
release_dir="$loop_root/releases/$release_id"
web_current="$loop_root/web-current"
shared_env="$loop_root/shared/.env.production"
pending_env="$loop_root/shared/.env.production.next"
nginx_site=/etc/nginx/sites-available/loop.conf
previous_release=""
previous_web_release=""
backup_path=""
env_backup=""
nginx_backup=""
env_changed=false
nginx_changed=false
rollback_armed=false
database_changed=false

read_network_id() {
  local env_file=$1
  local value
  value=$(sed -n 's/^LOOP_TON_NETWORK_ID=//p' "$env_file" | tail -n 1)
  value=${value%\"}
  value=${value#\"}
  value=${value%\'}
  value=${value#\'}
  if [[ $value != -3 && $value != -239 ]]; then
    echo "unsupported LOOP_TON_NETWORK_ID in $env_file" >&2
    return 1
  fi
  printf '%s\n' "$value"
}

network_name() {
  case "$1" in
    -3) printf 'testnet\n' ;;
    -239) printf 'mainnet\n' ;;
    *) return 1 ;;
  esac
}

if [[ -L "$loop_root/current" ]]; then
  previous_release=$(readlink -f "$loop_root/current")
fi
if [[ -L $web_current ]]; then
  previous_web_release=$(readlink -f "$web_current")
elif [[ -n $previous_release ]]; then
  previous_web_release=$previous_release
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
  if [[ $nginx_changed == true && -n $nginx_backup && -s $nginx_backup ]]; then
    nginx_restore="$nginx_site.rollback"
    install -m 0644 "$nginx_backup" "$nginx_restore"
    mv -Tf "$nginx_restore" "$nginx_site"
  fi
  cd "$release_dir"
  export LOOP_IMAGE_TAG="$release_id"
  docker compose --project-name loop --env-file .env.production stop api worker notifier >/dev/null

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
    previous_services=(api worker)
    if docker compose --project-name loop --env-file .env.production config --services |
      grep -Fxq notifier; then
      previous_services+=(notifier)
    fi
    docker compose --project-name loop --env-file .env.production up -d "${previous_services[@]}"
    docker compose --project-name loop --env-file .env.production up -d --wait \
      --wait-timeout 120 "${previous_services[@]}"
    ln -sfn "$previous_release" "$loop_root/current.next"
    mv -Tf "$loop_root/current.next" "$loop_root/current"
    if [[ -n $previous_web_release && -d $previous_web_release ]]; then
      ln -sfn "$previous_web_release" "$loop_root/web-current.next"
      mv -Tf "$loop_root/web-current.next" "$web_current"
    fi
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
source_network_id=$(read_network_id "$shared_env")
target_network_id=$source_network_id
if [[ -s $pending_env ]]; then
  target_network_id=$(read_network_id "$pending_env")
fi
chmod 755 "$release_dir"
install -d -m 0750 "$release_dir/build"
acton_bin=/opt/loop/tools/acton
if [[ -x $acton_bin ]]; then
  (
    cd "$release_dir"
    "$acton_bin" init --stdlib-only >/dev/null
  )
fi
ln -sfn "$shared_env" "$release_dir/.env.production"

cd "$release_dir"
export LOOP_IMAGE_TAG="$release_id"

verify_web_asset() {
  local asset
  local asset_url
  local expected_asset
  local expected_asset_file
  local index_html
  local required_style
  local -a dependent_assets=()

  expected_asset=$(
    sed -n 's/.*src="\([^"]*\/assets\/[^"]*\.js\)".*/\1/p' \
      "$release_dir/apps/web/dist/index.html" |
      head -n 1
  )
  if [[ ! $expected_asset =~ ^/assets/[A-Za-z0-9._-]+\.js$ ]]; then
    echo "release index does not contain a valid JavaScript asset" >&2
    return 1
  fi
  expected_asset_file="$release_dir/apps/web/dist$expected_asset"
  test -s "$expected_asset_file"
  while IFS= read -r asset; do
    dependent_assets+=("$asset")
  done < <(
    grep -oE 'assets/[A-Za-z0-9._-]+\.(js|css)' "$expected_asset_file" |
      LC_ALL=C sort -u
  )
  if ((${#dependent_assets[@]} == 0)); then
    echo "release JavaScript entry does not reference any dependent assets" >&2
    return 1
  fi
  for required_style in control landing styles; do
    if ! printf '%s\n' "${dependent_assets[@]}" |
      grep -Eq "^assets/${required_style}-[A-Za-z0-9_-]+\.css$"; then
      echo "release JavaScript entry does not reference the $required_style stylesheet" >&2
      return 1
    fi
  done
  for asset in "${dependent_assets[@]}"; do
    if [[ ! $asset =~ ^assets/[A-Za-z0-9._-]+\.(js|css)$ ]]; then
      echo "release JavaScript entry contains an invalid asset path: $asset" >&2
      return 1
    fi
    test -s "$release_dir/apps/web/dist/$asset"
  done

  index_html=$(
    curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
      --header 'Host: app.tonsuite.org' \
      http://127.0.0.1:18791/
  )
  grep -Fq "$expected_asset" <<<"$index_html"
  curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
    --header 'Host: app.tonsuite.org' \
    "http://127.0.0.1:18791$expected_asset" >/dev/null
  for asset in "${dependent_assets[@]}"; do
    asset_url="/$asset"
    curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
      --header 'Host: app.tonsuite.org' \
      "http://127.0.0.1:18791$asset_url" >/dev/null
  done
}

if [[ $release_kind == web ]]; then
  if [[ -z $previous_release || ! -d $previous_release ]]; then
    echo "web-only activation requires an active runtime release" >&2
    exit 3
  fi
  if [[ -s $pending_env ]]; then
    echo "pending production environment requires a full release" >&2
    exit 3
  fi
  if ! sudo nginx -T 2>/dev/null |
    grep -F 'root /opt/loop/web-current/apps/web/dist;' >/dev/null; then
    echo "nginx is not configured for independent web releases; run one full release first" >&2
    exit 3
  fi
  if ! cmp -s "$nginx_site" "$release_dir/deploy/nginx/loop.conf"; then
    echo "web-only release changes the active nginx site; use a full release" >&2
    exit 3
  fi

  runtime_paths=(
    apps/api/app
    apps/api/migrations
    apps/api/alembic.ini
    apps/api/pyproject.toml
    compose.yaml
    contracts
    deploy/Dockerfile.api
    deploy/nginx/loop-proxy.conf
    deploy/nginx/loop-security-headers.conf
    deployments
  )
  for runtime_path in "${runtime_paths[@]}"; do
    if ! diff -qr "$previous_release/$runtime_path" "$release_dir/$runtime_path" >/dev/null; then
      echo "web-only release changes runtime path: $runtime_path" >&2
      exit 3
    fi
  done

  rollback_web_release() {
    local exit_code=$?
    trap - ERR
    set +e
    if [[ -n $previous_web_release && -d $previous_web_release ]]; then
      ln -sfn "$previous_web_release" "$loop_root/web-current.next"
      mv -Tf "$loop_root/web-current.next" "$web_current"
      if sudo nginx -t; then
        sudo systemctl reload nginx
      fi
    fi
    exit "$exit_code"
  }
  trap rollback_web_release ERR

  ln -sfn "$release_dir" "$loop_root/web-current.next"
  mv -Tf "$loop_root/web-current.next" "$web_current"
  sudo nginx -t
  sudo systemctl reload nginx
  verify_web_asset
  curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
    https://app.tonsuite.org/ >/dev/null
  curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
    https://app.tonsuite.org/ready >/dev/null
  trap - ERR
  exit 0
fi

docker compose --project-name loop --env-file .env.production build --pull api
docker compose --project-name loop --env-file .env.production up -d --wait db redis
if [[ -n $previous_release ]]; then
  rollback_armed=true
  docker compose --project-name loop --env-file .env.production stop api worker notifier
  if [[ $source_network_id != "$target_network_id" ]]; then
    docker compose --project-name loop --env-file .env.production run --rm --no-deps api \
      python -m app.network_switch_preflight --target-network "$target_network_id"
  fi
  if [[ -s $pending_env ]]; then
    env_backup="$loop_root/shared/.env.production.rollback-$release_id"
    install -m 600 "$shared_env" "$env_backup"
    install -m 600 "$pending_env" "$shared_env.new"
    mv -Tf "$shared_env.new" "$shared_env"
    rm -f "$pending_env"
    env_changed=true
  fi

  target_network_name=$(network_name "$target_network_id")
  previous_duel_manifest="$previous_release/deployments/$target_network_name/duel.json"
  target_duel_manifest="$release_dir/deployments/$target_network_name/duel.json"
  test -s "$target_duel_manifest"
  target_duel_address=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["address"])' "$target_duel_manifest")
  if [[ $source_network_id == "$target_network_id" ]]; then
    test -s "$previous_duel_manifest"
    previous_duel_address=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["address"])' "$previous_duel_manifest")
    if [[ $previous_duel_address != "$target_duel_address" ]]; then
      docker compose --project-name loop --env-file .env.production run --rm --no-deps api \
        python -m app.duel_v11_preflight \
        --previous-contract "$previous_duel_address" \
        --target-contract "$target_duel_address"
    fi
  fi

  backup_path=$("$release_dir/deploy/backup-postgres.sh")
  if [[ $backup_path != "$loop_root/backups/"*.dump || ! -s $backup_path ]]; then
    echo "database backup was not created at the expected path" >&2
    false
  fi
fi
if [[ $target_network_id == -239 ]]; then
  docker compose --project-name loop --env-file .env.production run --rm --no-deps \
    -e "LOOP_RELEASE_COMMIT=$release_id" api \
    python scripts/check-mainnet-readiness.py --phase post-deploy
fi
database_changed=true
docker compose --project-name loop --env-file .env.production run --rm migrate
docker compose --project-name loop --env-file .env.production up -d api worker notifier
docker compose --project-name loop --env-file .env.production up -d --wait --wait-timeout 120 api worker notifier
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  http://127.0.0.1:8000/ready >/dev/null

nginx_backup="$loop_root/shared/nginx-loop.conf.rollback-$release_id"
install -m 0644 "$nginx_site" "$nginx_backup"
nginx_next="$nginx_site.$release_id.next"
install -m 0644 "$release_dir/deploy/nginx/loop.conf" "$nginx_next"
ln -sfn "$release_dir" "$loop_root/web-current.next"
mv -Tf "$loop_root/web-current.next" "$web_current"
ln -sfn "$release_dir" "$loop_root/current.next"
mv -Tf "$loop_root/current.next" "$loop_root/current"
mv -Tf "$nginx_next" "$nginx_site"
nginx_changed=true
sudo nginx -t
sudo systemctl reload nginx
verify_web_asset
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  https://app.tonsuite.org/ >/dev/null
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  https://app.tonsuite.org/ready >/dev/null
rollback_armed=false
trap - ERR
if [[ -n $env_backup ]]; then
  rm -f "$env_backup"
fi
if [[ -n $nginx_backup ]]; then
  rm -f "$nginx_backup"
fi
