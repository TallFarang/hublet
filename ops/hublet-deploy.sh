#!/bin/sh
set -eu

set -a
. "${HUBLET_DEPLOY_ENV:?set HUBLET_DEPLOY_ENV to the external deploy.env file}"
. "${HUBLET_ROOT:?set HUBLET_ROOT in deploy.env}/secrets.env"
set +a

OPS_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_DIR=${HUBLET_REPOSITORY_DIR:-$(dirname "$OPS_DIR")}
VENV_PYTHON="$HUBLET_ROOT/venv/bin/python"
RELEASE_FILE="$HUBLET_ROOT/RELEASE"
PREVIOUS_RELEASE_FILE="$HUBLET_ROOT/PREVIOUS_RELEASE"

git -C "$APP_DIR" fetch --quiet origin main
wanted_release=$(git -C "$APP_DIR" rev-parse "origin/main^{commit}")
current_release=$(cat "$RELEASE_FILE" 2>/dev/null || true)
[ "$wanted_release" != "$current_release" ] || exit 0

fresh_backup=$(find "$HUBLET_BACKUP_DIR" -mindepth 2 -maxdepth 2 \
  -type f -name .hublet-snapshot -mmin -1560 -print -quit 2>/dev/null || true)
if [ -z "$fresh_backup" ]; then
  echo "refusing deploy: no Hublet snapshot from the last 26 hours" >&2
  exit 1
fi

if [ -n "$(git -C "$APP_DIR" status --porcelain)" ]; then
  echo "refusing deploy: checkout has local changes" >&2
  exit 1
fi

printf '%s\n' "$current_release" >"$PREVIOUS_RELEASE_FILE"
git -C "$APP_DIR" checkout --quiet --detach "$wanted_release"
"$VENV_PYTHON" -m pip install --quiet -r "$APP_DIR/requirements.lock"
"$VENV_PYTHON" -m pip install --quiet --no-deps -e "$APP_DIR"
launchctl kickstart -k "gui/$(id -u)/io.hublet.runtime"
curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 2 \
  http://127.0.0.1:8787/health >/dev/null
printf '%s\n' "$wanted_release" >"$RELEASE_FILE"
