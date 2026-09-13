.PHONY: install tools studio lint format typecheck test

install:
	uv sync
	uv run pre-commit install
	$(MAKE) tools

# What `make test` requires and `uv sync` does not bring: the proxy the Web
# channel is served through. Its own target so that CI obtains it without
# installing this repository's git hooks.
tools:
	uv run python scripts/fetch_traefik.py

# Studio's board and the proxy in front of it, for looking at it. Not part of
# the gate: the suite starts its own windows against roots of its own.
studio:
	uv run python scripts/run_studio.py

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

# Once per platform Studio targets, because a platform is what pyright resolves
# `sys.platform` and the platform-guarded parts of typeshed against: it
# "will use the current platform" when none is given, so one run on one machine
# leaves the other platform's branches unreachable and unchecked. `Darwin` and
# `Windows` are two of the documented values.
# <https://microsoft.github.io/pyright/#/configuration?id=environment-options>
typecheck:
	uv run pyright --pythonplatform Darwin
	uv run pyright --pythonplatform Windows

test:
	uv run pytest
