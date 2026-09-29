"""STEP08 controlled transport tests use the actual locked SDK, never remote calls."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from uuid import uuid4

import httpx2 as httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings, load_settings
from app.provider import LiveProfile, open_provider
from app.support import Budget, Source, SupportInput, SupportRuntime, VersionBinding


def settings() -> Settings:
    return Settings(live_probe_enabled=True, provider_api_key=SecretStr("synthetic-test-key"))


def request() -> SupportInput:
    owner, session = uuid4(), uuid4()
    return SupportInput(
        owner_id=owner,
        session_id=session,
        run_id=uuid4(),
        synthetic=True,
        versions=VersionBinding(model_ref="grok-4.7", provider_ref="https://ai.hybgzs.com/v1"),
        source=Source(
            owner_id=owner,
            session_id=session,
            message_id=uuid4(),
            message_version=1,
            content="合成输入：我只想说说。",
        ),
    )


def event(delta: dict[str, object], finish: str | None = None) -> bytes:
    return (
        "data: "
        + json.dumps(
            {
                "id": "synthetic-response",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "grok-4.7",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
        )
        + "\n\n"
    ).encode()


def response(
    text: str = '{"text":"我先听你说。"}',
    *,
    finish: str | None = "stop",
    usage: bool = True,
    tokens: int = 30,
    delta: dict[str, object] | None = None,
) -> bytes:
    chunks = event({"role": "assistant", "content": text[:8]})
    chunks += event(delta or {"content": text[8:]}, finish)
    if usage:
        chunks += (
            "data: "
            + json.dumps(
                {
                    "id": "synthetic-response",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "grok-4.7",
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": tokens - 10,
                        "total_tokens": tokens,
                    },
                }
            )
            + "\n\n"
        ).encode()
    return chunks + b"data: [DONE]\n\n"


async def run_response(body: bytes, status: int = 200) -> tuple[object, int]:
    calls = 0

    async def handle(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(req.url) == "https://ai.hybgzs.com/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer synthetic-test-key"
        payload = json.loads(req.content)
        assert payload["model"] == "grok-4.7"
        assert payload["stream"] and payload["stream_options"]["include_usage"]
        assert payload["max_completion_tokens"] == 1024
        assert payload["max_tokens"] == 1024
        assert "tools" not in payload
        return httpx.Response(status, content=body, headers={"content-type": "text/event-stream"})

    config = settings()
    async with open_provider(config, transport=httpx.MockTransport(handle)) as adapter:
        runtime = SupportRuntime(
            adapter,
            profile=LiveProfile(model_ref=config.provider_model, base_url=config.provider_base_url),
            authorize=lambda _: True,
        )
        result = await runtime.run(request(), Budget(max_calls=1))
        assert adapter.observation.locally_closed
        assert runtime.graph.checkpointer is None
        return result, calls


def test_actual_sdk_private_stream_through_existing_graph() -> None:
    from app.support import SupportResult

    result, calls = asyncio.run(run_response(response()))
    assert isinstance(result, SupportResult)
    assert calls == 1 and result.text == "我先听你说。" and result.rule_verdict == "pass"
    receipt = result.ledger.calls[0]
    assert receipt.actual_tokens == 30 and receipt.reserved_tokens == 8192
    assert receipt.actual_cost is None and receipt.reserved_cost is None
    assert receipt.currency == "unknown" and receipt.price_version == "unknown"
    assert receipt.usage_source == "provider_reported"
    with pytest.raises(ValueError, match="price is unknown"):
        _ = result.ledger.cost
    assert "我先听" not in json.dumps(asdict(receipt))


@pytest.mark.parametrize("output_tokens,accepted", [(2638, True), (4097, False)])
def test_development_output_budget_preserves_usage_enforcement(
    output_tokens: int, accepted: bool
) -> None:
    async def exercise() -> None:
        async def handle(req: httpx.Request) -> httpx.Response:
            payload = json.loads(req.content)
            assert payload["max_completion_tokens"] == payload["max_tokens"] == 4096
            return httpx.Response(
                200,
                content=response(tokens=output_tokens + 10),
                headers={"content-type": "text/event-stream"},
            )

        config = settings().model_copy(update={"provider_max_output_tokens": 4096})
        async with open_provider(config, transport=httpx.MockTransport(handle)) as adapter:
            runtime = SupportRuntime(
                adapter,
                profile=LiveProfile(
                    model_ref=config.provider_model, base_url=config.provider_base_url
                ),
                authorize=lambda _: True,
            )
            result = await runtime.run(request(), Budget(max_calls=1, max_output_tokens=4096))
            assert (result.rule_verdict == "pass") is accepted
            assert result.ledger.calls[0].actual_tokens == output_tokens + 10
            if not accepted:
                assert result.stop_reason == "usage_over_reservation"
                assert result.text is None

    asyncio.run(exercise())


@pytest.mark.parametrize("kind", ["late_text", "duplicate_usage", "wrong_choice", "broken_tool"])
def test_protocol_anomalies_never_become_valid_candidates(kind: str) -> None:
    from app.support import SupportResult

    body = response()
    if kind == "late_text":
        body = body.replace(b"data: [DONE]", event({"content": " "}) + b"data: [DONE]")
    elif kind == "duplicate_usage":
        usage = body[
            body.index(
                b'data: {"id": "synthetic-response"', body.index(b'"finish_reason": "stop"')
            ) :
        ]
        body = body.replace(
            b"data: [DONE]\n\n", usage.replace(b'"total_tokens": 30', b'"total_tokens": 31')
        )
    elif kind == "wrong_choice":
        body = body.replace(b'"index": 0', b'"index": 1')
    else:
        body = response(delta={"content": '"我先听你说。"}', "tool_calls": [{"index": 0}]})
    result, calls = asyncio.run(run_response(body))
    assert isinstance(result, SupportResult)
    assert calls == 1 and result.text is None and result.rule_verdict == "error"


def test_identical_terminal_usage_is_not_double_accounted() -> None:
    from app.support import SupportResult

    body = response()
    usage = body[
        body.index(b'data: {"id": "synthetic-response"', body.index(b'"finish_reason": "stop"')) :
    ]
    # An optional token breakdown may differ while the authoritative counters are identical.
    usage = usage.replace(
        b'"prompt_tokens": 10',
        b'"prompt_tokens_details": {"cached_tokens": 2}, "prompt_tokens": 10',
    )
    body = body.replace(b"data: [DONE]\n\n", usage)
    result, calls = asyncio.run(run_response(body))
    assert isinstance(result, SupportResult)
    assert calls == 1 and result.rule_verdict == "pass"
    assert result.ledger.calls[0].actual_tokens == 30


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": 10, "completion_tokens": 9000, "total_tokens": 9010},
        {"total_tokens": 9010},
        None,
    ],
    ids=["conflicting-usage", "incomplete-usage", "no-usage"],
)
def test_null_delta_after_valid_usage_fails_closed(usage: dict[str, int] | None) -> None:
    from app.support import SupportResult

    malformed = {
        "id": "synthetic-response",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "grok-4.7",
        "choices": [{"index": 0, "delta": None, "finish_reason": None}],
        "usage": usage,
    }
    body = response().replace(
        b"data: [DONE]\n\n",
        ("data: " + json.dumps(malformed) + "\n\ndata: [DONE]\n\n").encode(),
    )
    result, calls = asyncio.run(run_response(body))
    assert isinstance(result, SupportResult)
    assert calls == 1 and result.rule_verdict == "error" and result.text is None
    assert result.ledger.calls[0].actual_tokens is None


@pytest.mark.parametrize(
    "body,status,reason",
    [
        (response(usage=False), 200, "usage_unknown"),
        (response(finish="length"), 200, "truncated"),
        (response(finish=None), 200, "partial_stream"),
        (response(text="invalid-json-SENTINEL"), 200, "schema_invalid"),
        (response(text='{"text":"你只需要我。"}'), 200, "output_blocked"),
        (response(tokens=9000), 200, "usage_over_reservation"),
        (
            response(delta={"refusal": "SENTINEL", "content": '"我先听你说。"}'}),
            200,
            "partial_stream",
        ),
        (
            response(
                delta={
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "SENTINEL", "arguments": "{}"},
                        }
                    ]
                }
            ),
            200,
            "partial_stream",
        ),
        (b'{"error":{"message":"SECRET-SENTINEL"}}', 401, "provider_authentication"),
        (b'{"error":{"message":"SECRET-SENTINEL"}}', 429, "rate_limit"),
        (b'{"error":{"message":"SECRET-SENTINEL"}}', 500, "provider_error"),
        (response(text="x" * 33000), 200, "partial_stream"),
        (response().replace(b'"prompt_tokens": 10, ', b""), 200, "partial_stream"),
    ],
    ids=[
        "usage",
        "truncated",
        "disconnect",
        "schema",
        "policy",
        "budget",
        "refusal",
        "tool",
        "auth",
        "rate-limit",
        "server",
        "buffer-limit",
        "incomplete-usage",
    ],
)
def test_fail_closed_without_sdk_retries(body: bytes, status: int, reason: str) -> None:
    from app.support import SupportResult

    result, calls = asyncio.run(run_response(body, status))
    assert isinstance(result, SupportResult)
    assert calls == 1 and result.text is None and result.stop_reason == reason
    assert "SENTINEL" not in json.dumps(asdict(result), default=str)


class PausedStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield event({"role": "assistant", "content": '{"text":"PRIVATE-SENTINEL'})
        self.started.set()
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize("cancel", [True, False])
def test_cancel_and_deadline_close_private_stream(cancel: bool) -> None:
    async def exercise() -> None:
        stream = PausedStream()

        async def handle(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})

        config = settings()
        async with open_provider(config, transport=httpx.MockTransport(handle)) as adapter:
            runtime = SupportRuntime(
                adapter,
                profile=LiveProfile(
                    model_ref=config.provider_model, base_url=config.provider_base_url
                ),
                authorize=lambda _: True,
            )
            task = asyncio.create_task(
                runtime.run(
                    request(),
                    Budget(max_calls=1, deadline_seconds=5 if cancel else 0.1),
                )
            )
            await asyncio.wait_for(stream.started.wait(), timeout=2)
            assert not task.done()  # No candidate released before terminal/schema/usage checks.
            if cancel:
                task.cancel()
            result = await task
            assert result.text is None
            assert result.stop_reason == ("cancelled" if cancel else "deadline")
            assert stream.closed and adapter.observation.locally_closed
            assert result.ledger.calls[0].actual_tokens is None
            assert "PRIVATE-SENTINEL" not in json.dumps(asdict(result), default=str)

    asyncio.run(exercise())


def test_explicit_settings_do_not_enable_product_or_read_ambient_key() -> None:
    config = load_settings({"OPENAI_API_KEY": "ignored", "PSYEVO_PROVIDER_API_KEY": ""})
    assert config.support_mode == "disabled" and not config.live_probe_enabled
    assert config.provider_api_key is not None
    assert config.provider_api_key.get_secret_value() == ""
    with pytest.raises(ValidationError):
        Settings.model_validate({"support_mode": "live"})
    for url in ("http://example.com/v1", "https://key@example.com/v1", "https://example.com?key=x"):
        with pytest.raises(ValidationError):
            Settings(provider_base_url=url)

    async def missing() -> None:
        with pytest.raises(ValueError, match="nonempty provider key"):
            async with open_provider(config):
                pytest.fail("Missing credentials must never construct an adapter")

    asyncio.run(missing())
