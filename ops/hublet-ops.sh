#!/bin/sh
set -eu

set -a
. "${HUBLET_DEPLOY_ENV:?set HUBLET_DEPLOY_ENV to the external deploy.env file}"
set +a

OPS_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$OPS_DIR/.."

case "${1:-}" in
  deploy)
    container_id=$(docker compose ps -q runtime)
    running_image=""
    if [ -n "$container_id" ]; then
      running_image=$(docker inspect --format '{{.Image}}' "$container_id")
    fi

    docker compose pull --quiet runtime
    image_name=$(docker compose config --images)
    wanted_image=$(docker image inspect --format '{{.Id}}' "$image_name")
    if [ "$running_image" = "$wanted_image" ]; then
      exit 0
    fi

    docker compose up -d --remove-orphans
    curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 2 \
      http://127.0.0.1:8787/health >/dev/null
    ;;
  backup)
    docker compose exec -T runtime hublet-backup
    ;;
  *)
    echo "usage: $0 deploy|backup" >&2
    exit 2
    ;;
esac
