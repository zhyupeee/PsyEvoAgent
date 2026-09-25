"""Explicit standalone lifecycle probe, not a job consumer or scheduler."""

import argparse
import asyncio

from app.config import load_settings


async def run_worker(stop: asyncio.Event) -> None:
    load_settings()
    print("worker.started consumers=0", flush=True)
    try:
        await stop.wait()
    finally:
        print("worker.stopped consumers=0", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Start, clean up and exit immediately")
    parser.add_argument("--support", action="store_true", help="Consume isolated fake support runs")
    args = parser.parse_args()

    async def serve() -> None:
        stop = asyncio.Event()
        if args.check:
            stop.set()
        if args.support:
            from app.run_worker import consume

            await consume(stop)
        else:
            await run_worker(stop)

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
