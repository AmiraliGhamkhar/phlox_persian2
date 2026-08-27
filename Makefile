.PHONY: help install install-local update outdated audit rebuild-dev rebuild-prod rebuild-test lint format typecheck install-hooks check-all docker-build docker-up docker-down docker-logs docker-ps docker-shell docker-restart docker-test docker-dev-build docker-dev-up docker-dev-down

help:
	@echo "Available commands:"
	@echo "  make install        - Install dependencies"
	@echo "  make install-local  - Install dependencies with local extras"
	@echo "  make update         - Update all dependencies"
	@echo "  make outdated       - Check for outdated packages"
	@echo "  make audit          - Check for security vulnerabilities"
	@echo "  make lint           - Run Python linting (ruff)"
	@echo "  make format         - Format Python code (ruff)"
	@echo "  make typecheck      - Run Python type checking (ty)"
	@echo "  make install-hooks  - Install pre-commit hooks"
	@echo "  make check-all      - Run all quality checks"
	@echo ""
	@echo "Docker:"
	@echo "  make rebuild-prod   - Rebuild prod Docker image"
	@echo "  make rebuild-dev    - Rebuild dev Docker image"
	@echo "  make rebuild-test   - Rebuild test Docker image"
	@echo "  make docker-up      - Build and start the production stack (needs .env)"
	@echo "  make docker-down    - Stop the production stack"
	@echo "  make docker-logs    - Tail production container logs"
	@echo "  make docker-test    - Run the pytest suite inside the test image"
	@echo "  make docker-dev-up  - Start the hot-reload dev stack (UI :3000)"

install:
	cd server && UV_LINK_MODE=copy uv pip install -r pyproject.toml

install-local:
	cd server && UV_LINK_MODE=copy uv pip install -r pyproject.toml --extra local

update:
	cd server && uv lock --upgrade
	cd server && UV_LINK_MODE=copy uv pip install -r pyproject.toml
	npm update

outdated:
	cd server && uv pip list --outdated

audit:
	cd server && uv pip check

# Images are tagged to match the compose files, so `make rebuild-*` and
# `docker compose up` stay interchangeable.
rebuild-dev:
	docker build -f Dockerfile.dev -t localhost/phlox-dev:latest .

rebuild-prod:
	docker build -f Dockerfile -t localhost/phlox:latest .

rebuild-test:
	docker build -f Dockerfile.test -t localhost/phlox-test:latest .

# --- Docker Compose ---------------------------------------------------------
docker-build:
	docker compose build

docker-up:
	@test -f .env || echo "WARN: no .env found - copy .env.example to .env and set DB_ENCRYPTION_KEY"
	docker compose up -d --build

docker-down:
	docker compose down

docker-restart:
	docker compose restart

docker-ps:
	docker compose ps

docker-logs:
	docker compose logs -f

docker-shell:
	docker compose exec app bash

# Runs the suite exactly like CI does and copies coverage.lcov out of the image.
docker-test: rebuild-test
	@docker rm -f phlox-test >/dev/null 2>&1 || true
	docker run --name phlox-test localhost/phlox-test:latest ; status=$$? ; \
	docker cp phlox-test:/usr/src/app/coverage.lcov ./coverage.lcov || true ; \
	docker rm -f phlox-test >/dev/null ; \
	exit $$status

docker-dev-build:
	docker compose -f docker-compose.dev.yml build

docker-dev-up:
	docker compose -f docker-compose.dev.yml up

docker-dev-down:
	docker compose -f docker-compose.dev.yml down

lint:
	cd server && uv run ruff check .

format:
	cd server && uv run ruff format .
	cd server && uv run ruff check . --fix

typecheck:
	cd server && uv run ty check .

install-hooks:
	cd server && uv run pre-commit install

check-all: lint typecheck
	@echo "All code quality checks passed!"
