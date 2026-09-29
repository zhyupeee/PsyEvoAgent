"""Explicit STEP08 internal-stream adapter; never publishes provider chunks."""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Any, Literal

import httpx2 as httpx
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, BaseMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, OpenAI

from app.config import Settings
from app.support import Frozen, ProviderFailure


class LiveProfile(Frozen):
    provider: Literal["hybgzs-compatible"] = "hybgzs-compatible"
    model_ref: str
    base_url: str
    adapter_version: str = version("langchain-openai")
    parameters: tuple[tuple[str, str], ...] = (("sdk_retries", "0"),)
    allowed_tasks: tuple[Literal["support"], ...] = ("support",)
    region: Literal["unknown"] = "unknown"
    retention: Literal["unknown"] = "unknown"
    price_version: Literal["unknown"] = "unknown"
    currency: Literal["unknown"] = "unknown"
    structured_method: Literal["json-text+pydantic"] = "json-text+pydantic"


@dataclass
class StreamObservation:
    chunks: int = 0
    first_chunk_ms: int | None = None
    finished: bool = False
    locally_closed: bool = False
    protocol_error: str | None = None
    duplicate_usage_reports: int = 0
    usage_reports: list[dict[str, int]] = field(default_factory=list)


class CheckedChatOpenAI(ChatOpenAI):
    """The locked adapter drops streaming refusal; preserve its presence, not its text."""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type[BaseMessageChunk],
        base_generation_info: dict[str, Any] | None,
    ) -> ChatGenerationChunk | None:
        choices = chunk.get("choices", [])
        if len(choices) > 1 or any(choice.get("index") != 0 for choice in choices):
            raise ProviderFailure("provider_error")
        if any(choice.get("delta") is None for choice in choices):
            # The SDK discards null-delta chunks, including any conflicting usage.
            raise ProviderFailure("provider_error")
        result = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if result is not None and any(
            (choice.get("delta") or {}).get("refusal") for choice in chunk.get("choices", [])
        ):
            result.message.additional_kwargs["refusal"] = True
        if result is not None and any(
            (choice.get("delta") or {}).get("tool_calls")
            or (choice.get("delta") or {}).get("function_call")
            for choice in choices
        ):
            # Malformed tool fragments can be discarded by the SDK parser.
            result.message.additional_kwargs["forbidden_tool"] = True
        usage = chunk.get("usage")
        if result is not None and usage is not None:
            # The SDK fills absent counters with zero. Missing counters remain unknown here.
            counters = [
                usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            ]
            if any(type(value) is not int or value < 0 for value in counters):
                result.message.additional_kwargs["invalid_usage"] = True
        return result


class InternalStreamProvider:
    """Bounded private buffer behind the existing graph's ainvoke boundary.

    Tools, refusal and non-text blocks are rejected before candidate parsing.
    The whole response must still pass the graph's schema/usage/output policy.
    No callbacks or provider metadata become public events or persisted text.
    """

    cache = False
    callbacks = None
    verbose = False
    sleep = 0

    def __init__(self, model: ChatOpenAI) -> None:
        if model.max_retries != 0 or model.cache is not False or model.callbacks or model.verbose:
            raise ValueError("Live adapter requires disabled retries, caches and callbacks")
        self.model = model
        self.observation = StreamObservation()

    async def ainvoke(self, messages: list[BaseMessage], *, config: dict[str, object]) -> AIMessage:
        if config != {"callbacks": []}:
            raise ValueError("External callbacks are disabled")
        started = time.monotonic()
        merged: AIMessageChunk | None = None
        size = 0
        partial = False
        finished = False
        terminal_usage: tuple[int, int, int] | None = None
        self.observation = StreamObservation()
        try:
            source = self.model.astream(messages, config={"callbacks": []})
            if not isinstance(source, AsyncGenerator):
                raise ProviderFailure("provider_error")
            async with aclosing(source) as stream:
                async for chunk in stream:
                    self.observation.chunks += 1
                    if self.observation.first_chunk_ms is None:
                        self.observation.first_chunk_ms = int((time.monotonic() - started) * 1000)
                    if not isinstance(chunk, AIMessageChunk) or not isinstance(chunk.content, str):
                        raise ProviderFailure("provider_error", partial=partial)
                    partial = partial or bool(chunk.content)
                    if (
                        chunk.tool_call_chunks
                        or chunk.tool_calls
                        or chunk.invalid_tool_calls
                        or chunk.additional_kwargs.get("tool_calls")
                        or chunk.additional_kwargs.get("function_call")
                        or chunk.additional_kwargs.get("forbidden_tool")
                    ):
                        raise ProviderFailure("provider_error", partial=partial)
                    if chunk.additional_kwargs.get("refusal"):
                        raise ProviderFailure("refusal", partial=partial)
                    if chunk.additional_kwargs.get("invalid_usage"):
                        raise ProviderFailure("provider_error", partial=partial)
                    finish = chunk.response_metadata.get("finish_reason")
                    if finished and (chunk.content or finish is not None):
                        self.observation.protocol_error = "data_after_finish"
                        raise ProviderFailure("provider_error", partial=partial)
                    if chunk.usage_metadata is not None:
                        counters = (
                            chunk.usage_metadata["input_tokens"],
                            chunk.usage_metadata["output_tokens"],
                            chunk.usage_metadata["total_tokens"],
                        )
                        if len(self.observation.usage_reports) < 3:
                            self.observation.usage_reports.append(
                                {
                                    "input_tokens": chunk.usage_metadata["input_tokens"],
                                    "output_tokens": chunk.usage_metadata["output_tokens"],
                                    "total_tokens": chunk.usage_metadata["total_tokens"],
                                }
                            )
                        if not (finished or finish is not None):
                            self.observation.protocol_error = "usage_before_finish"
                            raise ProviderFailure("provider_error", partial=partial)
                        if terminal_usage is not None:
                            if counters != terminal_usage:
                                self.observation.protocol_error = "conflicting_usage"
                                raise ProviderFailure("provider_error", partial=partial)
                            self.observation.duplicate_usage_reports += 1
                            # Some compatible gateways repeat terminal usage. Do not sum it twice.
                            chunk = chunk.model_copy(update={"usage_metadata": None})
                        else:
                            terminal_usage = counters
                    finished = finished or finish is not None
                    content = chunk.content
                    if not isinstance(content, str):
                        raise ProviderFailure("provider_error", partial=partial)
                    size += len(content.encode("utf-8"))
                    # Limits stop the call; they never force private content to be published.
                    if size > 32768 or self.observation.chunks > 4096:
                        raise ProviderFailure("truncated", partial=partial)
                    merged = chunk if merged is None else merged + chunk
            if merged is None or merged.response_metadata.get("finish_reason") is None:
                raise ProviderFailure("truncated", partial=partial)
            self.observation.finished = True
            return AIMessage(
                content=merged.content,
                usage_metadata=merged.usage_metadata,
                response_metadata={"finish_reason": merged.response_metadata["finish_reason"]},
            )
        except asyncio.CancelledError:
            raise
        except APIStatusError as exc:
            kind = {
                429: "rate_limit",
                401: "provider_authentication",
                403: "provider_authentication",
                404: "provider_model_unavailable",
            }.get(exc.status_code, "provider_error")
            logging.getLogger("uvicorn.error").warning(
                "provider.http_error status=%d", exc.status_code
            )
            raise ProviderFailure(kind, partial=partial) from None
        except APIConnectionError:
            raise ProviderFailure("transient", partial=partial) from None
        except ValueError as exc:
            kind = (
                "provider_address_blocked"
                if str(exc) == "provider_address_blocked"
                else "provider_error"
            )
            raise ProviderFailure(kind, partial=partial) from None
        finally:
            self.observation.locally_closed = True


@asynccontextmanager
async def open_provider(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> AsyncIterator[InternalStreamProvider]:
    if (
        not (settings.live_probe_enabled or settings.support_mode == "live")
        or not settings.provider_api_key
        or not settings.provider_api_key.get_secret_value().strip()
    ):
        raise ValueError("Live probe requires explicit enablement and a nonempty provider key")
    # Explicit clients prevent ambient OpenAI credentials/proxies, redirects and SDK retries.
    timeout = httpx.Timeout(settings.provider_deadline_seconds, connect=10)
    if settings.provider_custom_endpoint and transport is None:
        from app.provider_network import PublicTransport

        transport = PublicTransport(settings.provider_base_url)
    with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as sync_http:
        async with httpx.AsyncClient(
            timeout=timeout, trust_env=False, follow_redirects=False, transport=transport
        ) as async_http:
            # Spell out SDK arguments so credentials never enter an untyped kwargs bridge.
            sync_sdk = OpenAI(
                api_key=settings.provider_api_key.get_secret_value(),
                base_url=settings.provider_base_url,
                organization="",
                project="",
                max_retries=0,
                http_client=sync_http,
            )
            async_sdk = AsyncOpenAI(
                api_key=settings.provider_api_key.get_secret_value(),
                base_url=settings.provider_base_url,
                organization="",
                project="",
                max_retries=0,
                http_client=async_http,
            )
            yield InternalStreamProvider(
                CheckedChatOpenAI(
                    model=settings.provider_model,
                    api_key=settings.provider_api_key,
                    base_url=settings.provider_base_url,
                    client=sync_sdk.chat.completions,
                    async_client=async_sdk.chat.completions,
                    max_retries=0,
                    max_completion_tokens=settings.provider_max_output_tokens,
                    extra_body={"max_tokens": settings.provider_max_output_tokens},
                    timeout=settings.provider_deadline_seconds,
                    cache=False,
                    callbacks=[],
                    verbose=False,
                    stream_usage=True,
                    use_responses_api=False,
                )
            )
