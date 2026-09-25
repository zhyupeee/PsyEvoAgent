import asyncio
import importlib
import logging
import sys

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, load_settings
from app.main import Health, create_app
from app.worker import run_worker
from tests.fakes import FakeProvider


def test_api_lifecycle_health_and_unconfigured_storage(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    async def check() -> None:
        app = create_app(Settings(environment="test"))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as client:
                assert (await client.get("/api/v1/health")).json() == {
                    "status": "ok",
                    "stage": "S1-STEP02",
                }
                assert (await client.post("/api/v1/sessions", json={})).status_code == 503

    asyncio.run(check())
    assert [record.message for record in caplog.records if record.name == "uvicorn.error"] == [
        "api.started",
        "api.stopped",
    ]


def test_import_has_no_worker_or_consumer_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    # Poison the module: importing a worker from the API must fail this regression.
    monkeypatch.setitem(sys.modules, "app.worker", None)
    monkeypatch.setitem(sys.modules, "app.run_worker", None)
    import app.main

    importlib.reload(app.main)
    application = app.main.create_app(Settings(environment="test"))
    assert application.state.engine is None
    assert "/api/v1/runs/{run_id}/start" in application.openapi()["paths"]
    assert application.state.settings.support_mode == "disabled"
    assert application.state.run_connections.counts == {}


def test_settings_fail_closed_without_echoing_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSYEVO_ENV", "test")
    assert load_settings().environment == "test"
    with pytest.raises(ValidationError):
        load_settings({"PSYEVO_ENV": "production"})
    with pytest.raises(ValidationError):
        Settings.model_validate({"environment": "test", "model_api_key": "synthetic-only"})


def test_health_contract_rejects_extra_fields_and_wrong_types() -> None:
    for invalid in [
        {},
        {"status": "ok"},
        {"stage": "S1-STEP02"},
        {"status": 200, "stage": "S1-STEP02"},
        {"status": "ok", "stage": "S1-STEP02", "owner_id": "synthetic-other"},
    ]:
        with pytest.raises(ValidationError):
            Health.model_validate(invalid)


def test_health_openapi_requires_both_fields() -> None:
    schema = create_app(Settings(environment="test")).openapi()["components"]["schemas"]["Health"]
    assert schema["required"] == ["status", "stage"]


def test_fake_provider_is_repeatable_and_errors_propagate() -> None:
    async def check() -> None:
        provider = FakeProvider('{"status":"ok","stage":"S1-STEP02"}')
        for _ in range(2):
            assert Health.model_validate_json(await provider.invoke()).status == "ok"
        assert provider.calls == 2
        broken = FakeProvider('{"status":200}')
        with pytest.raises(ValidationError):
            Health.model_validate_json(await broken.invoke())
        failed = FakeProvider(TimeoutError("synthetic timeout"))
        with pytest.raises(TimeoutError):
            await failed.invoke()
        assert failed.calls == 1

    asyncio.run(check())


def test_worker_cancellation_cleans_up(capsys: pytest.CaptureFixture[str]) -> None:
    async def check() -> None:
        task = asyncio.create_task(run_worker(asyncio.Event()))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(check())
    assert capsys.readouterr().out.splitlines() == [
        "worker.started consumers=0",
        "worker.stopped consumers=0",
    ]
