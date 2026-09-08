.DEFAULT_GOAL := help

MODE ?= docker
UV ?= uv
WORKBENCH_PROJECT ?= runs/workbench
export WORKBENCH_PROJECT

COMPOSE ?= docker compose
PORT ?= 8765
LAYOUT ?= runs
export PORT FILE DIR LAYOUT SOURCE_ROOT

.PHONY: help check-docker init dev up down logs shell test build ingest

help:
	@printf '%s\n' \
	  'make init   Build dependencies and initialize persistent project data' \
	  'make dev    Run FastAPI with reload and the TypeScript UI watcher' \
	  'make up     Build and start the packaged app in the background' \
	  'make down   Stop containers; keep project data and dependency volumes' \
	  'make logs   Follow application logs (including the private UI URL)' \
	  'make ingest DIR=./traces  Import JSON/JSONL run files recursively' \
	  'make shell  Open a development container with the project mounted' \
	  'make test   Run Python and TypeScript checks inside Docker' \
	  'make build  Build development and packaged application images' \
	  '' \
	  'Default: Docker Compose v2. Override the port: make dev PORT=9000' \
	  'Native CLI logins + Harbor: make init MODE=native; make dev MODE=native' \
	  'Native mode needs uv, Node 24.15+, and Docker for Harbor environments.'

check-docker:
	@$(COMPOSE) version >/dev/null
	@docker info >/dev/null

ifeq ($(MODE),native)
init:
	npm ci --prefix ui
	npm --prefix ui run build
	$(UV) sync --locked
	$(UV) tool install harbor
	$(UV) run python -m agent_data_workbench.workbench.runtime --initialize-only

dev:
	@set -eu; \
	npm --prefix ui run dev & ui_pid=$$!; \
	trap 'kill "$$ui_pid" 2>/dev/null || true' EXIT INT TERM; \
	WORKBENCH_PORT=$(PORT) $(UV) run python -m agent_data_workbench.workbench.runtime --reload
else
init: check-docker
	$(COMPOSE) build backend
	$(COMPOSE) run --rm --no-deps backend python -m agent_data_workbench.workbench.runtime --initialize-only

# Compose forwards Ctrl-C and stops both processes together.
dev: check-docker
	$(COMPOSE) --profile production stop app
	$(COMPOSE) up --build --remove-orphans --abort-on-container-exit backend ui

endif

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
	@set -eu; \
	if [ -n "$${DIR:-}" ] && [ -n "$${FILE:-}" ]; then printf '%s\n' 'Supply DIR or FILE, not both' >&2; exit 2; fi; \
	input=$${DIR:-$${FILE:-}}; \
	if [ -z "$$input" ]; then printf '%s\n' 'Usage: make ingest DIR=./traces [LAYOUT=runs|records]' >&2; exit 2; fi; \
	work=$$(mktemp -d "$${TMPDIR:-/tmp}/workbench-import.XXXXXXXX"); \
	trap 'rm -rf "$$work"' 0; \
	trap 'exit 130' INT; trap 'exit 143' TERM; \
	if [ -d "$$input" ]; then resolved=$$(cd "$$input" && pwd); base=$$resolved; \
	else base=$$(cd "$$(dirname "$$input")" && pwd); resolved="$$base/$$(basename "$$input")"; fi; \
	if [ -n "$${SOURCE_ROOT:-}" ]; then base=$$(cd "$$SOURCE_ROOT" && pwd); fi; \
	prefix=$${base%/}/; \
	case "$$resolved" in "$$base") relative=. ;; "$$prefix"*) relative=$${resolved#"$$prefix"} ;; \
	  *) printf '%s\n' 'Input must be inside SOURCE_ROOT' >&2; exit 2 ;; esac; \
	if [ -d "$$input" ]; then \
	  (cd "$$base" && find "./$$relative" -type f \( -iname '*.json' -o -iname '*.jsonl' -o -iname '*.ndjson' \) -print0) > "$$work/files"; \
	  COPYFILE_DISABLE=1 tar -C "$$base" -cf "$$work/traces.tar" --null -T "$$work/files"; \
	else \
	  COPYFILE_DISABLE=1 tar -C "$$base" -cf "$$work/traces.tar" -- "$$relative"; \
	fi; \
	$(COMPOSE) run --rm -T --no-deps backend agent-data-workbench ingest /data/project --archive-stdin --layout "$$LAYOUT" < "$$work/traces.tar"
