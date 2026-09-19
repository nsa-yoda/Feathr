FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --create-home app

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev

COPY docs ./docs
COPY .env.example ./
RUN chown -R app:app /app

USER 10001:10001
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "event_platform.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
