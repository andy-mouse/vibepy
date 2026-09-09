.PHONY: install lint format typecheck test

install:
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check src tests packages examples
	uv run ruff format --check src tests packages examples

format:
	uv run ruff format src tests packages examples
	uv run ruff check --fix src tests packages examples

typecheck:
	uv run pyright

test:
	uv run pytest
