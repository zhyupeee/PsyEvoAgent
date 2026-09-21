import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import httpx
import psutil
import pytest

from app.dev import stop_server

BACKEND = Path(__file__).resolve().parents[1]


def test_reload_refuses_shutdown_timeout() -> None:
    process = Mock()
    process.is_alive.return_value = True
    stop = Mock()
    with pytest.raises(RuntimeError, match="did not shut down gracefully"):
        stop_server(process, stop)
    stop.set.assert_called_once()
    process.terminate.assert_called_once()
    process.kill.assert_called_once()


def test_standalone_worker_process_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.worker", "--check"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert result.stdout.splitlines() == [
        "worker.started consumers=0",
        "worker.stopped consumers=0",
    ]
    assert not result.stderr


@pytest.mark.parametrize("editing_error", ["def broken(:", "import missing_reload_probe_module"])
def test_real_api_reload_does_not_import_worker(tmp_path: Path, editing_error: str) -> None:
    # Mutate only a disposable copy, never the developer's source file.
    shutil.copytree(BACKEND / "app", tmp_path / "app", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "app/worker.py").write_text('raise RuntimeError("API imported worker")\n')
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    logfile = tmp_path / "reload.txt"
    with logfile.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "app.dev",
                "--port",
                str(port),
                "--reload-dir",
                str(tmp_path),
                "--stop-on-stdin-eof",
            ],
            cwd=tmp_path,
            stdout=output,
            stdin=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PSYEVO_ENV": "test"},
        )
        descendants: list[psutil.Process] = []
        try:
            with httpx.Client(timeout=1, trust_env=False) as client:

                def wait_ready(expected_starts: int) -> None:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        assert process.poll() is None, "API supervisor exited"
                        text = logfile.read_text(encoding="utf-8")
                        if text.count("api.started") >= expected_starts:
                            try:
                                response = client.get(f"http://127.0.0.1:{port}/api/v1/health")
                                if response.json() == {"status": "ok", "stage": "S1-STEP02"}:
                                    return
                            except (httpx.HTTPError, ValueError):
                                pass
                        time.sleep(0.1)
                    raise AssertionError(
                        "API/reload did not become ready:\n" + logfile.read_text(encoding="utf-8")
                    )

                wait_ready(1)
                time.sleep(1)  # Allow the reload watcher to register before touching the copy.
                source = tmp_path / "app/main.py"
                for expected_starts in (2, 3):
                    original = source.read_bytes()
                    source.write_text(editing_error + "\n", encoding="utf-8")
                    deadline = time.monotonic() + 30
                    error_name = (
                        "SyntaxError" if editing_error.startswith("def") else "ModuleNotFoundError"
                    )
                    while (
                        logfile.read_text(encoding="utf-8").count(error_name) < expected_starts - 1
                    ):
                        assert process.poll() is None, "API supervisor exited after editing error"
                        assert time.monotonic() < deadline, "Failed API child did not exit"
                        time.sleep(0.1)
                    time.sleep(1)  # Include idle watcher ticks after the child fails.
                    assert process.poll() is None, "API supervisor exited after editing error"
                    source.write_bytes(original)
                    wait_ready(expected_starts)
                log = logfile.read_text(encoding="utf-8")
                assert log.count("api.stopped") == 2
                assert "API imported worker" not in log
                assert "worker.started" not in log
                descendants = psutil.Process(process.pid).children(recursive=True)
                assert process.stdin is not None
                process.stdin.close()
                assert process.wait(timeout=15) == 0
                log = logfile.read_text(encoding="utf-8")
                assert log.count("api.stopped") == 3
                assert "dev.stopped" in log
        finally:
            if process.poll() is None:
                supervisor = psutil.Process(process.pid)
                descendants = supervisor.children(recursive=True)
                # Harness cleanup; reload above exercises graceful lifespan.
                supervisor.terminate()
                for child in descendants:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                _, alive = psutil.wait_procs(descendants + [supervisor], timeout=5)
                for child in alive:
                    child.kill()
            process.wait(timeout=10)
        assert all(not child.is_running() for child in descendants)
