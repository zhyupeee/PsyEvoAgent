"""Export actual synthetic graph outcomes and metadata-only call ledgers."""

import asyncio
import hashlib
import json
import platform
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from langchain_core.messages import AIMessage

from app.support import Budget, ModelProfile, ProviderFailure, VersionBinding
from tests.test_support import FIXTURE_PATH, SCENARIOS, message, model, request, runtime


def main(path: Path) -> None:
    started = datetime.now(UTC).isoformat()
    results: list[dict[str, object]] = []
    for case in SCENARIOS:
        for variant in ("acceptable", "unacceptable"):
            result = asyncio.run(
                runtime(model(message(case["examples"][variant]))).run(
                    request(case["input"]["messages"][-1]["content"]),
                    Budget(),
                )
            )
            expected = "pass" if variant == "acceptable" else "block"
            assert result.rule_verdict == expected
            results.append(
                {
                    "fixture_id": case["fixture_id"],
                    "variant": variant,
                    "acceptance_ids": case["acceptance_ids"],
                    "expected": expected,
                    "observed": result.rule_verdict,
                    "mode": result.mode,
                    "text_released": result.text is not None,
                    "semantic_score": result.semantic_score,
                    "stop_reason": result.stop_reason,
                    "ledger": asdict(result.ledger),
                    "status": "passed",
                }
            )
    faults: list[tuple[str, list[AIMessage | Exception], str | None]] = [
        ("429_then_success", [ProviderFailure("rate_limit"), message()], None),
        ("unknown_usage", [message(usage=False)], "usage_unknown"),
        ("partial_stream", [ProviderFailure("transient", partial=True)], "partial_stream"),
    ]
    for name, outcomes, expected_stop in faults:
        result = asyncio.run(runtime(model(*outcomes)).run(request(), Budget()))
        assert result.stop_reason == expected_stop
        results.append(
            {
                "fixture_id": name,
                "expected": expected_stop,
                "observed": result.stop_reason,
                "ledger": asdict(result.ledger),
                "status": "passed",
            }
        )
    profile = ModelProfile(
        text="tested",
        structured_output="tested",
        usage="tested",
        cancellation="tested",
        retries="tested",
        evidence_ref="tests.xml + runtime.json",
    )
    receipt = {
        "step_id": "S1-STEP04",
        "protocol": "s1-runtime-check/1",
        "started": started,
        "ended": datetime.now(UTC).isoformat(),
        "environment": {"platform": platform.platform(), "python": platform.python_version()},
        "execution_kind": "fake",
        "source_qualification": "synthetic-only-unreviewed",
        "fixture_sha256": hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest(),
        "versions": VersionBinding().model_dump(),
        "packages": {
            p: version(p) for p in ("langgraph", "langchain-core", "langsmith", "pydantic")
        },
        "budget": Budget().model_dump(mode="json"),
        "model_profile": profile.model_dump(),
        "live_capabilities": {
            key: "unknown"
            for key in (
                "provider",
                "model_ref",
                "price",
                "data_conditions",
                "usage",
                "cancel",
                "structured",
            )
        },
        "results": results,
        "limitations": [
            "Fake outcomes do not establish model response quality or semantic safety",
            "No real Provider or professional content review; live domain BLOCKED",
            "No API start/SSE, database run binding or persistent business call ledger (STEP05)",
            "Only rules are evaluated; independent human rubric remains unexecuted",
        ],
    }
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"Recorded {len(results)} synthetic outcomes without input/output content")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
