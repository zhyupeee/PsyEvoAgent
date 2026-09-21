"""Test-only scripted provider. No SDK, network, retries, or production adapter."""

import asyncio
from dataclasses import dataclass


@dataclass
class FakeProvider:
    outcome: str | Exception
    calls: int = 0

    async def invoke(self) -> str:
        self.calls += 1
        await asyncio.sleep(0)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome
