from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
OPS_DIR = REPOSITORY_ROOT / "ops"


def test_operations_script_pulls_only_changed_images_and_runs_backups() -> None:
    script = (OPS_DIR / "hublet-ops.sh").read_text()

    assert '"${HUBLET_DEPLOY_ENV:?set HUBLET_DEPLOY_ENV' in script
    assert "docker compose pull --quiet runtime" in script
    assert "docker compose ps -q runtime" in script
    assert "docker compose up -d --remove-orphans" in script
    assert "http://127.0.0.1:8787/health" in script
    assert "docker compose exec -T runtime hublet-backup" in script
    assert "docker compose down" not in script
    assert "rollback" not in script.casefold()
    assert "watchtower" not in script.casefold()


def test_launchd_templates_are_generic_and_schedule_deploys_and_backups() -> None:
    deploy = (OPS_DIR / "io.hublet.deploy.plist.example").read_text()
    backup = (OPS_DIR / "io.hublet.backup.plist.example").read_text()
    templates = deploy + backup

    assert "<integer>300</integer>" in deploy
    assert "<key>RunAtLoad</key>" in deploy
    assert "<key>StartCalendarInterval</key>" in backup
    assert "<string>deploy</string>" in deploy
    assert "<string>backup</string>" in backup
    assert "__HUBLET_REPOSITORY_DIR__" in templates
    assert "__HUBLET_DEPLOY_ENV__" in templates
    assert "__HUBLET_LOG_DIR__" in templates
    assert ("/" + "Users/") not in templates


def test_compose_image_can_be_pinned_outside_git() -> None:
    compose = (REPOSITORY_ROOT / "compose.yml").read_text()

    assert "${HUBLET_IMAGE:-ghcr.io/tallfarang/hublet:latest}" in compose
