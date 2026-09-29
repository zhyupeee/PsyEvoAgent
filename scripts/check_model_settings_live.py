"""Explicit paid synthetic API/Worker/title journey in an isolated empty test database."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import psutil
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.database import make_engine
from app.models import (
    IdentitySession,
    ModelCall,
    Preferences,
    ProviderBinding,
    User,
    now,
)
from app.provider_config import read_config
from app.security import digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    if os.environ.get("CI") or os.environ.get("PSYEVO_CHECK_NETWORK"):
        raise RuntimeError("Live verification is not a PR/CI test")
    url = os.environ["PSYEVO_TEST_DATABASE_URL"]
    Settings(environment="test", database_url=SecretStr(url))
    selected = read_config(ROOT / ".env.step08.ps1", Settings())
    assert selected.provider_api_key is not None
    master = Fernet.generate_key().decode()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PSYEVO_")}
    env.update(
        PSYEVO_ENV="test",
        PSYEVO_DATABASE_URL=url,
        PSYEVO_SUPPORT_MODE="live",
        PSYEVO_BROWSER_ORIGIN="http://127.0.0.1:8111",
        PSYEVO_PROVIDER_ENCRYPTION_KEY=master,
        PSYEVO_PROVIDER_BASE_URL=selected.provider_base_url,
        PSYEVO_PROVIDER_MODEL=selected.provider_model,
        PSYEVO_PROVIDER_API_KEY=selected.provider_api_key.get_secret_value(),
        PSYEVO_PROVIDER_DEADLINE_SECONDS=str(selected.provider_deadline_seconds),
        PSYEVO_PROVIDER_MAX_OUTPUT_TOKENS=str(
            min(1024, selected.provider_max_output_tokens)
        ),
    )
    from app.config import load_settings

    load_settings(env)  # Validate isolated live gates before any external request.
    destination = ROOT / ".artifacts" / "model-settings-validation"
    destination.mkdir(parents=True, exist_ok=True)
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        check=False,
        timeout=40,
    )
    if migration.returncode:
        raise RuntimeError(
            "Isolated migration failed; no raw connection details printed"
        )
    engine = make_engine(url)
    token = uuid4().hex
    with Session(engine) as db, db.begin():
        if db.scalar(select(User.id).limit(1)):
            raise RuntimeError(
                "Live journey requires a fresh isolated database; never auto-retry"
            )
        user = User(email="model-journey@example.com", password_hash="synthetic-unused")
        db.add(user)
        db.flush()
        db.add(Preferences(owner_id=user.id))
        db.add(
            IdentitySession(
                owner_id=user.id,
                token_hash=digest(token),
                csrf_token="synthetic-csrf",
                expires_at=now() + timedelta(hours=1),
            )
        )
    process: subprocess.Popen[bytes] | None = None
    receipt: dict[str, object] = {
        "synthetic": True,
        "model": selected.provider_model,
        "passed": False,
    }
    try:
        with (destination / "live-journey-worker.log").open("wb") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.dev",
                    "--support-worker",
                    "--stop-on-stdin-eof",
                    "--port",
                    "8111",
                ],
                cwd=ROOT / "backend",
                env=env,
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            with httpx.Client(
                base_url="http://127.0.0.1:8111/api/v1",
                timeout=5,
                trust_env=False,
                cookies={"psyevo_session": token},
                headers={
                    "Origin": "http://127.0.0.1:8111",
                    "X-CSRF-Token": "synthetic-csrf",
                },
            ) as client:
                deadline = time.monotonic() + 30
                while True:
                    assert process.poll() is None, "Isolated server exited"
                    try:
                        if client.get("health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    assert time.monotonic() < deadline, "Isolated server not ready"
                    time.sleep(0.2)
                source = client.post(
                    "sessions", json={}, headers={"Idempotency-Key": uuid4().hex}
                )
                assert source.status_code == 201
                sid = source.json()["id"]
                started = client.post(
                    f"sessions/{sid}/runs",
                    headers={"Idempotency-Key": uuid4().hex},
                    json={
                        "expected_session_version": 1,
                        "client_message_id": uuid4().hex,
                        "input": {
                            "message": "这是独立合成测试：今天学习有点累，我只想说说，不需要建议。"
                        },
                    },
                )
                assert started.status_code == 202
                rid = started.json()["run_id"]
                deadline = time.monotonic() + 110
                while True:
                    run = client.get(f"runs/{rid}").json()
                    source_data = client.get(f"sessions/{sid}").json()
                    if run["status"] in {"failed", "interrupted", "cancelled"}:
                        break
                    if source_data["title_generation_status"] in {
                        "succeeded",
                        "failed",
                        "cancelled",
                    }:
                        break
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.3)
                with Session(engine) as db:
                    binding = db.get(ProviderBinding, rid)
                    calls = list(
                        db.scalars(select(ModelCall).where(ModelCall.run_id == rid))
                    )
                    receipt.update(
                        run_status=run["status"],
                        stop_reason=run["stop_reason"],
                        title_status=source_data["title_generation_status"],
                        title_length=len(source_data["title"]),
                        encrypted_binding=bool(binding and binding.encrypted_config),
                        calls=[c.receipt for c in calls],
                        passed=run["status"] == "completed"
                        and source_data["title_source"] == "auto"
                        and len(calls) == 2,
                    )
            children = psutil.Process(process.pid).children(recursive=True)
            assert process.stdin is not None
            process.stdin.close()
            assert process.wait(timeout=30) == 0
            _, alive = psutil.wait_procs(children, timeout=5)
            assert not alive, "Managed live worker survived supervisor"
            receipt["clean_shutdown"] = True
    finally:
        if process is not None and process.poll() is None:
            from app.dev_instances import stop_tree

            stop_tree(psutil.Process(process.pid))
        engine.dispose()
        (destination / "live-journey.json").write_text(
            json.dumps(receipt, indent=2, default=str), encoding="utf-8"
        )
    print(json.dumps({k: v for k, v in receipt.items() if k != "calls"}))
    if not receipt["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
