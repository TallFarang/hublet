from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
OPS_DIR = REPOSITORY_ROOT / "ops"
DEPLOY_SCRIPT = OPS_DIR / "hublet-deploy.sh"


def git(*arguments: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def prepare_deployment(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str], str]:
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    checkout = tmp_path / "checkout"
    root = tmp_path / "hublet"
    git("init", "--bare", str(remote), cwd=tmp_path)
    git("clone", str(remote), str(seed), cwd=tmp_path)
    git("config", "user.email", "fixture@example.test", cwd=seed)
    git("config", "user.name", "Fixture", cwd=seed)
    (seed / "release.txt").write_text("one\n")
    git("add", "release.txt", cwd=seed)
    git("commit", "-m", "initial", cwd=seed)
    git("push", "-u", "origin", "HEAD:main", cwd=seed)
    git("clone", "--branch", "main", str(remote), str(checkout), cwd=tmp_path)
    current = git("rev-parse", "HEAD", cwd=checkout)

    backup = root / "backups" / "2026-08-16"
    backup.mkdir(parents=True)
    (backup / ".hublet-snapshot").touch()
    (root / "venv" / "bin").mkdir(parents=True)
    (root / "RELEASE").write_text(current + "\n")
    (root / "secrets.env").write_text(f"HUBLET_BACKUP_DIR={root / 'backups'}\n")
    deploy_env = root / "deploy.env"
    deploy_env.write_text(
        f"HUBLET_ROOT={root}\nHUBLET_REPOSITORY_DIR={checkout}\n"
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = root / "calls"
    command = f'#!/bin/sh\nprintf "%s\\n" "$0 $*" >>"{calls}"\n'
    for executable in (root / "venv" / "bin" / "python", fake_bin / "launchctl", fake_bin / "curl"):
        executable.write_text(command)
        executable.chmod(0o755)
    environment = os.environ | {
        "HUBLET_DEPLOY_ENV": str(deploy_env),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    return seed, checkout, root, environment, current


def publish_change(seed: Path) -> str:
    (seed / "release.txt").write_text("two\n")
    git("add", "release.txt", cwd=seed)
    git("commit", "-m", "update", cwd=seed)
    git("push", "origin", "HEAD:main", cwd=seed)
    return git("rev-parse", "HEAD", cwd=seed)


def run_deploy(environment: dict[str, str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", str(DEPLOY_SCRIPT)],
        check=check,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_deploy_is_a_noop_when_release_is_current(tmp_path: Path) -> None:
    _seed, checkout, root, environment, current = prepare_deployment(tmp_path)

    run_deploy(environment)

    assert git("rev-parse", "HEAD", cwd=checkout) == current
    assert not (root / "calls").exists()


def test_deploy_refuses_to_change_code_when_daily_backup_is_stale(tmp_path: Path) -> None:
    seed, checkout, root, environment, current = prepare_deployment(tmp_path)
    publish_change(seed)
    marker = root / "backups" / "2026-08-16" / ".hublet-snapshot"
    os.utime(marker, (0, 0))

    result = run_deploy(environment, check=False)

    assert result.returncode == 1
    assert "no Hublet snapshot from the last 26 hours" in result.stderr
    assert git("rev-parse", "HEAD", cwd=checkout) == current
    assert not (root / "calls").exists()


def test_deploy_updates_clean_checkout_and_release_marker(tmp_path: Path) -> None:
    seed, checkout, root, environment, _current = prepare_deployment(tmp_path)
    wanted = publish_change(seed)

    run_deploy(environment)

    assert git("rev-parse", "HEAD", cwd=checkout) == wanted
    assert (root / "RELEASE").read_text().strip() == wanted
    assert (root / "PREVIOUS_RELEASE").read_text().strip() == _current
    calls = (root / "calls").read_text()
    assert "pip install --quiet -r" in calls
    assert "pip install --quiet --no-deps -e" in calls
    assert "launchctl kickstart -k" in calls
    assert "curl --fail --silent" in calls


def test_failed_health_check_does_not_advance_release_marker(tmp_path: Path) -> None:
    seed, checkout, root, environment, current = prepare_deployment(tmp_path)
    wanted = publish_change(seed)
    fake_curl = Path(environment["PATH"].split(":", 1)[0]) / "curl"
    fake_curl.write_text("#!/bin/sh\nexit 1\n")

    result = run_deploy(environment, check=False)

    assert result.returncode == 1
    assert git("rev-parse", "HEAD", cwd=checkout) == wanted
    assert (root / "RELEASE").read_text().strip() == current
    assert (root / "PREVIOUS_RELEASE").read_text().strip() == current


def test_launchd_templates_are_generic_and_schedule_native_jobs() -> None:
    deploy = (OPS_DIR / "io.hublet.deploy.plist.example").read_text()
    backup = (OPS_DIR / "io.hublet.backup.plist.example").read_text()
    runtime = (OPS_DIR / "io.hublet.runtime.plist.example").read_text()
    templates = deploy + backup + runtime

    assert "<integer>300</integer>" in deploy
    assert "<key>StartCalendarInterval</key>" in backup
    assert "<key>KeepAlive</key>" in runtime
    assert "hublet-deploy.sh" in deploy
    assert "hublet-backup.sh" in backup
    assert "hublet-runtime.sh" in runtime
    assert "__HUBLET_REPOSITORY_DIR__" in templates
    assert "__HUBLET_DEPLOY_ENV__" in templates
    assert "__HUBLET_LOG_DIR__" in templates
    assert ("/" + "Users/") not in templates
