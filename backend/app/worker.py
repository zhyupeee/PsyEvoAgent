"""Standalone Worker: Support or explicitly isolated durable-job recovery probe."""

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
    parser.add_argument("--jobs-probe", action="store_true", help="Consume synthetic STEP03 jobs")
    parser.add_argument("--once", action="store_true", help="One job recovery scan")
    parser.add_argument("--probe-pause", choices=["after_claim", "before_commit", "after_commit"])
    args = parser.parse_args()
    if (args.support and args.jobs_probe) or (
        (args.once or args.probe_pause) and not args.jobs_probe
    ):
        parser.error("Job probe flags require a separate --jobs-probe invocation")

    async def serve() -> None:
        stop = asyncio.Event()
        if args.check:
            stop.set()
        if args.jobs_probe:
            from app.job_worker import consume as consume_jobs

            await consume_jobs(stop, once=args.once, pause=args.probe_pause)
        elif args.support:
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
