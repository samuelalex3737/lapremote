from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import uvicorn

from lapremote import __main__ as entry
from lapremote.config import Config, config_path, save_config


class RunRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, app: str, **kwargs: Any) -> None:
        self.calls.append((app, kwargs))


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> RunRecorder:
    rec = RunRecorder()
    monkeypatch.setattr(uvicorn, "run", rec)
    return rec


def test_uses_port_from_config(recorder: RunRecorder) -> None:
    save_config(Config(port=8111))
    assert entry.main([]) == 0
    app, kwargs = recorder.calls[0]
    assert app == "lapremote.server:create_app"
    assert kwargs["factory"] is True
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8111
    assert kwargs["reload"] is False
    assert kwargs["reload_dirs"] is None


def test_port_flag_overrides_config(recorder: RunRecorder) -> None:
    assert entry.main(["--port", "7790"]) == 0
    assert recorder.calls[0][1]["port"] == 7790


def test_dev_flag_enables_reload_on_package_dir(recorder: RunRecorder) -> None:
    assert entry.main(["--dev"]) == 0
    kwargs = recorder.calls[0][1]
    assert kwargs["reload"] is True
    assert kwargs["reload_dirs"] == [str(Path(entry.__file__).resolve().parent)]


def test_out_of_range_port_flag_is_rejected(recorder: RunRecorder) -> None:
    with pytest.raises(SystemExit) as exc:
        entry.main(["--port", "80"])
    assert exc.value.code == 2
    assert recorder.calls == []


def test_broken_config_exits_with_friendly_message(
    recorder: RunRecorder, capsys: pytest.CaptureFixture[str]
) -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    assert entry.main([]) == 2
    assert "LapRemote could not start" in capsys.readouterr().err
    assert recorder.calls == []
