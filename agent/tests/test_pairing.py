from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lapremote.security.pairing import (
    DeviceStore,
    LastOwnerError,
    PairingManager,
    UnknownDeviceError,
    hash_token,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_code_is_six_digits_and_has_ttl() -> None:
    clock = FakeClock()
    manager = PairingManager(ttl=300, clock=clock)
    code, remaining = manager.current()
    assert re.fullmatch(r"\d{6}", code)
    assert remaining == pytest.approx(300)


def test_code_works_once_then_rotates() -> None:
    rotated: list[str] = []
    manager = PairingManager(clock=FakeClock(), on_rotate=rotated.append)
    code, _ = manager.current()
    assert manager.consume(code) == "ok"
    assert manager.consume(code) == "invalid"
    assert len(rotated) == 1
    assert rotated[0] != code
    assert manager.current()[0] == rotated[0]


def test_expired_code_reports_expired_and_rotates() -> None:
    clock = FakeClock()
    rotated: list[str] = []
    manager = PairingManager(ttl=300, clock=clock, on_rotate=rotated.append)
    code, _ = manager.current()
    clock.now += 300
    assert manager.consume(code) == "expired"
    assert rotated
    # Still reported as expired (not "invalid") after the rotation.
    assert manager.consume(code) == "expired"


def test_expiry_rotates_on_current() -> None:
    clock = FakeClock()
    rotated: list[str] = []
    manager = PairingManager(ttl=10, clock=clock, on_rotate=rotated.append)
    first, _ = manager.current()
    clock.now += 11
    second, remaining = manager.current()
    assert second != first or rotated
    assert rotated == [second]
    assert remaining == pytest.approx(10)


def test_regenerate() -> None:
    rotated: list[str] = []
    manager = PairingManager(clock=FakeClock(), on_rotate=rotated.append)
    old, _ = manager.current()
    new = manager.regenerate()
    assert rotated == [new]
    assert manager.consume(old) == "expired"
    assert manager.consume(new) == "ok"


def test_wrong_code_is_invalid() -> None:
    manager = PairingManager(clock=FakeClock())
    code, _ = manager.current()
    assert manager.consume(f"{(int(code) + 7) % 1_000_000:06d}") == "invalid"
    assert manager.consume(code) == "ok"


def test_first_device_is_owner_then_guests(tmp_path: Path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    first, _ = store.add("Phone", "ios")
    second, _ = store.add("Tablet", "android")
    assert first.role == "owner"
    assert second.role == "guest"


def test_only_token_hash_is_persisted(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    store = DeviceStore(path)
    _device, token = store.add("Phone", "ios")
    text = path.read_text(encoding="utf-8")
    assert token not in text
    data = json.loads(text)
    assert data["version"] == 1
    assert data["devices"][0]["token_hash"] == hash_token(token)
    assert len(token) >= 43  # 32 bytes, url-safe base64


def test_verify(tmp_path: Path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    device, token = store.add("Phone", "ios")
    assert store.verify(device.device_id, token) is device
    assert store.verify(device.device_id, token + "x") is None
    assert store.verify("missing", token) is None


def test_store_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    device, token = DeviceStore(path).add("Phone", "ios")
    reloaded = DeviceStore(path)
    found = reloaded.verify(device.device_id, token)
    assert found is not None
    assert found.name == "Phone"
    assert found.role == "owner"


def test_revoke_and_roles(tmp_path: Path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    owner, _ = store.add("Phone", "ios")
    guest, guest_token = store.add("Tablet", "android")
    with pytest.raises(LastOwnerError):
        store.revoke(owner.device_id)
    with pytest.raises(LastOwnerError):
        store.set_role(owner.device_id, "guest")
    store.set_role(guest.device_id, "owner")
    store.set_role(owner.device_id, "guest")
    demoted = store.get(owner.device_id)
    assert demoted is not None
    assert demoted.role == "guest"
    # The promoted device is now the only owner, so it cannot be removed while others exist.
    with pytest.raises(LastOwnerError):
        store.revoke(guest.device_id)
    assert store.verify(guest.device_id, guest_token) is not None
    store.revoke(owner.device_id)
    assert store.get(owner.device_id) is None
    with pytest.raises(UnknownDeviceError):
        store.revoke("missing")
    with pytest.raises(UnknownDeviceError):
        store.set_role("missing", "owner")


def test_sole_device_can_be_revoked_and_next_pair_is_owner(tmp_path: Path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    owner, _ = store.add("Phone", "ios")
    store.revoke(owner.device_id)
    assert store.list() == []
    again, _ = store.add("New phone", "ios")
    assert again.role == "owner"


def test_blank_name_gets_default(tmp_path: Path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    device, _ = store.add("   ", "ios")
    assert device.name == "Phone"


def test_save_leaves_no_temp_files(tmp_path: Path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    for n in range(3):
        store.add(f"Phone {n}", "ios")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["devices.json"]
