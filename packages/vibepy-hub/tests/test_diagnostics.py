"""One failure model: a Hub diagnostic says what kind of failure it is."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests_support import hub
from vibepy_core.errors import ErrorCategory
from vibepy_hub.models import Diagnostic, RunningApp


def test_a_diagnostic_without_a_category_is_refused() -> None:
    with pytest.raises(ValidationError):
        Diagnostic.model_validate({"code": "hub.not_installed", "message": "no"})


async def test_a_hub_failure_says_whether_a_retry_could_succeed(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})

    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.category == ErrorCategory.CALLER
