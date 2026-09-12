"""Studio's declared type checker."""

import importlib.metadata

from packaging.requirements import Requirement


def test_studio_declares_pyright_with_nodejs() -> None:
    """Studio's own distribution metadata names pyright, with the nodejs extra, as a dependency."""
    requirements = [Requirement(r) for r in importlib.metadata.requires("vibepy-studio") or []]
    pyright = [r for r in requirements if r.name == "pyright"]
    assert pyright, requirements
    assert any("nodejs" in r.extras for r in pyright), pyright
