"""Run the local STEP02 gate after locked dependencies/browser are installed.

Invoke with backend/.venv/Scripts/python.exe on Windows, or its bin/python on POSIX.
No dependency installation, model calls, database access, or business writes.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psutil

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--node-dir", type=Path, help="Installed Node/pnpm directory if PATH shims fail"
)
parser.add_argument(
    "--base-ref",
    help="PR target ref used to check committed changes (auto-detected by default)",
)
parser.add_argument(
    "--require-os-isolation", action="store_true", help="Require Linux kernel egress isolation"
)
ARGS = parser.parse_args()
RUN = ROOT / ".artifacts" / ("step02-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
RUN.mkdir(parents=True)
# Do not inherit credentials, proxies, NODE_OPTIONS, or Python startup overrides.
ENV = {
    k: v
    for k, v in os.environ.items()
    if k.upper()
    in {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOME",
        "PLAYWRIGHT_BROWSERS_PATH",
    }
}
ENV.update(
    {
        "UV_CACHE_DIR": str(ROOT / ".artifacts/uv-cache"),
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / "scripts/network_guard"),
        "PSYEVO_CHECK_NETWORK": "loopback-only",
        "PSYEVO_ENV": "test",
        "NODE_OPTIONS": '--require="' + (ROOT / "scripts/network-guard.cjs").as_posix() + '"',
        "PSYEVO_MANAGED_SERVERS": "1",
        "VITE_MODEL_API_KEY": "synthetic-secret-step02-do-not-bundle",
    }
)
if ARGS.node_dir:
    ENV["PATH"] = str(ARGS.node_dir.resolve()) + os.pathsep + ENV["PATH"]
PNPM = shutil.which("pnpm.cmd" if os.name == "nt" else "pnpm", path=ENV["PATH"])
NODE = shutil.which("node", path=ENV["PATH"])
RECEIPT = {
    "step_id": "S1-STEP02",
    "acceptance_id": "S1-A13",
    "started": datetime.now(UTC).isoformat(),
    "execution_kind": "local-engineering-and-fake",
    "os_isolation_required": ARGS.require_os_isolation,
    "limitations": [
        "No business authorization, run cancellation, or model acceptance",
        "Network-only isolation is not a filesystem sandbox"
        if ARGS.require_os_isolation
        else "Network guards cover Python/Node/browser test paths, not an OS sandbox",
    ],
    "commands": [],
}
RECEIPT_EXCLUDED_DIRS = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vite",
    "__pycache__",
    "dist",
    "node_modules",
    "test-results",
}
RECEIPT_EXCLUDED_SECRET_NAMES = {".env", "credentials.json", "service-account.json"}
RECEIPT_EXCLUDED_SECRET_SUFFIXES = {".key", ".pem"}


def cleanup(process):
    if process.poll() is not None:
        return
    parent = psutil.Process(process.pid)
    children = parent.children(recursive=True)
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    try:
        parent.terminate()
    except psutil.NoSuchProcess:
        pass
    _, alive = psutil.wait_procs(children + [parent], timeout=5)
    for child in alive:
        child.kill()
    process.wait(timeout=10)


def check(args, cwd=ROOT, timeout=120):
    print("CHECK", " ".join(args), flush=True)
    with subprocess.Popen(
        args,
        cwd=cwd,
        env=ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    ) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
            code = process.returncode
        except subprocess.TimeoutExpired:
            cleanup(process)
            output, _ = process.communicate(timeout=10)
            output += "\nGate timeout\n"
            code = 124
    RECEIPT["commands"].append(
        {
            "command": args,
            "cwd": str(cwd.relative_to(ROOT)),
            "exit_code": code,
            "output": output,
        }
    )
    print(output, flush=True)
    return code == 0


def git_stdout(args: list[str]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        env=ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def resolve_pr_base_ref() -> str | None:
    requested = (
        ARGS.base_ref
        or os.environ.get("GITHUB_BASE_REF")
        or os.environ.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME")
    )
    candidates = []
    if requested:
        candidates.extend([requested, f"origin/{requested}"])
    else:
        remote_head = git_stdout(
            ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"]
        )
        if remote_head:
            candidates.append(remote_head)
        candidates.extend(["origin/main", "origin/master"])
    for candidate in dict.fromkeys(candidates):
        if git_stdout(["rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"]):
            return candidate
    if requested:
        raise RuntimeError(f"PR base ref is unavailable: {requested}")
    return None


def patch_checks() -> bool:
    passed = check(["git", "diff", "--check"])
    passed = check(["git", "diff", "--cached", "--check"]) and passed
    base_ref = resolve_pr_base_ref()
    RECEIPT["patch_base_ref"] = base_ref
    if base_ref:
        passed = check(["git", "diff", "--check", f"{base_ref}...HEAD"]) and passed
    return passed


def include_in_receipt(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return (
        path.is_file()
        and not any(part in RECEIPT_EXCLUDED_DIRS for part in relative.parts[:-1])
        and relative.name not in RECEIPT_EXCLUDED_SECRET_NAMES
        and not relative.name.startswith(".env.")
        and relative.suffix.lower() not in RECEIPT_EXCLUDED_SECRET_SUFFIXES
    )


def browser_checks():
    services = []
    try:
        for args, cwd, url, name in [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                    "--no-access-log",
                ],
                ROOT / "backend",
                "http://127.0.0.1:8000/api/v1/health",
                "api",
            ),
            ([PNPM, "dev"], ROOT / "frontend", "http://127.0.0.1:3000", "frontend"),
        ]:
            with httpx.Client(trust_env=False, timeout=0.5) as client:
                try:
                    client.get(url)
                except httpx.HTTPError:
                    pass
                else:
                    raise RuntimeError("Test port already occupied: " + url)
            log = (RUN / (name + ".txt")).open("w", encoding="utf-8")
            process = subprocess.Popen(args, cwd=cwd, env=ENV, stdout=log, stderr=subprocess.STDOUT)
            services.append((process, log))
            deadline = time.monotonic() + 45
            with httpx.Client(trust_env=False, timeout=1) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(name + " exited before readiness")
                    try:
                        if client.get(url).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.2)
                else:
                    raise RuntimeError(name + " readiness timed out")
        return check([PNPM, "test:e2e"], ROOT / "frontend")
    finally:
        for process, log in reversed(services):
            cleanup(process)
            log.close()


def main():
    passed = True
    try:
        if ARGS.require_os_isolation:
            if not check([sys.executable, "-I", str(ROOT / "scripts/probe_os_isolation.py")]):
                raise RuntimeError("OS isolation preflight failed; tests were not started")
        for args in [
            [sys.executable, "--version"],
            [NODE, "--version"],
            [PNPM, "--version"],
            ["uv", "--version"],
        ]:
            passed = check(args) and passed
        passed = (
            check(
                [
                    PNPM,
                    "install",
                    "--lockfile-only",
                    "--frozen-lockfile",
                    "--offline",
                    "--ignore-scripts",
                ],
                ROOT / "frontend",
            )
            and passed
        )
        passed = (
            check([sys.executable, str(ROOT / "scripts/probe_python_guard.py")]) and passed
        )
        passed = (
            check(
                [
                    NODE,
                    str(ROOT / "scripts/probe_node_guard.cjs"),
                ]
            )
            and passed
        )
        for args in [
            ["uv", "lock", "--check", "--offline"],
            [sys.executable, "-m", "ruff", "check", "."],
            [sys.executable, "-m", "ruff", "format", "--check", "."],
            [sys.executable, "-m", "mypy"],
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--basetemp=" + str(RUN / "pytest"),
            ],
        ]:
            passed = check(args, ROOT / "backend") and passed
        for script in ["lint", "typecheck", "test:unit", "build"]:
            passed = check([PNPM, script], ROOT / "frontend") and passed
        passed = browser_checks() and passed
        for script in ["_check_docs.py", "_check_s1_step01.py"]:
            passed = check([sys.executable, "-B", "-X", "utf8", script]) and passed
        passed = patch_checks() and passed
        leaks = [
            str(p.relative_to(ROOT))
            for p in (ROOT / "frontend/dist").rglob("*")
            if p.is_file() and b"synthetic-secret-step02-do-not-bundle" in p.read_bytes()
        ]
        RECEIPT["bundle_probe_leaks"] = leaks
        passed = not leaks and passed
    except Exception as error:
        RECEIPT["error"] = str(error)
        passed = False
    finally:
        RECEIPT["hashes"] = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ["backend", "frontend", "scripts"]
            for p in (ROOT / folder).rglob("*")
            if include_in_receipt(p)
        }
        RECEIPT["ended"] = datetime.now(UTC).isoformat()
        RECEIPT["status"] = "passed" if passed else "failed"
        (RUN / "receipt.json").write_text(
            json.dumps(RECEIPT, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("Receipt:", RUN / "receipt.json", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
