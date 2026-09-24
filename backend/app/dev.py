"""Local Uvicorn reload with cooperative shutdown, including Windows.

Uses watchfiles and Uvicorn's public server API; no consumer is started here.
"""

import argparse
import asyncio
import multiprocessing
import os
import signal
import sys
import threading
from contextlib import suppress
from multiprocessing.process import BaseProcess
from multiprocessing.synchronize import Event
from pathlib import Path
from types import FrameType

import uvicorn
from watchfiles import PythonFilter, watch


def serve(port: int, stop: Event) -> None:
    server = uvicorn.Server(
        uvicorn.Config(
            "app.main:create_app",
            factory=True,
            host="127.0.0.1",
            port=port,
            access_log=False,
            timeout_graceful_shutdown=5,
        )
    )

    async def run() -> None:
        async def monitor_stop() -> None:
            await asyncio.to_thread(stop.wait)
            server.should_exit = True

        monitor = asyncio.create_task(monitor_stop())
        try:
            await server.serve()
        finally:
            stop.set()
            monitor.cancel()
            with suppress(asyncio.CancelledError):
                await monitor

    asyncio.run(run())


def stop_server(process: BaseProcess, stop: Event) -> None:
    if not process.is_alive():
        # Import/startup failures are recoverable on the next source change.
        process.join()
        return
    stop.set()
    process.join(timeout=10)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        raise RuntimeError("Development API did not shut down gracefully; reload refused")
    if process.exitcode != 0:
        raise RuntimeError(f"Development API exited with code {process.exitcode}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument(
        "--stop-on-stdin-eof",
        action="store_true",
        help="For supervised runs: close stdin to stop and await API cleanup",
    )
    args = parser.parse_args()
    if not args.stop_on_stdin_eof:
        from app.dev_instances import replace_previous

        replace_previous("backend", Path(__file__).resolve().parents[1], args.port)
    shutdown = threading.Event()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, request_stop)
    if args.stop_on_stdin_eof:
        # A pending blocking pipe read can stall Windows child initialization.
        # Poll between watcher ticks instead; Python 3.12 supports Windows pipes.
        os.set_blocking(sys.stdin.fileno(), False)

    context = multiprocessing.get_context("spawn")
    stop = context.Event()
    process = context.Process(target=serve, args=(args.port, stop))
    process.start()
    try:
        for changes in watch(
            args.reload_dir,
            watch_filter=PythonFilter(),
            stop_event=shutdown,
            debounce=200,
            step=50,
            rust_timeout=500,
            yield_on_timeout=True,
            raise_interrupt=False,
        ):
            if args.stop_on_stdin_eof:
                try:
                    if os.read(sys.stdin.fileno(), 4096) == b"":
                        shutdown.set()
                except BlockingIOError:
                    pass
            if shutdown.is_set():
                break
            if changes:
                stop_server(process, stop)
                process.close()
                if shutdown.is_set():
                    break
                stop.clear()
                process = context.Process(target=serve, args=(args.port, stop))
                process.start()
                print("dev.reloaded", flush=True)
    finally:
        stop_server(process, stop)
        process.close()
    print("dev.stopped", flush=True)


if __name__ == "__main__":
    main()
