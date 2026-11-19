from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from lapremote import __main__ as entry
from lapremote.config import Config, config_path, save_config
from lapremote.server import HTTPS_ENV, PORT_ENV

from .wsclient import make_app


class RunRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, app: str, **kwargs: Any) -> None:
        self.calls.append((app, kwargs))


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> RunRecorder:
    rec = RunRecorder()
    monkeypatch.setattr(uvicorn, "run", rec)
    monkeypatch.delenv(PORT_ENV, raising=False)
    return rec


def test_uses_port_from_config(recorder: RunRecorder) -> None:
    save_config(Config(port=8111))
    assert entry.main([]) == 0
    app, kwargs = recorder.calls[0]
    assert app == "lapremote.server:create_app"
    assert kwargs["factory"] is True
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8111
    assert kwargs["reload"] is False
    assert kwargs["reload_dirs"] is None
    assert kwargs["access_log"] is False
    assert os.environ[PORT_ENV] == "8111"


def test_port_flag_overrides_config(recorder: RunRecorder) -> None:
    assert entry.main(["--port", "7790"]) == 0
    assert recorder.calls[0][1]["port"] == 7790
    assert os.environ[PORT_ENV] == "7790"


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


# ---------------------------------------------------------------- HTTPS


def test_https_needs_cert_and_key(
    recorder: RunRecorder, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(HTTPS_ENV, raising=False)
    assert entry.main(["--https"]) == 2
    assert recorder.calls == []
    assert os.environ.get(HTTPS_ENV) is None


def test_https_passes_the_files_to_uvicorn(
    recorder: RunRecorder, isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(HTTPS_ENV, raising=False)
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    config = Config()
    config.https.cert, config.https.key = str(cert), str(key)
    save_config(config, config_path())
    assert entry.main(["--https"]) == 0
    _, kwargs = recorder.calls[0]
    assert kwargs["ssl_certfile"] == str(cert)
    assert kwargs["ssl_keyfile"] == str(key)
    assert os.environ[HTTPS_ENV] == "1"


def test_https_problem_messages(tmp_path: Path) -> None:
    assert entry.https_problem("", "") is not None
    missing = entry.https_problem(str(tmp_path / "nope.pem"), str(tmp_path / "k.pem"))
    assert missing == f"the certificate file {tmp_path / 'nope.pem'} doesn't exist."


def test_https_env_reports_a_secure_context(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(HTTPS_ENV, "1")
    app = make_app(isolated_home)
    with TestClient(app):
        assert app.state.agent.features().secure_context is True
    monkeypatch.delenv(HTTPS_ENV)
    plain = make_app(isolated_home)
    with TestClient(plain):
        assert plain.state.agent.features().secure_context is False
