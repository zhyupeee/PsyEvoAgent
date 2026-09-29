"""Development supervisor helpers; workers are never started by API imports."""

import asyncio
import os
import time
from multiprocessing.synchronize import Event
from pathlib import Path

import psutil
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.database import make_engine
from app.models import Conversation, Run


def serve_worker(stop: Event, ready: Event, parent: int) -> None:
    from app.run_worker import consume

    async def serve() -> None:
        signal = asyncio.Event()

        async def monitor() -> None:
            while not signal.is_set():
                if stop.is_set() or not psutil.pid_exists(parent):
                    signal.set()
                await asyncio.sleep(0.1)

        task = asyncio.create_task(monitor())
        try:
            await consume(signal, ready=ready.set)
        finally:
            signal.set()
            await task

    asyncio.run(serve())


def retire_legacy_workers(directory: Path) -> None:
    """Remove only verified same-checkout/development-database standalone workers."""
    from app.dev_instances import stop_tree

    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        return
    candidates: dict[int, psutil.Process] = {}
    for process in psutil.process_iter():
        try:
            command, env = process.cmdline(), process.environ()
            if (
                process.pid != os.getpid()
                and Path(process.cwd()).resolve() == directory.resolve()
                and command[1:4] == ["-m", "app.worker", "--support"]
                and env.get("PSYEVO_ENV") == "development"
                and env.get("PSYEVO_DATABASE_URL") == settings.database_url.get_secret_value()
            ):
                candidates[process.pid] = process
        except (psutil.Error, OSError, ValueError):
            continue
    if not candidates:
        return
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        deadline = time.monotonic() + 150
        while True:
            with Session(engine) as db:
                active = db.scalar(select(Run.id).where(Run.status == "running").limit(1))
                title = db.scalar(
                    select(Conversation.id)
                    .where(Conversation.title_generation_status == "running")
                    .limit(1)
                )
            if not active and not title:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Existing worker is busy; replacement refused")
            time.sleep(0.2)
        for process in candidates.values():
            try:
                if not any(parent.pid in candidates for parent in process.parents()):
                    stop_tree(process)
            except psutil.NoSuchProcess:
                pass
    finally:
        engine.dispose()
