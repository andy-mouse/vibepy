.PHONY: install tools lint format typecheck test

install:
	uv sync
	uv run pre-commit install
	$(MAKE) tools

# What `make test` requires and `uv sync` does not bring: the proxy the Web
# channel is served through. Its own target so that CI obtains it without
# installing this repository's git hooks.
tools:
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
