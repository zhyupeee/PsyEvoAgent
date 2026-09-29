"""Explicit live stage-1 acceptance; reuses the isolated STEP07 regression gate."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args, rest = parser.parse_known_args()
    if not args.live or os.environ.get("CI") or os.environ.get("PSYEVO_CHECK_NETWORK"):
        raise SystemExit("Explicit --live outside PR/network-isolation required")
    if not os.environ.get("PSYEVO_PROVIDER_API_KEY", "").strip():
        raise SystemExit("Provider key is not configured")
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(subprocess.call(
        [sys.executable, "-X", "utf8", str(root / "scripts/check_step03.py"),
         "--step08-live", *rest], cwd=root,
    ))
