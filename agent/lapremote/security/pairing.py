"""One-time pairing codes and the paired-device store.

Device tokens are 32 random bytes handed to the phone exactly once. Only their
SHA-256 hash is written to ``devices.json``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import Role

log = get_logger("pairing")

CODE_TTL_SECONDS = 300.0
DEVICES_FILE_VERSION = 1

PairResult = Literal["ok", "invalid", "expired"]
Clock = Callable[[], float]


class LastOwnerError(Exception):
    """The change would leave no owner."""


class UnknownDeviceError(KeyError):
    """No paired device has that id."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


@dataclass
class _Code:
    value: str
    expires_at: float
    used: bool = False


class PairingManager:
    """Holds the single active pairing code.

    A code is valid for ``ttl`` seconds and can be used once. When it is used
    or expires, a fresh one is generated and ``on_rotate`` is called with it.
    """

    def __init__(
        self,
        ttl: float = CODE_TTL_SECONDS,
        clock: Clock = time.monotonic,
        on_rotate: Callable[[str], None] | None = None,
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._on_rotate = on_rotate
        self._lock = threading.Lock()
        self._current = self._make()
        self._retired: dict[str, Literal["used", "expired"]] = {}

    def _make(self) -> _Code:
        return _Code(new_code(), self._clock() + self._ttl)

    def _rotate_locked(self, reason: Literal["used", "expired"]) -> str:
        self._retired[self._current.value] = reason
        if len(self._retired) > 32:
            self._retired.pop(next(iter(self._retired)))
        self._current = self._make()
        return self._current.value

    def current(self) -> tuple[str, float]:
        """The active code and the seconds until it expires."""
        rotated: str | None = None
        with self._lock:
            if self._clock() >= self._current.expires_at:
                rotated = self._rotate_locked("expired")
            code, remaining = self._current.value, self._current.expires_at - self._clock()
        if rotated is not None and self._on_rotate is not None:
            self._on_rotate(rotated)
        return code, remaining

    def regenerate(self) -> str:
        with self._lock:
            code = self._rotate_locked("expired")
        if self._on_rotate is not None:
            self._on_rotate(code)
        return code

    def consume(self, code: str) -> PairResult:
        rotated: str | None = None
        with self._lock:
            now = self._clock()
            active = self._current
            if hmac.compare_digest(code.encode(), active.value.encode()):
                if now >= active.expires_at:
                    rotated = self._rotate_locked("expired")
                    result: PairResult = "expired"
                else:
                    active.used = True
                    rotated = self._rotate_locked("used")
                    result = "ok"
            elif self._retired.get(code) == "expired":
                result = "expired"
            else:
                # Wrong codes and already-used codes look the same to the caller.
                result = "invalid"
        if rotated is not None and self._on_rotate is not None:
            self._on_rotate(rotated)
        return result


@dataclass
class Device:
    device_id: str
    name: str
    platform: str
    role: Role
    token_hash: str
    paired_at: float
    last_seen_at: float | None = None


class DeviceStore:
    """Paired devices persisted to ``devices.json`` (token hashes only)."""

    def __init__(self, path: Path, clock: Clock = time.time) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._devices: dict[str, Device] = self._load()

    def _load(self) -> dict[str, Device]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            devices = [Device(**item) for item in raw.get("devices", [])]
        except (ValueError, TypeError, AttributeError) as exc:
            # Fail closed: keep the damaged file for inspection and start with no devices,
            # so phones pair again instead of anything being trusted by accident.
            broken = self._path.with_name(self._path.name + ".broken")
            self._path.replace(broken)
            log_event(
                log, "devices_file_broken", level=40, movedTo=str(broken), error=type(exc).__name__
            )
            return {}
        return {d.device_id: d for d in devices}

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "version": DEVICES_FILE_VERSION,
            "devices": [asdict(d) for d in self._devices.values()],
        }
        fd, tmp_name = tempfile.mkstemp(prefix=".devices-", suffix=".tmp", dir=self._path.parent)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(body, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            tmp.replace(self._path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def list(self) -> list[Device]:
        with self._lock:
            return sorted(self._devices.values(), key=lambda d: d.paired_at)

    def get(self, device_id: str) -> Device | None:
        with self._lock:
            return self._devices.get(device_id)

    def add(self, name: str, platform: str) -> tuple[Device, str]:
        """Create a device and return it with its plain token (shown only once)."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            has_owner = any(d.role == "owner" for d in self._devices.values())
            device = Device(
                device_id=secrets.token_hex(8),
                name=name.strip() or "Phone",
                platform=platform,
                role="guest" if has_owner else "owner",
                token_hash=hash_token(token),
                paired_at=self._clock(),
                last_seen_at=self._clock(),
            )
            self._devices[device.device_id] = device
            self._save_locked()
        return device, token

    def verify(self, device_id: str, token: str) -> Device | None:
        with self._lock:
            device = self._devices.get(device_id)
            # Always compare, even for unknown ids, so timing does not reveal which ids exist.
            expected = device.token_hash if device is not None else hash_token(secrets.token_hex(8))
            if not hmac.compare_digest(expected, hash_token(token)) or device is None:
                return None
            device.last_seen_at = self._clock()
            self._save_locked()
            return device

    def touch(self, device_id: str) -> None:
        with self._lock:
            device = self._devices.get(device_id)
            if device is not None:
                device.last_seen_at = self._clock()
                self._save_locked()

    def _owners_except(self, device_id: str) -> int:
        return sum(
            1 for d in self._devices.values() if d.role == "owner" and d.device_id != device_id
        )

    def revoke(self, device_id: str) -> Device:
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                raise UnknownDeviceError(device_id)
            others = [d for d in self._devices.values() if d.device_id != device_id]
            if device.role == "owner" and others and self._owners_except(device_id) == 0:
                raise LastOwnerError(device_id)
            del self._devices[device_id]
            self._save_locked()
            return device

    def set_role(self, device_id: str, role: Role) -> Device:
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                raise UnknownDeviceError(device_id)
            if device.role == "owner" and role == "guest" and self._owners_except(device_id) == 0:
                raise LastOwnerError(device_id)
            device.role = role
            self._save_locked()
            return device
