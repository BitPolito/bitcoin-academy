FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

WORKDIR /app

# Keep the managed environment outside /app: the development Compose override
# bind-mounts the source tree there and must not hide the installed environment.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

# Install third-party packages in a cacheable layer, strictly from uv.lock.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project

# Install the project only after its package exists, then copy runtime assets.
COPY app ./app
RUN uv sync --locked

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
