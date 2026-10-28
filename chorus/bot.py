"""Slack front end. @mention chorus in a channel (or DM it) and every model replies in the thread.

Follow-ups: mention chorus again inside the thread. Each model gets its own earlier answers
back as conversation history, plus (if cross_model_context is on) the other models' answers,
clearly labelled, so you can ask "what do you think of Grok's answer?".

Targeting: start the prompt with one or more model names and a colon to ask only those models:
    @chorus claude: expand on that
    @chorus gemini, grok: do you agree with each other?
Names match loosely against the labels in models.yaml (case-insensitive substring).
"""
from __future__ import annotations

import logging
import os
import re

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from .core import Chorus, Result
from .providers import ModelSpec, Turn

log = logging.getLogger(__name__)

MENTION_RE = re.compile(r"<@[^>]+>")
TARGET_RE = re.compile(r"^\s*((?:@?[\w.\-]+\s*,\s*)*@?[\w.\-]+)\s*:\s*(.+)$", re.S)
SLACK_TEXT_LIMIT = 12_000  # Slack allows ~40k chars per message; keep replies readable

WORKING_TEXT = "Getting responses from all models..."


def allowed_channels() -> set[str]:
    """CHORUS_ALLOWED_CHANNELS=C0123,C0456 restricts the bot to those channel IDs (DMs always allowed)."""
    raw = os.environ.get("CHORUS_ALLOWED_CHANNELS", "")
    return {c.strip() for c in raw.split(",") if c.strip()}


# --------------------------------------------------------------------------- formatting

def slack_escape(text: str) -> str:
    """Neutralise Slack control sequences: <!channel>, <!here>, <@U..>, <#C..>, <url|label>."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_to_mrkdwn(text: str) -> str:
    """Best-effort Markdown -> Slack mrkdwn. Escapes first, then rebuilds only safe links."""
    text = slack_escape(text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)  # headings -> bold
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)                          # **bold** -> *bold*
    text = re.sub(r"(?<![\w*])__(.+?)__(?![\w*])", r"_\1_", text)           # __x__ -> _x_
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)          # - item -> • item
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", text)  # [t](url) -> <url|t>
    return text


def heading_prefix(spec: ModelSpec) -> str:
    return f"*{spec.heading}*"


def format_result(r: Result) -> str:
    if r.error:
        body = f"_error: {slack_escape(r.error[:300])}_"
    else:
        body = md_to_mrkdwn(r.text.strip() or "_(empty)_")
    return f"{heading_prefix(r.spec)} _({r.seconds:.1f}s)_\n{body}"


def chunk(text: str, limit: int = SLACK_TEXT_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, buf = [], ""
    for para in text.split("\n"):
        if len(buf) + len(para) + 1 > limit and buf:
            parts.append(buf)
            buf = ""
        buf += ("\n" if buf else "") + para
    if buf:
        parts.append(buf)
    return parts


# --------------------------------------------------------------------------- targeting

def match_models(name: str, specs: list[ModelSpec]) -> list[ModelSpec]:
    n = name.lower().lstrip("@")
    return [s for s in specs if n in s.label.lower() or n in s.model.lower()]


def parse_targets(prompt: str, specs: list[ModelSpec]) -> tuple[list[ModelSpec], str, list[str]]:
    """Split a leading `name[, name]:` prefix off the prompt.

    Returns (models to run, remaining prompt, names that matched nothing).
    If *no* name matches any model, the prefix is treated as ordinary text ("Question: ...").
    """
    m = TARGET_RE.match(prompt)
    if not m:
        return specs, prompt, []
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    matched: list[ModelSpec] = []
    unknown: list[str] = []
    for name in names:
        hits = match_models(name, specs)
        if hits:
            matched.extend(h for h in hits if h not in matched)
        else:
            unknown.append(name)
    if not matched:
        return specs, prompt, []
    return matched, m.group(2).strip(), unknown


# --------------------------------------------------------------------------- thread history

def _split_reply(text: str, specs: list[ModelSpec]) -> tuple[ModelSpec, str] | None:
    """If a bot message is a model reply, return (which model, body)."""
    for spec in specs:
        if text.startswith(heading_prefix(spec)):
            body = text.split("\n", 1)[1] if "\n" in text else ""
            return spec, body
    return None


def thread_history(
    replies: list[dict],
    bot_user_id: str,
    spec: ModelSpec,
    all_specs: list[ModelSpec],
    cross_context: bool = True,
) -> list[Turn]:
    """Rebuild one model's conversation from a Slack thread.

    Human messages become user turns (minus the @mention and any `name:` targeting prefix).
    This model's own replies become assistant turns. With cross_context, other models'
    replies from the previous round are quoted at the top of the next user turn.
    """
    turns: list[Turn] = []
    others: dict[str, str] = {}  # label -> answer, for the round in progress

    def flush_others() -> str:
        if not cross_context or not others:
            return ""
        block = "\n\n".join(f"{label}:\n{answer}" for label, answer in others.items())
        others.clear()
        return (
            "[For context, other models answered the previous message as follows. "
            "These are not your answers.]\n\n"
            f"{block}\n\n[End of other models' answers.]\n\n"
        )

    for msg in replies:
        text = (msg.get("text") or "").strip()
        is_bot = msg.get("user") == bot_user_id or msg.get("bot_id")
        if is_bot:
            hit = _split_reply(text, all_specs)
            if not hit:
                continue
            who, body = hit
            body = body.strip()
            if body.startswith("_error:"):
                continue
            if who == spec:
                if turns and turns[-1]["role"] == "assistant":
                    turns[-1]["content"] += "\n" + body  # chunked reply
                elif turns:
                    turns.append({"role": "assistant", "content": body})
            else:
                others[who.label] = (others[who.label] + "\n" + body) if who.label in others else body
            continue

        clean = MENTION_RE.sub("", text).strip()
        if not clean:
            continue
        _, clean, _ = parse_targets(clean, all_specs)
        clean = flush_others() + clean
        if turns and turns[-1]["role"] == "user":
            turns[-1]["content"] += "\n\n" + clean
        else:
            turns.append({"role": "user", "content": clean})

    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    if turns and turns[-1]["role"] == "assistant":
        turns.pop()
    return turns


# --------------------------------------------------------------------------- app

def build_app(chorus: Chorus) -> AsyncApp:
    app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])
    state: dict[str, str] = {}

    async def bot_user_id(client) -> str:
        if "bot_user_id" not in state:
            auth = await client.auth_test()
            state["bot_user_id"] = auth["user_id"]
        return state["bot_user_id"]

    allow = allowed_channels()

    async def handle(event: dict, client, say) -> None:
        channel = event["channel"]
        thread_ts = event.get("thread_ts") or event["ts"]
        if allow and channel not in allow and event.get("channel_type") != "im":
            log.info("Ignoring mention in non-allowlisted channel %s", channel)
            return
        raw_prompt = MENTION_RE.sub("", event.get("text") or "").strip()
        if not raw_prompt:
            names = ", ".join(s.label for s in chorus.models)
            await say(
                text=f"Ask me something and every model will answer. "
                     f"Start with a name and a colon to ask just one, e.g. `claude: ...`\n"
                     f"Models: {names}",
                thread_ts=thread_ts,
            )
            return

        targets, prompt, unknown = parse_targets(raw_prompt, chorus.models)
        if unknown:
            names = ", ".join(s.label for s in chorus.models)
            await say(
                text=f"I don't have a model matching: {', '.join(unknown)}.\nModels: {names}",
                thread_ts=thread_ts,
            )
            return

        me = await bot_user_id(client)
        replies: list[dict] = []
        if event.get("thread_ts"):
            resp = await client.conversations_replies(channel=channel, ts=thread_ts, limit=200)
            replies = resp.get("messages", [])

        if len(targets) == len(chorus.models):
            await say(text=WORKING_TEXT, thread_ts=thread_ts)
        else:
            await say(
                text=f"Getting responses from {', '.join(t.label for t in targets)}...",
                thread_ts=thread_ts,
            )

        def turns_for(spec: ModelSpec) -> list[Turn]:
            history = thread_history(
                replies, me, spec, chorus.models, chorus.config.cross_model_context
            )
            return history or [{"role": "user", "content": prompt}]

        async for result in chorus.ask_per_model(turns_for, specs=targets):
            for piece in chunk(format_result(result)):
                await say(text=piece, thread_ts=thread_ts, mrkdwn=True)

    @app.event("app_mention")
    async def on_mention(event, client, say):
        await handle(event, client, say)

    @app.event("message")
    async def on_message(event, client, say):
        # Only direct messages; channel traffic requires an explicit @mention.
        if event.get("channel_type") == "im" and not event.get("bot_id") and "subtype" not in event:
            await handle(event, client, say)

    return app


async def run() -> None:
    from .config import load_config

    chorus = Chorus(load_config())
    log.info("Models: %s", ", ".join(m.label for m in chorus.models))
    app = build_app(chorus)
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()
