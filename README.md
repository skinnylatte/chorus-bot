# chorus

A Slackbot that lives in a channel. Anyone can `@chorus <prompt>` and get back one reply
per configured model, in a thread, so the differences between models are easy to see.

```
@chorus tell me the name of your model
  └ chorus: Getting responses from all models...
  └ chorus: 🧠 Claude Opus 5 (2.8s)         I'm Claude, made by Anthropic.
  └ chorus: ⚡ xAI Grok 4.7 (3.0s)          I'm Grok, a model built by xAI.
  └ chorus: 🤖 OpenAI GPT-6 Astra (3.5s)    I'm ChatGPT, an AI model created by OpenAI.
  └ chorus: 🔷 Google Gemini 4 Argon (3.8s) I am Gemini 4 Argon, built by Google.
  └ chorus: ☁️ Qwen3.8 Flash (4.2s)         I am Qwen, developed by Alibaba's Tongyi Lab.
```

Every model is reached through [OpenRouter](https://openrouter.ai) with a single key, so
adding a model is one entry in a YAML file. Direct Anthropic, OpenAI, and Gemini adapters
are included if you'd rather bypass OpenRouter for some of them.

## Using it

**Ask everyone.** Mention the bot in a channel it's been invited to, or DM it.

**Follow up.** Mention it again *inside the thread*. Each model continues its own conversation,
and is also shown what the other models said in the previous round, clearly labelled, so you can
ask things like `claude: what do you think of Grok's answer?`.

**Ask one or a few.** Start the prompt with a name and a colon:

```
@chorus claude: expand on that
@chorus gemini, grok: do you agree with each other?
```

Names match loosely against the labels in `models.yaml` (`claude`, `gpt`, `gemini`, `grok`, `qwen`…).
A prefix that matches nothing, like `Question: …`, is treated as ordinary text.

## Setup

1. **Install** (needs [uv](https://docs.astral.sh/uv/)):

   ```sh
   uv sync
   ```

2. **Create the Slack app.** Go to <https://api.slack.com/apps> → *Create New App* →
   *From a manifest* → choose YAML → paste `slack_manifest.yaml`. Then collect two tokens:
   - *Basic Information* → *App-Level Tokens* → *Generate Token and Scopes* → add scope
     `connections:write` → copy the `xapp-…` token (shown once).
   - *OAuth & Permissions* → *Install to Workspace* → copy the **Bot User OAuth Token** (`xoxb-…`).

   Socket Mode is enabled in the manifest, so no public URL or ngrok is needed.

3. **Keys.** Copy `.env.example` to `.env` and fill in:

   ```
   OPENROUTER_API_KEY=sk-or-...
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   ```

   Direct vendor keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`) are only needed
   for `models.yaml` entries that use those providers. Providers without a key are skipped at startup.

4. **Run:**

   ```sh
   uv run chorus
   ```

   Then invite the bot to a channel (`/invite @chorus`) and mention it.

## Models

Edit `models.yaml`. Each entry is a provider, an exact model ID, a label, and an emoji.
OpenRouter IDs look like `vendor/model`. To see what a provider currently serves:

```sh
uv run chorus list-models                 # all configured providers
uv run chorus list-models openrouter      # ~450 IDs; pipe to grep
```

`models.yaml` also holds the shared system prompt, the output token cap, and
`cross_model_context` (set to `false` to stop models seeing each other's earlier answers).

To test without Slack:

```sh
uv run chorus ask "What is the capital of France?"
```

## Deploying on Railway

The bot uses Socket Mode, so it is a background worker: no port, no domain, no healthcheck.
A `Dockerfile` and `railway.toml` are included and Railway picks them up automatically.

```sh
brew install railway && railway login
railway init
railway variables --set OPENROUTER_API_KEY=... --set SLACK_BOT_TOKEN=... --set SLACK_APP_TOKEN=...
railway up
railway logs        # expect "Models: ..." then "Bolt app is running!"
```

Or push to GitHub and use *New Project → Deploy from GitHub repo*, adding the three variables
under the service's *Variables* tab. Don't generate a domain; there is nothing to serve.
Only run one instance at a time: two copies with the same tokens both answer every mention.

## Security notes

- **Anyone in the workspace who can mention the bot can spend your OpenRouter credits.**
  Set a credit limit on the key in OpenRouter; that is the hard cap. To restrict the bot to
  specific channels, set `CHORUS_ALLOWED_CHANNELS` to a comma-separated list of channel IDs
  (DMs remain allowed).
- Model output is escaped before posting, so a model cannot trigger `@channel`, `@here`,
  or user pings, or inject fake links.
- Thread text, including other users' messages and other models' answers, is sent to the
  models as context. Don't use the bot in channels where that is a problem.
- Secrets live only in `.env` (git- and docker-ignored) or in Railway's variables. The container
  runs as a non-root user.

## Adding a provider

Add a file in `chorus/providers/` with a class that has `name`,
`async complete(model, turns, system, max_tokens) -> str`, and `async list_models() -> list[str]`,
then register it in `chorus/providers/__init__.py` with the env var that must be set for it to load.
`openrouter_provider.py` is the smallest example.

## Layout

```
models.yaml                 which models run, system prompt, output cap, cross-model context
slack_manifest.yaml         one-paste Slack app definition
chorus/bot.py               Slack events → thread replies; targeting; per-model history rebuild
chorus/core.py              fans a conversation out to the selected models concurrently
chorus/providers/           openrouter (default) plus direct anthropic, openai, gemini adapters
chorus/__main__.py          CLI: run bot, `ask`, `list-models`
Dockerfile, railway.toml    deployment
```

## License

MIT. See `LICENSE`.
