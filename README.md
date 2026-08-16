# Hublet

Hublet is a brutally lightweight personal structured-memory daemon for OpenClaw. It will
provide Coffee, Goals, Recipes, Food, and Health through one MCP endpoint and a small server-rendered
dashboard.

The v1 runtime is intentionally narrow: Python 3.13, FastAPI, the official MCP SDK,
`sqlite3`, Jinja2, and a local vendored copy of Pico CSS. The dashboard uses ordinary HTML
forms and dependency-free inline charts; there is no REST API, frontend framework, JavaScript,
charting dependency, downloaded font, or external CSS CDN.

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
- `HUBLET_AGENTBRIDGE_DIR` selects the only directory the Health importer may read.
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
write all five databases to `HUBLET_BACKUP_DIR/YYYY-MM-DD`, prints that path, and keeps the
newest 30 daily snapshots. Missing live databases or an incomplete copy fail without
publishing a final-dated snapshot. A successful snapshot is never overwritten on the same
date.

To restore, stop Hublet, replace the affected live `.db` file with the chosen snapshot,
start Hublet again, and verify `/healthz`.

## Food recovery import

`hublet-food-import LEDGER.csv CATALOGUE.csv --check` validates legacy Food CSVs in a
temporary database. Run it again without `--check` to transactionally populate an empty
`food.db`, or pass `--database PATH` to build an empty recovery candidate elsewhere. The
importer collapses append-only legacy correction chains onto their original stable IDs, creates
deterministic nutrition IDs and only the needed legacy variants, verifies correction-aware
totals, and confirms both source checksums remain unchanged.
Keep the source CSVs outside the repository as read-only rollback archives.

## Agentbridge Health sync

Set `HUBLET_AGENTBRIDGE_DIR` to the directory containing Agentbridge daily JSON exports. The
`health_sync_agentbridge` MCP tool scans that directory itself; callers cannot supply a path. Each
successful sync atomically replaces Health's current snapshot, while invalid or disappearing
exports leave the previous `health.db` intact. Unknown HealthKit types remain queryable as raw JSON.

For a weekly Goals report, OpenClaw should call Health sync, request `health_summary`, record the
returned mapped evidence through `goals_record_evidence`, and then request
`goals_report_snapshot`. Hublet keeps no Health import history because the Agentbridge exports and
daily SQLite snapshots already provide recovery.

## CI

Pull requests and pushes run a clean editable install, Ruff and pytest on a GitHub-hosted
runner. Hublet does not publish or require a container image.

## Mac deployment

Hublet runs directly from one Git checkout and one virtual environment under `launchd`.
Keep the checkout, live data, backups, logs and environment files in owner-chosen local
paths. Nothing in the repository fixes a Mac username, LAN address or private directory.

Create a private root directory, clone this repository into its `app` directory, and create
the runtime environment:

```sh
git clone https://github.com/TallFarang/hublet.git /absolute/path/to/hublet/app
python3.13 -m venv /absolute/path/to/hublet/venv
/absolute/path/to/hublet/venv/bin/python -m pip install \
  -r /absolute/path/to/hublet/app/requirements.lock
/absolute/path/to/hublet/venv/bin/python -m pip install \
  --no-deps -e /absolute/path/to/hublet/app
```

Copy `.env.example` to `<root>/secrets.env`, replace its placeholders, point its data and
backup settings outside the checkout, and keep it mode 600. Create an external `deploy.env`:

```sh
HUBLET_ROOT=/absolute/path/to/hublet
```

Write the checkout's current SHA to the release marker:

```sh
git -C /absolute/path/to/hublet/app rev-parse HEAD \
  > /absolute/path/to/hublet/RELEASE
```

Copy the three plist templates in `ops/` to `~/Library/LaunchAgents/`, replace their
placeholders with absolute local paths, and validate them with `plutil -lint`. Bootstrap
them with `launchctl bootstrap gui/$(id -u) <plist>`.

The runtime is kept alive by launchd, backups run daily at 03:15, and the deploy job checks
public GitHub `main` every five minutes. It exits when nothing changed and refuses to update
unless the checkout is clean and a successful daily snapshot is less than 26 hours old.
For a changed commit it updates the shared environment, restarts Hublet, checks `/healthz`,
then records the SHA in `RELEASE`. Shell and Git polling do not invoke an LLM.

Automatic rollback is intentionally omitted. To undo a release, unload the deploy job, stop
the runtime, check out the SHA in `<root>/PREVIOUS_RELEASE`, reinstall the locked runtime
requirements and editable project, restart `io.hublet.runtime`, and verify `/healthz`. Restore
databases separately from the daily snapshots only when required.

Never expose Hublet through router port forwarding. It is designed for one trusted user on
a home LAN.
