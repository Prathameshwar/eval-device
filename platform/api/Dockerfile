FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace/platform/api
COPY shared/training-contracts /workspace/shared/training-contracts
COPY platform/api/pyproject.toml platform/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY platform/api/src ./src
COPY platform/api/migrations ./migrations
COPY platform/api/alembic.ini ./
RUN uv sync --frozen --no-dev && useradd --create-home --uid 10001 pms && mkdir -p /workspace/platform/api/.local/media && chown -R pms:pms /workspace/platform/api/.local
USER pms
ENV PATH="/workspace/platform/api/.venv/bin:$PATH"
ENV PMS_BIND_HOST=0.0.0.0
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live',timeout=3)"
CMD ["pms-api"]
