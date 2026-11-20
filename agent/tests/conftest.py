from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from lapremote.config import HOME_ENV
from lapremote.server import HTTPS_ENV, PORT_ENV
from lapremote.services import INPUT_DRY_RUN_ENV


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own LAPREMOTE_HOME so the real ~/.lapremote is never touched."""
    home = tmp_path / "lapremote-home"
    monkeypatch.setenv(HOME_ENV, str(home))
    return home


@pytest.fixture(autouse=True)
def clean_env() -> Iterator[None]:
    """`main()` sets LAPREMOTE_* variables for the server process; never let them leak."""
    saved = dict(os.environ)
    for name in (PORT_ENV, HTTPS_ENV, INPUT_DRY_RUN_ENV):
        os.environ.pop(name, None)
    yield
    os.environ.clear()
    os.environ.update(saved)
