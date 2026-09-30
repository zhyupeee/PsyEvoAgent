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
parser.add_argument("--step05", action="store_true", help="Also verify durable fake runs and gateway SSE")
parser.add_argument("--step06", action="store_true", help="Also verify chat, preferences and independent exercise UI")
parser.add_argument("--step07", action="store_true", help="Also verify history, revisions, deletion and feedback")
parser.add_argument("--s2-step02", action="store_true", help="Verify records CRUD, source grants and record pages")
parser.add_argument("--step08-live", action="store_true", help="Explicit live integration after fake regression")
parser.add_argument("--multiturn-live", action="store_true", help="Two synthetic live context turns instead of historical STEP08 live journey")
args = parser.parse_args()
if args.s2_step02:
    args.step07 = True
if args.multiturn_live:
    args.step08_live = True
if args.step08_live:
    if os.environ.get("CI") or os.environ.get("PSYEVO_CHECK_NETWORK") or not os.environ.get("PSYEVO_PROVIDER_API_KEY", "").strip():
        parser.error("Live acceptance requires a key outside PR/network isolation")
    args.step07 = True
if args.step07:
    args.step06 = True
if args.step06:
    args.step05 = True
if any(not 1024 <= port <= 65535 for port in (args.web_port, args.api_port, args.tls_port)):
    parser.error("Ports must be between 1024 and 65535")
if len({args.web_port, args.api_port, args.tls_port}) != 3:
    parser.error("Web, API and TLS ports must be distinct")
BACKEND = ROOT / "backend"
IMAGE = "postgres:16.13-bookworm@sha256:472efd9a66f2b2f1a5aeb18b28de74332e6ef88c2b93a1a5d812fb6db67a5f60"
NAME = ("psyevo-step07-" if args.step07 else "psyevo-step06-" if args.step06 else "psyevo-step05-" if args.step05 else "psyevo-step03-") + uuid4().hex[:12]
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
    "step_id": "S1-STEP05" if args.step05 else "S1-STEP03",
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
if args.step05:
    RECEIPT["acceptance_ids"] = ["S1-A05", "S1-A11", "RSI-S1-A04", "RSI-S1-A07"]
    RECEIPT["limitations"] = ["Isolated synthetic accounts and fake model only; live Provider/content/SMTP BLOCKED", "No STEP06 chat UI or STEP07 deletion implementation", "Windows network guards are not kernel isolation"]
if args.step06:
    RECEIPT["step_id"] = "S1-STEP06"
    RECEIPT["acceptance_ids"] = ["S1-A02", "S1-A03", "RSI-S1-A08", "S1-A05", "S1-A11"]
    RECEIPT["limitations"] = ["Synthetic UI acceptance; live Provider/content review/SMTP BLOCKED", "No STEP07 history/deletion/feedback", "Language guards are not kernel isolation"]
    ENV["PSYEVO_STEP06_ARTIFACTS"] = str(RUN)
if args.step07:
    RECEIPT["step_id"] = "S1-STEP07"
    RECEIPT["acceptance_ids"] = ["S1-A04", "S1-A06", "S1-A08", "RSI-S1-A03", "RSI-S1-A07", "RSI-S1-A08"]
    RECEIPT["limitations"] = ["Isolated synthetic accounts/fake model; live Provider/content review/SMTP remain unresolved", "No STEP08 live integration or stage handoff", "No persistent checkpoints or application backup configured; content-free tombstones and usage metadata retained", "Language guards are not kernel isolation"]
    ENV["PSYEVO_STEP07_ARTIFACTS"] = str(RUN)
if args.step08_live:
    RECEIPT["step_id"] = "S1-STEP08"
    RECEIPT["execution_kind"] = "isolated-postgresql-fake-regression-plus-explicit-live-browser"
    RECEIPT["limitations"] = [
        "Live full-buffer support uses synthetic inputs only; no remote publication",
        "Full-buffer engineering scope; professional review and safe public chunks are not validated; SMTP delivery is verified separately",
        "Local cancellation/deletion do not prove external provider cancellation/deletion",
        "Provider price, data region and retention remain unknown",
        "Windows network guards apply to regression; live API/Worker explicitly permit provider access",
    ]

if args.s2_step02:
    RECEIPT["step_id"] = "S2-STEP02"
    RECEIPT["acceptance_ids"] = ["S2-A01", "S2-A02", "S2-A03"]
    RECEIPT["limitations"] = ["Synthetic PostgreSQL/API/browser and controlled model inputs; no live calls", "No background jobs, LangMem, memory retrieval or profiles", "No verified public resources; no remote publication", "Windows language egress guards are not kernel isolation"]
    ENV["PSYEVO_S2_STEP02_ARTIFACTS"] = str(RUN)


def run(label: str, args: list[str], cwd: Path = ROOT, timeout: int = 240) -> str:
    print(label, flush=True)
    try:
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
    except subprocess.TimeoutExpired as error:
        output = "\n".join(part.decode("utf-8", errors="replace") if isinstance(part, bytes) else part or "" for part in (error.stdout, error.stderr))
        (RUN / (label + ".txt")).write_text(output, encoding="utf-8")
        commands.append({"label": label, "exit_code": None, "timed_out": True, "log": label + ".txt"})
        raise
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
    if args.s2_step02:
        run("seed-s2-records", [sys.executable, "-c", seed.replace("admin@example.com", "s2-records-browser@example.com").replace("synthetic-admin-password", "synthetic-browser-password").replace("browser-b@example.com", "s2-records-other@example.com")], BACKEND)
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
    if args.step05:
        run("seed-step05", [sys.executable, "-c", seed.replace("admin@example.com", "step05-browser@example.com").replace("synthetic-admin-password", "synthetic-browser-password").replace("browser-b@example.com", "step05-unused@example.com")], BACKEND)
        if args.step07:
            run("seed-step07", [sys.executable, "-c", seed.replace("admin@example.com", "step07-browser@example.com").replace("synthetic-admin-password", "synthetic-browser-password").replace("browser-b@example.com", "step07-unused@example.com")], BACKEND)
        ENV.update(PSYEVO_SUPPORT_MODE="fake", PSYEVO_BROWSER_ORIGIN=f"http://127.0.0.1:{args.web_port}")
        with (RUN / "support-worker.txt").open("w", encoding="utf-8") as worker_log:
            worker = subprocess.Popen([sys.executable, "-m", "app.worker", "--support"], cwd=BACKEND, env=ENV, stdout=worker_log, stderr=subprocess.STDOUT)
            try:
                if args.s2_step02:
                    run("s2-step02-browser", [PNPM, "exec", "playwright", "test", "--config", "playwright.records.config.ts"], ROOT / "frontend")
                run("step05-gateway", [PNPM, "exec", "playwright", "test", "--config", "playwright.step05.config.ts"], ROOT / "frontend")
                if args.step06:
                    run("step06-browser", [PNPM, "exec", "playwright", "test", "--config", "playwright.step06.config.ts"], ROOT / "frontend")
                if args.step07:
                    run("step07-browser", [PNPM, "exec", "playwright", "test", "--config", "playwright.step07.config.ts"], ROOT / "frontend")
                if worker.poll() is not None:
                    raise RuntimeError("Support worker exited before gateway acceptance completed")
            finally:
                worker.terminate()
                worker.wait(timeout=15)
        if args.step07:
            run("model-settings-browser", [sys.executable, "scripts/check_model_settings.py"], timeout=240)
    if args.step08_live:
        run("seed-step08", [sys.executable, "-c", seed.replace("admin@example.com", "step08-live@example.com").replace("synthetic-admin-password", "synthetic-browser-password").replace("browser-b@example.com", "step08-other@example.com")], BACKEND)
        # Only API/Worker receive credentials. Browser/build/test environments remain scrubbed.
        live_env = dict(ENV)
        live_env.pop("PSYEVO_CHECK_NETWORK", None)
        live_env.pop("PYTHONPATH", None)
        live_env.pop("NODE_OPTIONS", None)
        live_env.update({key: value for key, value in os.environ.items() if key.startswith("PSYEVO_PROVIDER_")})
        live_env.update(PSYEVO_SUPPORT_MODE="live", PSYEVO_STEP08_ARTIFACTS=str(RUN))
        ENV.update(PSYEVO_STEP08_ARTIFACTS=str(RUN))
        with (RUN / "live-worker.txt").open("w", encoding="utf-8") as worker_log, (RUN / "live-api.txt").open("w", encoding="utf-8") as api_log:
            worker = subprocess.Popen([sys.executable, "-m", "app.worker", "--support"], cwd=BACKEND, env=live_env, stdout=worker_log, stderr=subprocess.STDOUT)
            api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(args.api_port), "--no-access-log"], cwd=BACKEND, env=live_env, stdout=api_log, stderr=subprocess.STDOUT)
            try:
                run("multiturn-live-browser" if args.multiturn_live else "step08-live-browser", [PNPM, "exec", "playwright", "test", "--config", "playwright.multiturn.config.ts" if args.multiturn_live else "playwright.step08.config.ts"], ROOT / "frontend", timeout=360)
                if worker.poll() is not None or api.poll() is not None:
                    raise RuntimeError("Live API/Worker exited unexpectedly")
            finally:
                api.terminate()
                worker.terminate()
                api.wait(timeout=15)
                worker.wait(timeout=15)
    if args.s2_step02:
        run("s2-records-before-restart", [sys.executable, "-m", "tests.records_receipt", "before", str(RUN / "records-restart.json")], BACKEND)
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
    if args.s2_step02:
        run("s2-records-after-restart", [sys.executable, "-m", "tests.records_receipt", "after", str(RUN / "records-restart.json")], BACKEND)
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
    if args.step05:
        verify_runs = '''
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.config import load_settings
from app.database import make_engine
from app.models import ModelCall, RunEvent, Run, User, Interaction
engine = make_engine(load_settings().database_url.get_secret_value())
with Session(engine) as db:
    user = db.scalar(select(User).where(User.email == "step05-browser@example.com"))
    assert user is not None
    runs = db.scalars(select(Run).where(Run.owner_id == user.id)).all()
    assert len(runs) == 1 and runs[0].status == "completed"
    rid = runs[0].id
    assert db.scalar(select(func.count()).select_from(ModelCall).where(ModelCall.run_id == rid, ModelCall.receipt["role"].astext == "support")) == 1
    assert db.scalar(select(func.count()).select_from(Interaction).where(Interaction.run_id == rid)) == 1
    assert db.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.run_id == rid)) == 128
print("PostgreSQL restart: one browser run, one model call, one initiation; event window retained")
engine.dispose()
'''
        run("step05-restart-facts", [sys.executable, "-c", verify_runs], BACKEND)
    if args.step06:
        verify_pages = '''
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.config import load_settings
from app.database import make_engine
from app.models import User, Preferences, Message, Run, Interaction, ModelCall, Conversation
engine = make_engine(load_settings().database_url.get_secret_value())
with Session(engine) as db:
    user = db.scalar(select(User).where(User.email == "step05-unused@example.com"))
    assert user is not None
    pref = db.scalar(select(Preferences).where(Preferences.owner_id == user.id))
    assert pref is not None and pref.display_preferences["font_size"] == "large"
    assert pref.display_preferences["hide_titles"] is True and pref.version == 2
    messages = list(db.scalars(select(Message).where(Message.owner_id == user.id, Message.role == "user")))
    assert len(messages) == 2
    sent = [m for m in messages if m.content == "合成页面输入，只想倾听"]
    assert len(sent) == 1
    run = db.get(Run, sent[0].run_id)
    assert run is not None and run.status == "completed"
    assert db.scalar(select(func.count()).select_from(Interaction).where(Interaction.run_id == run.id)) == 1
    assert db.scalar(select(func.count()).select_from(ModelCall).where(ModelCall.run_id == run.id, ModelCall.receipt["role"].astext == "support")) == 1
    source = db.get(Conversation, run.session_id)
    assert source.title_source == "auto" and source.title_revision == 2
    assert source.title_generation_status == "succeeded" and source.title == "合成对话主题"
    assert source.version == 1
    assert db.scalar(select(func.count()).select_from(ModelCall).where(ModelCall.run_id == run.id, ModelCall.receipt["role"].astext == "title")) == 1
print("STEP06 restart: preferences and title persisted; one input/run/support call/title call/initiation")
engine.dispose()
'''
        run("step06-restart-facts", [sys.executable, "-c", verify_pages], BACKEND)
    if args.step07:
        verify_history = '''
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.config import load_settings
from app.database import make_engine
from app.models import User, Preferences, Message, Run, RunBranch, Feedback, DeletionJob, Conversation, RunEvent, ModelCall
engine = make_engine(load_settings().database_url.get_secret_value())
with Session(engine) as db:
    user = db.scalar(select(User).where(User.email == "step07-browser@example.com"))
    assert user is not None
    feedback = list(db.scalars(select(Feedback).where(Feedback.owner_id == user.id)))
    assert len(feedback) == 1 and feedback[0].comment == "" and feedback[0].category == "misunderstood"
    assert feedback[0].source_refs == []
    pref = db.scalar(select(Preferences).where(Preferences.owner_id == user.id))
    assert pref is not None and pref.mode == "listen" and pref.version == 1
    branches = list(db.scalars(select(RunBranch).where(RunBranch.owner_id == user.id)))
    assert len(branches) == 2
    revised = list(db.scalars(select(Message).where(Message.owner_id == user.id, Message.content == "STEP07修订后的独立输入")))
    assert sorted(m.version for m in revised) == [2, 3]
    for row in revised:
        run = db.get(Run, row.run_id)
        assert run is not None and run.status == "completed"
        assert db.scalar(select(func.count()).select_from(ModelCall).where(ModelCall.run_id == run.id, ModelCall.receipt["role"].astext == "support")) == 1
    jobs = list(db.scalars(select(DeletionJob).where(DeletionJob.owner_id == user.id)))
    assert len(jobs) == 1 and jobs[0].status == "completed"
    source = db.get(Conversation, jobs[0].target)
    assert source is not None and source.deleted_at and source.status == "deleted"
    for run in db.scalars(select(Run).where(Run.session_id == source.id)):
        assert run.deleted_at
        assert all(m.content == "" and m.deleted_at for m in db.scalars(select(Message).where(Message.run_id == run.id)))
        assert db.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run.id)) == 0
print("STEP07 restart: unique empty-reason feedback, unchanged preferences, distinct input versions and one model call per branch; deleted content/events absent, receipt durable")
engine.dispose()
'''
        run("step07-restart-facts", [sys.executable, "-c", verify_history], BACKEND)
    run("documents", [sys.executable, "-B", "-X", "utf8", "_check_docs.py"])
    if args.step08_live and not args.multiturn_live:
        run("step08-restart-facts", [sys.executable, "-m", "tests.step08_receipt", str(RUN / "live-browser.json"), str(RUN / "live-facts.json")], BACKEND)
    run("diff", ["git", "diff", "--check"])
    RECEIPT["passed"] = True
finally:
    if created:
        if args.step08_live and any(c["label"] == "seed-step08" and c["exit_code"] == 0 for c in commands):
            try:
                run("live-diagnostics", [sys.executable, "-m", "tests.live_diagnostics", str(RUN / "live-diagnostics.json")], BACKEND)
            except Exception:
                RECEIPT["passed"] = False
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
