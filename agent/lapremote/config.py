"""Load and save the agent config at ~/.lapremote/config.json.

The data directory can be moved with the LAPREMOTE_HOME environment variable
(used by tests and by isolated dev runs).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

HOME_ENV = "LAPREMOTE_HOME"
CONFIG_FILENAME = "config.json"

ThreeFingerAction = Literal["task_view", "show_desktop", "prev_tab", "next_tab"]
AiProvider = Literal["ollama", "groq", "gemini"]


class ConfigError(Exception):
    """The config file exists but cannot be read or does not validate."""


class _ConfigModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        validate_assignment=True,
    )


class HttpsConfig(_ConfigModel):
    enabled: bool = False
    cert: str = ""
    key: str = ""


class PreviewConfig(_ConfigModel):
    fps: int = Field(default=8, ge=1, le=15)
    width: int = Field(default=480, ge=160, le=1920)
    quality: int = Field(default=60, ge=10, le=95)


class AiConfig(_ConfigModel):
    provider: AiProvider = "ollama"
    model: str = Field(default="qwen2.5:7b", min_length=1)
    ollama_url: str = Field(default="http://127.0.0.1:11434", min_length=1)


class ThreeFingerConfig(_ConfigModel):
    up: ThreeFingerAction = "task_view"
    down: ThreeFingerAction = "show_desktop"
    left: ThreeFingerAction = "prev_tab"
    right: ThreeFingerAction = "next_tab"


class GesturesConfig(_ConfigModel):
    three_finger: ThreeFingerConfig = Field(default_factory=ThreeFingerConfig)


class Config(_ConfigModel):
    port: int = Field(default=7777, ge=1024, le=65535)
    https: HttpsConfig = Field(default_factory=HttpsConfig)
    preferred_browser: str = Field(default="brave", min_length=1)
    preview: PreviewConfig = Field(default_factory=PreviewConfig)
    ai: AiConfig = Field(default_factory=AiConfig)
    gestures: GesturesConfig = Field(default_factory=GesturesConfig)
    remote_control_paused: bool = False

    def to_json_dict(self) -> dict[str, object]:
        """Serialise with the camelCase keys used on disk."""
        return self.model_dump(mode="json", by_alias=True)


def data_dir() -> Path:
    """Directory holding all runtime data (config, devices, logs)."""
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override)
    return Path.home() / ".lapremote"


def config_path() -> Path:
    return data_dir() / CONFIG_FILENAME


def save_config(config: Config, path: Path | None = None) -> Path:
    """Write the config atomically (temp file in the same folder, then replace)."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(config.to_json_dict(), indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=target.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return target


def load_config(path: Path | None = None) -> Config:
    """Read the config, creating it with defaults on first run.

    A broken file is never silently overwritten: it raises ConfigError so the
    user can fix or delete it.
    """
    target = path or config_path()
    if not target.exists():
        config = Config()
        save_config(config, target)
        return config
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = f"Can't read {target}: {exc}. Fix the file or delete it to restore defaults."
        raise ConfigError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"{target} must contain a JSON object. Fix the file or delete it to restore defaults."
        raise ConfigError(msg)
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        msg = f"{target} has invalid settings: {exc}"
        raise ConfigError(msg) from exc
