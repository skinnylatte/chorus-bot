"""Load models.yaml and .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .providers import ModelSpec

DEFAULT_SYSTEM = "Answer directly and concisely."


@dataclass(frozen=True)
class Config:
    system_prompt: str
    max_output_tokens: int
    cross_model_context: bool
    models: list[ModelSpec]


def load_config(path: str | os.PathLike | None = None) -> Config:
    load_dotenv()  # no-op if there is no .env
    cfg_path = Path(path or os.environ.get("CHORUS_MODELS_FILE", "models.yaml"))
    raw = yaml.safe_load(cfg_path.read_text()) or {}

    models = [
        ModelSpec(
            provider=str(m["provider"]).lower(),
            model=str(m["model"]),
            label=str(m.get("label", m["model"])),
            emoji=str(m.get("emoji", "")),
        )
        for m in raw.get("models", [])
    ]
    if not models:
        raise SystemExit(f"{cfg_path}: no models configured")

    return Config(
        system_prompt=str(raw.get("system_prompt", DEFAULT_SYSTEM)).strip(),
        max_output_tokens=int(raw.get("max_output_tokens", 4096)),
        cross_model_context=bool(raw.get("cross_model_context", True)),
        models=models,
    )
