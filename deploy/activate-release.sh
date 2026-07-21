#!/usr/bin/env bash
set -Eeuo pipefail

release_id=${1:?release id is required}
if [[ ! $release_id =~ ^[0-9a-f]{40}$ ]]; then
  echo "invalid release id" >&2
  exit 2
fi

loop_root=/opt/loop
release_dir="$loop_root/releases/$release_id"
shared_env="$loop_root/shared/.env.production"

test -d "$release_dir"
test -f "$shared_env"
ln -sfn "$shared_env" "$release_dir/.env.production"

cd "$release_dir"
export LOOP_IMAGE_TAG="$release_id"
docker compose --project-name loop --env-file .env.production build --pull api
docker compose --project-name loop --env-file .env.production up -d --wait db redis
docker compose --project-name loop --env-file .env.production run --rm migrate
docker compose --project-name loop --env-file .env.production up -d --wait --wait-timeout 120 api worker
curl --fail --silent --show-error http://127.0.0.1:8000/ready >/dev/null

ln -sfn "$release_dir" "$loop_root/current.next"
mv -Tf "$loop_root/current.next" "$loop_root/current"
sudo nginx -t
sudo systemctl reload nginx
curl --fail --silent --show-error https://144-31-30-62.sslip.io/ready >/dev/null
