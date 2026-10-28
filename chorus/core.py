"""Fan one conversation out to every configured model, yielding results as they finish."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from .config import Config
from .providers import ModelSpec, Provider, Turn, available_providers

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Result:
    spec: ModelSpec
    text: str
    seconds: float
    error: str | None = None


class Chorus:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.providers: dict[str, Provider] = available_providers()
        self.models = [m for m in config.models if m.provider in self.providers]
        skipped = [m for m in config.models if m.provider not in self.providers]
        for m in skipped:
            log.warning("Model %r will not run (provider %r has no credentials)", m.label, m.provider)
        if not self.models:
            raise SystemExit("No runnable models: set at least one provider API key.")

    async def _one(self, spec: ModelSpec, turns: list[Turn]) -> Result:
        provider = self.providers[spec.provider]
        started = time.monotonic()
        try:
            text = await provider.complete(
                spec.model, turns, self.config.system_prompt, self.config.max_output_tokens
            )
            return Result(spec, text, time.monotonic() - started)
        except Exception as exc:  # one bad provider must not sink the others
            log.exception("%s failed", spec.label)
            return Result(spec, "", time.monotonic() - started, error=f"{type(exc).__name__}: {exc}")

    async def ask_per_model(
        self,
        turns_for: Callable[[ModelSpec], list[Turn]],
        specs: list[ModelSpec] | None = None,
    ) -> AsyncIterator[Result]:
        """Yield each model's result as it completes; each model gets its own history.

        `specs` limits the run to a subset of the configured models.
        """
        tasks = [asyncio.create_task(self._one(spec, turns_for(spec))) for spec in (specs or self.models)]
        for done in asyncio.as_completed(tasks):
            yield await done

    async def ask(self, turns: list[Turn]) -> AsyncIterator[Result]:
        """Yield each model's result in the order they complete (same prompt to all)."""
        async for r in self.ask_per_model(lambda _spec: turns):
            yield r

    async def ask_all(self, turns: list[Turn]) -> list[Result]:
        """Collect every result, in models.yaml order."""
        results = [r async for r in self.ask(turns)]
        order = {spec: i for i, spec in enumerate(self.models)}
        return sorted(results, key=lambda r: order[r.spec])
