.PHONY: setup test build dev api web migrate clean

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.lock
	cd apps/web && npm ci

test:
	.venv/bin/ruff format --check services/api
	.venv/bin/ruff check services/api
	.venv/bin/pytest
	cd apps/web && npm run typecheck

build:
	cd apps/web && npm run build

api:
	.venv/bin/uvicorn lounge_api.main:app --app-dir services/api --reload --host 127.0.0.1 --port 8000

web:
	cd apps/web && npm run dev

migrate:
	.venv/bin/alembic upgrade head

dev:
	.venv/bin/alembic upgrade head
	bash scripts/dev.sh

clean:
	rm -rf apps/web/dist .pytest_cache
