#!/usr/bin/env bash
set -Eeuo pipefail

IFS=$'\n\t'

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/.." && pwd)
deploy_host=${LOOP_DEPLOY_HOST:-ton4-prod}
public_origin=https://app.tonsuite.org
expected_branch=${LOOP_DEPLOY_BRANCH:-main}
command=deploy
check_mode=standard
release_kind=full
dry_run=false
allow_unpushed=false

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy-vps.sh deploy [--fast|--full-checks] [--web-only] [--dry-run] [--allow-unpushed] [--host HOST]
  scripts/deploy-vps.sh status [--host HOST]
  scripts/deploy-vps.sh restart [--host HOST]

Commands:
  deploy    Build, package, upload, activate and verify an immutable release.
  status    Verify the active release, containers, public health and Telegram bot.
  restart   Restart API/bot and worker, reload nginx, then run status.

Options:
  --fast             Build the web client but skip local tests.
  --full-checks      Include browser, security and contract verification.
  --web-only         Activate static web files without restarting API/worker or touching the database.
  --dry-run          Run local checks and package the release without uploading it.
  --allow-unpushed   Permit a committed HEAD that is not present on its upstream branch.
  --host HOST        SSH host or alias. Default: LOOP_DEPLOY_HOST or ton4-prod.
  -h, --help         Show this help.
EOF
}

log() {
  printf '[loop-deploy] %s\n' "$*"
}

die() {
  printf '[loop-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ $# -gt 0 && $1 != -* ]]; then
  command=$1
  shift
fi

case "$command" in
  deploy | status | restart) ;;
  help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    die "unknown command: $command"
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fast)
      [[ $command == deploy ]] || die "--fast is only valid with deploy"
      [[ $check_mode != full ]] || die "--fast and --full-checks are mutually exclusive"
      check_mode=fast
      ;;
    --full-checks)
      [[ $command == deploy ]] || die "--full-checks is only valid with deploy"
      [[ $check_mode != fast ]] || die "--fast and --full-checks are mutually exclusive"
      check_mode=full
      ;;
    --web-only)
      [[ $command == deploy ]] || die "--web-only is only valid with deploy"
      release_kind=web
      ;;
    --dry-run)
      [[ $command == deploy ]] || die "--dry-run is only valid with deploy"
      dry_run=true
      ;;
    --allow-unpushed)
      [[ $command == deploy ]] || die "--allow-unpushed is only valid with deploy"
      allow_unpushed=true
      ;;
    --host)
      shift
      [[ $# -gt 0 ]] || die "--host requires a value"
      deploy_host=$1
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "unknown option: $1"
      ;;
  esac
  shift
done

for dependency in bash curl ssh; do
  command -v "$dependency" >/dev/null 2>&1 || die "missing required command: $dependency"
done

tmp_base=/tmp
tmp_dir=$(mktemp -d "$tmp_base/loop-deploy.XXXXXX")
if [[ $tmp_dir != "$tmp_base"/loop-deploy.* ]]; then
  die "unexpected temporary directory: $tmp_dir"
fi

cleanup() {
  local exit_code=$?
  trap - EXIT
  if [[ -n ${deploy_unit:-} ]]; then
    cleanup_remote_unit_if_finished || true
  fi
  if [[ -n ${tmp_dir:-} && -d $tmp_dir && $tmp_dir == "$tmp_base"/loop-deploy.* ]]; then
    rm -rf -- "$tmp_dir"
  fi
  exit "$exit_code"
}
trap cleanup EXIT

ssh_options=(
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
  -o ControlMaster=auto
  -o ControlPersist=30
  -o "ControlPath=$tmp_dir/ssh-%C"
)

ssh_run() {
  ssh "${ssh_options[@]}" "$deploy_host" "$@"
}

remote_current_release() {
  ssh_run bash -s -- "$release_kind" <<'REMOTE'
set -Eeuo pipefail

release_kind=$1
link=/opt/loop/current
if [[ $release_kind == web ]]; then
  link=/opt/loop/web-current
fi
current=$(readlink -f "$link" 2>/dev/null || true)
if [[ -n $current ]]; then
  basename "$current"
fi
REMOTE
}

status_remote() {
  log "Checking $deploy_host"
  ssh_run bash -s <<'REMOTE'
set -Eeuo pipefail

loop_root=/opt/loop
release_dir=$(readlink -f "$loop_root/current")
release_id=$(basename "$release_dir")
web_release_dir=$(readlink -f "$loop_root/web-current" 2>/dev/null || printf '%s' "$release_dir")
web_release_id=$(basename "$web_release_dir")
test -d "$release_dir"
test -d "$web_release_dir"
test -f "$release_dir/.env.production"

cd "$release_dir"
export LOOP_IMAGE_TAG="$release_id"

printf 'release: %s\n' "$release_id"
printf 'web release: %s\n' "$web_release_id"
docker compose --project-name loop --env-file .env.production ps \
  --format 'table {{.Service}}\t{{.Status}}' db redis api worker

service_state=$(
  docker compose --project-name loop --env-file .env.production ps \
    --format '{{.Service}} {{.State}} {{.Health}}' db redis api worker
)
printf '%s\n' "$service_state" |
  awk '
    {
      seen[$1] = 1
      if (NF != 3 || $2 != "running" || $3 != "healthy") {
        bad = 1
      }
    }
    END {
      if (bad || !seen["api"] || !seen["db"] || !seen["redis"] || !seen["worker"]) {
        exit 1
      }
    }
  '

curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  http://127.0.0.1:8000/live >/dev/null
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  http://127.0.0.1:8000/ready >/dev/null
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  https://app.tonsuite.org/live >/dev/null
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  https://app.tonsuite.org/ready >/dev/null

docker compose --project-name loop --env-file .env.production exec -T api python - <<'PY'
import json
import os
import urllib.request

token = os.environ.get("LOOP_BOT_TOKEN", "")


def telegram(method: str) -> dict:
    if not token:
        return {}
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/{method}",
            timeout=10,
        ) as response:
            return json.load(response)
    except Exception:
        return {}


me = telegram("getMe")
webhook = telegram("getWebhookInfo")
me_result = me.get("result") or {}
webhook_result = webhook.get("result") or {}
bot_ok = bool(me.get("ok") and webhook.get("ok") and webhook_result.get("url"))
print(
    json.dumps(
        {
            "bot_ok": bot_ok,
            "username": me_result.get("username"),
            "inline": bool(me_result.get("supports_inline_queries")),
            "webhook_configured": bool(webhook_result.get("url")),
            "pending_updates": webhook_result.get("pending_update_count"),
            "last_error": bool(webhook_result.get("last_error_date")),
        },
        ensure_ascii=False,
    )
)
raise SystemExit(0 if bot_ok else 1)
PY

printf 'health: live, ready, bot OK\n'
REMOTE
}

restart_remote() {
  log "Restarting the active release on $deploy_host"
  ssh_run bash -s <<'REMOTE'
set -Eeuo pipefail

exec 8>/opt/loop/deploy.lock
if ! flock -n 8; then
  echo "another LOOP deployment or restart is running" >&2
  exit 75
fi

release_dir=$(readlink -f /opt/loop/current)
release_id=$(basename "$release_dir")
test -d "$release_dir"

cd "$release_dir"
export LOOP_IMAGE_TAG="$release_id"
docker compose --project-name loop --env-file .env.production restart api worker
docker compose --project-name loop --env-file .env.production up \
  -d --wait --wait-timeout 120 api worker
nginx -t
systemctl reload nginx
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  http://127.0.0.1:8000/ready >/dev/null
REMOTE
  status_remote
}

sha256_file() {
  local file=$1
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  else
    shasum -a 256 "$file" | awk '{print $1}'
  fi
}

sha256_stream() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  else
    shasum -a 256 | awk '{print $1}'
  fi
}

assert_no_tracked_secrets() {
  local path
  local basename
  while IFS= read -r path; do
    basename=${path##*/}
    case "$basename" in
      .env.example) ;;
      .env | .env.* | wallets.toml | libraries.toml)
        die "refusing to package tracked sensitive file: $path"
        ;;
    esac
  done < <(git -C "$repo_root" ls-files)
}

git_preflight() {
  local branch
  local dirty
  local upstream
  local remote_name
  local remote_branch
  local remote_head

  branch=$(git -C "$repo_root" branch --show-current)
  [[ -n $branch ]] || die "detached HEAD cannot be deployed"
  [[ $branch == "$expected_branch" ]] ||
    die "expected branch $expected_branch, found $branch"

  dirty=$(git -C "$repo_root" status --porcelain --untracked-files=normal)
  [[ -z $dirty ]] || die "working tree is not clean; commit or stash local changes"

  release_id=$(git -C "$repo_root" rev-parse HEAD)
  [[ $release_id =~ ^[0-9a-f]{40}$ ]] || die "HEAD is not a full Git commit"

  assert_no_tracked_secrets

  if [[ $allow_unpushed == false ]]; then
    upstream=$(git -C "$repo_root" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}')
    remote_name=${upstream%%/*}
    remote_branch=${upstream#*/}
    remote_head=$(
      git -C "$repo_root" ls-remote --exit-code "$remote_name" "refs/heads/$remote_branch" |
        awk 'NR == 1 { print $1 }'
    )
    [[ $remote_head == "$release_id" ]] ||
      die "HEAD $release_id is not the current $upstream; push it first or use --allow-unpushed"
  fi
}

run_local_checks() {
  log "Running $check_mode local release checks"
  case "$check_mode" in
    fast)
      env \
        -u VITE_API_BASE_URL \
        -u VITE_MOCK_TELEGRAM \
        -u VITE_TONCONNECT_MANIFEST_URL \
        npm --prefix "$repo_root" run build:web
      ;;
    standard)
      env \
        -u VITE_API_BASE_URL \
        -u VITE_MOCK_TELEGRAM \
        -u VITE_TONCONNECT_MANIFEST_URL \
        make -C "$repo_root" lint typecheck test-unit test-integration
      ;;
    full)
      env \
        -u VITE_API_BASE_URL \
        -u VITE_MOCK_TELEGRAM \
        -u VITE_TONCONNECT_MANIFEST_URL \
        make -C "$repo_root" lint typecheck test test-e2e test-security contracts-verify
      ;;
  esac
}

package_release() {
  local source_tar="$tmp_dir/source.tar"
  local staging_dir="$tmp_dir/release"
  local dist_file
  local digest
  local link
  local target
  local -a metadata_flags=()

  for dependency in git npm tar; do
    command -v "$dependency" >/dev/null 2>&1 || die "missing required command: $dependency"
  done

  git -C "$repo_root" archive --format=tar --output="$source_tar" "$release_id"
  mkdir -p "$staging_dir"
  tar -xf "$source_tar" -C "$staging_dir"
  mkdir -p "$staging_dir/apps/web"
  COPYFILE_DISABLE=1 cp -R "$repo_root/apps/web/dist" "$staging_dir/apps/web/dist"
  test -s "$staging_dir/apps/web/dist/index.html" ||
    die "web build did not produce apps/web/dist/index.html"

  content_hash=$(
    {
      printf 'release %s\n' "$release_id"
      while IFS= read -r dist_file; do
        digest=$(sha256_file "$dist_file")
        printf 'file %s %s\n' "${dist_file#"$staging_dir/apps/web/dist/"}" "$digest"
      done < <(find "$staging_dir/apps/web/dist" -type f -print | LC_ALL=C sort)
      while IFS= read -r link; do
        target=$(readlink "$link")
        printf 'link %s %s\n' "${link#"$staging_dir/apps/web/dist/"}" "$target"
      done < <(find "$staging_dir/apps/web/dist" -type l -print | LC_ALL=C sort)
    } | sha256_stream
  )

  if [[ $(uname -s) == Darwin ]]; then
    metadata_flags=(--no-xattrs --no-mac-metadata)
  fi

  archive_path="$tmp_dir/loop-$release_id.tgz"
  COPYFILE_DISABLE=1 tar "${metadata_flags[@]}" -czf "$archive_path" -C "$staging_dir" .
  archive_checksum=$(sha256_file "$archive_path")
  archive_size=$(wc -c <"$archive_path" | tr -d '[:space:]')
  index_asset=$(
    sed -n 's/.*src="\([^"]*\/assets\/[^"]*\.js\)".*/\1/p' \
      "$staging_dir/apps/web/dist/index.html" |
      head -n 1
  )
  [[ $archive_size =~ ^[0-9]+$ ]] || die "could not determine archive size"
  [[ -n $index_asset ]] || die "could not find the built JavaScript asset"

  log "Packaged ${archive_size} bytes; SHA-256 ${archive_checksum:0:16}…"
}

remote_preflight() {
  log "Checking remote dependencies and disk space"
  ssh_run bash -s -- "$archive_size" "$release_kind" <<'REMOTE'
set -Eeuo pipefail

archive_size=$1
release_kind=$2
[[ $archive_size =~ ^[0-9]+$ ]]
[[ $release_kind == full || $release_kind == web ]]
[[ $EUID -eq 0 ]]

for dependency in cmp diff docker flock nginx sha256sum systemctl systemd-run tar; do
  command -v "$dependency" >/dev/null 2>&1 || {
    echo "missing remote dependency: $dependency" >&2
    exit 2
  }
done

test -s /opt/loop/shared/.env.production
install -d -m 0750 /opt/loop/incoming
install -d -m 0755 /opt/loop/releases

available=$(df -PB1 /opt/loop | awk 'NR == 2 { print $4 }')
if [[ $release_kind == web ]]; then
  required=$((archive_size * 3 + 1073741824))
else
  release_dir=$(readlink -f /opt/loop/current)
  release_id=$(basename "$release_dir")
  cd "$release_dir"
  export LOOP_IMAGE_TAG="$release_id"
  database_size=$(
    docker compose --project-name loop --env-file .env.production exec -T db sh -c \
      'psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --command="SELECT pg_database_size(current_database())"'
  )
  database_size=$(printf '%s' "$database_size" | tr -d '[:space:]')
  [[ $database_size =~ ^[0-9]+$ ]] || {
    echo "could not determine production database size" >&2
    exit 3
  }
  required=$((archive_size * 3 + database_size * 2 + 4294967296))
fi
if ((available < required)); then
  echo "not enough free space: need $required bytes, have $available" >&2
  exit 3
fi
printf 'remote free space: %s bytes; required headroom: %s bytes\n' "$available" "$required"
REMOTE
}

upload_and_start_activation() {
  local nonce
  local remote_part
  local scp_options=("${ssh_options[@]}")

  nonce="$(date +%s)-$$"
  remote_part="/opt/loop/incoming/$release_id.${archive_checksum:0:16}.$nonce.part"
  deploy_unit="loop-deploy-${release_id:0:12}-$nonce"

  log "Uploading release to $deploy_host"
  scp "${scp_options[@]}" -q "$archive_path" "$deploy_host:$remote_part"

  log "Verifying and staging the release"
  ssh_run bash -s -- \
    "$release_id" \
    "$archive_checksum" \
    "$content_hash" \
    "$remote_part" \
    "$deploy_unit" \
    "$release_kind" <<'REMOTE'
set -Eeuo pipefail

release_id=$1
expected_archive_checksum=$2
content_hash=$3
remote_part=$4
deploy_unit=$5
release_kind=$6

[[ $release_id =~ ^[0-9a-f]{40}$ ]]
[[ $expected_archive_checksum =~ ^[0-9a-f]{64}$ ]]
[[ $content_hash =~ ^[0-9a-f]{64}$ ]]
[[ $remote_part == /opt/loop/incoming/"$release_id".*.part ]]
[[ $deploy_unit =~ ^loop-deploy-[0-9a-f]{12}-[0-9]+-[0-9]+$ ]]
[[ $release_kind == full || $release_kind == web ]]

exec 8>/opt/loop/stage.lock
if ! flock -w 30 8; then
  echo "another LOOP release is being staged" >&2
  exit 75
fi

actual_archive_checksum=$(sha256sum "$remote_part" | awk '{ print $1 }')
if [[ $actual_archive_checksum != "$expected_archive_checksum" ]]; then
  echo "uploaded archive checksum mismatch" >&2
  exit 4
fi

if ! tar -tzf "$remote_part" |
  awk '
    /^\// { bad = 1 }
    /(^|\/)\.\.(\/|$)/ { bad = 1 }
    END { exit bad ? 1 : 0 }
  '; then
  echo "archive contains an unsafe path" >&2
  exit 4
fi

release_dir="/opt/loop/releases/$release_id"
staging_dir=$(mktemp -d "/opt/loop/releases/.staging-${release_id:0:12}.XXXXXX")

cleanup_stage() {
  local exit_code=$?
  trap - EXIT
  if [[ -n ${staging_dir:-} && -d $staging_dir &&
    $staging_dir == /opt/loop/releases/.staging-"${release_id:0:12}".* ]]; then
    rm -rf -- "$staging_dir"
  fi
  if [[ -n ${remote_part:-} && -f $remote_part &&
    $remote_part == /opt/loop/incoming/"$release_id".*.part ]]; then
    rm -f -- "$remote_part"
  fi
  exit "$exit_code"
}
trap cleanup_stage EXIT

tar --no-same-owner --no-same-permissions -xzf "$remote_part" -C "$staging_dir"
test -s "$staging_dir/apps/web/dist/index.html"
test -x "$staging_dir/deploy/activate-release.sh"
test -s "$staging_dir/compose.yaml"

printf '%s\n%s\n%s\n' \
  "$release_id" "$content_hash" "$expected_archive_checksum" \
  >"$staging_dir/.loop-release"
chmod 0444 "$staging_dir/.loop-release"
chmod 0755 "$staging_dir"

if [[ -e $release_dir ]]; then
  marker="$release_dir/.loop-release"
  marker_release=$(sed -n '1p' "$marker" 2>/dev/null || true)
  marker_content=$(sed -n '2p' "$marker" 2>/dev/null || true)
  if [[ $marker_release != "$release_id" || $marker_content != "$content_hash" ]]; then
    echo "release directory exists with a different or missing marker: $release_dir" >&2
    exit 5
  fi
  printf 'reusing verified release directory: %s\n' "$release_dir"
else
  mv "$staging_dir" "$release_dir"
  staging_dir=""
  printf 'installed release directory: %s\n' "$release_dir"
fi

rm -f -- "$remote_part"
remote_part=""

systemd-run \
  --quiet \
  --no-block \
  --unit="$deploy_unit" \
  --description="LOOP release $release_id" \
  --property=Type=oneshot \
  --property=RemainAfterExit=yes \
  -- \
  /bin/bash "$release_dir/deploy/activate-release.sh" "$release_id" "$release_kind"

printf 'activation unit: %s.service\n' "$deploy_unit"
REMOTE
}

wait_for_activation() {
  local attempt=1
  local exit_code

  log "Waiting for $deploy_unit.service"
  while ((attempt <= 4)); do
    set +e
    ssh_run bash -s -- "$deploy_unit.service" 1200 <<'REMOTE'
set -Eeuo pipefail

service=$1
timeout_seconds=$2
deadline=$((SECONDS + timeout_seconds))
previous_state=""

while ((SECONDS < deadline)); do
  properties=$(systemctl show "$service" \
    --property=LoadState \
    --property=ActiveState \
    --property=SubState \
    --property=Result \
    --property=ExecMainStatus 2>/dev/null || true)
  load_state=$(printf '%s\n' "$properties" | sed -n 's/^LoadState=//p')
  active_state=$(printf '%s\n' "$properties" | sed -n 's/^ActiveState=//p')
  sub_state=$(printf '%s\n' "$properties" | sed -n 's/^SubState=//p')
  result=$(printf '%s\n' "$properties" | sed -n 's/^Result=//p')
  main_status=$(printf '%s\n' "$properties" | sed -n 's/^ExecMainStatus=//p')
  state="$load_state/$active_state/$sub_state/$result/$main_status"

  if [[ $state != "$previous_state" ]]; then
    printf 'activation: %s\n' "$state"
    previous_state=$state
  fi

  if [[ $active_state == failed ||
    $result != success && $result != "" && $active_state == inactive ]]; then
    journalctl --no-pager --unit "$service" --lines 120
    exit 20
  fi
  if [[ $result == success &&
    ($active_state == active && $sub_state == exited || $active_state == inactive) ]]; then
    exit 0
  fi
  if [[ $load_state == not-found ]]; then
    echo "activation unit was not found: $service" >&2
    exit 21
  fi
  sleep 3
done

echo "activation timed out after $timeout_seconds seconds" >&2
exit 124
REMOTE
    exit_code=$?
    set -e

    case "$exit_code" in
      0)
        return 0
        ;;
      255)
        log "SSH was interrupted; activation is still server-side. Reconnecting ($attempt/4)"
        attempt=$((attempt + 1))
        sleep 2
        ;;
      *)
        die "activation failed while waiting (exit $exit_code)"
        ;;
    esac
  done

  die "could not reconnect to observe activation"
}

verify_public_asset() {
  local asset
  local attempt
  local entry_file="$repo_root/apps/web/dist$index_asset"
  local index_html="$tmp_dir/public-index.html"
  local -a dependent_assets=()

  test -s "$entry_file" || die "local built entry is missing: $entry_file"
  while IFS= read -r asset; do
    dependent_assets+=("$asset")
  done < <(
    grep -oE 'assets/[A-Za-z0-9._-]+\.(js|css)' "$entry_file" |
      LC_ALL=C sort -u
  )
  ((${#dependent_assets[@]} > 0)) ||
    die "local built entry does not reference any dependent assets"

  log "Verifying public health and ${#dependent_assets[@]} built dependencies"
  for attempt in 1 2 3 4 5 6; do
    if curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
      "$public_origin/" >"$index_html" &&
      grep -Fq "$index_asset" "$index_html" &&
      curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
        "$public_origin$index_asset" >/dev/null &&
      (
        for asset in "${dependent_assets[@]}"; do
          curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
            "$public_origin/$asset" >/dev/null || exit 1
        done
      ) &&
      curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
        "$public_origin/live" >/dev/null &&
      curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
        "$public_origin/ready" >/dev/null; then
      return 0
    fi
    sleep 2
  done

  die "public release did not serve the expected built asset"
}

cleanup_remote_unit() {
  if [[ -n ${deploy_unit:-} ]]; then
    ssh_run "systemctl stop '$deploy_unit.service' >/dev/null 2>&1 || true; systemctl reset-failed '$deploy_unit.service' >/dev/null 2>&1 || true" ||
      true
  fi
}

cleanup_remote_unit_if_finished() {
  local remote_command
  remote_command=$(
    cat <<EOF
sub_state=\$(systemctl show '$deploy_unit.service' --property=SubState --value 2>/dev/null || true)
active_state=\$(systemctl show '$deploy_unit.service' --property=ActiveState --value 2>/dev/null || true)
if [[ \$sub_state == exited || \$active_state == failed || \$active_state == inactive ]]; then
  systemctl stop '$deploy_unit.service' >/dev/null 2>&1 || true
  systemctl reset-failed '$deploy_unit.service' >/dev/null 2>&1 || true
fi
EOF
  )
  ssh_run "$remote_command"
}

case "$command" in
  status)
    status_remote
    ;;
  restart)
    restart_remote
    ;;
  deploy)
    for dependency in git make npm scp tar; do
      command -v "$dependency" >/dev/null 2>&1 || die "missing required command: $dependency"
    done

    git_preflight
    if [[ $dry_run == false ]]; then
      active_release=$(remote_current_release)
      if [[ $active_release == "$release_id" ]]; then
        log "Release $release_id is already active; nothing to upload"
        status_remote
        exit 0
      fi
    fi

    run_local_checks
    package_release

    if [[ $dry_run == true ]]; then
      log "Dry run complete for $release_id; no server state changed"
      exit 0
    fi

    remote_preflight
    upload_and_start_activation
    wait_for_activation

    active_release=$(remote_current_release)
    [[ $active_release == "$release_id" ]] ||
      die "server activated $active_release instead of $release_id"
    status_remote
    verify_public_asset
    cleanup_remote_unit
    deploy_unit=""
    log "Release $release_id is active and verified"
    ;;
esac
