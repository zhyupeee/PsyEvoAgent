"""Transport bounds, independent of synthetic PostgreSQL business acceptance."""

import asyncio
import threading
from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr
from sqlalchemy import event
from starlette.types import Message

from app.api import APIError
from app.config import Settings
from app.database import make_engine
from app.run_stream import BoundedEvents, Connections
from app.run_worker import consume
from app.runs import merge_intervals


def test_slow_transport_stops_without_prefetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.run_stream.SEND_TIMEOUT", 0.01)
    produced: list[int] = []

    async def check() -> None:
        async def body() -> AsyncIterator[bytes]:
            for number in range(100):
                produced.append(number)
                yield b"data: synthetic\n\n"

        async def stalled(message: Message) -> None:
            if message["type"] == "http.response.body":
                await asyncio.Event().wait()

        await BoundedEvents(body()).stream_response(stalled)

    asyncio.run(check())
    assert produced == [0]


def test_stream_connection_limit_and_release() -> None:
    connections = Connections()
    connections.acquire("a")
    connections.acquire("a")
    connections.acquire("b")
    with pytest.raises(APIError) as caught:
        connections.acquire("a")
    assert caught.value.status == 429
    connections.release("a")
    connections.acquire("a")
    connections.release("a")
    connections.release("a")
    assert "a" not in connections.counts


def test_interval_union_and_fake_mode_closed_by_default() -> None:
    assert merge_intervals([(0, 100), (10, 50), (90, 120), (200, 250)]) == 170
    assert Settings().support_mode == "disabled"
    with pytest.raises(ValueError, match="isolated"):
        Settings(support_mode="fake")


def test_worker_shutdown_drains_bounded_execution_before_pool_disposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "postgresql+psycopg://synthetic:synthetic@127.0.0.1:9/psyevo_synthetic_check_shutdown"
    engine = make_engine(url)  # No connection is opened by the patched consumer.
    started, release = threading.Event(), threading.Event()
    order: list[str] = []

    def work(_: object) -> bool:
        started.set()
        assert release.wait(timeout=2)
        order.append("finished")
        return True

    event.listen(engine, "engine_disposed", lambda _: order.append("disposed"))
    monkeypatch.setattr("app.run_worker.execute_one", work)
    monkeypatch.setattr("app.database.make_engine", lambda _: engine)
    monkeypatch.setattr(
        "app.config.load_settings",
        lambda: Settings(environment="test", support_mode="fake", database_url=SecretStr(url)),
    )

    async def check() -> None:
        worker = asyncio.create_task(consume(asyncio.Event()))
        assert await asyncio.to_thread(started.wait, 1)
        worker.cancel()
        await asyncio.sleep(0)
        assert not worker.done() and order == []
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await worker

    asyncio.run(check())
    assert order == ["finished", "disposed"]
