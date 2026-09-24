"""Replace only identifiable development servers from this checkout."""

import argparse
import os
import socket
import sys
from contextlib import suppress
from pathlib import Path
from typing import Literal

import psutil

Service = Literal["backend", "frontend"]


def command_port(command: list[str], default: int) -> int:
    for index, argument in enumerate(command):
        if argument == "--port":
            return int(command[index + 1])
        if argument.startswith("--port="):
            return int(argument.split("=", 1)[1])
    return default


def matches_server(command: list[str], service: Service, directory: Path, port: int) -> bool:
    if service == "backend":
        return (
            len(command) >= 3
            and command[1:3] == ["-m", "app.dev"]
            and "--stop-on-stdin-eof" not in command
            and command_port(command[3:], 8000) == port
        )
    return (
        len(command) >= 2
        and (directory / command[1]).resolve()
        == (directory / "node_modules/vite/bin/vite.js").resolve()
        and not any(argument in {"build", "preview"} for argument in command[2:])
        and command_port(command[2:], 3000) == port
    )


def stop_tree(process: psutil.Process) -> None:
    children = process.children(recursive=True)
    print(f"dev.replace stopping previous server pid={process.pid}", flush=True)
    with suppress(psutil.NoSuchProcess):
        process.terminate()
    # SIGTERM lets app.dev clean up on POSIX. Windows terminate is immediate;
    # stop the supervisor first so it cannot spawn another reload child.
    if os.name != "nt":
        psutil.wait_procs([process], timeout=12)
    for child in children:
        with suppress(psutil.NoSuchProcess):
            child.terminate()
    _, alive = psutil.wait_procs([process, *children], timeout=5)
    for remaining in alive:
        with suppress(psutil.NoSuchProcess):
            remaining.kill()
    _, alive = psutil.wait_procs(alive, timeout=5)
    if alive:
        raise RuntimeError("Previous development server did not stop; restart refused")


def replace_previous(
    service: Service, directory: Path, port: int, *, allow_port_fallback: bool = False
) -> None:
    # Engineering checks must never take over existing development services.
    if os.environ.get("PSYEVO_ENV", "development") != "development":
        return
    directory = directory.resolve()
    current = psutil.Process()
    protected = {current.pid, *(parent.pid for parent in current.parents())}
    candidates: dict[int, psutil.Process] = {}
    for process in psutil.process_iter():
        try:
            if (
                process.pid not in protected
                and Path(process.cwd()).resolve() == directory
                and matches_server(process.cmdline(), service, directory, port)
                and process.environ().get("PSYEVO_ENV", "development") == "development"
                and not process.environ().get("PSYEVO_TEST_WEB_PORT")
            ):
                candidates[process.pid] = process
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError, IndexError):
            continue
    for process in candidates.values():
        with suppress(psutil.NoSuchProcess):
            if not any(parent.pid in candidates for parent in process.parents()):
                stop_tree(process)
    # Unknown owners are never killed, and app.dev must not sit watching after
    # a failed bind. Uvicorn/Vite still own the final bind (and any startup race).
    with socket.socket() as probe:
        if sys.platform == "win32":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            if service == "frontend" and allow_port_fallback:
                print(
                    f"dev.replace port {port} is in use by another process; "
                    "Vite will choose a free port",
                    flush=True,
                )
                return
            raise RuntimeError(
                f"Port {port} is still in use; no unrelated process was stopped"
            ) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-port", type=int, required=True)
    parser.add_argument("--allow-port-fallback", action="store_true")
    args = parser.parse_args()
    replace_previous(
        "frontend",
        Path(__file__).resolve().parents[2] / "frontend",
        args.frontend_port,
        allow_port_fallback=args.allow_port_fallback,
    )


if __name__ == "__main__":
    main()
