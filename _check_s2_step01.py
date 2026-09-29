"""Check S2-STEP01 synthetic contract material, not product authorization or assessment."""

import argparse
import copy
import hashlib
import json
import platform
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "PsyEvoAgent项目计划" / "阶段2"
FIXTURE = STAGE / "fixtures/S2-STEP01/scenarios.json"
PURPOSES = {
    "current_run": "support",
    "candidate_extraction": "memory",
    "personalization": "memory",
    "dependency_assessment": "profile",
    "evaluation": "evaluation",
}
DIMENSIONS = {
    "language_expectation",
    "frequency_change",
    "duration_schedule",
    "regulation_concentration",
    "reassurance_loop",
    "unavailability_response",
    "decision_autonomy",
    "use_control",
    "exclusivity_replacement",
    "functional_impact",
    "protective_factors",
}
CASE_IDS = {"RSI-S2-A02", "RSI-S2-A03", "RSI-S2-A04"}
BINDING_IDS = {
    *("own-" + purpose for purpose in PURPOSES),
    "same-experience-other-owner",
    "forged-actor",
    "memory-is-not-profile",
    "profile-is-not-memory",
    "extraction-is-not-retrieval",
    "evaluation-is-not-profile",
    "wrong-source-type",
    "wrong-source-id",
    "old-source-version",
    "old-grant-version",
    "old-config-version",
    "deleted-source",
    "revoked-grant",
    "ended-scope",
    "disabled-candidate_extraction",
    "disabled-personalization",
    "disabled-dependency_assessment",
    "disabled-evaluation",
    "profile-disabled-memory-independent",
    "profile-disabled-support-independent",
    "history-declined",
    "history-revoked",
    "missing-grant",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, names):
    require(isinstance(value, dict) and set(value) == set(names.split()), "fields: " + names)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def positive(value):
    return type(value) is int and value > 0


def reference(value):
    fields(value, "source_type source_id source_version purpose grant_ref")
    require(all(nonempty(value[x]) for x in value if x != "source_version"), "reference strings")
    require(positive(value["source_version"]), "source version")
    require(value["purpose"] in PURPOSES, "purpose enum")


def binding_result(case, data):
    """Compare references in authored fixtures only; never read or authorize business data."""
    ref = case["source_ref"]
    source = next(
        (
            s
            for s in data["sources"]
            if (s["type"], s["id"]) == (ref["source_type"], ref["source_id"])
        ),
        None,
    )
    grant = next((g for g in data["grants"] if g["id"] == ref["grant_ref"]), None)
    if source is None:
        return "source_missing"
    if grant is None:
        return "grant_missing"
    if not case["actor"] == source["owner"] == grant["owner"]:
        return "owner_mismatch"
    if (grant["source_type"], grant["source_id"]) != (source["type"], source["id"]):
        return "source_binding"
    if source["deleted"]:
        return "source_deleted"
    if not source["version"] == ref["source_version"] == grant["source_version"]:
        return "source_version"
    if grant["version"] != case["grant_version"]:
        return "grant_version"
    if grant["revoked"] or not grant["scope_active"]:
        return "grant_inactive"
    if not case["purpose"] == ref["purpose"] == grant["purpose"]:
        return "purpose_mismatch"
    if case["config_version"] != grant["config_version"]:
        return "config_version"
    if not case["defaults"][PURPOSES[case["purpose"]]]:
        return "purpose_disabled"
    return "valid"


def validate(data):
    fields(
        data,
        "schema_version contract_version annotation_version step_id source "
        "sources grants binding_cases dimensions profile_cases",
    )
    require(
        (
            data["schema_version"],
            data["contract_version"],
            data["annotation_version"],
            data["step_id"],
        )
        == ("s2-fixtures/1", "s2-source-contract/1", "s2-annotation/1", "S2-STEP01"),
        "registered versions",
    )
    require(
        data["source"]
        == {
            "kind": "synthetic",
            "author": "Codex",
            "review_status": "not_professionally_validated",
            "contains_private_data": False,
        },
        "synthetic provenance",
    )
    require(data["source"]["contains_private_data"] is False, "private data flag")
    for name in ("sources", "grants", "binding_cases", "dimensions", "profile_cases"):
        require(isinstance(data[name], list) and data[name], "list: " + name)
    for source in data["sources"]:
        fields(source, "id owner type version deleted")
        require(all(nonempty(source[x]) for x in ("id", "owner", "type")), "source identity")
        require(positive(source["version"]) and type(source["deleted"]) is bool, "source state")
    for grant in data["grants"]:
        fields(
            grant,
            "id owner source_type source_id source_version purpose version "
            "revoked scope_active config_version",
        )
        require(
            all(
                nonempty(grant[x])
                for x in ("id", "owner", "source_type", "source_id", "config_version")
            ),
            "grant identity",
        )
        require(
            grant["purpose"] in PURPOSES
            and positive(grant["source_version"])
            and positive(grant["version"]),
            "grant version/purpose",
        )
        require(
            type(grant["revoked"]) is bool and type(grant["scope_active"]) is bool, "scope flags"
        )
    for name in ("sources", "grants"):
        ids = [(s["type"], s["id"]) if name == "sources" else s["id"] for s in data[name]]
        require(len(ids) == len(set(ids)), "duplicate " + name)
    results = []
    for case in data["binding_cases"]:
        fields(
            case,
            "fixture_id acceptance_ids actor purpose source_ref grant_version "
            "config_version defaults history expected product_status",
        )
        require(case["acceptance_ids"] == ["RSI-S2-A03", "RSI-S2-A04"], "binding case mapping")
        require(case["product_status"] == "planned", "no product execution")
        reference(case["source_ref"])
        require(nonempty(case["actor"]) and case["purpose"] in PURPOSES, "actor/purpose")
        require(
            positive(case["grant_version"]) and nonempty(case["config_version"]), "binding versions"
        )
        fields(case["defaults"], "support memory profile evaluation optimization")
        require(all(type(v) is bool for v in case["defaults"].values()), "config flags")
        require(isinstance(case["history"], list), "history list")
        for old in case["history"]:
            fields(old, "purpose decision version")
            require(
                old["purpose"] in {"saved_memory", "optional_profile"}
                and old["decision"] in {"declined", "revoked"}
                and positive(old["version"]),
                "historical decisions are not generated consent",
            )
        history = copy.deepcopy(case["history"])
        observed = binding_result(case, data)
        require(observed == case["expected"], "unexpected fixture binding: " + case["fixture_id"])
        require(case["history"] == history, "history changed")
        results.append(
            {
                "fixture_id": case["fixture_id"],
                "expected": case["expected"],
                "observed": observed,
                "kind": "synthetic-reference-comparison",
            }
        )
    ids = [c["fixture_id"] for c in data["binding_cases"]]
    require(len(ids) == len(set(ids)) and set(ids) == BINDING_IDS, "binding coverage")
    profile_case = next(
        c for c in data["binding_cases"] if c["fixture_id"] == "own-dependency_assessment"
    )
    seen = []
    for item in data["dimensions"]:
        fields(
            item,
            "dimension support counter unknown source_ref evidence_kind "
            "alternative_explanations expected product_status",
        )
        seen.append(item["dimension"])
        require(item["product_status"] == "planned", "no assessor execution")
        require(all(nonempty(item[k]) for k in ("support", "counter", "unknown")), "three stances")
        require(len({item[k] for k in ("support", "counter", "unknown")}) == 3, "distinct examples")
        require(
            item["evidence_kind"] in {"utterance", "event", "self_report", "correction"}, "kind"
        )
        require(
            isinstance(item["alternative_explanations"], list)
            and item["alternative_explanations"]
            and all(nonempty(x) for x in item["alternative_explanations"]),
            "alternatives",
        )
        require(
            item["expected"]
            == {
                "support_stance": "support",
                "counter_stance": "counter",
                "unknown_stance": "ambiguous",
                "missing_state": "unknown",
                "missing_value": None,
                "unknown_reason": "not_observed",
                "sufficiency": "limited",
                "trend": "unknown",
            },
            "unknown/null/stance contract",
        )
        reference(item["source_ref"])
        probe = {**profile_case, "source_ref": item["source_ref"]}
        require(binding_result(probe, data) == "valid", "annotation source binding")
    require(set(seen) == DIMENSIONS and len(seen) == len(DIMENSIONS), "eleven dimensions")
    expected_profiles = {
        "cold-start": "unknown",
        "missing-fields": "limited",
        "conflicting-sources": "conflicting",
        "frequent-without-impact": "limited",
        "persistent-severe-impact": "limited",
    }
    seen = []
    for case in data["profile_cases"]:
        fields(
            case,
            "fixture_id input sufficiency reason counter_refs protective_factors "
            "must acceptance_ids product_status numeric_score",
        )
        seen.append(case["fixture_id"])
        require(case["sufficiency"] == expected_profiles.get(case["fixture_id"]), "sufficiency")
        require(
            case["acceptance_ids"] == ["RSI-S2-A02"] and case["product_status"] == "planned",
            "profile case mapping",
        )
        require(
            case["numeric_score"] is None and case["protective_factors"] is None,
            "no invented scores",
        )
        require(nonempty(case["input"]) and nonempty(case["reason"]), "input and unknown reason")
        require(
            isinstance(case["must"], list)
            and len(case["must"]) >= 2
            and all(nonempty(x) for x in case["must"]),
            "explicit annotation requirements",
        )
        require(isinstance(case["counter_refs"], list), "counter refs list")
        for ref in case["counter_refs"]:
            reference(ref)
            probe = {**profile_case, "source_ref": ref}
            require(binding_result(probe, data) == "valid", "counter source binding")
        if case["sufficiency"] == "conflicting":
            require(bool(case["counter_refs"]), "conflict requires counter evidence")
    require(set(seen) == set(expected_profiles) and len(seen) == 5, "profile scenario coverage")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", action="store_true")
    args = parser.parse_args()
    receipt = {
        "step_id": "S2-STEP01",
        "started_at": datetime.now(UTC).isoformat(),
        "execution_kind": "local_static_synthetic_contract_check",
        "status": "failed",
        "environment": {"python": platform.python_version(), "platform": platform.system()},
        "model_calls": 0,
        "database_calls": 0,
        "product_cases": {case: "planned" for case in sorted(CASE_IDS)},
        "limitations": [
            "Not product/API/DB authorization or model-input validation",
            "Authored annotation expectations, not an executed Assessor",
            "No clinical calibration, LangMem, Worker or memory persistence",
        ],
    }
    try:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        receipt["bindings"] = validate(data)
        acceptance = (STAGE / "03-测试与验收标准.md").read_text(encoding="utf-8")
        require(
            CASE_IDS <= set(re.findall(r"^\| ((?:RSI-)?S2-A\d+)\b", acceptance, re.M)),
            "case anchors",
        )
        technical = (STAGE / "02-技术方案与实施计划.md").read_text(encoding="utf-8")
        require(all(f"| {dim} |" in technical for dim in DIMENSIONS), "dimension traceability")
        mutations = {
            "duplicate_case": lambda d: d["binding_cases"].append(d["binding_cases"][0]),
            "owner_forgery": lambda d: d["binding_cases"][0].update(actor="owner-b"),
            "source_version": lambda d: d["binding_cases"][0]["source_ref"].update(
                source_version=2
            ),
            "purpose_substitution": lambda d: d["binding_cases"][0]["source_ref"].update(
                purpose="evaluation"
            ),
            "config_disabled": lambda d: d["binding_cases"][0]["defaults"].update(support=False),
            "missing_reference_version": lambda d: d["dimensions"][0]["source_ref"].pop(
                "source_version"
            ),
            "text_reference": lambda d: d["dimensions"][0].update(source_ref="source-a"),
            "missing_dimension": lambda d: d["dimensions"].pop(),
            "unknown_as_zero": lambda d: d["dimensions"][0]["expected"].update(missing_value=0),
            "missing_counter": lambda d: d["dimensions"][0].pop("counter"),
            "missing_alternatives": lambda d: d["dimensions"][0].update(
                alternative_explanations=[]
            ),
            "conflict_without_counter": lambda d: d["profile_cases"][2].update(counter_refs=[]),
            "invented_score": lambda d: d["profile_cases"][0].update(numeric_score=0),
            "false_product_pass": lambda d: d["binding_cases"][0].update(product_status="passed"),
            "fabricated_granted": lambda d: next(
                c for c in d["binding_cases"] if c["fixture_id"] == "history-declined"
            )["history"][0].update(decision="granted"),
        }
        rejected = []
        for name, mutate in mutations.items():
            damaged = copy.deepcopy(data)
            mutate(damaged)
            try:
                validate(damaged)
            except ValueError:
                rejected.append(name)
            else:
                raise ValueError("accepted damaged fixture: " + name)
        receipt.update(
            status="passed",
            rejected_mutations=rejected,
            dimensions=11,
            annotation_examples=33,
            profile_scenarios=5,
            failed_checks=0,
            versions={
                k: data[k] for k in ("schema_version", "contract_version", "annotation_version")
            },
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        receipt.update(error=str(exc), failed_checks=1)
    receipt["ended_at"] = datetime.now(UTC).isoformat()
    paths = [Path(__file__), FIXTURE, *sorted(STAGE.glob("0[1-4]-*.md"))]
    receipt["sha256"] = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
        if p.exists()
    }
    if args.receipt:
        target = (
            STAGE
            / "evidence/S2-STEP01"
            / (
                "contract-check-"
                + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
                + "-"
                + uuid4().hex[:8]
                + ".json"
            )
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(target.relative_to(ROOT))
    print("S2-STEP01 contract material:", receipt["status"], receipt.get("error", ""))
    print("Expected: 28 bindings; 11 dimensions / 33 examples; 5 profile scenarios; 15 corruptions")
    print("Stage2 product cases remain planned; no API/database/model execution by this checker")
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
