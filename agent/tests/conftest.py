from __future__ import annotations

from pathlib import Path

import pytest

from lapremote.config import HOME_ENV


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own LAPREMOTE_HOME so the real ~/.lapremote is never touched."""
    home = tmp_path / "lapremote-home"
    monkeypatch.setenv(HOME_ENV, str(home))
    return home
