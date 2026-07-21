.DEFAULT_GOAL := help
PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: help setup dev lint typecheck test test-unit test-integration test-e2e \
	test-security contracts-build contracts-test contracts-deploy-testnet \
	contracts-verify contracts-inspect chain-smoke-test screenshots docker-up \
	docker-down deploy smoke-test

help: ## Show available project commands
	@awk 'BEGIN {FS = ":.*## "; printf "LOOP commands:\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-28s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install pinned web and API dependencies
	npm ci
	python3 -m venv .venv
	$(PIP) install -e 'apps/api[dev]'

dev: ## Run the web development server
	npm run dev:web

lint: ## Lint and format-check all application code
	npm run lint:web
	$(PYTHON) -m ruff check apps/api
	npm run format:check

typecheck: ## Type-check the API and build-check the web app
	cd apps/api && ../../$(PYTHON) -m mypy app
	npm run build:web

test: test-unit test-integration contracts-test ## Run the supported automated suites

test-unit: ## Run API and web unit tests
	$(PYTHON) -m pytest apps/api/tests -q
	npm run test:web

test-integration: ## Validate a fresh database migration graph
	@migration_db=$$(mktemp /tmp/loop-migration.XXXXXX); trap 'rm -f "$$migration_db"' EXIT; \
		cd apps/api && LOOP_DATABASE_URL="sqlite+aiosqlite:///$$migration_db" ../../$(PYTHON) -m alembic upgrade head && \
		LOOP_DATABASE_URL="sqlite+aiosqlite:///$$migration_db" ../../$(PYTHON) -m alembic check

test-e2e: ## Run Mini App browser flows
	npm run test:e2e

test-security: ## Run security-focused API tests and dependency audits
	$(PYTHON) -m pytest apps/api/tests/test_security.py apps/api/tests/test_routes_hardening.py -q
	npm audit --omit=dev --audit-level=high

contracts-build: ## Compile BANK and DUEL contracts with Acton
	acton check
	acton build

contracts-test: ## Run deterministic contract tests
	acton test

contracts-deploy-testnet: ## Deploy contracts only with explicit broadcast consent
	@test "$(ALLOW_TESTNET_DEPLOY)" = "1" || (echo 'Set ALLOW_TESTNET_DEPLOY=1 to broadcast' >&2; exit 2)
	acton run deploy-bank
	acton run deploy-duel

contracts-verify: contracts-build ## Match local builds, manifests and finalized testnet state
	$(PYTHON) scripts/verify-contracts.py

contracts-inspect: ## Decode live contract state using Acton getters
	acton rpc info $$(jq -r .address deployments/testnet/bank.json) BankQueue
	acton rpc info $$(jq -r .address deployments/testnet/duel.json) DuelEscrow

chain-smoke-test: contracts-verify contracts-inspect ## Run read-only testnet checks

screenshots: ## Capture documentation screenshots from the production web build
	npm run screenshots

docker-up: ## Start the local production stack
	docker compose --env-file .env.production up -d --wait db redis api worker

docker-down: ## Stop the local production stack without deleting data
	docker compose --env-file .env.production down

deploy: ## Activate an immutable server release (RELEASE=<40-char SHA>)
	@test -n "$(RELEASE)" || (echo 'RELEASE is required' >&2; exit 2)
	deploy/activate-release.sh "$(RELEASE)"

smoke-test: ## Verify production readiness and public health
	curl --fail --silent --show-error https://144-31-30-62.sslip.io/ready
