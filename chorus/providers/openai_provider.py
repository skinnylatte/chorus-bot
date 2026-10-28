from __future__ import annotations

from openai import AsyncOpenAI

from .base import Turn


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self.client = AsyncOpenAI()  # reads OPENAI_API_KEY

    async def complete(self, model: str, turns: list[Turn], system: str, max_tokens: int) -> str:
        response = await self.client.responses.create(
            model=model,
            instructions=system,
            input=[{"role": t["role"], "content": t["content"]} for t in turns],
            max_output_tokens=max_tokens,
        )
        return response.output_text

    async def list_models(self) -> list[str]:
        page = await self.client.models.list()
        return sorted(m.id for m in page.data)
