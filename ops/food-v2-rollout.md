# Adopting the existing Food v2 database

Run these steps on the deployed Mac as the account that owns Hublet. Lewis handles
committing and pushing the tested repository changes. Do not replace the database with
a development copy, lower `user_version`, or remove the newer-schema safety check.

## Before publishing the release

Pause the deploy LaunchAgent before pushing to `main`, so polling cannot race the backup:

```sh
launchctl bootout "gui/$(id -u)/io.hublet.deploy"
```

If it is already unloaded, confirm that state with `launchctl print` rather than treating
an unrelated failure as success. Runtime and backups can remain loaded.

Inspect and archive the local source diff and any untracked files outside the checkout.
Compare the local schema edits with this release. Reconcile only understood source changes
so `git status --porcelain` is empty; stop for review if other unexplained changes exist.
Keep live databases, backups, secrets, and deployment configuration outside the checkout.
The updater's dirty-checkout guard remains enabled.

## Take a fresh backup

Load the installed external configuration into the shell without printing secrets:

```sh
export HUBLET_DEPLOY_ENV=/absolute/path/to/deploy.env
set -a
. "$HUBLET_DEPLOY_ENV"
. "$HUBLET_ROOT/secrets.env"
set +a
```

Record `PRAGMA user_version`, `PRAGMA table_info(nutrition)`, total nutrition and record
counts, and `SELECT COUNT(*) FROM nutrition WHERE macros_complete=0` using a read-only
SQLite connection. The reported production baseline is version 2 with 167 incomplete
nutrition entries; use the actual pre-deploy count if legitimate writes have occurred.
Confirm the column matches the v2 definition in `food_schema.py`.

The daily backup command refuses to replace today's snapshot. The following uses that
same online backup implementation in a separate directory, then preserves the completed
snapshot under a unique name in the normal backup root. Run in a shell that stops on errors:

```sh
set -eu
backup_root="$HUBLET_BACKUP_DIR"
backup_staging=$(mktemp -d "$backup_root/.predeploy-food-v2.XXXXXX")
fresh_snapshot=$(HUBLET_BACKUP_DIR="$backup_staging" "$HUBLET_ROOT/venv/bin/hublet-backup")
backup_destination="$backup_root/predeploy-food-v2-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$backup_destination"
mv "$fresh_snapshot" "$backup_destination"
rmdir "$backup_staging"
test -f "$backup_destination/.hublet-snapshot"
```

Retain this snapshot. Its marker sits at the depth expected by the updater, and the
normal daily retention routine leaves the named pre-deploy snapshot alone. Check the
backed-up databases with `PRAGMA integrity_check` before updating.

## Deploy and verify

Once the tested release is on `main` and the fresh backup is verified, run the existing
updater with the loaded configuration:

```sh
repository_dir="${HUBLET_REPOSITORY_DIR:-$HUBLET_ROOT/app}"
/bin/sh "$repository_dir/ops/hublet-deploy.sh"
```

On existing v2 databases, startup skips the migration and leaves all rows unchanged.
On v1 databases, startup adds the flag with default 1. A database newer than v2 still
fails startup. Confirm `/healthz`, the deployed `RELEASE` SHA, Food API responses, and the
dashboard. Compare Food schema, rows, and incomplete-entry count with the fresh snapshot,
accounting for legitimate concurrent writes; startup itself must not alter existing v2 rows.

Confirm calorie-only entries retain their calories and expose null macros, mixed daily
macro totals are null, and the dashboard displays “Incomplete” and “Macros unknown”.
Then reload the installed deploy LaunchAgent:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/io.hublet.deploy.plist"
```

If verification fails, leave scheduled deployment paused and diagnose against the backup.
Any code rollback must also support Food v2. The previous v1 release cannot run this
database; do not downgrade or restore older data just to make that release start.
