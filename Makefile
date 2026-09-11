.PHONY: install tools hub lint format typecheck test

install:
	uv sync
	uv run pre-commit install
	$(MAKE) tools

# What `make test` requires and `uv sync` does not bring: the proxy the Web
# channel is served through. Its own target so that CI obtains it without
# installing this repository's git hooks.
tools:
	uv run python scripts/fetch_traefik.py

# The Hub's board and the proxy in front of it, for looking at it. Not part of
# the gate: the suite starts its own windows against roots of its own.
hub:
	uv run python scripts/run_hub.py

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
