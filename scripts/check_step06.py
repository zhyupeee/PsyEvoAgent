"""STEP06 reuses the isolated database, worker and browser acceptance gate."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(subprocess.call(
        [sys.executable, "-X", "utf8", str(root / "scripts/check_step03.py"), "--step06", *sys.argv[1:]], cwd=root
    ))
