"""Small JSON files in ~/.lapremote: atomic writes and seeded defaults."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

# Defaults ship in the repo's shared/ folder and inside the package for builds.
_PACKAGE_DEFAULTS = Path(__file__).resolve().parent / "defaults"
_REPO_DEFAULTS = Path(__file__).resolve().parents[2] / "shared"


def default_file(name: str) -> Path:
    """The shipped default for `name` (shortcuts.default.json, scenes.default.json)."""
    for folder in (_PACKAGE_DEFAULTS, _REPO_DEFAULTS):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    msg = f"default file {name} is missing from the install"
    raise FileNotFoundError(msg)


def write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_or_seed(path: Path, default_name: str) -> object:
    """Read `path`, copying the shipped default there on first use.

    A corrupt file is moved aside (``.broken``) and replaced by the default, so a
    bad edit never stops the agent from starting.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(default_file(default_name), path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        path.replace(path.with_suffix(path.suffix + ".broken"))
        shutil.copyfile(default_file(default_name), path)
        return json.loads(path.read_text(encoding="utf-8"))
