# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.14.7
ARG NODE_VERSION=24.20.0
ARG UV_VERSION=0.12.10

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM node:${NODE_VERSION}-bookworm-slim AS node

FROM node AS frontend
WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY ui/ ./
RUN npm run build

FROM python:${PYTHON_VERSION}-slim-trixie AS python-base
COPY --from=uv /uv /uvx /usr/local/bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    WORKBENCH_PROJECT=/data/project \
    WORKBENCH_HOST=0.0.0.0 \
    WORKBENCH_PORT=8765 \
    WORKBENCH_ORIGIN=http://127.0.0.1:8765
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 workbench \
    && useradd --uid 10001 --gid workbench --create-home workbench \
    && mkdir -p /app /data \
    && chown workbench:workbench /app /data
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./

FROM python-base AS production-dependencies
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY src/ ./src/
COPY --from=frontend /app/src/agent_data_workbench/web/ ./src/agent_data_workbench/web/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM python-base AS development
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-install-project
COPY --chown=workbench:workbench src/ ./src/
COPY --chown=workbench:workbench tests/ ./tests/
COPY --chown=workbench:workbench ui/ ./ui/
COPY --from=frontend --chown=workbench:workbench /app/ui/node_modules/ ./ui/node_modules/
COPY --from=frontend --chown=workbench:workbench /app/src/agent_data_workbench/web/ ./src/agent_data_workbench/web/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked
USER workbench
EXPOSE 8765
CMD ["python", "-m", "agent_data_workbench.runtime", "--reload"]

FROM python-base AS runtime
COPY --from=production-dependencies /opt/venv /opt/venv
USER workbench
EXPOSE 8765
CMD ["python", "-m", "agent_data_workbench.runtime"]
