.PHONY: install lint format typecheck test

install:
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check src tests samples
	uv run ruff format --check src tests samples

format:
	uv run ruff format src tests samples
	uv run ruff check --fix src tests samples

typecheck:
	uv run pyright

test:
	uv run pytest
