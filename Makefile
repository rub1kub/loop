.DEFAULT_GOAL := help
PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: help setup dev lint typecheck test test-unit test-integration test-e2e \
	test-security contracts-build contracts-test contracts-deploy-testnet \
	contracts-deploy-duel-testnet \
	contracts-verify contracts-inspect contracts-mainnet-technical \
	contracts-audit-pack \
	contracts-mainnet-preflight contracts-deploy-mainnet contracts-mainnet-verify \
	chain-smoke-test screenshots docker-up \
	docker-down deploy deploy-vps deploy-status deploy-restart smoke-test

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
	@test -n "$(LOOP_DUEL_INVITE_PUBLIC_KEY)" || (echo 'LOOP_DUEL_INVITE_PUBLIC_KEY is required' >&2; exit 2)
	acton run deploy-bank-testnet
	acton run deploy-duel-testnet

contracts-deploy-duel-testnet: ## Deploy only the current DUEL with an explicit broadcast gate
	@test "$(ALLOW_TESTNET_DEPLOY)" = "1" || (echo 'Set ALLOW_TESTNET_DEPLOY=1 to broadcast' >&2; exit 2)
	@test -n "$(LOOP_DUEL_INVITE_PUBLIC_KEY)" || (echo 'LOOP_DUEL_INVITE_PUBLIC_KEY is required' >&2; exit 2)
	acton run deploy-duel-testnet

GAS_FUZZ_SEED ?= 4990371069678758165

contracts-mainnet-technical: ## Run deterministic, fork, coverage, mutation and gas gates
	acton fmt --check
	acton check
	acton build
	acton test --fork-net mainnet --coverage --coverage-format lcov \
		--coverage-file coverage.lcov
	$(PYTHON) scripts/check-contract-coverage.py coverage.lcov \
		--minimum-lines 98 --minimum-branches 75
	acton test --fuzz-seed $(GAS_FUZZ_SEED) \
		--baseline-snapshot contracts/gas-baseline.json --fail-on-diff
	acton test tests/bank_queue.test.tolk --mutate --mutate-contract BankQueue \
		--mutation-levels critical --mutation-minimum-percent 90
	acton test tests/bank_queue.test.tolk --mutate --mutate-contract BankQueue \
		--mutation-levels major --mutation-minimum-percent 75
	acton test tests/duel_contract.test.tolk --mutate --mutate-contract DuelEscrow \
		--mutation-levels critical --mutation-minimum-percent 95
	acton test tests/duel_contract.test.tolk --mutate --mutate-contract DuelEscrow \
		--mutation-levels major --mutation-minimum-percent 75
	$(PYTHON) -m pytest apps/api/tests/test_config.py \
		apps/api/tests/test_bank_canary_runner.py \
		apps/api/tests/test_duel_canary_operations.py \
		apps/api/tests/test_mainnet_readiness.py \
		apps/api/tests/test_network_switch_preflight.py apps/api/tests/test_security.py \
		apps/api/tests/test_routes_hardening.py -q
	npm --workspace @loop/web run test -- --run src/ton.test.ts

contracts-audit-pack: contracts-build ## Build a deterministic secret-free auditor archive
	$(PYTHON) scripts/build-mainnet-audit-pack.py

contracts-mainnet-preflight: contracts-mainnet-technical ## Require external audit and release evidence
	$(PYTHON) scripts/check-mainnet-readiness.py --phase pre-deploy

contracts-deploy-mainnet: contracts-mainnet-preflight ## Deploy paused contracts with explicit real-funds consent
	@test "$(ALLOW_MAINNET_DEPLOY)" = "I_UNDERSTAND_REAL_FUNDS" || \
		(echo 'Set ALLOW_MAINNET_DEPLOY=I_UNDERSTAND_REAL_FUNDS to broadcast' >&2; exit 2)
	@test -n "$(LOOP_CONTRACT_OWNER_ADDRESS)" || \
		(echo 'LOOP_CONTRACT_OWNER_ADDRESS is required' >&2; exit 2)
	@test -n "$(LOOP_CONTRACT_TREASURY_ADDRESS)" || \
		(echo 'LOOP_CONTRACT_TREASURY_ADDRESS is required' >&2; exit 2)
	@test -n "$(LOOP_DUEL_INVITE_PUBLIC_KEY)" || \
		(echo 'LOOP_DUEL_INVITE_PUBLIC_KEY is required' >&2; exit 2)
	acton run deploy-bank-mainnet
	acton run deploy-duel-mainnet

contracts-mainnet-verify: contracts-build ## Verify mainnet bytecode, state, smoke and published source
	$(PYTHON) scripts/verify-contracts.py --network mainnet --require-smoke
	$(PYTHON) scripts/check-mainnet-readiness.py --phase post-deploy

contracts-verify: contracts-build ## Match local builds, manifests and finalized testnet state
	$(PYTHON) scripts/verify-contracts.py

contracts-inspect: ## Decode live contract state using Acton getters
	acton rpc info $$(jq -r .address deployments/testnet/bank.json)
	acton rpc info $$(jq -r .address deployments/testnet/duel.json)

chain-smoke-test: contracts-verify contracts-inspect ## Run read-only testnet checks

screenshots: ## Capture documentation screenshots from the production web build
	npm run screenshots

docker-up: ## Start the local production stack
	docker compose --env-file .env.production up -d --wait db redis api worker notifier

docker-down: ## Stop the local production stack without deleting data
	docker compose --env-file .env.production down

deploy: ## Activate an immutable server release (RELEASE=<40-char SHA>)
	@test -n "$(RELEASE)" || (echo 'RELEASE is required' >&2; exit 2)
	deploy/activate-release.sh "$(RELEASE)"

deploy-vps: ## Build, upload and activate the current commit directly on the VPS
	scripts/deploy-vps.sh deploy

deploy-status: ## Verify the active VPS release, services, public health and bot
	scripts/deploy-vps.sh status

deploy-restart: ## Restart the active VPS API/bot and worker, then verify them
	scripts/deploy-vps.sh restart

smoke-test: ## Verify production readiness and public health
	curl --fail --silent --show-error https://app.tonsuite.org/ready
