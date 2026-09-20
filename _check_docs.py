# -*- coding: utf-8 -*-
"""Check planning documents only; this does not run product acceptance cases."""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit


STAGES = ("1", "2", "3", "4", "5", "5A", "6", "7")
STEP_COUNTS = (8, 8, 7, 8, 8, 7, 7, 8)
TASK = r"(?:RSI-)?S\d+A?-T\d+"
CASE = r"(?:RSI-)?S\d+A?-A\d+"
STEP = r"S\d+A?-STEP\d+"


def section(text, title):
    """Stop at the next heading, excluding prose after the coverage index."""
    match = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match[1] if match else ""


def anchors(text):
    result = set(re.findall(r'<a\s+id="([^"]+)"', text))
    counts = Counter()
    for title in re.findall(r"^#{1,6}\s+(.+)", text, re.M):
        slug = "".join(
            char for char in title.lower().replace("`", "")
            if char in "-_ " or unicodedata.category(char)[0] in "LN"
        ).replace(" ", "-")
        suffix = f"-{counts[slug]}" if counts[slug] else ""
        result.add(slug + suffix)
        counts[slug] += 1
    return result


def check(workspace):
    root = workspace / "PsyEvoAgent项目计划"
    documents = {}
    errors = []
    for stage in STAGES:
        for number in range(1, 5):
            matches = list((root / f"阶段{stage}").glob(f"0{number}-*.md"))
            if len(matches) != 1:
                errors.append(f"阶段{stage}/0{number}: expected one document, found {len(matches)}")
            else:
                documents[stage, number] = matches[0].resolve()
    if errors:
        print("\n".join(errors))
        return 1

    paths = [workspace / "README.md", workspace / "AGENTS.md", *root.rglob("*.md")]
    texts = {p.resolve(): p.read_text(encoding="utf-8") for p in paths}
    tasks, cases, aud = [], [], []
    mapped_tasks, mapped_cases = set(), set()
    index_tasks = set()
    dependencies = {}
    subitem_count = 0

    for stage, expected in zip(STAGES, STEP_COUNTS):
        technical = texts[documents[stage, 2]]
        acceptance = texts[documents[stage, 3]]
        checklist = texts[documents[stage, 4]]
        local_tasks = re.findall(rf"^\|\s*({TASK})\b", technical, re.M)
        local_cases = re.findall(rf"^\|\s*({CASE})\b", acceptance, re.M)
        tasks.extend(local_tasks)
        cases.extend(local_cases)
        aud.extend(re.findall(rf"^\|\s*(AUD-S\d+A?-A\d+)\s*\|\s*({CASE})\s*\|", acceptance, re.M))
        steps = re.findall(rf"^## ({STEP})\b(.*?)(?=^## |\Z)", checklist, re.M | re.S)
        actual = [name for name, body in steps]
        wanted = [f"S{stage}-STEP{i:02}" for i in range(1, expected + 1)]
        if actual != wanted:
            errors.append(f"阶段{stage}: step sequence/count mismatch: {actual}")
        for name, body in steps:
            items = re.findall(rf"\*\*{re.escape(name)}\.(\d+)\*\*", body)
            subitem_count += len(items)
            if not 3 <= len(items) <= 6 or items != [str(i) for i in range(1, len(items) + 1)]:
                errors.append(f"{name}: invalid subitem count/sequence: {items}")
            for field in ("进入条件", "任务关联", "完成与正常路径", "失败路径检查", "阻塞与边界", "验收对应", "交付下一步"):
                if f"**{field}：**" not in body:
                    errors.append(f"{name}: missing {field}")
            mapped_tasks.update(re.findall(rf"(?<![\w-]){TASK}\b", body))
            mapped_cases.update(re.findall(rf"(?<![\w-]){CASE}\b", body))
        index_rows = "\n".join(line for line in section(checklist, "任务覆盖索引").splitlines() if line.startswith("|"))
        local_index = set(re.findall(rf"\[({TASK})\]", index_rows))
        index_tasks.update(local_index)
        if stage == "5A":
            for task in ("RSI-S5-T06", "RSI-S5-T07"):
                if task not in local_index:
                    errors.append(f"阶段5A coverage index missing {task}")
        for line in section(checklist, "步骤总览").splitlines():
            refs = re.findall(rf"\[({STEP})\]", line)
            if refs:
                dependencies[refs[0]] = refs[1:]
        print(f"阶段{stage}: tasks={len(local_tasks)}, cases={len(local_cases)}, steps={len(steps)}")

    for label, definitions, mapped, expected in (
        ("tasks", tasks, mapped_tasks, 92), ("cases", cases, mapped_cases, 153)
    ):
        defined = set(definitions)
        if len(definitions) != expected or len(defined) != expected:
            errors.append(f"{label}: expected {expected} unique definitions, got {len(definitions)}/{len(defined)}")
        if defined - mapped:
            errors.append(f"{label}: unmapped {sorted(defined - mapped)}")
        if mapped - defined:
            errors.append(f"{label}: undefined references {sorted(mapped - defined)}")
    if set(tasks) - index_tasks:
        errors.append(f"coverage indexes missing {sorted(set(tasks) - index_tasks)}")
    if len(aud) != 17 or len({a for a, _ in aud}) != 17 or len({b for _, b in aud}) != 17:
        errors.append("AUD mappings must have 17 unique aliases and targets")
    if {b for _, b in aud} - set(cases):
        errors.append("AUD mapping references an undefined case")

    visited, active = set(), set()

    def visit(step):
        if step in active:
            errors.append(f"step dependency cycle at {step}")
            return
        if step in visited:
            return
        active.add(step)
        for dependency in dependencies.get(step, []):
            if dependency not in dependencies:
                errors.append(f"{step}: undefined dependency {dependency}")
            else:
                visit(dependency)
        active.remove(step)
        visited.add(step)

    for step in dependencies:
        visit(step)

    # Contract recovery must remain self-contained after removal of historical files.
    entity_owners = {
        "ConsentRecord": "1", "InteractionEvent": "1",
        "DependencyEvidence": "2", "DependencyProfile": "2",
        "PolicyDecision": "3", "AgentEvaluation": "3", "OutcomeObservation": "3",
        "EvaluatorVersion": "5", "ImprovementProposal": "6", "PolicyVersion": "6",
        "ApprovalRecord": "6", "RollbackRecord": "6",
        "ExperimentRun": "7", "MetaOptimizerVersion": "7",
    }
    index = section(texts[documents["1", 2]], "14类核心实体维护索引")
    indexed = re.findall(r"^\| ([A-Za-z]+) \|", index, re.M)
    if Counter(indexed) != Counter(entity_owners.keys()):
        errors.append("core entity index must contain exactly the 14 canonical entities")
    for entity, stage in entity_owners.items():
        body = section(texts[documents[stage, 2]], "本阶段核心逻辑实体与合成片段")
        if len(re.findall(rf"^\| {entity} \|", body, re.M)) != 1:
            errors.append(f"{entity}: missing or duplicated authoritative field definition")
    shared = section(texts[documents["1", 2]], "共同身份、授权、实体封套与版本合同")
    for term in (
        "service_context", "optional_profile", "saved_memory", "research_export",
        "retention_policy_id", "personal_sensitive", "research_restricted", "nonpersonal_asset",
        "source_type", "source_id", "source_version", "purpose", "grant_ref",
        "code/message/request_id/retryable", "failed_retryable", "user_statement",
        "user_feeling", "system_inference", "confirmed_preference", "VersionBinding",
    ):
        if term not in shared:
            errors.append(f"shared contract missing {term}")
    source_index = section(texts[documents["1", 2]], "来源编号总索引")
    for domain, expected in (("原版复用", 14), ("RSI研究", 12)):
        ids = re.findall(rf"^\| {domain} R(\d+) \|", source_index, re.M)
        if ids != [f"{n:02}" for n in range(1, expected + 1)]:
            errors.append(f"{domain}: incomplete or duplicate source index")
    for stage in STAGES:
        if "共同合同与来源补充检查" not in texts[documents[stage, 3]]:
            errors.append(f"阶段{stage}: missing recovered contract acceptance checks")
        if "#integration-checks" not in texts[documents[stage, 4]]:
            errors.append(f"阶段{stage}: checklist does not consume recovered checks")
    mcp = texts[documents["4", 2]]
    if not re.search(r'<a id="aud-08"></a>\s*<a id="conditional-mcp"></a>', mcp):
        errors.append("AUD-08 must point to the MCP contract")
    for path, text in texts.items():
        for stale in ("完整24实体", "原总体所述24", "总体8.4", "总体原文待补", "两份项目总体规划、完整实体封套及来源目录"):
            if stale in text:
                errors.append(f"{path}: stale contract reference {stale}")
        if re.search(r"\]\([^)]*历史旧计划", text):
            errors.append(f"{path}: dependency on removed historical directory")

    anchor_sets = {p: anchors(t) for p, t in texts.items()}
    link_count = 0
    for path, text in texts.items():
        explicit = re.findall(r'<a\s+id="([^"]+)"', text)
        if len(explicit) != len(set(explicit)):
            errors.append(f"{path}: duplicate explicit anchors")
        fence, previous_columns = None, None
        for number, line in enumerate(text.splitlines(), 1):
            if line.startswith("```"):
                fence = None if fence is not None else line[3:]
                previous_columns = None
                continue
            if fence is not None:
                continue
            if line.startswith("|"):
                columns = len(re.split(r"(?<!\\)\|", line)) - 2
                if previous_columns is not None and columns != previous_columns:
                    errors.append(f"{path}:{number}: table column mismatch")
                previous_columns = columns
            else:
                previous_columns = None
            for url in re.findall(r"\[[^\]\n]*\]\(([^)\s]+)\)", line):
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc:
                    continue
                link_count += 1
                target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
                if not target.exists():
                    errors.append(f"{path}:{number}: missing file {url}")
                elif parsed.fragment and unquote(parsed.fragment) not in anchor_sets.get(target, set()):
                    errors.append(f"{path}:{number}: missing anchor {url}")
        if fence is not None:
            errors.append(f"{path}: unclosed code fence")
        for payload in re.findall(r"^```json\s*\n(.*?)^```", text, re.M | re.S):
            try:
                json.loads(payload)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}: invalid JSON: {exc}")

    print(f"Documents=32; tasks={len(set(tasks))}; cases={len(set(cases))}; AUD={len(aud)}")
    print(f"Steps={len(dependencies)}; subitems={subitem_count}; local links={link_count}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"Document checks: {'FAILED' if errors else 'PASSED'} ({len(errors)} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(check(Path(__file__).resolve().parent))