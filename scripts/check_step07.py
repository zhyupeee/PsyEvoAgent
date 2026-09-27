"""STEP07 reuses the isolated PostgreSQL, Worker and actual browser gate."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(subprocess.call(
        [sys.executable, "-X", "utf8", str(root / "scripts/check_step03.py"), "--step07", *sys.argv[1:]], cwd=root
    ))
