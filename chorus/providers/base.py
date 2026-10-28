"""Common shape every provider adapter implements."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict


class Turn(TypedDict):
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str
    label: str
    emoji: str

    @property
    def heading(self) -> str:
        return f"{self.emoji} {self.label}".strip()


class Provider(Protocol):
    """One adapter per vendor. `complete` returns the final text for the whole conversation."""

    name: str

    async def complete(
        self,
        model: str,
        turns: list[Turn],
        system: str,
        max_tokens: int,
    ) -> str: ...

    async def list_models(self) -> list[str]: ...
