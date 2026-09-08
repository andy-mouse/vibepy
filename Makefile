.PHONY: install lint format typecheck test

install:
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check src tests hub samples
	uv run ruff format --check src tests hub samples

format:
	uv run ruff format src tests hub samples
	uv run ruff check --fix src tests hub samples

typecheck:
	uv run pyright

test:
	uv run pytest
