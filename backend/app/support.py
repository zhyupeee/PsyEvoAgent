"""STEP04 synthetic-only single Support graph; no API, persistence or consumers.

The caller supplies trusted identity/source snapshots. This is not an HTTP DTO.
Live adapters remain closed until provider/data/price capabilities are verified.
"""

import asyncio
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from importlib.metadata import version
from typing import Literal, TypedDict
from uuid import UUID, uuid4

from langchain_core.globals import get_debug, get_verbose
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Mode = Literal["listen", "clarify", "explore", "action", "close", "support_route"]
Capability = Literal["documented", "tested", "unsupported", "unknown"]


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VersionBinding(Frozen):
    policy_version: Literal["support-policy/1"] = "support-policy/1"
    assessor_version: Literal["disabled"] = "disabled"
    evaluator_version: Literal["behavior-rules/1"] = "behavior-rules/1"
    graph_version: Literal["support-graph/1"] = "support-graph/1"
    model_ref: Literal["local-scripted/1"] = "local-scripted/1"
    schema_version: Literal["support-runtime/1"] = "support-runtime/1"
    experiment_config_version: Literal["experiment-defaults/1"] = "experiment-defaults/1"


class ModelProfile(Frozen):
    provider: Literal["local-fake"] = "local-fake"
    model_ref: Literal["local-scripted/1"] = "local-scripted/1"
    adapter_version: str = Field(default_factory=lambda: version("langchain-core"))
    parameters: tuple[tuple[str, str], ...] = (("sdk_retries", "0"),)
    region: Literal["local"] = "local"
    retention: Literal["in-process-synthetic-only"] = "in-process-synthetic-only"
    allowed_tasks: tuple[Literal["support"], ...] = ("support",)
    structured_method: Literal["json-text+pydantic"] = "json-text+pydantic"
    text: Capability = "unknown"
    structured_output: Capability = "unknown"
    tools_with_structured_output: Capability = "unsupported"
    streaming: Capability = "unsupported"
    usage: Capability = "unknown"
    cancellation: Capability = "unknown"
    retries: Capability = "unknown"
    evidence_ref: str | None = None
    price_version: Literal["fake-price/1"] = "fake-price/1"
    currency: Literal["SYNTHETIC"] = "SYNTHETIC"


class Source(Frozen):
    owner_id: UUID
    session_id: UUID
    message_id: UUID
    message_version: int = Field(gt=0, strict=True)
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value


class SupportInput(Frozen):
    owner_id: UUID
    session_id: UUID
    run_id: UUID
    source: Source
    preference: Literal["listen", "explore"] = "listen"
    synthetic: Literal[True]
    versions: VersionBinding = Field(default_factory=VersionBinding)


class Budget(Frozen):
    max_calls: int = Field(default=2, ge=1, le=2, strict=True)
    max_tokens: int = Field(default=8192, ge=1, le=8192, strict=True)
    max_output_tokens: int = Field(default=1024, ge=1, le=1024, strict=True)
    max_cost: Decimal = Field(default=Decimal("8.192"), gt=0, le=Decimal("8.192"))
    deadline_seconds: float = Field(default=10, gt=0, le=10, allow_inf_nan=False)


class Candidate(Frozen):
    text: str = Field(min_length=1, max_length=4000)


@dataclass
class CallReceipt:
    run_id: str
    request_id: str
    attempt: int
    model_ref: str
    versions: dict[str, str]
    reserved_tokens: int
    reserved_cost: Decimal
    role: str = "support"
    price_version: str = "fake-price/1"
    currency: str = "SYNTHETIC"
    actual_tokens: int | None = None
    actual_cost: Decimal | None = None
    usage_source: str = "unknown"
    status: str = "reserved"
    elapsed_ms: int = 0


@dataclass
class Ledger:
    calls: list[CallReceipt] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(
            c.actual_tokens if c.actual_tokens is not None else c.reserved_tokens
            for c in self.calls
        )

    @property
    def cost(self) -> Decimal:
        return sum(
            (c.actual_cost if c.actual_cost is not None else c.reserved_cost for c in self.calls),
            Decimal(0),
        )


@dataclass(frozen=True)
class SupportResult:
    mode: Mode
    text: str | None
    stop_reason: str | None
    rule_verdict: Literal["pass", "block", "error"]
    ledger: Ledger
    versions: VersionBinding
    allowed_tools: tuple[str, ...] = ()
    semantic_score: None = None


class ProviderFailure(Exception):
    """Sanitized fake-adapter error classification; never logs exception text."""

    def __init__(self, kind: str, *, retry_after: float = 0, partial: bool = False):
        if kind not in ("rate_limit", "transient", "refusal", "truncated", "provider_error"):
            kind = "provider_error"
        super().__init__(kind)
        self.kind = kind
        self.retry_after = retry_after
        self.partial = partial


class ControlledStop(Exception):
    pass


def select_mode(request: SupportInput) -> Mode:
    text = request.source.content
    if any(word in text for word in ("伤害自己", "威胁", "求助", "不安全")):
        return "support_route"
    if any(word in text for word in ("结束", "先到这里")):
        return "close"
    if any(word in text for word in ("只想", "不需要办法", "不要再建议", "不想")):
        return "listen"
    if any(word in text for word in ("下一步", "有什么办法")):
        return "action"
    if any(word in text for word in ("一起想", "愿意", "分析")):
        return "explore"
    if any(word in text for word in ("讨厌我", "梳理", "为什么", "什么意思")):
        return "clarify"
    return request.preference


# Deliberately finite rule baseline. Passing these rules is not semantic approval.
BLOCK_RULES = (
    r"只需要我|不要再信任|只有我.*(理解|懂)|不许离开",
    r"辜负我|你欠我|离开会让我|必须再陪我",
    r"确诊你|你患有.*疾病|不需要专业评估",
    r"(建议|应该|可以|用).*伤害(自己|他人)|自伤.*解决",
    r"我记得你|完成全部问卷|先填写.*问卷",
    r"肯定讨厌你|判断完全正确|只是你想太多",
    r"我替你决定|已经.*(发给|通知|联系|保存)|我已.*(联系|转介|保存)",
    r"不开画像就不能|必须现在|先玩小游戏就好了|肯定仍有效",
    r"\d{3,}",  # No verified resource numbers are available in this slice.
)


def output_policy(text: str, mode: Mode) -> bool:
    normalized = "".join(text.split())
    if not normalized or any(re.search(rule, normalized) for rule in BLOCK_RULES):
        return False
    if mode == "listen" and re.search(r"你(还是)?应该|你必须|按我列|建议你", normalized):
        return False
    return True


SYSTEM = (
    "你是单一Support。仅回应当前消息，不编历史或第三方动机；尊重拒绝与结束，"
    "不得诊断、关系操控、危险建议、编造联系方式或声称已执行操作。没有工具。"
    '只返回JSON对象 {"text":"回应"}。当前方式：'
)


class GraphState(TypedDict):
    request: SupportInput
    mode: Mode
    budget: Budget
    deadline: float
    ledger: Ledger
    candidate: str | None
    stop_reason: str | None
    verdict: Literal["pass", "block", "error"]


class SupportRuntime:
    def __init__(
        self,
        model: FakeMessagesListChatModel,
        *,
        profile: ModelProfile,
        authorize: Callable[[SupportInput], bool],
        sdk_retries: int = 0,
    ) -> None:
        if not isinstance(model, FakeMessagesListChatModel) or sdk_retries != 0:
            raise ValueError("Only local fake adapters with zero SDK retries are enabled")
        if profile.adapter_version != version("langchain-core"):
            raise ValueError("Adapter version mismatch")
        if model.cache is not False or model.callbacks or model.verbose:
            raise ValueError("Shared caches and callbacks are not enabled")
        if get_debug() or get_verbose() or profile.parameters != (("sdk_retries", "0"),):
            raise ValueError("Unmetered retries and verbose traces are not enabled")
        if profile.allowed_tasks != ("support",) or model.sleep:
            raise ValueError("Support requires a cancellable local fake adapter")
        self.model = model
        self.profile = profile
        self.authorize = authorize
        graph = StateGraph(GraphState)
        graph.add_node("meta", self._meta)
        graph.add_node("support", self._support)
        graph.add_node("output_policy", self._output)
        graph.add_edge(START, "meta")
        graph.add_edge("meta", "support")
        graph.add_edge("support", "output_policy")
        graph.add_edge("output_policy", END)
        self.graph = graph.compile()

    def _check(self, state: GraphState) -> None:
        request = state["request"]
        try:
            available = self.authorize(request)
        except Exception:
            available = False
        if (
            request.owner_id != request.source.owner_id
            or request.session_id != request.source.session_id
            or not available
        ):
            raise ControlledStop("source_unavailable")
        if time.monotonic() >= state["deadline"]:
            raise ControlledStop("deadline")

    def _meta(self, state: GraphState) -> dict[str, object]:
        try:
            self._check(state)
        except ControlledStop as exc:
            return {"stop_reason": str(exc)}
        return {"mode": select_mode(state["request"])}

    async def _support(self, state: GraphState) -> dict[str, object]:
        if state["stop_reason"]:
            return {}
        budget, ledger = state["budget"], state["ledger"]
        messages = [
            SystemMessage(SYSTEM + state["mode"]),
            HumanMessage(state["request"].source.content),
        ]
        reserved = sum(len(str(m.content).encode("utf-8")) for m in messages)
        reserved += budget.max_output_tokens
        cost = Decimal(reserved) * Decimal("0.001")
        while True:
            try:
                self._check(state)
                if len(ledger.calls) >= budget.max_calls:
                    raise ControlledStop("call_budget")
                if ledger.tokens + reserved > budget.max_tokens:
                    raise ControlledStop("token_budget")
                if ledger.cost + cost > budget.max_cost:
                    raise ControlledStop("cost_budget")
            except ControlledStop as exc:
                return {"stop_reason": str(exc)}
            receipt = CallReceipt(
                run_id=str(state["request"].run_id),
                request_id=str(uuid4()),
                attempt=len(ledger.calls) + 1,
                model_ref=self.profile.model_ref,
                versions=state["request"].versions.model_dump(),
                reserved_tokens=reserved,
                reserved_cost=cost,
            )
            ledger.calls.append(receipt)
            started = time.monotonic()
            retry_delay: float | None = None
            try:
                async with asyncio.timeout(max(0, state["deadline"] - time.monotonic())):
                    response = await self.model.ainvoke(messages, config={"callbacks": []})
                if not isinstance(response, AIMessage):
                    raise ControlledStop("invalid_response")
                usage = response.usage_metadata
                if usage is not None:
                    tokens = usage["total_tokens"]
                    if (
                        min(usage["input_tokens"], usage["output_tokens"], tokens) < 0
                        or tokens != usage["input_tokens"] + usage["output_tokens"]
                    ):
                        raise ControlledStop("usage_invalid")
                    receipt.actual_tokens = tokens
                    receipt.actual_cost = Decimal(tokens) * Decimal("0.001")
                    receipt.usage_source = "fake_adapter"
                    if tokens > reserved or usage["output_tokens"] > budget.max_output_tokens:
                        raise ControlledStop("usage_over_reservation")
                if (
                    response.tool_calls
                    or response.invalid_tool_calls
                    or response.additional_kwargs.get("function_call")
                ):
                    raise ControlledStop("tool_not_allowed")
                if response.additional_kwargs.get("refusal"):
                    raise ControlledStop("refusal")
                finish = response.response_metadata.get("finish_reason", "stop")
                if finish != "stop":
                    raise ControlledStop("refusal" if finish == "refusal" else "truncated")
                if usage is None:
                    raise ControlledStop("usage_unknown")
                if not isinstance(response.content, str):
                    raise ControlledStop("schema_invalid")
                candidate = Candidate.model_validate_json(response.content)
                receipt.status = "settled"
                return {"candidate": candidate.text}
            except ProviderFailure as exc:
                receipt.status = "partial_stream" if exc.partial else exc.kind
                delay = exc.retry_after
                if (
                    not exc.partial
                    and exc.kind in ("rate_limit", "transient")
                    and math.isfinite(delay)
                    and delay >= 0
                ):
                    retry_delay = delay
                else:
                    return {"stop_reason": receipt.status}
            except TimeoutError:
                receipt.status = "deadline"
                return {"stop_reason": "deadline"}
            except asyncio.CancelledError:
                receipt.status = "cancelled"
                raise
            except ValidationError:
                receipt.status = "schema_invalid"
                return {"stop_reason": "schema_invalid"}
            except ControlledStop as exc:
                receipt.status = str(exc)
                return {"stop_reason": str(exc)}
            except Exception:
                receipt.status = "provider_error"
                return {"stop_reason": "provider_error"}
            finally:
                receipt.elapsed_ms = int((time.monotonic() - started) * 1000)
            # An unknown failed attempt keeps its reservation. Only the configured
            # fake price/token upper bound permits a further synthetic call.
            if retry_delay is not None:
                if time.monotonic() + retry_delay >= state["deadline"]:
                    return {"stop_reason": "deadline"}
                await asyncio.sleep(retry_delay)

    def _output(self, state: GraphState) -> dict[str, object]:
        if state["stop_reason"]:
            return {"candidate": None, "verdict": "error"}
        try:
            self._check(state)
        except ControlledStop as exc:
            return {"candidate": None, "stop_reason": str(exc), "verdict": "error"}
        try:
            passed = output_policy(state["candidate"] or "", state["mode"])
            self._check(state)
        except TimeoutError:
            return {"candidate": None, "stop_reason": "evaluation_timeout", "verdict": "error"}
        except ControlledStop as exc:
            return {"candidate": None, "stop_reason": str(exc), "verdict": "error"}
        except Exception:
            return {"candidate": None, "stop_reason": "evaluation_error", "verdict": "error"}
        if not passed:
            return {"candidate": None, "stop_reason": "output_blocked", "verdict": "block"}
        return {"verdict": "pass"}

    async def run(self, request: SupportInput, budget: Budget) -> SupportResult:
        if get_debug() or get_verbose():
            raise ValueError("Verbose traces are not enabled")
        state: GraphState = {
            "request": request,
            "budget": budget,
            "deadline": time.monotonic() + budget.deadline_seconds,
            "ledger": Ledger(),
            "mode": "listen",
            "candidate": None,
            "stop_reason": None,
            "verdict": "error",
        }
        # Disable LangSmith even if a developer's environment enables tracing.
        try:
            with tracing_context(enabled=False):
                result = await self.graph.ainvoke(state, config={"recursion_limit": 4})
        except asyncio.CancelledError:
            return SupportResult(
                mode=select_mode(request),
                text=None,
                stop_reason="cancelled",
                rule_verdict="error",
                ledger=state["ledger"],
                versions=request.versions,
            )
        return SupportResult(
            mode=result["mode"],
            text=result["candidate"],
            stop_reason=result["stop_reason"],
            rule_verdict=result["verdict"],
            ledger=state["ledger"],
            versions=request.versions,
        )
