# Hublet

Hublet is a brutally lightweight personal structured-memory daemon for OpenClaw. It will
provide Coffee, Goals, and Recipes through one MCP endpoint and a small server-rendered
dashboard.

The v1 runtime is intentionally narrow: Python 3.13, FastAPI, the official MCP SDK,
`sqlite3`, Jinja2, and a local vendored copy of Pico CSS. The dashboard uses ordinary HTML
forms; there is no REST API, frontend framework, JavaScript dependency, or external CSS CDN.

## Development status

This repository currently contains the public-safe project scaffold and implementation
contract. Runtime features will be added in small test-first vertical slices.

## Local configuration

Copy `.env.example` to an ignored environment file and replace every placeholder. Keep all
credentials and live databases outside the repository. `HUBLET_PUBLIC_ORIGIN` is the exact
deployment origin used to validate state-changing dashboard requests; examples in this
repository use only reserved or loopback names.

The complete configuration contract is:

- `HUBLET_DATA_DIR` selects the live SQLite data directory.
- `HUBLET_BACKUP_DIR` selects the independent snapshot directory.
- `HUBLET_PUBLIC_ORIGIN` is the dashboard origin used for Origin/Referer validation.
- `HUBLET_DASHBOARD_TOKEN` authenticates the dashboard login form.
- `HUBLET_SESSION_SECRET` signs the dashboard session cookie.
- `HUBLET_MCP_TOKEN` authenticates the MCP endpoint as a bearer token.
- `HUBLET_MCP_ALLOWED_HOSTS` is the comma-separated MCP Host-header allowlist. Public
  examples use the SDK wildcard-port syntax
  `hublet.example.test:*,localhost:*,127.0.0.1:*`.

Dashboard sessions and MCP bearer access are independent credentials.

## Development install

Install the resolved development dependency closure first, then install Hublet itself
without asking pip to resolve dependencies again:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
```

`requirements.lock` contains only the resolved runtime closure. `requirements-dev.lock`
contains that runtime closure plus the three approved development dependencies and their
transitive requirements.

## Backups

Run `hublet-backup` from the installed environment. It uses SQLite's online backup API to
write all three databases to `HUBLET_BACKUP_DIR/YYYY-MM-DD`, prints that path, and keeps the
newest 30 daily snapshots. Missing live databases or an incomplete copy fail without
publishing a final-dated snapshot. A successful snapshot is never overwritten on the same
date.

To restore, stop Hublet, replace the affected live `.db` file with the chosen snapshot,
start Hublet again, and verify `/health`.

## CI and container images

Pull requests and pushes run Ruff and pytest on GitHub-hosted runners. A green push to
`main` also publishes `ghcr.io/tallfarang/hublet` for both amd64 and arm64, tagged as
`latest` and with the immutable commit SHA.

After the first publish, change the package visibility to **Public** once in its GitHub
Package settings; [GHCR packages start private by default](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Mac deployment

Keep the checkout, live data, backups, logs, and environment files in owner-chosen local
paths. Nothing in the repository fixes a Mac username, LAN address, or private directory.
The Compose service publishes port 8787 on the host; set `HUBLET_PUBLIC_ORIGIN` in the
external secrets file to the real hostname or LAN address trusted devices use.

Create the local directories, copy `.env.example` to an external `secrets.env`, replace its
placeholders with three independently generated random values, and keep it mode 600. Create
an external `deploy.env` containing the host-side paths:

```sh
HUBLET_HOST_DATA_DIR=$HOME/.hublet/data
HUBLET_HOST_BACKUP_DIR=$HOME/.hublet/backups
HUBLET_ENV_FILE=$HOME/.hublet/secrets.env
```

To pin or roll back the image, add `HUBLET_IMAGE=ghcr.io/tallfarang/hublet:<commit-sha>` to
that file. Run either operation manually with:

```sh
HUBLET_DEPLOY_ENV=$HOME/.hublet/deploy.env sh ops/hublet-ops.sh deploy
HUBLET_DEPLOY_ENV=$HOME/.hublet/deploy.env sh ops/hublet-ops.sh backup
```

For automatic operation, copy the two templates in `ops/` to `~/Library/LaunchAgents/`,
replace their three `__HUBLET_*__` placeholders with absolute local paths, and validate them
with `plutil -lint`. Bootstrap them with `launchctl bootstrap gui/$(id -u) <plist>`. The
deploy job checks every five minutes but restarts the service only when the pulled image
changes; the backup job runs daily at 03:15. Their local log paths are set in the templates.

Never expose Hublet through router port forwarding. It is designed for one trusted user on
a home LAN.
