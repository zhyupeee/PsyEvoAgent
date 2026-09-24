"""STEP04 gate: reuse engineering gate, then export fake-runtime acceptance evidence.

No dependency installs or live model calls. For kernel isolation use the existing
check_step02_isolated.sh entry with --step04 after preparing dependencies.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-os-isolation", action="store_true")
    args = parser.parse_args()
    run_dir = ROOT / ".artifacts" / ("step04-" + uuid4().hex[:12])
    run_dir.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
        "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOME", "PLAYWRIGHT_BROWSERS_PATH",
    }}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PSYEVO_ENV="test",
               PSYEVO_CHECK_NETWORK="loopback-only",
               PYTHONPATH=str(ROOT / "scripts/network_guard"))
    commands: list[dict[str, object]] = []
    receipt: dict[str, object] = {
        "step_id": "S1-STEP04", "protocol": "s1-runtime-check/1",
        "execution_kind": "fake", "started": datetime.now(UTC).isoformat(),
        "os_isolation_required": args.require_os_isolation, "commands": commands,
        "status": "failed", "acceptance_ids": [
            "S1-A01", "S1-A09", "S1-A12", "RSI-S1-A05", "RSI-S1-A06",
        ],
        "limitations": "Local fake slice only; live provider/content BLOCKED; no STEP05/06",
    }
    checks = [
        ("engineering", [sys.executable, "scripts/check_step02.py"] +
         (["--require-os-isolation"] if args.require_os_isolation else []), ROOT),
        ("runtime-tests", [sys.executable, "-m", "pytest", "tests/test_support.py",
                           "--junitxml=" + str(run_dir / "tests.xml")], ROOT / "backend"),
        ("runtime-receipt", [sys.executable, "-m", "tests.support_receipt",
                             str(run_dir / "runtime.json")], ROOT / "backend"),
    ]
    try:
        for label, command, cwd in checks:
            print(label, flush=True)
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding="utf-8", timeout=900, check=False)
            (run_dir / (label + ".txt")).write_text(result.stdout + result.stderr, encoding="utf-8")
            commands.append({"label": label, "command": command, "exit_code": result.returncode,
                             "log": label + ".txt"})
            if result.returncode:
                print(result.stdout[-4000:] + result.stderr[-2000:])
                return 1
            if label == "engineering":
                for line in result.stdout.splitlines():
                    if line.startswith("Receipt:"):
                        source = Path(line.removeprefix("Receipt:").strip())
                        (run_dir / "engineering.json").write_bytes(source.read_bytes())
        receipt["status"] = "passed"
        return 0
    finally:
        receipt["ended"] = datetime.now(UTC).isoformat()
        receipt["source_sha256"] = {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
                "backend/app/support.py", "backend/tests/test_support.py",
                "backend/tests/support_receipt.py", "backend/pyproject.toml", "backend/uv.lock",
                "scripts/check_step04.py", "scripts/check_step02_isolated.sh",
            )
        }
        (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print("Receipt: " + str(run_dir / "receipt.json"), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
