import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest

from app.dev_instances import matches_server, replace_previous, stop_tree


def test_recognition_limits_replacement_to_service_and_port(tmp_path: Path) -> None:
    backend = [sys.executable, "-m", "app.dev"]
    assert matches_server(backend, "backend", tmp_path, 8000)
    assert not matches_server(backend, "backend", tmp_path, 8001)
    assert matches_server(backend + ["--port=8001"], "backend", tmp_path, 8001)
    assert not matches_server(backend + ["--stop-on-stdin-eof"], "backend", tmp_path, 8000)
    assert not matches_server([sys.executable, "-m", "app.worker"], "backend", tmp_path, 8000)
    vite = ["node", str(tmp_path / "node_modules/vite/bin/vite.js")]
    assert matches_server(vite, "frontend", tmp_path, 3000)
    assert matches_server(vite + ["--port", "3001"], "frontend", tmp_path, 3001)
    assert not matches_server(vite, "frontend", tmp_path, 3001)
    assert not matches_server(vite + ["preview"], "frontend", tmp_path, 3000)
    assert not matches_server(vite + ["build"], "frontend", tmp_path, 3000)
    assert not matches_server(["node", "/other/vite.js"], "frontend", tmp_path, 3000)


def test_unknown_port_owner_is_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSYEVO_ENV", "development")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match="no unrelated process was stopped"):
            replace_previous("backend", tmp_path, port)
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


def test_test_mode_does_not_scan_processes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSYEVO_ENV", "test")

    def forbidden() -> None:
        raise AssertionError("Test mode must not inspect or stop development processes")

    monkeypatch.setattr(psutil, "process_iter", forbidden)
    replace_previous("backend", tmp_path, 8000)


def test_second_backend_start_replaces_supervisor_and_child(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "app"
    shutil.copytree(source, tmp_path / "app", ignore=shutil.ignore_patterns("__pycache__"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith("PSYEVO_")}
    env["PSYEVO_ENV"] = "development"
    processes: list[subprocess.Popen[bytes]] = []
    command = [sys.executable, "-m", "app.dev", "--port", str(port)]
    with (tmp_path / "servers.log").open("wb") as output:
        try:
            for _ in range(2):
                process = subprocess.Popen(
                    command, cwd=tmp_path, env=env, stdout=output, stderr=subprocess.STDOUT
                )
                processes.append(process)
                deadline = time.monotonic() + 30
                with httpx.Client(timeout=1, trust_env=False) as client:
                    while True:
                        assert process.poll() is None, (tmp_path / "servers.log").read_text()
                        old_stopped = len(processes) == 1 or processes[0].poll() is not None
                        if old_stopped:
                            try:
                                response = client.get(f"http://127.0.0.1:{port}/api/v1/health")
                                if response.status_code == 200:
                                    break
                            except httpx.HTTPError:
                                pass
                        assert time.monotonic() < deadline, (tmp_path / "servers.log").read_text()
                        time.sleep(0.1)
                if len(processes) == 1:
                    old_children = psutil.Process(process.pid).children(recursive=True)
                    assert old_children
                    other_checkout = tmp_path / "other-checkout"
                    shutil.copytree(tmp_path / "app", other_checkout / "app")
                    refused = subprocess.run(
                        command,
                        cwd=other_checkout,
                        env=env,
                        capture_output=True,
                        timeout=20,
                    )
                    assert refused.returncode != 0
                    assert b"no unrelated process was stopped" in refused.stderr
                    assert process.poll() is None
            assert all(not child.is_running() for child in old_children)
            assert "dev.replace stopping previous server" in (tmp_path / "servers.log").read_text()
        finally:
            for process in processes:
                if process.poll() is None:
                    stop_tree(psutil.Process(process.pid))
                process.wait(timeout=15)
