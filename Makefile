# ──────────────────────────────────────────────────────────────
#  boilerplate-ecom-telebot · task runner
# ──────────────────────────────────────────────────────────────

PY         ?= python
PIP        ?= uv pip
VENV       ?= .venv
PYTHON     := $(VENV)/bin/python
RUFF       := $(VENV)/bin/ruff
MYPY       := $(VENV)/bin/mypy
PYTEST     := $(VENV)/bin/pytest
ALEMBIC    := $(VENV)/bin/alembic

export PYTHONPATH := src

.DEFAULT_GOAL := help

.PHONY: help install sync run check-imports lint format type test \
        migrate-new migrate-up migrate-down seed up down logs shell clean

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## create venv + install deps via uv
	uv venv $(VENV) --python=3.12
	$(PIP) install --python=$(PY) -e ".[dev]"
	$(MAKE) install-hooks

sync: ## sync deps with lockfile
	uv sync --all-extras

install-hooks: ## set up pre-commit
	$(PYTHON) -m pre_commit install

run: ## run bot locally (polling)
	$(PYTHON) -m bot_app.main

run-webhook: ## run bot locally (webhook, requires env settings)
	USE_WEBHOOK=True $(PYTHON) -m bot_app.main

check-imports: ## verify all modules import without errors
	$(PYTHON) -c "import bot_app.main, bot_app.bootstrap, bot_app.core.config; print('✓ all modules import cleanly')"

lint: ## ruff lint
	$(RUFF) check src tests

format: ## ruff format + auto-fix
	$(RUFF) format src tests
	$(RUFF) check --fix src tests

type: ## mypy strict
	$(MYPY) src

test: ## pytest with coverage
	$(PYTEST)

migrate-new: ## autogenerate new alembic migration (msg=MESSAGE)
	$(ALEMBIC) revision --autogenerate -m "$(MESSAGE)"

migrate-up: ## apply all migrations
	$(ALEMBIC) upgrade head

migrate-down: ## roll back one migration
	$(ALEMBIC) downgrade -1

seed: ## load demo data
	$(PYTHON) scripts/seed_demo_data.py

up: ## start docker-compose stack
	docker compose up -d --build
	@echo "waiting for postgres to be ready…"
	@sleep 3
	docker compose run --rm bot alembic upgrade head
	@echo ""
	@echo "✓ stack up. tail logs: make logs"

down: ## stop docker-compose stack
	docker compose down

logs: ## tail bot logs
	docker compose logs -f bot

shell: ## open a shell in the bot container
	docker compose exec bot /app/.venv/bin/python

clean: ## remove caches and venv
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache src/**/__pycache__
	find . -name "*.pyc" -delete
