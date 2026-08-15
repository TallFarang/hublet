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

Never expose Hublet through router port forwarding. It is designed for one trusted user on
a home LAN.
