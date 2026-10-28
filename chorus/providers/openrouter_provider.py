"""OpenRouter: one key, every vendor. Uses OpenRouter's OpenAI-compatible chat endpoint."""
from __future__ import annotations

import os

from openai import AsyncOpenAI

from .base import Turn

BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self) -> None:
        # Optional attribution headers shown on OpenRouter's activity page.
        headers = {"X-Title": os.environ.get("OPENROUTER_APP_NAME", "chorus")}
        if site := os.environ.get("OPENROUTER_SITE_URL"):
            headers["HTTP-Referer"] = site
        self.client = AsyncOpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"], base_url=BASE_URL, default_headers=headers
        )

    async def complete(self, model: str, turns: list[Turn], system: str, max_tokens: int) -> str:
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, *turns],
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        text = choice.message.content or "_(empty response)_"
        if choice.finish_reason == "length":
            text += "\n\n_[truncated: hit max_output_tokens]_"
        return text

    async def list_models(self) -> list[str]:
        page = await self.client.models.list()
        return sorted(m.id for m in page.data if not m.id.endswith(":batch"))
