FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# Install dependencies first so they cache separately from source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 chorus \
    && chown -R chorus:chorus /app
USER chorus

# Socket Mode: no inbound port. Needs OPENROUTER_API_KEY, SLACK_BOT_TOKEN, SLACK_APP_TOKEN.
CMD ["uv", "run", "--no-sync", "chorus"]
