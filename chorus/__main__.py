"""CLI.

  chorus                 run the Slack bot (needs SLACK_BOT_TOKEN + SLACK_APP_TOKEN)
  chorus ask "prompt"    run the prompt through every configured model from the terminal
  chorus list-models     print the model IDs each configured provider currently serves
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import load_config


async def _ask(prompt: str) -> None:
    from .core import Chorus

    chorus = Chorus(load_config())
    async for r in chorus.ask([{"role": "user", "content": prompt}]):
        print(f"\n=== {r.spec.heading}  ({r.seconds:.1f}s) ===")
        print(f"ERROR: {r.error}" if r.error else r.text)


async def _list_models(only: str | None) -> None:
    from .providers import available_providers

    load_config()  # loads .env
    for name, provider in available_providers().items():
        if only and name != only:
            continue
        print(f"\n[{name}]")
        try:
            for mid in await provider.list_models():
                print(f"  {mid}")
        except Exception as exc:
            print(f"  error: {exc}")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="chorus", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    ask = sub.add_parser("ask", help="query all models from the terminal")
    ask.add_argument("prompt", nargs="+")
    lm = sub.add_parser("list-models", help="list model IDs per provider")
    lm.add_argument("provider", nargs="?", choices=["anthropic", "openai", "gemini", "openrouter"])
    args = parser.parse_args(argv)

    if args.cmd == "ask":
        asyncio.run(_ask(" ".join(args.prompt)))
    elif args.cmd == "list-models":
        asyncio.run(_list_models(args.provider))
    else:
        from .bot import run
        try:
            asyncio.run(run())
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    main()
