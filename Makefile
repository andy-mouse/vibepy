.PHONY: install lint format typecheck test

install:
	uv sync
	uv run pre-commit install
	uv run python scripts/fetch_traefik.py

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run pyright

test:
	uv run pytest
