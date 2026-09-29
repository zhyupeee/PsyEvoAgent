"""Model-settings page acceptance against an explicitly isolated synthetic database."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
from cryptography.fernet import Fernet
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.database import make_engine
from app.models import Preferences, User
from app.security import password_hash
from sqlalchemy import select
from sqlalchemy.orm import Session


def main() -> None:
    url = os.environ["PSYEVO_TEST_DATABASE_URL"]
    Settings(environment="test", database_url=SecretStr(url))
    destination = ROOT / ".artifacts" / "model-settings-validation"
    destination.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    with Session(engine) as db, db.begin():
        user = db.scalar(select(User).where(User.email == "model-settings@example.com"))
        if user is None:
            user = User(
                email="model-settings@example.com",
                password_hash=password_hash("synthetic-model-password"),
            )
            db.add(user)
            db.flush()
            db.add(Preferences(owner_id=user.id))
    engine.dispose()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PSYEVO_")}
    web_env = {
        **env,
        "PSYEVO_ENV": "test",
        "PSYEVO_TEST_API_PORT": "8110",
        "PSYEVO_TEST_WEB_PORT": "3110",
        "PSYEVO_MANAGED_SERVERS": "1",
        "PSYEVO_MODEL_SETTINGS_ARTIFACTS": str(destination),
    }
    api_env = {
        **web_env,
        "PSYEVO_DATABASE_URL": url,
        "PSYEVO_SUPPORT_MODE": "fake",
        "PSYEVO_PROVIDER_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "PSYEVO_BROWSER_ORIGIN": "http://127.0.0.1:3110",
    }
    processes: list[subprocess.Popen[bytes]] = []
    logs = []
    try:
        for name, command, cwd, child_env in (
            (
                "api",
                [
                    sys.executable,
                    "-m",
                    "app.dev",
                    "--support-worker",
                    "--stop-on-stdin-eof",
                    "--port",
                    "8110",
                ],
                ROOT / "backend",
                api_env,
            ),
            (
                "web",
                [
                    shutil.which("node") or "node",
                    "node_modules/vite/bin/vite.js",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "3110",
                ],
                ROOT / "frontend",
                web_env,
            ),
        ):
            log = (destination / (name + ".log")).open("wb")
            logs.append(log)
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=child_env,
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            )
        with httpx.Client(timeout=2, trust_env=False) as client:
            deadline = time.monotonic() + 60
            while True:
                assert all(p.poll() is None for p in processes), (
                    "Synthetic server exited"
                )
                try:
                    if (
                        client.get("http://127.0.0.1:3110/api/v1/health").status_code
                        == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("Synthetic servers did not become ready")
                time.sleep(0.2)
        with (destination / "browser.txt").open("wb") as output:
            result = subprocess.run(
                [
                    shutil.which("pnpm.cmd") or shutil.which("pnpm") or "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "--config",
                    "playwright.model-settings.config.ts",
                ],
                cwd=ROOT / "frontend",
                env=web_env,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=150,
                check=False,
            )
        if result.returncode:
            raise RuntimeError(
                "Model settings browser checks failed; inspect browser.txt"
            )
        descendants = psutil.Process(processes[0].pid).children(recursive=True)
        assert processes[0].stdin is not None
        processes[0].stdin.close()
        assert processes[0].wait(timeout=30) == 0
        _, survivors = psutil.wait_procs(descendants, timeout=5)
        assert not survivors, "Managed child survived supervisor: " + str(
            [p.pid for p in survivors]
        )
        print("Browser checks passed; managed API and Worker both stopped cleanly.")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                from app.dev_instances import stop_tree

                stop_tree(psutil.Process(process.pid))
            process.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
