"""Validate S1-STEP01 fixture material, never product behavior or clinical quality."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "PsyEvoAgent项目计划" / "阶段1"
FIXTURE = STAGE / "fixtures" / "S1-STEP01" / "scenarios.json"
EXPECTED_IDS = {
    "cold_start", "listen", "clarify", "explore", "refuse_advice", "bullying",
    "close", "support_unknown", "support_expired", "late_exclusivity",
    "late_obligation", "late_diagnosis", "late_danger",
}
CASES = {"S1-A01", "S1-A07", "RSI-S1-A01", "RSI-S1-A05"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected.split()),
            "missing or unexpected fields")


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate(data):
    fields(data, "schema_version scope_version step_id task_ids source cases")
    require(data["schema_version"] == "s1-fixtures/1", "fixture version")
    require(data["scope_version"] == "s1-scope/1", "scope version")
    require(data["step_id"] == "S1-STEP01", "step scope")
    require(data["task_ids"] == ["S1-T01", "RSI-S1-T01"], "task mapping")
    require(data["source"] == {
        "id": "s1-synthetic/1", "kind": "synthetic", "author": "Codex",
        "review_status": "pending_verification", "approved_for_real_users": False,
    }, "synthetic provenance and unreviewed status")
    require(data["source"]["approved_for_real_users"] is False, "approval type")
    require(isinstance(data["cases"], list), "cases must be a list")
    seen, mapped = [], set()
    for case in data["cases"]:
        fields(case, "fixture_id acceptance_ids input expected examples product_status")
        require(nonempty(case["fixture_id"]), "fixture id")
        seen.append(case["fixture_id"])
        ids = case["acceptance_ids"]
        require(isinstance(ids, list) and ids and all(nonempty(x) for x in ids),
                "acceptance ids")
        require(len(ids) == len(set(ids)) and set(ids) <= CASES, "acceptance mapping")
        mapped.update(ids)
        require(case["product_status"] == "planned", "product acceptance is unexecuted")
        fields(case["input"], "messages age_band resource_status")
        require(case["input"]["age_band"] in ("adult", "minor", "unknown"), "age band")
        require(case["input"]["resource_status"] in ("unknown", "expired"), "resource state")
        messages = case["input"]["messages"]
        require(isinstance(messages, list) and messages, "messages")
        for message in messages:
            fields(message, "role content")
            require(message["role"] in ("user", "assistant") and nonempty(message["content"]),
                    "message role/content")
        fields(case["expected"], "mode must must_not")
        require(case["expected"]["mode"] in (
            "listen", "clarify", "explore", "action", "close", "support_route"
        ), "support mode")
        for key in ("must", "must_not"):
            values = case["expected"][key]
            require(isinstance(values, list) and values and all(nonempty(x) for x in values),
                    "positive and negative expectations required")
        fields(case["examples"], "acceptable unacceptable")
        require(all(nonempty(x) for x in case["examples"].values()), "examples required")
        require(case["examples"]["acceptable"] != case["examples"]["unacceptable"],
                "counterexample must differ")
    require(len(seen) == len(set(seen)) and set(seen) == EXPECTED_IDS, "scenario coverage/duplicates")
    require(mapped == CASES, "acceptance coverage")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", action="store_true", help="write local fixture-check receipt")
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    validate(data)
    acceptance = (STAGE / "03-测试与验收标准.md").read_text(encoding="utf-8")
    defined = set(re.findall(r"^\| ((?:RSI-)?S1-A\d+)\b", acceptance, re.M))
    require(CASES <= defined, "undefined acceptance reference")
    scope = (STAGE / "01-阶段目标与功能设计.md").read_text(encoding="utf-8")
    require(all(name in scope for name in EXPECTED_IDS), "unmapped scope scenario")

    # Corrupt copies in memory: these test material validation, not an Agent.
    mutations = [
        ("duplicate_fixture", lambda d: d["cases"].append(copy.deepcopy(d["cases"][0]))),
        ("missing_negative", lambda d: d["cases"][0]["expected"].pop("must_not")),
        ("unknown_acceptance", lambda d: d["cases"][0].update(acceptance_ids=["S1-A999"])),
        ("false_product_pass", lambda d: d["cases"][0].update(product_status="passed")),
        ("false_human_approval", lambda d: d["source"].update(approved_for_real_users=True)),
        ("invalid_mode", lambda d: d["cases"][0]["expected"].update(mode="diagnose")),
        ("missing_scenario", lambda d: d["cases"].pop()),
        ("injected_owner", lambda d: d["cases"][0]["input"].update(owner_id="synthetic-other")),
    ]
    rejected = []
    for name, mutate in mutations:
        damaged = copy.deepcopy(data)
        mutate(damaged)
        try:
            validate(damaged)
        except ValueError:
            rejected.append(name)
        else:
            raise ValueError(f"material validator accepted mutation: {name}")

    receipt = {
        "step_id": "S1-STEP01", "task_ids": data["task_ids"],
        "execution_kind": "local_static_fixture_check", "source_kind": "synthetic",
        "environment": {"platform": platform.system(), "python": platform.python_version()},
        "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
        "expected": "13 traceable fixtures; 8 invalid material mutations rejected",
        "observed": {"valid_fixtures": len(data["cases"]), "rejected_mutations": rejected},
        "status": "passed", "failed_checks": 0,
        "product_cases": {case: "planned" for case in sorted(CASES)},
        "versions": {"app": None, "graph": None, "model": None, "provider": None,
                     "sdk": None, "product_schema": None, "evaluator": None,
                     "fixture": data["schema_version"], "scope": data["scope_version"]},
        "model_calls": 0,
        "limitations": ["No product/API/database/provider execution",
                        "No independent human rubric or professional content approval",
                        "Expected examples are authored fixtures, not observed responses"],
        "sha256": {},
    }
    paths = [Path(__file__), FIXTURE, ROOT / "_check_docs.py", ROOT / "README.md",
             ROOT / "AGENTS.md", *sorted((ROOT / "PsyEvoAgent项目计划").glob("阶段*/*.md"))]
    for path in paths:
        receipt["sha256"][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.receipt:
        target = STAGE / "evidence" / "S1-STEP01" / "fixture-check.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("S1-STEP01 material checks: PASSED; 13 fixtures; 8 rejected mutations; 0 failures")
    print("Product acceptance: 0 executed; all 4 referenced cases remain planned")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"S1-STEP01 material checks: FAILED ({type(exc).__name__}: {exc})", file=sys.stderr)
        raise SystemExit(1)
