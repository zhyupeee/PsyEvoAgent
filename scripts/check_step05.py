"""Reuse the existing disposable PostgreSQL and real gateway gate for STEP05."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(subprocess.call(
        [sys.executable, str(root / "scripts/check_step03.py"), "--step05", *sys.argv[1:]], cwd=root
    ))
