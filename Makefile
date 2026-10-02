#  SerpFlow
#
#  A search control plane for SerpApi. Every target below is documented in the
#  README; `make help` prints the same list.
#
#  Quick start:
#      make install      create the venv and install everything
#      make up           start postgres, redis and kafka
#      make upgrade      apply migrations
#      make seed         load the catalog, benchmarks and demo data
#      make demo         prove the thesis
#      make dev          run the API and the frontend

SHELL            := /bin/bash
.DEFAULT_GOAL    := help
.SHELLFLAGS      := -eu -o pipefail -c

BACKEND          := backend
FRONTEND         := frontend
VENV             := $(BACKEND)/.venv
PY               := $(VENV)/bin/python
PY_WIN           := $(VENV)/Scripts/python.exe
PYTHON           := $(shell test -x $(PY) && echo $(PY) || echo $(PY_WIN))
UV               := uv
COMPOSE          := docker compose
ARGS             ?=

.PHONY: help install install-backend install-frontend dev backend frontend worker mcp \
        up down restart logs ps migrate migration upgrade downgrade seed demo \
        kafka-topics catalog-build catalog-validate benchmark api-check test test-unit \
        test-integration test-e2e lint format typecheck build clean health \
        docker-build docker-up docker-down shell psql redis-cli

# ---------------------------------------------------------------- help
help:  ## Show this help
	@echo ""
	@echo "  SerpFlow"
	@echo "  A search control plane for SerpApi."
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ---------------------------------------------------------------- install
install: install-backend install-frontend  ## Install backend and frontend dependencies

install-backend:  ## Create the Python 3.13 venv and install the backend
	cd $(BACKEND) && $(UV) venv --python 3.13 .venv
	cd $(BACKEND) && $(UV) pip install --python .venv -e ".[dev]"
	@echo ""
	@echo "  Backend installed. Next: make up && make upgrade && make seed"

install-frontend:  ## Install frontend dependencies
	cd $(FRONTEND) && npm install

# ---------------------------------------------------------------- run
dev:  ## Run the API and the frontend together
	@echo "  API      http://localhost:8000      docs at /docs"
	@echo "  Frontend http://localhost:5173"
	@echo ""
	$(MAKE) -j2 backend frontend

backend:  ## Run the FastAPI server with reload
	cd $(BACKEND) && $(PYTHON) -m app.server --reload --host 0.0.0.0 --port 8000

frontend:  ## Run the Vite dev server
	cd $(FRONTEND) && npm run dev

worker:  ## Run the Kafka background consumers on their own
	cd $(BACKEND) && $(PYTHON) -m app.workers.runner

mcp:  ## Run the MCP server over stdio
	cd $(BACKEND) && $(PYTHON) -m app.mcp.server

# ---------------------------------------------------------------- services
up:  ## Start postgres, redis and kafka
	$(COMPOSE) up -d postgres redis kafka
	@echo ""
	@echo "  postgres  localhost:5432"
	@echo "  redis     localhost:6379"
	@echo "  kafka     localhost:9092   (KRaft mode, no ZooKeeper)"

down:  ## Stop all services
	$(COMPOSE) down

restart:  ## Restart all services
	$(COMPOSE) restart

logs:  ## Tail service logs
	$(COMPOSE) logs -f --tail=120

ps:  ## Show service status
	$(COMPOSE) ps

# ---------------------------------------------------------------- database
migrate: upgrade  ## Alias for upgrade

migration:  ## Create a migration from the models (ARGS="-m 'message'")
	cd $(BACKEND) && $(PYTHON) -m alembic revision --autogenerate $(ARGS)

upgrade:  ## Apply all migrations
	cd $(BACKEND) && $(PYTHON) -m alembic upgrade head

downgrade:  ## Roll back one migration
	cd $(BACKEND) && $(PYTHON) -m alembic downgrade -1

seed:  ## Load the catalog, benchmark fixtures and demo data (ARGS=--reset)
	cd $(BACKEND) && $(PYTHON) scripts/seed.py $(ARGS)

demo:  ## Run the reference demo and prove the thesis (ARGS=--reset-cache)
	cd $(BACKEND) && $(PYTHON) scripts/demo.py $(ARGS)

psql:  ## Open a psql shell
	$(COMPOSE) exec postgres psql -U serpflow -d serpflow

redis-cli:  ## Open a redis-cli shell
	$(COMPOSE) exec redis redis-cli

# ---------------------------------------------------------------- kafka
kafka-topics:  ## Create every Kafka topic
	cd $(BACKEND) && $(PYTHON) -m app.workers.topics

# ---------------------------------------------------------------- docs
api-reference:  ## Regenerate the API reference page from the OpenAPI schema
	$(PYTHON) scripts/generate_api_reference.py $(ARGS)

docs-check:  ## Verify every relative link in every markdown file resolves
	$(PYTHON) scripts/check_doc_links.py

api-check:  ## Exercise every API operation against a running instance (ARGS=--verbose)
	$(PYTHON) scripts/check_api.py $(ARGS)

# ---------------------------------------------------------------- catalog
catalog-build:  ## Regenerate catalog drafts from the SerpApi docs (ARGS=--diff)
	cd $(BACKEND) && $(PYTHON) scripts/catalog_build.py $(ARGS)

catalog-validate:  ## Lint the committed catalog
	cd $(BACKEND) && $(PYTHON) -m app.cli.main catalog validate

# ---------------------------------------------------------------- benchmark
benchmark:  ## Run the routing benchmark (real LLM calls, on demand only)
	cd $(BACKEND) && $(PYTHON) -m app.cli.main benchmark compare $(ARGS)

# ---------------------------------------------------------------- quality
test:  ## Run the whole test suite
	cd $(BACKEND) && $(PYTHON) -m pytest -q

test-unit:  ## Run unit tests only (no services needed)
	cd $(BACKEND) && $(PYTHON) -m pytest tests/unit -q

test-integration:  ## Run integration tests (needs postgres and redis)
	cd $(BACKEND) && $(PYTHON) -m pytest tests/integration -q

test-e2e:  ## Run the end-to-end suite, including the thesis assertion
	cd $(BACKEND) && $(PYTHON) -m pytest tests/e2e -q

test-ui:  ## Build, serve and check the public pages in a real browser
	cd $(FRONTEND) && node scripts/verify-ui.mjs

lint:  ## Lint backend and frontend
	cd $(BACKEND) && $(PYTHON) -m ruff check .
	cd $(FRONTEND) && npm run lint

format:  ## Format backend and frontend
	cd $(BACKEND) && $(PYTHON) -m ruff format .
	cd $(BACKEND) && $(PYTHON) -m ruff check --fix .
	cd $(FRONTEND) && npm run format

typecheck:  ## Type-check backend and frontend
	cd $(BACKEND) && $(PYTHON) -m mypy app
	cd $(FRONTEND) && npm run typecheck

# ---------------------------------------------------------------- build
build:  ## Build the frontend bundle
	cd $(FRONTEND) && npm run build

docker-build:  ## Build every container image
	$(COMPOSE) build

docker-up:  ## Start the full stack in containers
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  Frontend  http://localhost:5173"
	@echo "  API       http://localhost:8000/docs"

docker-down:  ## Stop the full stack
	$(COMPOSE) down -v

# ---------------------------------------------------------------- misc
health:  ## Check the service and every dependency
	cd $(BACKEND) && $(PYTHON) -m app.cli.main health

shell:  ## Open a Python shell with the app importable
	cd $(BACKEND) && $(PYTHON)

clean:  ## Remove build artefacts and caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(FRONTEND)/dist $(FRONTEND)/.vite $(BACKEND)/.serpflow-objects
	@echo "  Cleaned. The venv, node_modules and docker volumes were left alone."
