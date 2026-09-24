"""STEP03 real PostgreSQL + API + browser gate; uses its own disposable container.

Run after locked dependencies, Chromium and postgres:16.13-bookworm are prepared.
No image pulls, real accounts, provider calls or existing database access.
"""

import hashlib
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--web-port", type=int, default=3000)
parser.add_argument("--api-port", type=int, default=8000)
parser.add_argument("--tls-port", type=int, default=3443)
args = parser.parse_args()
if any(not 1024 <= port <= 65535 for port in (args.web_port, args.api_port, args.tls_port)):
    parser.error("Ports must be between 1024 and 65535")
if len({args.web_port, args.api_port, args.tls_port}) != 3:
    parser.error("Web, API and TLS ports must be distinct")
BACKEND = ROOT / "backend"
IMAGE = "postgres:16.13-bookworm@sha256:472efd9a66f2b2f1a5aeb18b28de74332e6ef88c2b93a1a5d812fb6db67a5f60"
NAME = "psyevo-step03-" + uuid4().hex[:12]
RUN = ROOT / ".artifacts" / NAME
RUN.mkdir(parents=True)
ENV = {
    key: value
    for key, value in os.environ.items()
    if key.upper()
    in {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOME",
        "PLAYWRIGHT_BROWSERS_PATH",
    }
}
ENV.update(
    PYTHONUTF8="1",
    PYTHONDONTWRITEBYTECODE="1",
    PSYEVO_ENV="test",
    PSYEVO_TEST_MAIL_DIR=str(RUN / "mail"),
    PSYEVO_BROWSER_ORIGIN=f"http://127.0.0.1:{args.web_port}",
    PSYEVO_TEST_WEB_PORT=str(args.web_port),
    PSYEVO_TEST_API_PORT=str(args.api_port),
    UV_CACHE_DIR=str(ROOT / ".artifacts/uv-cache"),
    PSYEVO_CHECK_NETWORK="loopback-only",
    PYTHONPATH=str(ROOT / "scripts/network_guard"),
    NODE_OPTIONS='--require="' + (ROOT / "scripts/network-guard.cjs").as_posix() + '"',
)
PNPM = shutil.which("pnpm.cmd" if os.name == "nt" else "pnpm")
if PNPM is None:
    raise SystemExit("pnpm is not installed")
RECEIPT: dict[str, object] = {
    "step_id": "S1-STEP03",
    "started": datetime.now(UTC).isoformat(),
    "execution_kind": "real-local-postgresql-api-browser-with-synthetic-accounts",
    "acceptance_ids": ["S1-A02", "S1-A06", "RSI-S1-A02", "RSI-S1-A03"],
    "image": IMAGE,
    "commands": [],
    "passed": False,
    "limitations": [
        "Experiment entry only; no remote service published",
        "No model, feedback, run execution or complete deletion acceptance",
        "Language/browser network guards are not kernel egress isolation",
    ],
}
commands: list[dict[str, object]] = []
RECEIPT["commands"] = commands


def run(label: str, args: list[str], cwd: Path = ROOT, timeout: int = 240) -> str:
    print(label, flush=True)
    result = subprocess.run(
        args,
        cwd=cwd,
        env=ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    output = result.stdout + result.stderr
    (RUN / (label + ".txt")).write_text(output, encoding="utf-8")
    commands.append(
        {"label": label, "exit_code": result.returncode, "log": label + ".txt"}
    )
    if result.returncode:
        print(output[-8000:])
        raise RuntimeError(f"{label} failed")
    return output


created = False
try:
    for port in (args.web_port, args.api_port, args.tls_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    run("image", ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"])
    run(
        "database-create",
        [
            "docker",
            "run",
            "--pull=never",
            "--name",
            NAME,
            "--label",
            "psyevo.synthetic-step03=true",
            "-p",
            "127.0.0.1::5432",
            "-e",
            "POSTGRES_USER=psyevo",
            "-e",
            "POSTGRES_PASSWORD=synthetic-check-only",
            "-e",
            "POSTGRES_DB=psyevo_synthetic_check",
            "-d",
            IMAGE,
        ],
    )
    created = True
    port = (
        run("database-port", ["docker", "port", NAME, "5432/tcp"])
        .strip()
        .split(":")[-1]
    )
    url = f"postgresql+psycopg://psyevo:synthetic-check-only@127.0.0.1:{port}/psyevo_synthetic_check?connect_timeout=3"
    ENV.update(PSYEVO_DATABASE_URL=url, PSYEVO_TEST_DATABASE_URL=url)
    for attempt in range(30):
        ready = subprocess.run(
            ["docker", "exec", NAME, "pg_isready", "-h", "127.0.0.1", "-U", "psyevo"],
            env=ENV,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Disposable PostgreSQL did not become ready")
    run(
        "database-version",
        [
            "docker",
            "exec",
            NAME,
            "psql",
            "-U",
            "psyevo",
            "-d",
            "psyevo_synthetic_check",
            "-Atc",
            "SELECT version()",
        ],
    )
    run("lock", ["uv", "lock", "--check", "--offline"], BACKEND)
    run("lint", [sys.executable, "-m", "ruff", "check", "."], BACKEND)
    run("format", [sys.executable, "-m", "ruff", "format", "--check", "."], BACKEND)
    run("types", [sys.executable, "-m", "mypy"], BACKEND)
    run("migration", [sys.executable, "-m", "alembic", "upgrade", "head"], BACKEND)
    run("schema-drift", [sys.executable, "-m", "alembic", "check"], BACKEND)
    run(
        "api-migrations",
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "postgres",
            "--junitxml=" + str(RUN / "postgres-tests.xml"),
        ],
        BACKEND,
    )
    run("foundation", [sys.executable, "-m", "pytest"], BACKEND)
    seed = """
from sqlalchemy.orm import Session
from app.config import load_settings
from app.database import make_engine
from app.models import Preferences, User
from app.security import password_hash
engine = make_engine(load_settings().database_url.get_secret_value())
with Session(engine) as db, db.begin():
    for name, password in [('admin@example.com', 'synthetic-admin-password'), ('browser-b@example.com', 'synthetic-browser-password')]:
        user = User(email=name, password_hash=password_hash(password))
        db.add(user)
        db.flush()
        db.add(Preferences(owner_id=user.id))
engine.dispose()
"""
    run("seed-synthetic", [sys.executable, "-c", seed], BACKEND)
    run("frontend-build", [PNPM, "build"], ROOT / "frontend")
    run("frontend-check", [PNPM, "check"], ROOT / "frontend")
    run(
        "browser",
        [PNPM, "exec", "playwright", "test", "--config", "playwright.step03.config.ts"],
        ROOT / "frontend",
    )
    openssl = shutil.which("openssl")
    if openssl is None and os.name == "nt":
        git_openssl = Path("C:/Program Files/Git/usr/bin/openssl.exe")
        if git_openssl.is_file():
            openssl = str(git_openssl)
    if openssl is None:
        raise RuntimeError("OpenSSL is required for local HTTPS verification")
    cert, key = RUN / "tls-cert.pem", RUN / "tls-key.pem"
    run("test-certificate", [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"])
    ENV.update(PSYEVO_BROWSER_ORIGIN=f"https://127.0.0.1:{args.tls_port}", PSYEVO_TEST_TLS_PORT=str(args.tls_port), PSYEVO_TEST_TLS_CERT=str(cert), PSYEVO_TEST_TLS_KEY=str(key))
    run("https-browser", [PNPM, "exec", "playwright", "test", "--config", "playwright.https.config.ts"], ROOT / "frontend")
    run("database-restart", ["docker", "restart", NAME])
    # Docker may assign a new published port after restart when HostPort was random.
    port = (
        run("database-restarted-port", ["docker", "port", NAME, "5432/tcp"])
        .strip()
        .split(":")[-1]
    )
    url = f"postgresql+psycopg://psyevo:synthetic-check-only@127.0.0.1:{port}/psyevo_synthetic_check?connect_timeout=3"
    ENV.update(PSYEVO_DATABASE_URL=url, PSYEVO_TEST_DATABASE_URL=url)
    for attempt in range(30):
        ready = subprocess.run(
            ["docker", "exec", NAME, "pg_isready", "-U", "psyevo"],
            env=ENV,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("PostgreSQL restart readiness timed out")
    persisted = """
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import load_settings
from app.database import make_engine
from app.models import Consent, Preferences, User
engine = make_engine(load_settings().database_url.get_secret_value())
with Session(engine) as db:
    a = db.scalar(select(User).where(User.email == 'admin@example.com'))
    assert a is not None
    pref = db.scalar(select(Preferences).where(Preferences.owner_id == a.id))
    assert pref is not None and pref.age_band == 'unknown' and pref.version == 1
    rows = list(db.scalars(select(Consent).where(Consent.owner_id == a.id)))
    assert len(rows) == 0
    registered = list(db.scalars(select(User).where(User.email.like('browser-%'), User.email != 'browser-b@example.com')))
    assert registered
    for user in registered:
        pref = db.scalar(select(Preferences).where(Preferences.owner_id == user.id))
        assert pref is not None and pref.age_band == 'unknown'
        assert not list(db.scalars(select(Consent).where(Consent.owner_id == user.id)))
print('Registered accounts persisted across PostgreSQL restart; no consent fabricated')
engine.dispose()
"""
    run("database-browser-receipt", [sys.executable, "-c", persisted], BACKEND)
    run("documents", [sys.executable, "-B", "-X", "utf8", "_check_docs.py"])
    run("diff", ["git", "diff", "--check"])
    RECEIPT["passed"] = True
finally:
    if created:
        # Only this invocation's randomly named, labelled disposable test container.
        run("database-cleanup", ["docker", "rm", "-f", "-v", NAME])
    RECEIPT["finished"] = datetime.now(UTC).isoformat()
    files = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    RECEIPT["source_sha256"] = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in files
        if (ROOT / path).is_file()
        and path.startswith(("backend/", "frontend/", "scripts/"))
    }
    (RUN / "receipt.json").write_text(
        json.dumps(RECEIPT, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Receipt: " + str(RUN / "receipt.json"), flush=True)
