#!/bin/sh
set -eu

set -a
. "${HUBLET_DEPLOY_ENV:?set HUBLET_DEPLOY_ENV to the external deploy.env file}"
. "${HUBLET_ROOT:?set HUBLET_ROOT in deploy.env}/secrets.env"
set +a

OPS_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$(dirname "$OPS_DIR")"
exec "$HUBLET_ROOT/venv/bin/python" -m uvicorn app.main:app --factory \
  --host 0.0.0.0 --port 8787 --workers 1
