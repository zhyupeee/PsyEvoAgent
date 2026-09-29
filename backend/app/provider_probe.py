"""Explicit STEP08 synthetic internal-stream PoC, not webpage/live acceptance."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from app.config import Settings, load_settings
from app.provider import LiveProfile, open_provider
from app.support import Budget, CallReceipt, Source, SupportInput, SupportRuntime, VersionBinding

SYNTHETIC_INPUT = "这是独立合成测试：今天学习有点累，我只想说说，不需要建议。"


async def probe(
    settings: Settings,
    *,
    run_id: str | None = None,
    authorize: Callable[[SupportInput], bool] = lambda _: True,
    record_call: Callable[[CallReceipt], None] | None = None,
) -> dict[str, object]:
    owner, session, run = uuid4(), uuid4(), uuid4()
    if run_id is not None:
        from uuid import UUID

        run = UUID(run_id)
    profile = LiveProfile(model_ref=settings.provider_model, base_url=settings.provider_base_url)
    budget = Budget(
        max_calls=1,
        max_cost=None,
        max_output_tokens=settings.provider_max_output_tokens,
        deadline_seconds=settings.provider_deadline_seconds,
    )
    request = SupportInput(
        owner_id=owner,
        session_id=session,
        run_id=run,
        synthetic=True,
        versions=VersionBinding(model_ref=profile.model_ref, provider_ref=profile.base_url),
        source=Source(
            owner_id=owner,
            session_id=session,
            message_id=uuid4(),
            message_version=1,
            content=SYNTHETIC_INPUT,
        ),
    )
    async with open_provider(settings) as provider:
        runtime = SupportRuntime(
            provider, profile=profile, authorize=authorize, record_call=record_call
        )
        result = await runtime.run(request, budget)
        passed = result.rule_verdict == "pass" and result.text is not None
        return {
            "status": "passed" if passed else "failed",
            "profile": profile.model_dump(),
            "budget": {
                "max_calls": budget.max_calls,
                "reserved_token_envelope": budget.max_tokens,
                "max_output_tokens": budget.max_output_tokens,
                "deadline_seconds": budget.deadline_seconds,
                "cost_limit": None,
                "cost_status": "unknown",
                "tokenizer_status": "unknown; entire envelope reserved, not an estimate",
            },
            "run_id": str(run),
            "versions": result.versions.model_dump(),
            "ledger": [asdict(call) for call in result.ledger.calls],
            "stream": asdict(provider.observation),
            "rule_verdict": result.rule_verdict,
            "stop_reason": result.stop_reason,
            "capabilities": {
                "text": "tested" if passed else "unknown",
                "json_text_schema": "tested" if passed else "unknown",
                "internal_stream": "tested" if passed else "unknown",
                "usage": "tested" if passed else "unknown",
                "public_chunks": "unsupported",
                "remote_cancellation": "unknown",
                "refusal": "unknown",
                "tool_structured_combination": "unknown",
                "semantic_safety": "unknown",
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Explicitly allow one synthetic request"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    destination = root / ".artifacts" / ("step08-live-" + uuid4().hex[:12])
    destination.mkdir(parents=True)
    receipt: dict[str, object] = {
        "step_id": "S1-STEP08.1",
        "execution_kind": "live-internal-stream-poc",
        "started": datetime.now(UTC).isoformat(),
        "status": "blocked",
        "credential_reference": "PSYEVO_PROVIDER_API_KEY",
        "packages": {
            p: version(p) for p in ("langchain-openai", "openai", "langchain-core", "langgraph")
        },
        "limitations": [
            "Synthetic fixed input only; no database, webpage or public stream validation",
            "Finite output rules do not establish semantic safety or professional review",
            "Price, data region, retention and remote cancellation remain unknown",
        ],
    }
    # Do not let ambient SDK debug/tracing settings log input, output or credentials.
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        if not args.live or os.environ.get("PSYEVO_CHECK_NETWORK") or os.environ.get("CI"):
            receipt["reason"] = "explicit_live_required_outside_pr_or_network_guard"
            return 2
        try:
            settings = load_settings()
        except Exception:
            receipt["reason"] = "invalid_configuration"
            return 2
        if (
            not settings.live_probe_enabled
            or not settings.provider_api_key
            or not settings.provider_api_key.get_secret_value().strip()
        ):
            receipt["reason"] = "provider_not_configured"
            return 2
        try:
            receipt.update(asyncio.run(probe(settings)))
        except Exception:
            receipt.update(status="failed", reason="probe_error")
        return 0 if receipt["status"] == "passed" else 1
    finally:
        logging.disable(previous_logging)
        receipt["ended"] = datetime.now(UTC).isoformat()
        receipt["source_sha256"] = {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "backend/app/provider.py",
                "backend/app/provider_probe.py",
                "backend/app/support.py",
                "backend/app/config.py",
                "backend/pyproject.toml",
                "backend/uv.lock",
            )
        }
        (destination / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print("Receipt: " + str(destination / "receipt.json"))


if __name__ == "__main__":
    raise SystemExit(main())
