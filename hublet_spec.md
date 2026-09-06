# Hublet

Hublet is a small, single-user structured-memory service for OpenClaw. It runs as one Python
process, exposes semantic MCP tools, and serves a read-only dashboard on a trusted home LAN.

## Product intent

- OpenClaw is the only user-facing write interface.
- The web UI is a simple dashboard, not an administration application.
- Each plugin owns one SQLite database outside the checkout.
- Prefer deleting features to adding abstractions or operational machinery.
- Add safeguards when a demonstrated risk requires them.

## Runtime

Hublet uses Python 3.13, FastAPI, the MCP Python SDK, Jinja2, SQLite, and local CSS. There is no
SPA, client-side application framework, ORM, migration framework, queue, cache, event bus,
container, reverse proxy, or separate plugin process.

Plugins are explicitly listed Python modules. Each plugin supplies:

- A name and icon.
- A database filename and ordered SQLite migrations.
- MCP tool registration.
- A read-only dashboard route.
- A short launcher summary.

The plugin convention is intentionally not a marketplace or dynamic discovery system.

## Data ownership

- `health.db` is the permanent Health master. Agentbridge exports are import sources, not required
  archives after a successful sync and backup.
- `food.db` is the structured Food master, including nutrition variants and consumption records.
- `goals.db` owns goal definitions and observations. Goals may read linked Health and Food series
  for display but plugins must not mutate each other's databases.
- `recipes.db` stores Apple Notes references and cooking experiments; Apple Notes remains the
  canonical recipe body.
- `coffee.db` stores purchased bags and complete method-aware brew snapshots.

Dashboard presentation lives in `dashboard.json`. OpenClaw can replace the complete validated
document through MCP. Supported choices remain deliberately small: enabled state, label,
precision, data view, and Value, Line, or Bar presentation, including per-goal presentation.

## Active plugin behaviour

### Goals

Goals stores categorised definitions, targets, evidence sources, and idempotent observations. The
dashboard shows active goals and reads linked Health and Food data directly. The existing model is
scheduled for separate simplification; new narrative or reporting features should not be added in
the meantime.

### Food

Food supports receipt ingestion, consumption recording and correction, nutrition upsert/search,
record queries, and compact daily confirmed totals. Receipt ingestion is atomic and idempotent.
The dashboard provides period totals, meal visibility, and a filterable nutrition catalogue.

### Health

Health scans only `HUBLET_AGENTBRIDGE_DIR`. Current source revisions replace matching dates, new
dates append, and stored dates remain if their source JSON disappears. Conflicting HealthKit UUIDs
or invalid exports abort without changing the retained master. Unknown record types and raw JSON
remain queryable.

### Coffee and Recipes

Coffee records each purchase as a distinct bag and stores complete V60, AeroPress, French press,
or espresso recipe snapshots. History can match repeat beans across bags by exact
case-insensitive roaster and name, while roast and origin metadata support starting-point searches.
Lagom Mini is the default grinder; filter bypass water is structured, while serving details such
as a split iced batch or latte stay in notes. Espresso yield and pressure in bar are optional
readings. Recipes links Apple Notes and records cooking experiments. OpenClaw performs
interpretation, recipe inheritance, and recommendations rather than Hublet embedding advisory
engines.

## Web and security boundaries

- Dashboard pages require a signed session created with the dashboard token.
- MCP uses an independent bearer token and Host allowlist.
- Dashboard POST requests require the configured public Origin or Referer.
- Public routes are limited to login and health checks.
- Live databases, tokens, hostnames, paths, backups, and environment files must not be committed.
- Hublet is for a trusted LAN and must not be exposed through router port forwarding.

Required environment settings are:

- `HUBLET_DATA_DIR`
- `HUBLET_BACKUP_DIR`
- `HUBLET_AGENTBRIDGE_DIR`
- `HUBLET_PUBLIC_ORIGIN`
- `HUBLET_DASHBOARD_TOKEN`
- `HUBLET_SESSION_SECRET`
- `HUBLET_MCP_TOKEN`
- `HUBLET_MCP_ALLOWED_HOSTS`

Generic allowed-host examples use
`hublet.example.test:*,localhost:*,127.0.0.1:*`.

## Backup and deployment

`hublet-backup` uses SQLite's online backup API and atomically publishes a dated snapshot of every
plugin database plus `dashboard.json`. It retains the newest 30 daily snapshots. A partial or
missing source never publishes a final snapshot.

Hublet runs under macOS launchd. Automatic deployment is an essential part of the system:

- The deployment job polls public GitHub `main` every five minutes.
- It requires a clean checkout and a successful snapshot from the previous 26 hours.
- A new revision is checked out with locked dependencies, then Hublet is restarted.
- `/healthz` must pass before the release marker advances.
- The previous revision is recorded for manual rollback.

Runtime, backup, and deployment paths and credentials remain external to the checkout.

## Engineering constraints

- Brutal simplicity is the primary constraint.
- Target 200 lines per code file and split only at coherent boundaries.
- Keep high-value tests for data integrity, authentication, MCP contracts, current domain
  behaviour, dashboard projections, backups, and deployment.
- Do not test exact documentation prose or complete transitive dependency inventories.
- Do not add generic CRUD APIs, destructive MCP tools, dynamic plugins, frontend frameworks, or
  infrastructure for hypothetical future requirements.
