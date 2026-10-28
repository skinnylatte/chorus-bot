from __future__ import annotations

import anthropic

from .base import Turn


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        # Reads ANTHROPIC_API_KEY (or an `ant auth login` profile) from the environment.
        self.client = anthropic.AsyncAnthropic()

    async def complete(self, model: str, turns: list[Turn], system: str, max_tokens: int) -> str:
        # Thinking is adaptive by default on current models, so no `thinking` param is sent.
        # `fallbacks="default"` re-runs the request on another Claude model if a safety
        # classifier declines it, so the thread still gets an answer.
        response = await self.client.beta.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=turns,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            detail = ""
            if response.stop_details and response.stop_details.explanation:
                detail = f" ({response.stop_details.explanation})"
            return f"_Declined to answer{detail}._"

        text = "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason == "max_tokens":
            text += "\n\n_[truncated: hit max_output_tokens]_"
        return text

    async def list_models(self) -> list[str]:
        return [m.id async for m in self.client.models.list()]
