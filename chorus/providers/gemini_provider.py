from __future__ import annotations

import os

from google import genai
from google.genai import types

from .base import Turn


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    async def complete(self, model: str, turns: list[Turn], system: str, max_tokens: int) -> str:
        contents = [
            types.Content(
                role="user" if t["role"] == "user" else "model",
                parts=[types.Part(text=t["content"])],
            )
            for t in turns
        ]
        response = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text or "_(empty response)_"

    async def list_models(self) -> list[str]:
        names = []
        async for m in await self.client.aio.models.list():
            names.append(m.name.removeprefix("models/"))
        return sorted(names)
