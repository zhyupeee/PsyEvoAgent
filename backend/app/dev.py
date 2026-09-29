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
        loop = asyncio.get_running_loop()
        monitor: asyncio.Handle

        def monitor_stop() -> None:
            nonlocal monitor
            # A multiprocessing.Event cannot be awaited. A timer avoids a
            # blocking executor thread surviving a Windows reload/EOF race.
            if stop.is_set():
                server.should_exit = True
            else:
                monitor = loop.call_later(0.05, monitor_stop)

        monitor = loop.call_soon(monitor_stop)
        try:
            await server.serve()
        finally:
            stop.set()
            monitor.cancel()

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
    parser.add_argument("--support-worker", action="store_true")
    parser.add_argument(
        "--stop-on-stdin-eof",
        action="store_true",
        help="For supervised runs: close stdin to stop and await API cleanup",
    )
    args = parser.parse_args()
    if not args.stop_on_stdin_eof:
        from app.dev_instances import replace_previous

        replace_previous("backend", Path(__file__).resolve().parents[1], args.port)
        if args.support_worker:
            from app.dev_support import retire_legacy_workers

            retire_legacy_workers(Path(__file__).resolve().parents[1])
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
    worker_stop, worker_ready = context.Event(), context.Event()
    worker: BaseProcess | None = None

    def start_worker() -> BaseProcess | None:
        if not args.support_worker:
            return None
        from app.dev_support import serve_worker

        worker_stop.clear()
        worker_ready.clear()
        child = context.Process(target=serve_worker, args=(worker_stop, worker_ready, os.getpid()))
        child.start()
        if not worker_ready.wait(timeout=15):
            worker_stop.set()
            child.join(timeout=2)
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
            child.close()
            raise RuntimeError("Support worker did not become ready")
        return child

    def stop_worker() -> None:
        if worker is not None:
            worker_stop.set()
            worker.join(timeout=135)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
                raise RuntimeError("Support worker failed to drain")
            worker.close()

    worker = start_worker()
    process = context.Process(target=serve, args=(args.port, stop))
    process.start()
    process_closed = False
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
            if worker is not None and not worker.is_alive():
                raise RuntimeError("Support worker stopped; restart backend")
            if changes:
                stop_server(process, stop)
                process.close()
                process_closed = True
                stop_worker()
                worker = None
                if shutdown.is_set():
                    # Recreate no child; the closed process is already reaped.
                    print("dev.stopped", flush=True)
                    return
                stop.clear()
                worker = start_worker()
                process = context.Process(target=serve, args=(args.port, stop))
                process.start()
                process_closed = False
                print("dev.reloaded", flush=True)
    finally:
        try:
            if not process_closed:
                stop_server(process, stop)
                process.close()
        finally:
            stop_worker()
    print("dev.stopped", flush=True)


if __name__ == "__main__":
    main()
