.DEFAULT_GOAL := help

COMPOSE ?= docker compose
PORT ?= 8765
export PORT FILE

.PHONY: help check-docker init dev up down logs shell test build ingest

help:
	@printf '%s\n' \
	  'make init   Build dependencies and initialize persistent project data' \
	  'make dev    Run FastAPI with reload and the TypeScript UI watcher' \
	  'make up     Build and start the packaged app in the background' \
	  'make down   Stop containers; keep project data and dependency volumes' \
	  'make logs   Follow application logs (including the private UI URL)' \
	  'make ingest FILE=traces.jsonl  Import a local JSON/JSONL export' \
	  'make shell  Open a development container with the project mounted' \
	  'make test   Run Python and TypeScript checks inside Docker' \
	  'make build  Build development and packaged application images' \
	  '' \
	  'Requires Docker with Compose v2. Override the port: make dev PORT=9000'

check-docker:
	@$(COMPOSE) version >/dev/null
	@docker info >/dev/null

init: check-docker
	$(COMPOSE) build backend
	$(COMPOSE) run --rm --no-deps backend python -m agent_data_workbench.runtime --initialize-only

# Compose forwards Ctrl-C and stops both processes together.
dev: check-docker
	$(COMPOSE) --profile production stop app
	$(COMPOSE) up --build --remove-orphans --abort-on-container-exit backend ui

up: check-docker
	$(COMPOSE) stop backend ui
	$(COMPOSE) --profile production up --build --detach --wait app
	$(COMPOSE) logs --tail=20 app

down: check-docker
	$(COMPOSE) --profile production down --remove-orphans

logs: check-docker
	$(COMPOSE) --profile production logs --follow backend ui app

shell: init
	$(COMPOSE) run --rm --no-deps backend sh

test: init
	$(COMPOSE) run --rm --no-deps backend sh -c 'python -m pytest -q -p no:cacheprovider && ruff check --no-cache src tests && ruff format --check --no-cache src tests'
	$(COMPOSE) run --rm --no-deps ui sh -c 'npm ci && npm test && npm run format:check && npm run build'

build: check-docker
	$(COMPOSE) --profile production build backend app

ingest: init
	@test -n "$$FILE" || { printf '%s\n' 'Usage: make ingest FILE=path/to/traces.jsonl' >&2; exit 2; }
	@case "$$FILE" in *.jsonl|*.ndjson|*.JSONL|*.NDJSON) suffix=jsonl ;; *) suffix=json ;; esac; \
	$(COMPOSE) run --rm -T --no-deps -e "TRACE_SUFFIX=$$suffix" backend sh -c 'file="/tmp/import.$${TRACE_SUFFIX}"; cat > "$$file" && agent-data-workbench ingest "$$WORKBENCH_PROJECT" "$$file"' < "$$FILE"
