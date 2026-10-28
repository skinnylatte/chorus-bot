"""Provider registry. A provider is only constructed if its API key is present."""
from __future__ import annotations

import logging
import os

from .base import ModelSpec, Provider, Turn

log = logging.getLogger(__name__)

# provider name -> (env var that must be set, factory)
_REGISTRY: dict[str, tuple[str, str]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "chorus.providers.anthropic_provider:AnthropicProvider"),
    "openai": ("OPENAI_API_KEY", "chorus.providers.openai_provider:OpenAIProvider"),
    "gemini": ("GEMINI_API_KEY", "chorus.providers.gemini_provider:GeminiProvider"),
    "openrouter": ("OPENROUTER_API_KEY", "chorus.providers.openrouter_provider:OpenRouterProvider"),
}


def _load(path: str) -> type:
    module_name, _, cls_name = path.partition(":")
    module = __import__(module_name, fromlist=[cls_name])
    return getattr(module, cls_name)


def available_providers() -> dict[str, Provider]:
    """Instantiate every provider whose credentials are configured."""
    providers: dict[str, Provider] = {}
    for name, (env_var, path) in _REGISTRY.items():
        if not os.environ.get(env_var):
            log.warning("Skipping provider %r: %s is not set", name, env_var)
            continue
        providers[name] = _load(path)()
    return providers


__all__ = ["ModelSpec", "Provider", "Turn", "available_providers"]
