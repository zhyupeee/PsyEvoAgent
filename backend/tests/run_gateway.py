"""Explicit synthetic gateway fixtures, never registered in app.main."""

from fastapi import FastAPI

from app.api import DB, Auth, owned
from app.config import load_settings
from app.main import create_app
from app.models import Run
from app.runs import emit, execution


def create_gateway_app() -> FastAPI:
    settings = load_settings()
    if settings.environment != "test" or settings.support_mode != "fake":
        raise RuntimeError("Isolated fake gateway only")
    app = create_app(settings)

    @app.post("/api/v1/checks/runs/{run_id}/expire-cursor", status_code=204)
    def expire(run_id: str, db: DB, auth: Auth) -> None:
        run = owned(db, Run, run_id, auth.owner_id)
        ex = execution(db, run)
        assert ex is not None and run.status == "completed"
        for _ in range(130):
            emit(db, run, ex, "run.completed", {"synthetic_retention_probe": True})

    return app
