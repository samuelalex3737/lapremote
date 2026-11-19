from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lapremote.config import Config, ConfigError, config_path, data_dir, load_config, save_config

# Section 9 of the build spec, verbatim.
SPEC_DEFAULTS = {
    "port": 7777,
    "https": {"enabled": False, "cert": "", "key": ""},
    "preferredBrowser": "brave",
    "preview": {"fps": 8, "width": 480, "quality": 60},
    "ai": {"provider": "ollama", "model": "qwen2.5:7b", "ollamaUrl": "http://127.0.0.1:11434"},
    "gestures": {
        "threeFinger": {
            "up": "task_view",
            "down": "show_desktop",
            "left": "prev_tab",
            "right": "next_tab",
        }
    },
    "remoteControlPaused": False,
}


def test_defaults_match_spec_exactly() -> None:
    assert Config().to_json_dict() == SPEC_DEFAULTS


def test_data_dir_honours_env(isolated_home: Path) -> None:
    assert data_dir() == isolated_home
    assert config_path() == isolated_home / "config.json"


def test_data_dir_defaults_to_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAPREMOTE_HOME")
    assert data_dir() == Path.home() / ".lapremote"


def test_first_load_creates_file_with_defaults(isolated_home: Path) -> None:
    assert not config_path().exists()
    config = load_config()
    assert config == Config()
    on_disk = json.loads(config_path().read_text(encoding="utf-8"))
    assert on_disk == SPEC_DEFAULTS


def test_save_then_load_round_trips() -> None:
    config = Config()
    config.port = 8123
    config.ai.provider = "groq"
    config.gestures.three_finger.up = "show_desktop"
    save_config(config)
    assert load_config() == config


def test_partial_file_is_filled_with_defaults() -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"port": 9000, "preview": {"fps": 12}}), encoding="utf-8")
    config = load_config()
    assert config.port == 9000
    assert config.preview.fps == 12
    assert config.preview.width == 480
    assert config.ai.model == "qwen2.5:7b"


def test_unknown_keys_are_ignored() -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"somethingNew": True}), encoding="utf-8")
    assert load_config() == Config()


def test_broken_json_raises_and_keeps_file() -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Can't read"):
        load_config()
    assert path.read_text(encoding="utf-8") == "{not json"


def test_non_object_json_raises() -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON object"):
        load_config()


@pytest.mark.parametrize(
    "bad",
    [
        {"port": 80},
        {"port": 70000},
        {"preview": {"fps": 30}},
        {"preview": {"quality": 5}},
        {"ai": {"provider": "openai"}},
        {"gestures": {"threeFinger": {"up": "rm -rf"}}},
    ],
)
def test_invalid_values_raise(bad: dict[str, object]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid settings"):
        load_config()


def test_assignment_is_validated() -> None:
    config = Config()
    with pytest.raises(ValidationError):
        config.port = 10


def test_save_is_atomic_and_leaves_no_temp_files(isolated_home: Path) -> None:
    save_config(Config())
    save_config(Config(port=8000))
    files = sorted(p.name for p in isolated_home.iterdir())
    assert files == ["config.json"]
    assert load_config().port == 8000


def test_save_to_explicit_path(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "custom.json"
    assert save_config(Config(), target) == target
    assert load_config(target) == Config()
