from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_GITIGNORE_ENTRIES = {
    ".coverage",
    ".coverage.*",
    ".DS_Store",
    ".env",
    ".env.*",
    "!.env.example",
    "*.db",
    "*.egg-info/",
    "*.key",
    "*.pem",
    "*.sqlite",
    "*.sqlite3",
    "backups/",
    "coverage.xml",
    "data/",
    "htmlcov/",
    "secrets/",
}
DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
SQLITE_HEADER = b"SQLite " + b"format 3\0"
APPROVED_LOCAL_HOSTNAMES = {"hublet-host.local"}
FICTIONAL_SECRET = re.compile(
    r"(?i)(?:change-me|example|placeholder|replace-me)(?:-[a-z0-9]+)*"
)
SECRET_ASSIGNMENT = re.compile(
    r"(?im)(?:^|\s)[A-Za-z0-9_-]*(?:api[_-]?key|password|secret|token)"
    r"[A-Za-z0-9_-]*\s*[:=]\s*(?P<quote>[\"']?)(?P<value>[A-Za-z0-9_./+=-]{16,})"
    r"(?P=quote)"
)
TEXT_PATTERNS = {
    "absolute user home path": re.compile(r"/(?:Users|home)/"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "private IPv4 address": re.compile(
        r"\b(?:10(?:\.\d{1,3}){3}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
        r"192\.168(?:\.\d{1,3}){2})\b"
    ),
    "private key": re.compile(
        r"-----BEGIN (?:DSA |EC |ENCRYPTED |OPENSSH |RSA )?PRIVATE KEY-----"
    ),
    "PuTTY private key": re.compile(r"(?im)^PuTTY-User-Key-File-\d+:"),
    "service token": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "SSH config": re.compile(r"(?im)^\s*(?:HostName|IdentityFile|ProxyJump)\s+\S+"),
    "SSH destination": re.compile(
        r"(?im)(?:^|[;&|]\s*)ssh\s+(?:-[^\s]+\s+)*"
        r"(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9.-]+\b"
    ),
}
LOCAL_HOSTNAME = re.compile(
    r"(?i)\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.local\b"
)


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    files = []
    for relative_path in result.stdout.splitlines():
        candidate = REPOSITORY_ROOT / relative_path
        if candidate.is_symlink() or candidate.is_file():
            files.append(candidate)
    return files


def text_findings(contents: str) -> list[str]:
    findings = [label for label, pattern in TEXT_PATTERNS.items() if pattern.search(contents)]
    for match in LOCAL_HOSTNAME.finditer(contents):
        if match.group(0).lower() not in APPROVED_LOCAL_HOSTNAMES:
            findings.append("unapproved .local hostname")
    for match in SECRET_ASSIGNMENT.finditer(contents):
        if FICTIONAL_SECRET.fullmatch(match.group("value")) is None:
            findings.append("secret assignment")
    return findings


def file_findings(path: Path, contents: bytes) -> list[str]:
    if path.is_symlink():
        return ["symbolic link"]
    findings = []
    if path.suffix.lower() in DATABASE_SUFFIXES:
        findings.append("database filename")
    if contents.startswith(SQLITE_HEADER):
        findings.append("SQLite file header")
    decoded_contents = contents.decode(errors="replace").replace("\0", "\n")
    findings.extend(text_findings(decoded_contents))
    return findings


def ignore_entries(filename: str) -> set[str]:
    return {
        line.strip()
        for line in (REPOSITORY_ROOT / filename).read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_gitignore_protects_local_data_secrets_and_coverage() -> None:
    assert REQUIRED_GITIGNORE_ENTRIES <= ignore_entries(".gitignore")


def test_repository_contains_no_private_material() -> None:
    findings = {}
    for path in repository_files():
        contents = b"" if path.is_symlink() else path.read_bytes()
        current_findings = file_findings(path, contents)
        if current_findings:
            findings[str(path.relative_to(REPOSITORY_ROOT))] = current_findings

    assert findings == {}


def test_scanner_detects_sqlite_magic_without_database_suffix(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.bin"
    fixture.write_bytes(SQLITE_HEADER + b"data")

    assert "SQLite file header" in file_findings(fixture, fixture.read_bytes())


def test_scanner_checks_secret_patterns_even_when_file_contains_nul(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.bin"
    binary_payload = b"\0" + (
        "HUBLET_MCP_TOKEN=" + "nonfictional-credential-value"
    ).encode()
    fixture.write_bytes(binary_payload)

    assert "secret assignment" in file_findings(fixture, fixture.read_bytes())


def test_scanner_blocks_private_addresses_but_allows_loopback() -> None:
    private_address = f"{192}.{168}.{50}.{4}"

    assert "private IPv4 address" in text_findings(private_address)
    assert "private IPv4 address" not in text_findings("127.0.0.1")


def test_scanner_blocks_concrete_local_hosts_but_allows_generic_host() -> None:
    concrete_hostname = "private-host" + ".local"

    assert "unapproved .local hostname" in text_findings(concrete_hostname)
    assert "unapproved .local hostname" not in text_findings("hublet-host.local")


def test_scanner_blocks_command_form_ssh_destinations() -> None:
    ssh_destination = "ssh " + "actual-user@" + "personal.example.test"

    assert "SSH destination" in text_findings(ssh_destination)


def test_scanner_rejects_symlinks_without_following_target(tmp_path: Path) -> None:
    target = tmp_path / "outside.txt"
    target.write_text("HUBLET_MCP_TOKEN=" + "nonfictional-credential-value")
    link = tmp_path / "inside.txt"
    link.symlink_to(target)

    assert file_findings(link, b"") == ["symbolic link"]


def test_scanner_blocks_absolute_homes_private_keys_and_ssh_config() -> None:
    user_home = "/" + "Users/example/project"
    private_key = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    putty_key = "PuTTY-User-Key-" + "File-3: ssh-rsa"
    ssh_config = "Host private\n" + "  IdentityFile ~/.ssh/id_example"

    assert "absolute user home path" in text_findings(user_home)
    assert "private key" in text_findings(private_key)
    assert "PuTTY private key" in text_findings(putty_key)
    assert "SSH config" in text_findings(ssh_config)


def test_scanner_allows_clearly_fictional_secrets_of_any_length() -> None:
    fictional_value = "HUBLET_MCP_TOKEN=" + "replace-me-long-fictional-value"

    assert "secret assignment" not in text_findings(fictional_value)
