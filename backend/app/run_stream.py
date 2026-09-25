"""Bounded native FastAPI SSE, with fresh authorization for each published event."""

import asyncio
import re
import threading
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, format_sse_event
from starlette.types import Message, Receive, Scope, Send

from app.api import DB, APIError, Auth
from app.runs import authorized_event

router = APIRouter(prefix="/api/v1")
SEND_TIMEOUT = 2.0
HEARTBEAT_SECONDS = 1.0
MAX_EVENT_BYTES = 32768


class Connections:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counts: dict[str, int] = {}

    def acquire(self, owner: str) -> None:
        with self.lock:
            if self.counts.get(owner, 0) >= 2:
                raise APIError(429, "stream_limit")
            self.counts[owner] = self.counts.get(owner, 0) + 1

    def release(self, owner: str) -> None:
        with self.lock:
            count = self.counts.get(owner, 0) - 1
            if count > 0:
                self.counts[owner] = count
            else:
                self.counts.pop(owner, None)


class BoundedEvents(EventSourceResponse):
    async def stream_response(self, send: Send) -> None:
        async def bounded(message: Message) -> None:
            async with asyncio.timeout(SEND_TIMEOUT):
                await send(message)

        try:
            await super().stream_response(bounded)
        except TimeoutError:
            # Subscription only. The run retains its original budget/deadline.
            return


@router.get("/runs/{run_id}/events")
def events(
    run_id: str, request: Request, db: DB, auth: Auth, after_event_id: str | None = None
) -> EventSourceResponse:
    header = request.headers.get("last-event-id")
    if header is not None and after_event_id is not None and header != after_event_id:
        raise APIError(422, "cursor_conflict")
    value = after_event_id if after_event_id is not None else (header or "0")
    if not re.fullmatch(r"0|[1-9][0-9]{0,9}", value):
        raise APIError(422, "invalid_cursor")
    owner, identity_id, cursor = auth.owner_id, auth.id, int(value)
    # Function-scoped identity transaction must end before independent replay transactions.
    db.commit()
    engine = request.app.state.engine
    authorized_event(engine, owner, identity_id, run_id, cursor)
    connections: Connections = request.app.state.run_connections
    connections.acquire(owner)

    async def content() -> AsyncIterator[bytes]:
        current_cursor = cursor
        while True:
            try:
                data, done, _ = await asyncio.to_thread(
                    authorized_event, engine, owner, identity_id, run_id, current_cursor
                )
            except APIError:
                return  # Headers already sent: close; client queries authorized status.
            if data is not None:
                # No producer queue: at most one bounded event is held for socket send.
                import json

                payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
                frame = format_sse_event(
                    data_str=payload.decode(), event=str(data["type"]), id=str(data["event_id"])
                )
                if len(frame) > MAX_EVENT_BYTES:
                    return
                current_cursor = int(str(data["event_id"]))
                yield frame
            elif done:
                return
            else:
                yield b": heartbeat\n\n"
                await asyncio.sleep(HEARTBEAT_SECONDS)

    class Subscription(BoundedEvents):
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            try:
                await super().__call__(scope, receive, send)
            finally:
                connections.release(owner)

    return Subscription(content(), headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})
